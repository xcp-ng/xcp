#!/usr/bin/env python3

"""
Analyze the RPMs of an XCP-ng release and produce reports about them:
- role of each package (installed by default, extra, build dependency, unused...)
- provenance (who built it, who added it, who maintains it, notes)
- version comparison with CentOS 7 and EPEL 7

Everything is read from the online repositories metadata (repodata) and the
dependencies are resolved with libsolv, so there's no need to mirror the
repositories nor to run yum inside a CentOS container.

koji is only used for the built-by-* tags and the installable_extras group. These are read-only
queries, which don't need authentication.

Note, in what follows:
- NVR means Name Version Release
- NVRA means Name Version Release Arch
Those are common concepts in the RPM world.
"""

import argparse
import datetime
import functools
import glob
import html
import json
import logging
import os
import shutil
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

import markdown
import rpm
import solv
from autoindex import write_dir_indexes

MAIN_REPOS = ['base', 'updates', 'candidates', 'testing', 'ci']
BUILDERS = ['centos', 'epel', 'xs', 'xcp-ng']
REPO_URL = "https://updates.xcp-ng.org/{major}/{version}/{repo}/{arch}/"
PACKAGES_URL = "https://raw.githubusercontent.com/xcp-ng/xcp/master/scripts/rpm_owners/packages.json"
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
KOJI_HUB = "https://kojihub.xcp-ng.org"
# CA of the koji hub certificate (self-signed kojica)
KOJI_CA = os.path.join(DATA_DIR, 'koji-ca.crt')

KOJI_URL = "https://koji.xcp-ng.org"
KOJI_BUILD_URL = KOJI_URL + "/search?match=exact&type=build&terms=%s"
# Unless you know an exact *binary* RPM name, there's no better URL than a simple search on the name
CENTOS_RPM_URL = "https://pkgs.org/download/%s"
EPEL_RPM_URL = "https://pkgs.org/download/%s"

log = logging.getLogger('rpmwatcher')

#
# Data sources
#

def fetch_metadata(url, cache_dir, md_type, cache_key):
    """ Download a metadata file of a repository (primary, filelists...), return its local path """
    with urllib.request.urlopen(url + 'repodata/repomd.xml') as f:
        repomd = ET.fromstring(f.read())
    ns = {'repo': 'http://linux.duke.edu/metadata/repo'}
    for data in repomd.findall('repo:data', ns):
        if data.get('type') == md_type:
            href = data.find('repo:location', ns).get('href')
            break
    else:
        raise Exception("No %s metadata in %s" % (md_type, url))
    # the file name contains its checksum, so a cached file is always up to date
    prefix = os.path.join(cache_dir, "%s-%s-" % (cache_key, md_type))
    path = prefix + os.path.basename(href)
    if not os.path.exists(path):
        # remove the previous versions of this file
        for old in glob.glob(glob.escape(prefix) + '*'):
            os.unlink(old)
        log.info("downloading %s", url + href)
        with urllib.request.urlopen(url + href) as src, open(path + '.part', 'wb') as dst:
            shutil.copyfileobj(src, dst)
        os.rename(path + '.part', path)
    return path

def load_pool(xcp_version, repo_url, cache_dir):
    pool = solv.Pool()
    pool.setarch('x86_64')
    major = xcp_version.split('.')[0]
    for arch in ['x86_64', 'Source']:
        for repo_name in MAIN_REPOS:
            url = repo_url.format(major=major, version=xcp_version, repo=repo_name, arch=arch)
            repo = pool.add_repo(repo_name)
            f = solv.xfopen(fetch_metadata(url, cache_dir, 'primary', repo_name + '-' + arch))
            repo.add_rpmmd(f, None)
            f.close()
            if arch != 'Source':
                # needed for build dependencies on files, e.g. /usr/lib64/crt1.o
                f = solv.xfopen(fetch_metadata(url, cache_dir, 'filelists', repo_name + '-' + arch))
                repo.add_rpmmd(f, 'FL', solv.Repo.REPO_EXTEND_SOLVABLES)
                f.close()
    pool.addfileprovides()
    pool.createwhatprovides()
    return pool

def read_koji_info(xcp_version, hub, snapshot):
    """ Return ({srpm_nvr: builder}, [installable extra RPM names]) """
    if snapshot:
        with open(snapshot) as f:
            data = json.load(f)
        return data['built_by'], data['installable_extras']

    import koji
    session = koji.ClientSession(hub, {'serverca': KOJI_CA})
    built_by = {}
    for builder in BUILDERS:
        for build in session.listTagged('built-by-%s' % builder):
            built_by.setdefault(build['nvr'], builder)
    extras = []
    for group in session.getTagGroups('V%s' % xcp_version):
        if group['name'] == 'installable_extras':
            extras = [p['package'] for p in group['packagelist']]
    return built_by, extras

def read_packages_info(location):
    """ "manually written" information about our packages, maintained in scripts/rpm_owners/packages.json """
    if os.path.exists(location):
        with open(location) as f:
            packages = json.load(f)
    else:
        with urllib.request.urlopen(location) as f:
            packages = json.load(f)
    return {
        name: {'added_by': info['added_by'], 'maintainer': info['maintainer'], 'note': info.get('note', '')}
        for name, info in packages.items()
    }

def read_frozen_srpms(filename):
    """ CentOS 7 and EPEL 7 are EOL: their latest versions are stored in the data directory """
    with open(os.path.join(DATA_DIR, filename)) as f:
        return {name: dict(zip(['epoch', 'version', 'release'], evr)) for name, evr in json.load(f).items()}

#
# Analysis
#

def split_evr(evr):
    epoch, _, vr = evr.rpartition(':')
    version, release = vr.rsplit('-', 1)
    return epoch, version, release

def nvra(s):
    _, version, release = split_evr(s.evr)
    return "%s-%s-%s.%s" % (s.name, version, release, s.arch)

def srpm_nvr(s):
    return s.lookup_sourcepkg()[:-len('.src.rpm')]

class Analyzer:
    def __init__(self, pool):
        self.pool = pool
        self.srpms = {}     # srpm_nvr: solvable, from the Source repos
        self.rpms = {}      # rpm_nvra: solvable, from the binary repos
        self.rpms_by_srpm = {}
        for repo in pool.repos:
            for s in repo.solvables:
                if s.arch in ('src', 'nosrc'):
                    key = "%s-%s" % (s.name, s.evr.split(':')[-1])
                    self.srpms.setdefault(key, s)
                elif '-debuginfo-' not in s.name + '-' and nvra(s) not in self.rpms:
                    self.rpms[nvra(s)] = s
                    self.rpms_by_srpm.setdefault(srpm_nvr(s), []).append(nvra(s))

    def latest_srpms(self):
        latest = {}
        for s in self.srpms.values():
            if s.name not in latest or latest[s.name].evrcmp(s) < 0:
                latest[s.name] = s
        return latest.values()

    def solve(self, jobs):
        """ Return the solvables a "yum install" would pull, or None if not installable """
        solver = self.pool.Solver()
        problems = solver.solve(jobs)
        if problems:
            log.debug("cannot solve %s: %s", jobs, [str(p) for p in problems])
            return None
        return solver.transaction().newsolvables()

    def install_name(self, name):
        sel = self.pool.select(name, solv.Selection.SELECTION_NAME)
        if sel.isempty():
            return None
        return self.solve(sel.jobs(solv.Job.SOLVER_INSTALL))

    def install_base_system(self, solvables):
        """
        Mark these packages as installed, so that they are not reported as dependencies
        and the solver takes them into account (e.g. kernel, so that packages such as
        kernel-alt are not seen as better fit for the "kernel" provides).
        """
        system = self.pool.add_repo('@System')
        for s in solvables:
            c = system.add_solvable()
            c.name, c.evr, c.arch = s.name, s.evr, s.arch
            vendor = s.lookup_str(solv.SOLVABLE_VENDOR)
            if vendor:
                c.vendor = vendor
            for key in (solv.SOLVABLE_PROVIDES, solv.SOLVABLE_REQUIRES,
                        solv.SOLVABLE_CONFLICTS, solv.SOLVABLE_OBSOLETES):
                for dep in s.lookup_deparray(key, 0):
                    c.add_deparray(key, dep)
        system.internalize()
        self.pool.installed = system
        self.pool.createwhatprovides()

    def runtime_deps(self, rpm_nvra):
        """ installable, [dependencies not already installed in the base system] """
        s = self.rpms[rpm_nvra]
        new = self.solve([self.pool.Job(solv.Job.SOLVER_SOLVABLE | solv.Job.SOLVER_INSTALL, s.id)])
        if new is not None:
            return True, sorted(nvra(x) for x in new if x.id != s.id)
        # Not installable. Like yum, still report the dependencies that can be resolved.
        deps = set()
        for dep in s.lookup_deparray(solv.SOLVABLE_REQUIRES, 0):
            new = self.solve([self.pool.Job(solv.Job.SOLVER_SOLVABLE_PROVIDES | solv.Job.SOLVER_INSTALL, dep.id)])
            deps.update(nvra(x) for x in new or [] if x.id != s.id)
        return False, sorted(deps)

    def build_deps(self, srpm_nvr):
        """ [direct build deps], [deps of the build deps], like yum-builddep would install them """
        s = self.srpms[srpm_nvr]
        requires = [d for d in s.lookup_deparray(solv.SOLVABLE_REQUIRES) if not str(d).startswith('rpmlib(')]
        jobs = [self.pool.Job(solv.Job.SOLVER_SOLVABLE_PROVIDES | solv.Job.SOLVER_INSTALL, d.id) for d in requires]
        new = self.solve(jobs)
        if new is None:
            log.warning("build dependencies of %s cannot be resolved", srpm_nvr)
            return [], []
        providers = {p.id for d in requires for p in self.pool.whatprovides(d.id)}
        direct = sorted(nvra(x) for x in new if x.id in providers)
        indirect = sorted(nvra(x) for x in new if x.id not in providers)
        return direct, indirect

def srpm_info(s):
    epoch, version, release = split_evr(s.evr)
    return {
        'name': s.name,
        'vendor': s.lookup_str(solv.SOLVABLE_VENDOR) or '',
        'summary': s.lookup_str(solv.SOLVABLE_SUMMARY) or '',
        'nvr': "%s-%s-%s" % (s.name, version, release),
        'epoch': epoch,
        'version': version,
        'release': release,
        'koji_tag': s.repo.name,
    }

def collect(analyzer, built_by, extras, packages_info, centos_srpms, epel_srpms):
    """
    Return (xcp_builds, xcp_rpms, rpms_installed_by_default, extra_installable_nvra)

    The starting point is the latest build of each SRPM. But the repositories also contain older
    builds, and the dependency resolution may pull RPMs from them (e.g. a python2 subpackage
    that newer builds don't produce anymore). Those builds are added along the way, with only
    the RPMs that are actually pulled.
    """
    xcp_builds = {}
    xcp_rpms = {}

    def add_build(nvr, with_all_rpms):
        if nvr in xcp_builds:
            return
        if nvr in analyzer.srpms:
            info = srpm_info(analyzer.srpms[nvr])
        else:
            log.warning("SRPM %s is not in the repositories", nvr)
            name, version, release = nvr.rsplit('-', 2)
            info = {'name': name, 'vendor': '', 'summary': '', 'nvr': nvr, 'epoch': '',
                    'version': version, 'release': release, 'koji_tag': 'unknown'}
        info['latest'] = with_all_rpms
        info['built-by'] = built_by.get(nvr, 'unknown')
        if info['name'] in centos_srpms:
            info['latest-centos'] = centos_srpms[info['name']]
        if info['name'] in epel_srpms:
            info['latest-epel'] = epel_srpms[info['name']]
        info.update(packages_info.get(info['name'], {}))
        info['rpms'] = []
        xcp_builds[nvr] = info
        if with_all_rpms:
            for rpm_nvra in analyzer.rpms_by_srpm.get(nvr, []):
                add_rpm(rpm_nvra)

    def add_rpm(rpm_nvra):
        if rpm_nvra in xcp_rpms:
            return
        s = analyzer.rpms[rpm_nvra]
        xcp_rpms[rpm_nvra] = {'name': s.name, 'srpm_nvr': srpm_nvr(s)}
        add_build(srpm_nvr(s), with_all_rpms=False)
        xcp_builds[srpm_nvr(s)]['rpms'].append(rpm_nvra)

    for s in analyzer.latest_srpms():
        add_build("%s-%s" % (s.name, s.evr.split(':')[-1]), with_all_rpms=True)

    log.info("resolving the RPMs installed by default (deps of xcp-ng-deps)")
    new = analyzer.install_name('xcp-ng-deps')
    if new is None:
        raise Exception("What? xcp-ng-deps is not installable?")
    rpms_installed_by_default = sorted(nvra(s) for s in new)

    log.info("resolving the base system (kernel and its deps)")
    base = analyzer.install_name('kernel')
    if base is None:
        raise Exception("kernel is not installable")
    analyzer.install_base_system(base)

    extra_installable_nvra = []
    for name in extras:
        new = analyzer.install_name(name)
        # the package may be missing if it's still in xcp-ng-incoming and already listed
        match = [s for s in new or [] if s.name == name]
        if match:
            extra_installable_nvra.append(nvra(match[0]))
        else:
            log.warning("extra package %s is not installable", name)

    for rpm_nvra in rpms_installed_by_default + extra_installable_nvra:
        add_rpm(rpm_nvra)

    # Resolve until no new RPM or build gets added
    while True:
        todo_rpms = [r for r in xcp_rpms if 'deps' not in xcp_rpms[r]]
        todo_builds = [b for b in xcp_builds
                       if xcp_builds[b]['built-by'] == 'xcp-ng' and 'build-deps' not in xcp_builds[b]
                       and b in analyzer.srpms]
        if not todo_rpms and not todo_builds:
            break
        log.info("resolving the deps of %d RPMs and the build deps of %d SRPMs", len(todo_rpms), len(todo_builds))
        for rpm_nvra in todo_rpms:
            installable, deps = analyzer.runtime_deps(rpm_nvra)
            xcp_rpms[rpm_nvra].update(installable=installable, deps=deps)
            for dep in deps:
                add_rpm(dep)
        for nvr in todo_builds:
            xcp_builds[nvr]['build-deps'] = analyzer.build_deps(nvr)
            for dep in xcp_builds[nvr]['build-deps'][0] + xcp_builds[nvr]['build-deps'][1]:
                add_rpm(dep)

    for build_info in xcp_builds.values():
        build_info['rpms'].sort()
    return xcp_builds, xcp_rpms, rpms_installed_by_default, extra_installable_nvra

#
# Roles
#

def compute_roles(xcp_builds, xcp_rpms, rpms_installed_by_default, extra_installable_nvra):
    # For each RPM we store most roles as well as the related RPMs or SRPMs:
    # - main: RPMs installed by default
    # - extra: RPMs available in the repos and available for installation on dom0
    # - extra_dep: RPMs that are pulled as dependencies for extra RPMs and aren't extra or main
    # - main_builddep: direct build dependency for a SRPM that produces main RPMs
    # - main_builddep_dep: dependency of a main_builddep RPM
    # - main_indirect_builddep: builddep of a builddep or of a dep of a builddep, with no limits of depth
    # - extra_builddep: build dependency for a SRPM that produces an extra package or one of its dependencies
    # - extra_builddep_dep: dependency of an extra_builddep RPM
    # - extra_indirect_builddep: builddep of a builddep or of a dep of a builddep, with no limits of depth
    # - other_builddep: direct build dependency for a SRPM that has no RPM with a role
    # - other_builddep_dep: dependency of a other_builddep
    # - other_indirect_builddep: builddep of a builddep or of a dep of a builddep, with no limits of depth
    # - other_dep: dependency for a package that has no roles, not even other_builddep_xxx or other_indirect_builddep
    #              the "other_dep" package must also have no roles itself, except other_*
    # - None: no roles

    for rpm_nvra in xcp_rpms:
        xcp_rpms[rpm_nvra]['roles'] = {}

    def add_rpm_role(rpm_nvra, role, related):
        xcp_rpms[rpm_nvra]['roles'].setdefault(role, set()).add(related)

    for rpm_nvra in xcp_rpms:
        if rpm_nvra in rpms_installed_by_default:
            # for now the related RPM for the 'main' role is the RPM itself
            add_rpm_role(rpm_nvra, 'main', rpm_nvra)
        if rpm_nvra in extra_installable_nvra:
            add_rpm_role(rpm_nvra, 'extra', rpm_nvra)

    for rpm_nvra in xcp_rpms:
        if rpm_nvra in extra_installable_nvra:
            for dep in xcp_rpms[rpm_nvra]['deps']:
                if not xcp_rpms[dep]['roles']:
                    add_rpm_role(dep, 'extra_dep', rpm_nvra)

    def intersect_or_both_empty(list1, list2):
        if not list1 and not list2:
            return True
        return bool(set(list1) & set(list2))

    def srpm_rpms_have_roles(srpm_nvr):
        return any(xcp_rpms[r]['roles'] for r in xcp_builds[srpm_nvr]['rpms'])

    def update_builddep_role(roles_from, role_to, direct):
        """
        Identify and flag RPMs that are builddeps or deps of builddeps
        """
        for rpm_nvra in xcp_rpms:
            if intersect_or_both_empty(xcp_rpms[rpm_nvra]['roles'].keys(), roles_from):
                srpm_nvr = xcp_rpms[rpm_nvra]['srpm_nvr']
                # if roles_from is empty and the RPM belongs to a SRPM that already has RPMs with roles,
                # don't retain that RPM. We don't want other_builddep and other_builddep_dep to pop everywhere
                # a SRPM produces an unused RPM among other useful RPMs
                if not roles_from and srpm_rpms_have_roles(srpm_nvr):
                    continue
                if 'build-deps' in xcp_builds[srpm_nvr]:
                    for dep_rpm_nvra in xcp_builds[srpm_nvr]['build-deps'][0 if direct else 1]:
                        add_rpm_role(dep_rpm_nvra, role_to, srpm_nvr)

    def update_indirect_builddep_role(role_prefix, role_to, iterations=10):
        """
        Identify and flag RPMs that are builddeps for builddeps themselves.
        Or deps of builddeps of builddeps.
        Or builddeps of deps of builddeps of deps of builddeps.
        All of them.
        """
        # Start with builddeps (direct or not) of RPMs whose role starts with role_prefix
        roles_to_scan = [role_prefix + '_builddep', role_prefix + '_builddep_dep']
        for _ in range(iterations):
            for rpm_nvra in list(xcp_rpms):
                if not set(xcp_rpms[rpm_nvra]['roles']) & set(roles_to_scan):
                    continue
                # scan the builddeps of its SRPM
                srpm_nvr = xcp_rpms[rpm_nvra]['srpm_nvr']
                if 'build-deps' not in xcp_builds[srpm_nvr]:
                    continue
                for dep_type in [0, 1]:
                    for dep_rpm_nvra in xcp_builds[srpm_nvr]['build-deps'][dep_type]:
                        # since the roles_to_scan are already build deps, the SRPMs to point
                        # as target of the indirect builddep must be those that the build deps
                        # themselves target
                        for role_from in roles_to_scan:
                            for upper_srpm_nvr in list(xcp_rpms[rpm_nvra]['roles'].get(role_from, [])):
                                # If...
                                # 1. dep_rpm_nvra   ---(direct or pulled build dep of)--->     srpm_nvr
                                # 2. srpm_nvr       -------------(produces)-------------->     rpm_nvra
                                # 3. rpm_nvra       ------("role_from" build dep of)----->     upper_srpm_nvr
                                # Then...
                                # dep_rpm_nvra      -------("role_to" build dep of)------>     upper_srpm_nvr
                                add_rpm_role(dep_rpm_nvra, role_to, upper_srpm_nvr)
            # after the first iteration
            roles_to_scan = [role_to]

    update_builddep_role(roles_from=['main'], role_to='main_builddep', direct=True)
    update_builddep_role(roles_from=['main'], role_to='main_builddep_dep', direct=False)
    update_indirect_builddep_role(role_prefix='main', role_to='main_indirect_builddep')
    update_builddep_role(roles_from=['extra', 'extra_dep'], role_to='extra_builddep', direct=True)
    update_builddep_role(roles_from=['extra', 'extra_dep'], role_to='extra_builddep_dep', direct=False)
    update_indirect_builddep_role(role_prefix='extra', role_to='extra_indirect_builddep')

    # Now deps of RPMs that still have no roles
    update_builddep_role(roles_from=[], role_to='other_builddep', direct=True)
    update_builddep_role(roles_from=[], role_to='other_builddep_dep', direct=False)
    update_indirect_builddep_role(role_prefix='other', role_to='other_indirect_builddep')
    for rpm_nvra in xcp_rpms:
        if not xcp_rpms[rpm_nvra]['roles']:
            for dep in xcp_rpms[rpm_nvra]['deps']:
                # other_dep possible only if has no other role than 'other_*'
                if not [x for x in xcp_rpms[dep]['roles'] if not x.startswith('other_')]:
                    add_rpm_role(dep, 'other_dep', rpm_nvra)

    # Update SRPM roles based on RPM roles
    for srpm_nvr, build_info in xcp_builds.items():
        srpm_roles = {}
        for rpm_nvra in build_info['rpms']:
            for rpm_role, role_data in xcp_rpms[rpm_nvra]['roles'].items():
                if rpm_role in ('extra_dep', 'other_dep'):
                    # ignore deps towards RPM of the same SRPM
                    role_data = [x for x in role_data if xcp_rpms[x]['srpm_nvr'] != srpm_nvr]
                if role_data:
                    srpm_roles.setdefault(rpm_role, set()).update(role_data)
        build_info['roles'] = srpm_roles

#
# Reports
#

ROLE_PRIORITY = [
    'main',
    'main_builddep',
    'main_builddep_dep',
    'main_indirect_builddep',
    'extra',
    'extra_dep',
    'extra_builddep',
    'extra_builddep_dep',
    'extra_indirect_builddep',
    'other_builddep',
    'other_builddep_dep',
    'other_indirect_builddep',
    'other_dep',
    'None',
]

BUILT_BY_ORDER = ['xcp-ng', 'centos', 'epel', 'xs', 'unknown']

SRPM_FIELDS = {
    # key: label
    'srpm_name': 'SRPM name',
    'repo': 'repo',
    'version': 'version',
    'centos_version': 'CentOS version',
    'epel_version': 'EPEL version',
    'summary': 'summary',
    'built_by': 'built by',
    'added_by': 'added by',
    'maintainer': 'maintainer',
    'note': 'note',
    'main_role': 'main role',
    'roles': 'main roles',
    'direct_build_deps': 'direct build deps',
    'rpms': 'rpms',
}

REPORTS = {
    'roles_and_deps': ['srpm_name', 'repo', 'version', 'built_by', 'added_by', 'maintainer', 'note',
                       'main_role', 'roles', 'direct_build_deps', 'rpms'],
    'versions': ['srpm_name', 'summary', 'repo', 'version', 'centos_version', 'epel_version',
                 'built_by', 'added_by', 'maintainer', 'note', 'main_role', 'roles'],
}

def simplify_roles(roles):
    # Most packages have lots of roles, so we need to simplify visually
    roles = {role: sorted(data) for role, data in roles.items()}
    # * 'main' hides 'extra_*' and 'other_*'
    if 'main' in roles:
        roles = {r: d for r, d in roles.items() if not r.startswith(('extra_', 'other_'))}
    # * 'extra' hides 'other_*'
    if 'extra' in roles:
        roles = {r: d for r, d in roles.items() if not r.startswith('other_')}
    # * 'xxx_builddep' hides 'xxx_builddep_dep' (same value of xxx and same SRPM)
    for role1 in ['main_builddep', 'extra_builddep', 'other_builddep']:
        role2 = role1 + '_dep'
        if role1 in roles and role2 in roles:
            roles[role2] = [x for x in roles[role2] if x not in roles[role1]]
            if not roles[role2]:
                del roles[role2]
    # * anything hides something that ends in "_indirect_builddep"
    if [r for r in roles if not r.endswith('_indirect_builddep')]:
        roles = {r: d for r, d in roles.items() if not r.endswith('_indirect_builddep')}
    # * anything that does not begin with 'other' hides 'other*'
    if [r for r in roles if not r.startswith('other')]:
        roles = {r: d for r, d in roles.items() if not r.startswith('other')}
    return roles

def format_role(xcp_builds, xcp_rpms, role, data, max_entries=None):
    if role in ['main', 'extra', 'extra_dep', 'other_dep']:
        # short RPM names
        details = [xcp_rpms[rpm_nvra]['name'] for rpm_nvra in data]
    else:
        # short SRPM names
        details = [xcp_builds[srpm_nvr]['name'] for srpm_nvr in data]
    label_for = "" if role in ['main', 'extra'] else "for "
    if max_entries is not None and len(details) > max_entries:
        details = details[:max_entries] + ['...']
    return "%s (%s%s)" % (role, label_for, ' '.join(details))

def shorten(items, max_entries):
    if max_entries is not None and len(items) > max_entries:
        return items[:max_entries] + ['...']
    return items

def evr_tuple(info):
    # voluntarily avoiding epoch in version comparisons because we might have different epochs
    return ('1', info['version'], info['release'])

def build_report_rows(xcp_builds, xcp_rpms, report_fields, elaborate):
    """ elaborate: links, bold versions and shortened lists, for markdown and HTML """
    rows = []
    for srpm_nvr, build_info in xcp_builds.items():
        srpm_name = build_info['name']
        roles = simplify_roles(build_info['roles'])
        role_lines = [format_role(xcp_builds, xcp_rpms, role, roles[role], max_entries=5 if elaborate else None)
                      for role in ROLE_PRIORITY if role in roles]
        main_role = next((role for role in ROLE_PRIORITY if role in roles), 'None')

        # build deps are present only for packages built by XCP-ng
        direct_build_deps = ''
        if 'build-deps' in build_info:
            names = [xcp_rpms[r]['name'] for r in build_info['build-deps'][0]]
            direct_build_deps = ' '.join(shorten(names, 10 if elaborate else None))
        rpms = ' '.join(shorten([xcp_rpms[r]['name'] for r in build_info['rpms']], 10 if elaborate else None))

        # versions: highest version in bold display
        version = build_info['version'] + '-' + build_info['release']
        others = {}
        for distro in ['centos', 'epel']:
            info = build_info.get('latest-' + distro)
            others[distro] = (info['version'] + '-' + info['release'], evr_tuple(info)) if info else ('', ('0', '0', '0'))
        candidates = [evr_tuple(build_info), others['centos'][1], others['epel'][1]]
        max_tuple = max(candidates, key=functools.cmp_to_key(rpm.labelCompare))
        centos_version, epel_version = others['centos'][0], others['epel'][0]
        if max_tuple == evr_tuple(build_info):
            if (centos_version or epel_version) and max_tuple not in candidates[1:]:
                version = '**%s**' % version
        elif max_tuple == others['centos'][1]:
            centos_version = '**%s**' % centos_version
        else:
            epel_version = '**%s**' % epel_version

        if elaborate:
            srpm_name_value = "[%s](%s)" % (srpm_name, KOJI_BUILD_URL % urllib.parse.quote(srpm_nvr))
            if centos_version:
                centos_version = "[%s](%s)" % (centos_version, CENTOS_RPM_URL % srpm_name)
            if epel_version:
                epel_version = "[%s](%s)" % (epel_version, EPEL_RPM_URL % srpm_name)
        else:
            srpm_name_value = srpm_name

        values = {
            'srpm_name': srpm_name_value,
            'repo': build_info['koji_tag'],
            'version': version,
            'centos_version': centos_version,
            'epel_version': epel_version,
            'summary': build_info['summary'],
            'built_by': build_info['built-by'],
            'added_by': build_info.get('added_by', '').lower(),
            'maintainer': build_info.get('maintainer', ''),
            'note': build_info.get('note', ''),
            'main_role': main_role,
            'roles': '\n'.join(role_lines),
            'direct_build_deps': direct_build_deps,
            'rpms': rpms,
        }
        if elaborate:
            # the markdown table is converted to HTML, which keeps raw HTML: escape the text
            # coming from the packages metadata or packages.json, and the table separator
            for field in ['summary', 'added_by', 'maintainer', 'note', 'roles', 'direct_build_deps', 'rpms']:
                values[field] = html.escape(values[field], quote=False).replace('|', '\\|')
        sort_key = (ROLE_PRIORITY.index(main_role), BUILT_BY_ORDER.index(values['built_by']), srpm_name, srpm_nvr)
        rows.append((sort_key, [values[field] for field in report_fields]))
    return [row for _, row in sorted(rows)]

def js_color_cell_values(values, color):
    return """
    if (%s.indexOf(cells[i].innerHTML) >= 0) {
        cells[i].style.color = '%s';
    }
""" % (json.dumps(values), color)

HTML_HEADER = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>XCP-ng {version}: {report_name}</title>
<style>
table {{
    border-width: 1px;
    border-collapse: collapse;
}}
td, th {{
    font-size: 0.75em;
    border-width: 1px;
    border-color: silver;
    border-style: solid;
    padding: 2px;
}}
</style>
</head>
<body>
<p>Generated on {date}</p>
"""

def html_script():
    script = """
<script>
var table = document.getElementsByTagName('table')[0];
var tbody = table.getElementsByTagName('tbody')[0];
var cells = tbody.getElementsByTagName('td');

for (var i=0, len=cells.length; i<len; i++){
"""
    script += js_color_cell_values([v for v in ROLE_PRIORITY if v.startswith('main')], 'green')
    script += js_color_cell_values([v for v in ROLE_PRIORITY if v.startswith('extra')], 'blue')
    script += js_color_cell_values([v for v in ROLE_PRIORITY if v.startswith('other')] + ['None'], 'tomato')
    script += js_color_cell_values(['updates'], 'blue')
    script += js_color_cell_values(['candidates', 'testing', 'ci'], 'orangered')
    script += js_color_cell_values(['xcp-ng'], '#263740')
    script += js_color_cell_values(['centos'], 'sienna')
    script += js_color_cell_values(['epel'], 'orchid')
    script += js_color_cell_values(['xs'], 'tomato')
    script += js_color_cell_values(['unknown'], 'red')
    script += """
}
</script>
</body>
</html>
"""
    return script

def write_reports(xcp_builds, xcp_rpms, xcp_version, reports_dir):
    os.makedirs(reports_dir, exist_ok=True)
    date = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    for report_name, fields in REPORTS.items():
        header = [SRPM_FIELDS[field] for field in fields]

        rows = build_report_rows(xcp_builds, xcp_rpms, fields, elaborate=False)
        with open(os.path.join(reports_dir, 'report_%s.csv' % report_name), 'w') as f:
            for row in [header] + rows:
                f.write(';'.join(field.replace('\n', ' - ') for field in row) + '\n')

        rows = build_report_rows(xcp_builds, xcp_rpms, fields, elaborate=True)
        table = ' | '.join(header) + '\n' + ' | '.join(['-'] * len(header)) + '\n'
        for row in rows:
            table += ' | '.join(field.replace('\n', '<br>') for field in row) + '\n'
        with open(os.path.join(reports_dir, 'report_%s.md' % report_name), 'w') as f:
            f.write(table)
        with open(os.path.join(reports_dir, 'report_%s.html' % report_name), 'w') as f:
            f.write(HTML_HEADER.format(version=xcp_version, report_name=report_name, date=date))
            f.write(markdown.markdown(table, extensions=['tables']))
            f.write(html_script())

class SetEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, set):
            return sorted(obj)
        return json.JSONEncoder.default(self, obj)

def main():
    parser = argparse.ArgumentParser(description='Produce reports about XCP-ng RPMs')
    parser.add_argument('version', help='XCP-ng 2-digit version, e.g. 8.3')
    parser.add_argument('--output', default='out', help='output directory, reports go in OUTPUT/VERSION/reports')
    parser.add_argument('--cache', default='cache', help='directory where the repository metadata is cached')
    parser.add_argument('--packages-info', default=PACKAGES_URL,
                        help='path or URL of rpm_owners/packages.json (default: xcp-ng/xcp on GitHub)')
    parser.add_argument('--repo-url', default=REPO_URL,
                        help='URL of the repositories, with {major}, {version}, {repo} and {arch} placeholders '
                             '(default: %(default)s)')
    parser.add_argument('--index-root', default='/',
                        help='path of the output directory on the web site, for the titles of the index pages')
    parser.add_argument('--koji-hub', default=KOJI_HUB, help='URL of the koji hub')
    parser.add_argument('--koji-snapshot', help='JSON file with the koji data, instead of querying koji (for tests)')
    parser.add_argument('-v', '--verbose', action='store_true')
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    xcp_version = args.version
    os.makedirs(args.cache, exist_ok=True)
    output_dir = os.path.join(args.output, xcp_version)
    os.makedirs(output_dir, exist_ok=True)

    built_by, extras = read_koji_info(xcp_version, args.koji_hub, args.koji_snapshot)
    packages_info = read_packages_info(args.packages_info)
    centos_srpms = read_frozen_srpms('centos7-srpms.json')
    epel_srpms = read_frozen_srpms('epel7-srpms.json')

    analyzer = Analyzer(load_pool(xcp_version, args.repo_url, args.cache))
    xcp_builds, xcp_rpms, by_default, extra_nvra = collect(analyzer, built_by, extras, packages_info,
                                                           centos_srpms, epel_srpms)
    compute_roles(xcp_builds, xcp_rpms, by_default, extra_nvra)

    for name, data in [('xcp-ng_builds.json', xcp_builds), ('xcp-ng_rpms.json', xcp_rpms),
                       ('rpms_installed_by_default_nvra.json', by_default),
                       ('extra_installable_nvra.json', extra_nvra)]:
        with open(os.path.join(output_dir, name), 'w') as f:
            json.dump(data, f, sort_keys=True, indent=4, cls=SetEncoder)
    write_reports(xcp_builds, xcp_rpms, xcp_version, os.path.join(output_dir, 'reports'))
    # S3 static websites don't list directories
    write_dir_indexes(output_dir, args.index_root.rstrip('/') + '/' + xcp_version)
    log.info("%d SRPMs, %d RPMs, reports written in %s", len(xcp_builds), len(xcp_rpms), output_dir)

if __name__ == "__main__":
    main()
