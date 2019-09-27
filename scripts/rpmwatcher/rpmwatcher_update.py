#!/bin/env python

"""
Update stats about XCP-ng RPMs.

Prerequisites:
- a directory that contains
  - a local CentOS repo of SRPMs, all SRPMs in the first-level directory. Directory name: centos.
  - a local EPEL repo of SRPMs, all SRPMs in the first-level directory. Directory name: epel.
  - a local XCP-ng repo of SRPMs, all SRPMs in the first-level directory. Directory name: xcp-ng/{version}, e.g. xcp-ng/8.0
  - a working directory: workdir
- the user running the script must have access to koji through cli
"""

from __future__ import print_function
import argparse
import subprocess
import os
import rpm
import json
import urllib2

DEVNULL = open(os.devnull, 'w')

MAIN_TAGS = ['base', 'updates', 'testing']

def check_dir(dirpath):
    if not os.path.isdir(dirpath):
        raise Exception("Directory %s doesn't exist" % dirpath)
    return dirpath

def list_tags_for_version(version):
    tags = subprocess.check_output(['koji', 'list-tags', 'v%s*' % version]).splitlines()

    sorted_tags = []
    # first get the main tags
    for tag_suffix in MAIN_TAGS:
        t = 'v%s-%s' % (version, tag_suffix)
        if t in tags:
            sorted_tags.append(t)
            tags.remove(t)

#     # add the remaining tags
#     # UPDATE: not adding them anymore until we download the corresponding SRPMs and RPMs from koji
#     #         and can add them as repos to be used by rpmwatcher_extract_deps.py
#     sorted_tags += sorted(tags)

    return sorted_tags

def get_builds_for_tag(tag, latest=False):
    builds = []
    param_latest = ['--latest'] if latest else []
    lines = subprocess.check_output(['koji', 'list-tagged', tag, '--quiet'] + param_latest).splitlines()
    for line in lines:
        srpm_nvr = line.split()[0]
        builds.append(srpm_nvr)
    return sorted(builds)

def get_info_from_srpm_file(filepath):
    if not os.path.exists(filepath):
        return {}
    output = subprocess.check_output(
        ['rpm', '-qp', filepath, '--qf', '%{name};;%{vendor};;%{summary};;%{nvr};;%{epoch};;%{version};;%{release}'],
        stderr=DEVNULL).split(';;')
    return {
        'name': output[0],
        'vendor': output[1],
        'summary': output[2],
        'nvr': output[3],
        'epoch': '' if output[4] == '(none)' else output[4],
        'version': output[5],
        'release': output[6],
    }

def get_latest_srpms_info_from_dir(dirpath):
    result = {}
    for filename in os.listdir(dirpath):
        info = get_info_from_srpm_file(os.path.join(dirpath, filename))
        if info['name'] not in result:
            result[info['name']] = info
        else:
            # keep only the newest
            prev_info = result[info['name']]
            if rpm.labelCompare((prev_info['epoch'], prev_info['version'], prev_info['release']),
                                (info['epoch'], info['version'], info['release'])) < 0:
                result[info['name']] = info
    return result


def main():
    parser = argparse.ArgumentParser(description='Update stats about XCP-ng RPMs')
    parser.add_argument('version', help='XCP-ng 2-digit version, e.g. 8.0')
    parser.add_argument('basedir', help='path to the base directory where repos must be present and where '
                                        'we\'ll output results.')
    args = parser.parse_args()

    base_dir = os.path.abspath(check_dir(args.basedir))
    xcp_version = args.version
    xcp_srpm_repo = check_dir(os.path.join(base_dir, 'xcp-ng', xcp_version))
    centos_srpm_repo = check_dir(os.path.join(base_dir, 'centos'))
    epel_srpm_repo = check_dir(os.path.join(base_dir, 'epel'))
    work_dir = check_dir(os.path.join(base_dir, 'workdir', xcp_version))

    built_by = {}
    built_by['centos'] = get_builds_for_tag('built-by-centos')
    built_by['epel'] = get_builds_for_tag('built-by-epel')
    built_by['xs'] = get_builds_for_tag('built-by-xs')
    built_by['xcp-ng'] = get_builds_for_tag('built-by-xcp-ng')


    # Get "manually written" information about our packages
    expected_headers = ['SRPM_name', 'added_by', 'import_reason', 'latest_release_URL', 'latest_release_regexp']
    filename = "packages_provenance.csv"
    provenance_csv = urllib2.urlopen(
        'https://raw.githubusercontent.com/xcp-ng/xcp/master/data/%s/%s' % (xcp_version, filename)
    ).read()
    provenance_csv = [line.split(';') for line in provenance_csv.splitlines()]
    csv_headers = provenance_csv[0]
    if csv_headers != expected_headers:
        raise Exception("The headers in %s were different from what was expected. Expected %s, got %s."
                        % (filename, expected_headers, csv_headers))
    provenance_csv = provenance_csv[1:]

    # Read centos and epel repos
    # This takes time because each SRPM will be read by rpm -qp --qf
    # We could speed this up a lot by parsing repodata
    centos_srpms = get_latest_srpms_info_from_dir(centos_srpm_repo)
    epel_srpms = get_latest_srpms_info_from_dir(epel_srpm_repo)

    tags = list_tags_for_version(xcp_version)

    xcp_builds = {}
    excluded_builds = []
    latest_release_by_name = {}
    for tag in tags:
        builds = get_builds_for_tag(tag, latest=True)
        for srpm_nvr in builds:
            build_info = get_info_from_srpm_file(os.path.join(xcp_srpm_repo, srpm_nvr + '.src.rpm'))
            if not build_info:
                # SRPM not present in repos
                excluded_builds.append(srpm_nvr)
                continue

            name = build_info['name']

            # Keep only the latest release for a given SRPM name
            if name in latest_release_by_name:
                prev_info = latest_release_by_name[name]
                is_latest = rpm.labelCompare((prev_info['epoch'],  prev_info['version'],  prev_info['release']),
                                             (build_info['epoch'], build_info['version'], build_info['release'])) < 0
                if not is_latest:
                    # skip
                    continue
                else:
                    # remove previous one
                    del xcp_builds[prev_info['nvr']]

            latest_release_by_name[name] = {
                'nvr': build_info['nvr'],
                'epoch': build_info['epoch'],
                'version': build_info['version'],
                'release': build_info['release']
            }

            build_info['koji_tag'] = tag

            build_info['built-by'] = 'unknown'
            for builder in built_by:
                if srpm_nvr in built_by[builder]:
                    build_info['built-by'] = builder
                    break

            if name in centos_srpms:
                build_info['latest-centos'] = centos_srpms[name]
            if name in epel_srpms:
                build_info['latest-epel'] = epel_srpms[name]

            # provenance
            srpm_name_index = csv_headers.index('SRPM_name')
            for row in provenance_csv:
                if row[srpm_name_index] == name:
                    for i in xrange(len(csv_headers)):
                        field_name = csv_headers[i]
                        if field_name == 'SRPM_name':
                            continue
                        if field_name in build_info:
                            raise("Key collision! I'm trying to add the '%s' key which already exists!" % field_name)
                        build_info[field_name] = row[i]

            xcp_builds[srpm_nvr] = build_info

    # Add list of RPMs nvra for each SRPM
    xcp_ng_rpms_srpms = {}
    with open(os.path.join(work_dir, 'xcp-ng-rpms-srpms.txt')) as f:
        for line in f.read().splitlines():
            rpm_filename, srpm_filename, rpm_shortname = line.split(",")
            if '-debuginfo-' in rpm_filename:
                continue
            srpm_nvr = srpm_filename[:-8] # remove .src.rpm
            rpm_nvra = rpm_filename[:-4] # remove .rpm
            if srpm_nvr in xcp_builds:
                if 'rpms' not in xcp_builds[srpm_nvr]:
                    xcp_builds[srpm_nvr]['rpms'] = []
                xcp_builds[srpm_nvr]['rpms'].append(rpm_nvra)
            # also populate this dict that will be useful later
            xcp_ng_rpms_srpms[rpm_nvra] = {'name': rpm_shortname, 'srpm_nvr': srpm_nvr}

    # Get the list of RPMs that are considered "extra installable packages"
    # rpmwatcher_extract_roles.py will need them and can't use koji since it is run within a container
    lines = subprocess.check_output(['koji', 'list-groups', 'V%s' % xcp_version, 'installable_extras']).splitlines()
    lines = lines[1:]
    extra_rpms = []
    for line in lines:
        extra_rpms.append(line.strip().split(':')[0])

    # Write files
    with open(os.path.join(work_dir, 'excluded_builds.txt'), 'w') as f:
        f.write('\n'.join(excluded_builds))
    with open(os.path.join(work_dir, 'xcp-ng_builds_WIP.json'), 'w') as f:
        f.write(json.dumps(xcp_builds, sort_keys=True, indent=4))
    with open(os.path.join(work_dir, 'extra_installable.txt'), 'w') as f:
        f.write('\n'.join(extra_rpms))
    with open(os.path.join(work_dir, 'xcp-ng-rpms-srpms.json'), 'w') as f:
        f.write(json.dumps(xcp_ng_rpms_srpms, sort_keys=True, indent=4))

if __name__ == "__main__":
    main()
