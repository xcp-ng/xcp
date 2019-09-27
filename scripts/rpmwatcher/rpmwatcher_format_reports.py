#!/bin/env python

"""
Formats reports about our RPMs

Prerequisites:
- python-markdown
- a /data directory that contains the workdir dir updated by rpmwatcher_extract_roles.py

Note, in what follows:
- NVR means Name Version Release
- NVRA means Name Version Release Arch
Those are common concepts in the RPM world.
"""

from __future__ import print_function
import argparse
import subprocess
import os
import json
import glob
import tempfile
import codecs
import StringIO
import markdown
import rpm
import urllib

KOJI_URL = "https://koji.xcp-ng.org"
KOJI_BUILD_URL = KOJI_URL + "/search?match=exact&type=build&terms=%s"
# Unless you know an exact *binary* RPM name, there's no better URL than a simple search on the name, without the version
# They don't display information pages for SRPMs, unfortunately...
# Also: this URL does only exact name matches, whereas if you use their search field there's
# an implicit wildcard... But the URL is the same... Not-significant URLs...
CENTOS_RPM_URL = "https://pkgs.org/download/%s"
# I could use Fedora's koji for a more direct URL, but it is slow to respond to search queries
# and I don't want to put too much burden on it (if for example a crawler tries every URL)
EPEL_RPM_URL = "https://pkgs.org/download/%s"

def check_dir(dirpath):
    if not os.path.isdir(dirpath):
        raise Exception("Directory %s doesn't exist" % dirpath)
    return dirpath

def format_role(xcp_builds, xcp_rpms, role, data, max_entries=None):
    if role in ['main', 'extra']:
        # short RPM names
        details = [xcp_rpms[rpm_nvra]['name'] for rpm_nvra in data]
        label_for = ""
    elif role in ['extra_dep', 'other_dep']:
        # short RPM names
        details = [xcp_rpms[rpm_nvra]['name'] for rpm_nvra in data]
        label_for = "for "
    else:
        # short SRPM names
        details = []
        for srpm_nvr in data:
            details.append(xcp_builds[srpm_nvr]['name'])
        label_for = "for "
    if max_entries is not None:
        if len(details) > max_entries:
            details = details[:max_entries] + ['...']
    return "%s (%s%s)" % (role, label_for, ' '.join(details))

def js_color_cell_values(values=[], color='black'):
    return """
    if (%s.indexOf(cells[i].innerHTML) >=0 ){
        cells[i].style.color = '%s';
    }
""" % (json.dumps(values), color)

# From https://docs.python.org/3/howto/sorting.html
def cmp_to_key(mycmp):
    'Convert a cmp= function into a key= function'
    class K(object):
        def __init__(self, obj, *args):
            self.obj = obj
        def __lt__(self, other):
            return mycmp(self.obj, other.obj) < 0
        def __gt__(self, other):
            return mycmp(self.obj, other.obj) > 0
        def __eq__(self, other):
            return mycmp(self.obj, other.obj) == 0
        def __le__(self, other):
            return mycmp(self.obj, other.obj) <= 0
        def __ge__(self, other):
            return mycmp(self.obj, other.obj) >= 0
        def __ne__(self, other):
            return mycmp(self.obj, other.obj) != 0
    return K

def main():
    parser = argparse.ArgumentParser(description='Format reports about XCP-ng RPMs')
    parser.add_argument('version', help='XCP-ng 2-digit version, e.g. 8.0')
    parser.add_argument('basedir', help='path to the base directory where repos must be present and where '
                                        'we\'ll read data from.')
    format_choices = ['csv', 'markdown', 'html']
    parser.add_argument('format', help='output format: %s.' % " or ".join(format_choices), choices=format_choices)
    args = parser.parse_args()

    format = args.format
    shorten_output = format != 'csv'
    elaborate_output = format != 'csv'
    base_dir = os.path.abspath(check_dir(args.basedir))
    xcp_version = args.version
    xcp_srpm_repo = check_dir(os.path.join(base_dir, 'xcp-ng', xcp_version))
    xcp_rpm_repo = check_dir(os.path.join(base_dir, 'xcp-ng_rpms', xcp_version))
    work_dir = check_dir(os.path.join(base_dir, 'workdir', xcp_version))

    # Read data from workdir
    with open(os.path.join(work_dir, 'xcp-ng_builds.json')) as f:
        xcp_builds = json.load(f)
    with open(os.path.join(work_dir, 'xcp-ng_rpms.json')) as f:
        xcp_rpms = json.load(f)

    role_priority = [
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
        'other_dep'
    ]

    srpm_fields_ref = {
        # key: label
        'srpm_name': 'SRPM name',
        'repo': 'repo',
        'version': 'version',
        'centos_version': 'CentOS version',
        'epel_version': 'EPEL version',
        'summary': 'summary',
        'built_by': 'built by',
        'added_by': 'added by',
        'import_reason': 'import reason',
        'main_role': 'main role',
        'provenance': 'provenance',
        'roles': 'roles',
        'direct_build_deps': 'direct build deps',
        'rpms': 'rpms',
    }

    srpm_reports_ref = {
        'roles_and_deps': [
            'srpm_name',
            'repo',
            'version',
            'built_by',
            'added_by',
            'import_reason',
            'main_role',
            'roles',
            'direct_build_deps',
            'rpms'
        ],
        'versions': [
            'srpm_name',
            'summary',
            'repo',
            'version',
            'centos_version',
            'epel_version',
            'built_by',
            'added_by',
            'import_reason',
            'main_role',
            'roles'
        ]
    }

    srpm_reports = {}
    for report_name in srpm_reports_ref:
        srpm_reports[report_name] = []

    # data
    for srpm_nvr, build_info in xcp_builds.iteritems():
        repo = build_info['koji_tag'][len('v%s-' % xcp_version):]
        srpm_name = build_info['name']
        summary = build_info['summary']
        built_by = build_info['built-by']
        added_by = build_info.get('added_by', '').lower()
        import_reason = build_info.get('import_reason', '')

        # roles
        main_role = None
        roles_list = []
        for role in role_priority:
            if role in build_info['roles']:
                if main_role is None:
                    main_role = role
                roles_list.append(format_role(xcp_builds, xcp_rpms, role, build_info['roles'][role],
                                              max_entries=5 if shorten_output else None))
        roles = "\n".join(roles_list)
        if main_role is None:
            main_role = 'None'

        # build deps are present only for packages built by XCP-ng
        direct_build_deps = ""
        if 'build-deps' in build_info:
            direct_build_deps_list = [xcp_rpms[rpm_nvra]['name'] for rpm_nvra in build_info['build-deps'][0]]
            if shorten_output and len(direct_build_deps_list) > 10:
                direct_build_deps_list = direct_build_deps_list[:10] + ['...']
            direct_build_deps = " ".join(direct_build_deps_list)

        # rpms
        rpms_list = [xcp_rpms[rpm_nvra]['name'] for rpm_nvra in build_info['rpms']]
        if shorten_output and len(rpms_list) > 10:
            rpms_list = rpms_list[:10] + ['...']
        rpms = " ".join(rpms_list)

        # versions: highest version in bold display
        # note: voluntarily avoiding epoch in version comparisons because we might have different epochs
        version = build_info['version'] + '-' + build_info['release']
        nvr_tuple = ('1', build_info['version'], build_info['release'])
        if 'latest-centos' in build_info:
            centos_version = build_info['latest-centos']['version'] + '-' + build_info['latest-centos']['release']
            centos_nvr_tuple = ('1', build_info['latest-centos']['version'], build_info['latest-centos']['release'])
        else:
            centos_version = ""
            centos_nvr_tuple = ('0', '0', '0')
        if 'latest-epel' in build_info:
            epel_version = build_info['latest-epel']['version'] + '-' + build_info['latest-epel']['release']
            epel_nvr_tuple = ('1', build_info['latest-epel']['version'], build_info['latest-epel']['release'])
        else:
            epel_version = ""
            epel_nvr_tuple = ('0', '0', '0')

        max_nvr_tuple = max([nvr_tuple, centos_nvr_tuple, epel_nvr_tuple], key=cmp_to_key(rpm.labelCompare))
        if max_nvr_tuple == nvr_tuple:
            if (centos_version or epel_version) and max_nvr_tuple not in [epel_nvr_tuple, centos_nvr_tuple]:
                version = '**%s**' % version
        elif max_nvr_tuple == centos_nvr_tuple:
            centos_version = '**%s**' % centos_version
        elif max_nvr_tuple == epel_nvr_tuple:
            epel_version = '**%s**' % epel_version

        # add data to reports
        for report_name, report in srpm_reports.iteritems():
            row = []
            for field in srpm_reports_ref[report_name]:
                if field == 'srpm_name':
                    if elaborate_output:
                        value = "[%s](%s)" % (srpm_name, KOJI_BUILD_URL % urllib.quote(srpm_nvr))
                    else:
                        value = srpm_name
                elif field == 'repo':
                    value = repo
                elif field == 'version':
                    value = version
                elif field == 'centos_version':
                    if centos_version and elaborate_output:
                        value = "[%s](%s)" % (centos_version, CENTOS_RPM_URL % srpm_name)
                    else:
                        value = centos_version
                elif field == 'epel_version':
                    if epel_version and elaborate_output:
                        value = "[%s](%s)" % (epel_version, EPEL_RPM_URL % srpm_name)
                    else:
                        value = epel_version
                elif field == 'summary':
                    value = summary
                elif field == 'built_by':
                    value = built_by
                elif field == 'added_by':
                    value= added_by
                elif field == 'import_reason':
                    value= import_reason
                elif field == 'main_role':
                    value = main_role
                elif field == 'roles':
                    value = roles
                elif field == 'direct_build_deps':
                    value = direct_build_deps
                elif field == 'rpms':
                    value = rpms
                else:
                    raise("Couldn't handle field '%s'" % field)
                row.append(value)
            report.append(row)

    # sort rows in reports
    built_by_order = [
        'xcp-ng',
        'centos',
        'epel',
        'xs',
        'unknown'
    ]
    role_priority.append('None')

    for report_name, report in srpm_reports.iteritems():
        headers = srpm_reports_ref[report_name]
        def custom_cmp(row1, row2):
            role_index = headers.index('main_role')
            if role_priority.index(row1[role_index]) > role_priority.index(row2[role_index]):
                return 1
            if role_priority.index(row1[role_index]) < role_priority.index(row2[role_index]):
                return -1

            built_by_index = headers.index('built_by')
            if built_by_order.index(row1[built_by_index]) > built_by_order.index(row2[built_by_index]):
                return 1
            if built_by_order.index(row1[built_by_index]) < built_by_order.index(row2[built_by_index]):
                return -1

            name_index = headers.index('srpm_name')
            return cmp([row1[name_index]], [row2[name_index]])

        report.sort(cmp=custom_cmp)
        # add header
        report.insert(0, [srpm_fields_ref[field] for field in srpm_reports_ref[report_name]])

        # format and write output
        if format == 'csv':
            with codecs.open(os.path.join(work_dir, 'report_%s.csv' % report_name), 'w', encoding='utf8') as f:
                for row in report:
                    row = [field.replace('\n', ' - ') for field in row]
                    f.write(';'.join(row) + '\n')
        elif format in ['markdown', 'html']:
            s = StringIO.StringIO()
            s.write(' | '.join(report[0]) + '\n')
            separator = '-'
            for i in xrange(len(report[0]) - 1):
                separator += ' | -'
            s.write(separator + '\n')

            for row in report[1:]:
                row = [field.replace('\n', '<br>') for field in row]
                s.write(' | '.join(row) + '\n')
            try:
                if format == 'markdown':
                    with codecs.open(os.path.join(work_dir, 'report_%s.md' % report_name), 'w', encoding='utf8') as f:
                        f.write(s.getvalue())
                elif format == 'html':
                    with codecs.open(os.path.join(work_dir, 'report_%s.html' % report_name), 'w', encoding='utf8') as f:
                        f.write("""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<style>
table {
    border-width: 1px;
    border-collapse: collapse;
}
td, th {
    font-size: 0.75em;
    border-width: 1px;
    border-color: silver;
    border-style: solid;
    padding: 2px;
}
</style>
</head>

""")
                        f.write(markdown.markdown(s.getvalue(), extensions=['tables']))
                        script = """
<script>
var table = document.getElementsByTagName('table')[0];
var tbody = table.getElementsByTagName('tbody')[0];
var cells = tbody.getElementsByTagName('td');

for (var i=0, len=cells.length; i<len; i++){
"""
                        script += js_color_cell_values([v for v in role_priority if v.startswith('main')], 'green')
                        script += js_color_cell_values([v for v in role_priority if v.startswith('extra')], 'blue')
                        script += js_color_cell_values([v for v in role_priority if v.startswith('other')] + ['None'], 'tomato')
                        script += js_color_cell_values(['updates'], 'blue')
                        script += js_color_cell_values(['testing'], 'orangered')
                        script += js_color_cell_values(['xcp-ng'], '#263740')
                        script += js_color_cell_values(['centos'], 'sienna')
                        script += js_color_cell_values(['epel'], 'orchid')
                        script += js_color_cell_values(['xs'], 'tomato')
                        script += js_color_cell_values(['unknown'], 'red')
                        script += """
}
</script>
</html>
"""
                        f.write(script)
                else:
                    raise("Unexpected.")
            finally:
                s.close()
        else:
            raise("Oops, I don't know how to handle format '%s'." % format)

if __name__ == "__main__":
    main()
