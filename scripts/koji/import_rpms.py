#!/bin/env python
from __future__ import print_function
import argparse
import os
import subprocess
import glob

def get_srpm_info(srpmpath):
    return subprocess.check_output(['rpm', '-qp', srpmpath, '--qf', '%{name};;%{nevr}']).split(';;')

def check_dir(dirpath):
    if not os.path.isdir(dirpath):
        raise Exception("Directory %s doesn't exist" % dirpath)
    return dirpath

def main():
    parser = argparse.ArgumentParser(description='Import source RPM(s) and RPM(s) to koji and tag the builds')
    parser.add_argument('directory', help='path to a directory containing the source RPM(s)'
                                          ' and RPM(s) we want to import')
    parser.add_argument('package_tags', help='comma-separated list of tags for the package(s)')
    parser.add_argument('build_tags', help='comma-separated list of tags for imported build(s)')
    parser.add_argument('--owner', help='owner for the package(s)', default='kojiadmin')
    args = parser.parse_args()

    DEVNULL = open(os.devnull, 'w')

    directory = os.path.abspath(check_dir(args.directory))

    srpms = []
    packages = []
    builds = []
    rpms = []

    for f in glob.glob(os.path.join(directory, '*.rpm')):
        if f.endswith('.src.rpm'):
            srpms.append(f)
            package, build = get_srpm_info(f)
            packages.append(package)
            builds.append(build)
        else:
            rpms.append(f)

    # import the SRPMs
    print('*** Importing SRPMs ***')
    subprocess.check_call(['koji', 'import'] + srpms)
    print()

    # import the RPMS
    print('*** Importing RPMs ***')
    subprocess.check_call(['koji', 'import'] + rpms)
    print()

    # tag packages
    pkg_tags = args.package_tags.split(',')
    for tag in pkg_tags:
        print('*** Tagging packages %s with tag %s' % (' '.join(packages), tag))
        subprocess.check_call(['koji', 'add-pkg', tag, ' '.join(packages), '--owner', args.owner])

    # tag builds
    build_tags = args.build_tags.split(',')
    for tag in build_tags:
        print('*** Tagging builds %s with tag %s' % (' '.join(builds), tag))
        subprocess.check_call(['koji', 'tag-build', tag, ' '.join(builds)])

if __name__ == "__main__":
    main()
