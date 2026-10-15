#!/usr/bin/python2

"""
Resolve the dependencies of the RPMs of an XCP-ng release with yum, the way it's done on an
XCP-ng host, and write them in a JSON file that rpmwatcher.py turns into reports.

It runs in an XCP-ng 8.3 container (see Dockerfile.resolve), which has the same yum as the
centos:7.5.1804 container used by scripts/rpmwatcher. The yum commands, and the way their output
is read, come from scripts/rpmwatcher/rpmwatcher_extract_deps.py. Only the XCP-ng repositories
are used, and the build dependencies are read from the metadata of their Source repositories,
so neither the RPMs nor the SRPMs are downloaded.

koji is also queried here, for the built-by-* tags and the installable_extras group. These are
read-only queries, which don't need authentication.

Note, in what follows:
- NVR means Name Version Release
- NVRA means Name Version Release Arch
Those are common concepts in the RPM world.
"""

from __future__ import print_function

import argparse
import json
import logging
import os
import shutil
import ssl
import subprocess
import tempfile

import xmlrpclib
from rpmUtils.miscutils import compareEVR

MAIN_REPOS = ['base', 'updates', 'candidates', 'testing', 'ci']
BUILDERS = ['centos', 'epel', 'xs', 'xcp-ng']
REPO_URL = "https://updates.xcp-ng.org/{major}/{version}/{repo}/{arch}/"
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
KOJI_HUB = "https://kojihub.xcp-ng.org"
# CA of the koji hub certificate (self-signed kojica)
KOJI_CA = os.path.join(DATA_DIR, 'koji-ca.crt')
GPG_KEY = "file:///etc/pki/rpm-gpg/RPM-GPG-KEY-xcpng"

log = logging.getLogger('resolve')

def read_koji_info(xcp_version, hub, snapshot):
    """ Return ({srpm_nvr: builder}, [installable extra RPM names]) """
    if snapshot:
        with open(snapshot) as f:
            data = json.load(f)
        return data['built_by'], data['installable_extras']

    session = xmlrpclib.ServerProxy(hub, allow_none=True, context=ssl.create_default_context(cafile=KOJI_CA))
    built_by = {}
    for builder in BUILDERS:
        for build in session.listTagged('built-by-%s' % builder):
            built_by.setdefault(build['nvr'], builder)
    extras = []
    for group in session.getTagGroups('V%s' % xcp_version):
        if group['name'] == 'installable_extras':
            extras = [p['package'] for p in group['packagelist']]
    return built_by, extras

class Yum:
    """ yum commands run on an installroot, with only the XCP-ng repositories """

    def __init__(self, xcp_version, repo_url, gpgcheck):
        self.tmp_dir = tempfile.mkdtemp(prefix='rpmwatcher-')
        self.install_root = os.path.join(self.tmp_dir, 'root')
        # The repositories are defined in our own configuration file. reposdir points to an empty
        # directory, so that the repository files of the image or of the installroot (e.g. installed
        # by xcp-ng-release) are not used.
        os.mkdir(os.path.join(self.tmp_dir, 'repos.d'))
        self.conf = os.path.join(self.tmp_dir, 'yum.conf')
        major = xcp_version.split('.')[0]
        with open(self.conf, 'w') as f:
            # the settings of dom0 that change what yum installs, no plugins (e.g. priorities)
            f.write("[main]\nreposdir=%s\nobsoletes=1\nexactarch=1\ninstallonlypkgs=\nplugins=0\n"
                    % os.path.join(self.tmp_dir, 'repos.d'))
            for repo in MAIN_REPOS:
                for arch, suffix, enabled in [('x86_64', '', 1), ('Source', '-source', 0)]:
                    f.write("""
[xcp-ng-{repo}{suffix}]
name = XCP-ng {repo}{suffix} Repository
baseurl = {url}
enabled = {enabled}
gpgcheck = {gpgcheck}
repo_gpgcheck = {gpgcheck}
gpgkey = {gpgkey}
""".format(repo=repo, suffix=suffix, enabled=enabled, gpgcheck=int(gpgcheck), gpgkey=GPG_KEY,
           url=repo_url.format(major=major, version=xcp_version, repo=repo, arch=arch)))

    def cleanup(self):
        shutil.rmtree(self.tmp_dir)

    def run(self, cmd, check=False):
        cmd = [cmd[0], '-c', self.conf, '--installroot=' + self.install_root] + cmd[1:]
        log.debug("%s", ' '.join(cmd))
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        output = p.communicate()[0]
        if check and p.returncode != 0:
            raise Exception("%s failed:\n%s" % (' '.join(cmd), output))
        return output

    def import_gpg_keys(self):
        # The keys used to check the repository metadata are imported when a command is run with -y.
        # It must be done again when the installroot changes (e.g. after installing xcp-ng-release).
        self.run(['yumdownloader', '-q', '-y', '--urls', '--enablerepo=*-source', 'xcp-ng-deps'], check=True)

    def packages(self, source):
        """ Return all the packages of the repositories, as dicts """
        fields = ['name', 'epoch', 'version', 'release', 'arch', 'sourcerpm', 'repoid', 'vendor', 'summary']
        # the summary is last, it may contain the separator
        cmd = ['repoquery', '-a', '--show-duplicates', '--qf', '|'.join('%%{%s}' % f for f in fields)]
        if source:
            cmd += ['--disablerepo=*', '--enablerepo=*-source', '--archlist=src']
        packages = []
        for line in self.run(cmd, check=True).splitlines():
            values = line.split('|', len(fields) - 1)
            if len(values) == len(fields) and values[fields.index('repoid')].startswith('xcp-ng-'):
                p = {f: '' if v == '(none)' else v for f, v in zip(fields, values)}
                p['repo'] = p['repoid'][len('xcp-ng-'):].replace('-source', '')
                packages.append(p)
        return packages

    def runtime_deps(self, name, include_self=False):
        """
        name can be either a "short" rpm package name ("n") or the full "nvra".
        Return installable, [dependencies not already in the installroot]
        """
        output = self.run(['yumdownloader', '--quiet', '--resolve', '--urls', name])
        installable = "Dependency resolution failed" not in output
        deps = [a.split('/')[-1][:-4] for a in output.splitlines() if a.endswith(".rpm")]
        if not include_self:
            deps = deps[1:]
        return installable, deps

    def latest_rpm_nvra(self, name):
        output = self.run(['yumdownloader', '--quiet', '--urls', name])
        urls = [a for a in output.splitlines() if a.endswith(".rpm")]
        return urls[0].split('/')[-1][:-4] if urls else None

    def build_deps(self, srpm_nvr):
        """
        Return [direct build deps], [deps of the build deps], as yum-builddep would install them.
        --assumeno shows the same transaction as --downloadonly, without downloading anything.
        """
        output = self.run(['yum-builddep', '--assumeno', '--enablerepo=*-source', srpm_nvr])
        phase = 0
        direct_deps = []
        deps_deps = []
        wrapped_line = False
        values = []
        for line in output.splitlines():
            if line.startswith("Installing:"):
                phase = 1
                continue
            elif phase == 1 and line.startswith("Installing for dependencies:"):
                phase = 2
                continue
            elif phase >= 1 and line.strip() == "":
                break

            if phase > 0:
                row = line.strip().split()
                values = values + row if wrapped_line else row

                if len(values) < 5:
                    # line has been wrapped
                    wrapped_line = True
                    continue
                else:
                    wrapped_line = False

                name = values[0]
                arch = values[1]
                evr = values[2]
                vr = evr if ':' not in evr else evr.split(':')[1]
                rpm_nvra = "%s-%s.%s" % (name, vr, arch)
                if phase == 1:
                    direct_deps.append(rpm_nvra)
                else:
                    deps_deps.append(rpm_nvra)

        if phase == 0 and "No uninstalled build requires" not in output:
            log.warning("build dependencies of %s cannot be resolved:\n%s", srpm_nvr, output[-1000:])
        return direct_deps, deps_deps

def evr(p):
    return (p['epoch'] or '0', p['version'], p['release'])

def resolve(yum, built_by, extras):
    """
    Return (xcp_builds, xcp_rpms, rpms_installed_by_default, extra_installable_nvra)

    The starting point is the latest build of each SRPM. But the repositories also contain older
    builds, and the dependency resolution may pull RPMs from them (e.g. a python2 subpackage
    that newer builds don't produce anymore). Those builds are added along the way, with only
    the RPMs that are actually pulled.
    """
    yum.import_gpg_keys()

    # the first repository wins, in the order of MAIN_REPOS
    srpms = {}      # srpm_nvr: package
    rpms = {}       # rpm_nvra: package
    rpms_by_srpm = {}
    for source in [True, False]:
        for p in sorted(yum.packages(source), key=lambda p: MAIN_REPOS.index(p['repo'])):
            if source:
                srpms.setdefault("%s-%s-%s" % (p['name'], p['version'], p['release']), p)
            elif '-debuginfo-' not in p['name'] + '-':
                rpm_nvra = "%s-%s-%s.%s" % (p['name'], p['version'], p['release'], p['arch'])
                if rpm_nvra not in rpms:
                    rpms[rpm_nvra] = p
                    rpms_by_srpm.setdefault(p['sourcerpm'][:-len('.src.rpm')], []).append(rpm_nvra)
    latest = {}
    for p in srpms.values():
        if p['name'] not in latest or compareEVR(evr(latest[p['name']]), evr(p)) < 0:
            latest[p['name']] = p
    log.info("%d SRPMs (%d latest builds) and %d RPMs in the repositories", len(srpms), len(latest), len(rpms))

    xcp_builds = {}
    xcp_rpms = {}

    def add_build(nvr, with_all_rpms):
        if nvr in xcp_builds:
            return
        if nvr in srpms:
            p = srpms[nvr]
            info = {'name': p['name'], 'vendor': p['vendor'], 'summary': p['summary'], 'nvr': nvr,
                    'epoch': '' if p['epoch'] == '0' else p['epoch'], 'version': p['version'],
                    'release': p['release'], 'koji_tag': p['repo']}
        else:
            log.warning("SRPM %s is not in the repositories", nvr)
            name, version, release = nvr.rsplit('-', 2)
            info = {'name': name, 'vendor': '', 'summary': '', 'nvr': nvr, 'epoch': '',
                    'version': version, 'release': release, 'koji_tag': 'unknown'}
        info['latest'] = with_all_rpms
        info['built-by'] = built_by.get(nvr, 'unknown')
        info['rpms'] = []
        xcp_builds[nvr] = info
        if with_all_rpms:
            for rpm_nvra in rpms_by_srpm.get(nvr, []):
                add_rpm(rpm_nvra)

    def add_rpm(rpm_nvra):
        if rpm_nvra in xcp_rpms:
            return
        if rpm_nvra not in rpms:
            log.warning("RPM %s is not in the repositories", rpm_nvra)
            return
        p = rpms[rpm_nvra]
        nvr = p['sourcerpm'][:-len('.src.rpm')]
        xcp_rpms[rpm_nvra] = {'name': p['name'], 'srpm_nvr': nvr}
        add_build(nvr, with_all_rpms=False)
        xcp_builds[nvr]['rpms'].append(rpm_nvra)

    for p in latest.values():
        add_build("%s-%s-%s" % (p['name'], p['version'], p['release']), with_all_rpms=True)

    log.info("resolving the RPMs installed by default (deps of xcp-ng-deps)")
    installable, rpms_installed_by_default = yum.runtime_deps('xcp-ng-deps', include_self=True)
    if not installable:
        raise Exception("What? xcp-ng-deps is not installable?")

    # Add a few base packages to the install root, e.g. kernel to avoid other packages such as kernel-alt
    # to be seen as better fit for the "kernel" provides than standard kernel because of higher version
    log.info("installing the base system in the installroot (kernel and its deps)")
    yum.run(['yum', 'install', '-q', '-y', 'kernel'], check=True)
    yum.import_gpg_keys()

    extra_installable_nvra = []
    for name in extras:
        rpm_nvra = yum.latest_rpm_nvra(name)
        # the package may be missing if it's still in xcp-ng-incoming and already listed
        if rpm_nvra:
            extra_installable_nvra.append(rpm_nvra)
        else:
            log.warning("extra package %s is not available", name)

    for rpm_nvra in rpms_installed_by_default + extra_installable_nvra:
        add_rpm(rpm_nvra)

    # Resolve until no new RPM or build gets added
    while True:
        todo_rpms = [r for r in xcp_rpms if 'deps' not in xcp_rpms[r]]
        todo_builds = [b for b in xcp_builds
                       if xcp_builds[b]['built-by'] == 'xcp-ng' and 'build-deps' not in xcp_builds[b]
                       and b in srpms]
        if not todo_rpms and not todo_builds:
            break
        log.info("resolving the deps of %d RPMs and the build deps of %d SRPMs", len(todo_rpms), len(todo_builds))
        for rpm_nvra in todo_rpms:
            installable, deps = yum.runtime_deps(rpm_nvra)
            xcp_rpms[rpm_nvra].update(installable=installable, deps=deps)
            for dep in deps:
                add_rpm(dep)
        for nvr in todo_builds:
            xcp_builds[nvr]['build-deps'] = yum.build_deps(nvr)
            for dep in xcp_builds[nvr]['build-deps'][0] + xcp_builds[nvr]['build-deps'][1]:
                add_rpm(dep)

    for build_info in xcp_builds.values():
        build_info['rpms'].sort()
    return xcp_builds, xcp_rpms, rpms_installed_by_default, extra_installable_nvra

def main():
    parser = argparse.ArgumentParser(description='Resolve the dependencies of XCP-ng RPMs with yum')
    parser.add_argument('version', help='XCP-ng 2-digit version, e.g. 8.3')
    parser.add_argument('--output', default='work', help='output directory, the result goes in OUTPUT/VERSION.json')
    parser.add_argument('--repo-url', default=REPO_URL,
                        help='URL of the repositories, with {major}, {version}, {repo} and {arch} placeholders '
                             '(default: %(default)s)')
    parser.add_argument('--no-gpgcheck', action='store_true', help="don't check the repositories signatures")
    parser.add_argument('--koji-hub', default=KOJI_HUB, help='URL of the koji hub')
    parser.add_argument('--koji-snapshot', help='JSON file with the koji data, instead of querying koji (for tests)')
    parser.add_argument('-v', '--verbose', action='store_true')
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    if not os.path.isdir(args.output):
        os.makedirs(args.output)

    built_by, extras = read_koji_info(args.version, args.koji_hub, args.koji_snapshot)
    yum = Yum(args.version, args.repo_url, not args.no_gpgcheck)
    try:
        xcp_builds, xcp_rpms, by_default, extra_nvra = resolve(yum, built_by, extras)
    finally:
        yum.cleanup()

    path = os.path.join(args.output, args.version + '.json')
    with open(path + '.part', 'w') as f:
        json.dump({'xcp_builds': xcp_builds, 'xcp_rpms': xcp_rpms, 'rpms_installed_by_default': by_default,
                   'installable_extras': extras, 'extra_installable_nvra': extra_nvra},
                  f, sort_keys=True, indent=4)
    os.rename(path + '.part', path)
    log.info("%d SRPMs, %d RPMs, written in %s", len(xcp_builds), len(xcp_rpms), path)

if __name__ == "__main__":
    main()
