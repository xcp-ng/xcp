#!/usr/bin/env python3

"""
Analyze the RPMs of an XCP-ng release and produce reports about them:
- role of each package (installed by default, extra, build dependency, unused...)
- provenance (who built it, who added it, who maintains it, notes)
- version comparison with CentOS 7 and EPEL 7

The packages and their dependencies are read from the output of resolve.py, which resolves
them with yum in an XCP-ng container.

Note, in what follows:
- NVR means Name Version Release
- NVRA means Name Version Release Arch
Those are common concepts in the RPM world.
"""

import argparse
import datetime
import functools
import html
import json
import logging
import os
import urllib.parse
import urllib.request

import markdown
import rpm
from autoindex import write_dir_indexes

PACKAGES_URL = "https://raw.githubusercontent.com/xcp-ng/xcp/master/scripts/rpm_owners/packages.json"
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')

KOJI_URL = "https://koji.xcp-ng.org"
KOJI_BUILD_URL = KOJI_URL + "/search?match=exact&type=build&terms=%s"
# Unless you know an exact *binary* RPM name, there's no better URL than a simple search on the name
CENTOS_RPM_URL = "https://pkgs.org/download/%s"
EPEL_RPM_URL = "https://pkgs.org/download/%s"

log = logging.getLogger('rpmwatcher')

#
# Data sources
#

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

def add_build_info(xcp_builds, packages_info, centos_srpms, epel_srpms):
    """ Add the information that doesn't come from the XCP-ng repositories """
    for info in xcp_builds.values():
        if info['name'] in centos_srpms:
            info['latest-centos'] = centos_srpms[info['name']]
        if info['name'] in epel_srpms:
            info['latest-epel'] = epel_srpms[info['name']]
        info.update(packages_info.get(info['name'], {}))

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
    parser.add_argument('--input', default='work', help='output directory of resolve.py')
    parser.add_argument('--packages-info', default=PACKAGES_URL,
                        help='path or URL of rpm_owners/packages.json (default: xcp-ng/xcp on GitHub)')
    parser.add_argument('--index-root', default='/',
                        help='path of the output directory on the web site, for the titles of the index pages')
    parser.add_argument('-v', '--verbose', action='store_true')
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    xcp_version = args.version
    output_dir = os.path.join(args.output, xcp_version)
    os.makedirs(output_dir, exist_ok=True)

    with open(os.path.join(args.input, xcp_version + '.json')) as f:
        resolved = json.load(f)
    xcp_builds = resolved['xcp_builds']
    xcp_rpms = resolved['xcp_rpms']
    by_default = resolved['rpms_installed_by_default']
    extra_nvra = resolved['extra_installable_nvra']
    add_build_info(xcp_builds, read_packages_info(args.packages_info),
                   read_frozen_srpms('centos7-srpms.json'), read_frozen_srpms('epel7-srpms.json'))
    compute_roles(xcp_builds, xcp_rpms, by_default, extra_nvra)

    for name, data in [('xcp-ng_builds.json', xcp_builds), ('xcp-ng_rpms.json', xcp_rpms),
                       ('rpms_installed_by_default_nvra.json', by_default),
                       ('extra_installable_nvra.json', extra_nvra)]:
        with open(os.path.join(output_dir, name), 'w') as f:
            json.dump(data, f, sort_keys=True, indent=4, cls=SetEncoder)
    # list of the extra packages we support, referenced from the documentation and used by xcp-ng-tests,
    # sorted like `koji list-groups` did for the previous rpmwatcher
    with open(os.path.join(output_dir, 'extra_installable.txt'), 'w') as f:
        f.write('\n'.join(sorted(resolved['installable_extras'])))
    write_reports(xcp_builds, xcp_rpms, xcp_version, os.path.join(output_dir, 'reports'))
    # S3 static websites don't list directories
    write_dir_indexes(output_dir, args.index_root.rstrip('/') + '/' + xcp_version)
    log.info("%d SRPMs, %d RPMs, reports written in %s", len(xcp_builds), len(xcp_rpms), output_dir)

if __name__ == "__main__":
    main()
