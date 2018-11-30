#!/bin/env python
from __future__ import print_function
import argparse
import csv
import rpm
import subprocess
import os
import glob
import shutil
import io

def get_srpm_info(srpmpath):
    return subprocess.check_output(['rpm', '-qp', srpmpath, '--qf', '%{name};;%{evr}']).split(';;')

def compare_evrs(evr1, evr2):
    # returns -1 if evr1<evr2, 0 if equal, 1 if >...
    p = subprocess.Popen(['rpmdev-vercmp', evr1, evr2], stdout=subprocess.PIPE)
    output, _ = p.communicate()
    if " < " in output:
        return -1
    if " > " in output:
        return 1
    if " == " in output:
        return 0
    raise Exception("Unexpected output from rpmdev-vercmp: %s" % output)

def path_for_srpm(rpmdir, srpmfilename):
    return os.path.join(rpmdir, 'SRPMS', srpmfilename)

def check_dir(dirpath):
    if not os.path.isdir(dirpath):
        raise Exception("Directory %s doesn't exist" % dirpath)
    return dirpath

def main():
    parser = argparse.ArgumentParser(description='Starting from a source RPM, looks for the latest version '
                                                 'and copies it to the destination directory')
    parser.add_argument('source_rpm', help='path to a source RPM')
    parser.add_argument('rpmdir', help='directory that contains the SRPMs and RPMs we\'ll '
                                       'be searching for newer versions')
    parser.add_argument('rpms_and_srpms',
                        help='file that contains a list of x86_64 and noarch packages with their source RPM')
    parser.add_argument('downloaddir', help='where to download the newer RPMs to')
    args = parser.parse_args()

    DEVNULL = open(os.devnull, 'w')

    rpmdir = os.path.abspath(check_dir(args.rpmdir))
    downloaddir = os.path.abspath(check_dir(args.downloaddir))


    # get package name from source RPM, e.g. findutils for findutils-4.5.11-5.el7.src.rpm
    filename = os.path.basename(args.source_rpm)
    name, evr = get_srpm_info(args.source_rpm)

    print("Searching for newer version of %s (%s)" % (filename, name))

    srpms_to_rpms = {}
    srpm_evrs = {}
    with open(args.rpms_and_srpms, 'rb') as csvfile:
        for row in csv.reader(csvfile, delimiter=','):
            srpm_filename = row[1]
            if srpm_filename not in srpms_to_rpms:
                if srpm_filename.startswith(name + "-"):
                    package_name, srpm_evr = get_srpm_info(path_for_srpm(rpmdir, srpm_filename))
                    # the "if" test above allowed filtering out most packages but is not 100% precise
                    if package_name != name:
                        continue
                    srpms_to_rpms[srpm_filename] = [row[0]]
                    srpm_evrs[srpm_filename] = srpm_evr
            else:
                srpms_to_rpms[srpm_filename].append(row[0])

    if filename not in srpms_to_rpms:
        print("Warning: source RPM %s is missing from the reference." % filename)
        srpm_evrs.append(filename, evr)

    latest_srpm = filename
    for srpm_filename, srpm_evr in srpm_evrs.iteritems():
        if compare_evrs(srpm_evr, srpm_evrs[latest_srpm]) > 0:
            latest_srpm = srpm_filename

    print(latest_srpm)

    if latest_srpm != filename:
        print("Newer version found: %s" % latest_srpm)
        # copy SRPM
        srpm_destination = os.path.join(downloaddir, 'Source', 'SPackages')
        if not os.path.isdir(srpm_destination):
            os.makedirs(srpm_destination)
        shutil.copy(path_for_srpm(rpmdir, latest_srpm), os.path.join(srpm_destination, latest_srpm))
        # copy all RPMs too
        rpm_destination = os.path.join(downloaddir, 'x86_64', 'Packages')
        if not os.path.isdir(rpm_destination):
            os.makedirs(rpm_destination)
        for rpm_filename in srpms_to_rpms[latest_srpm]:
            print("-> %s" % rpm_filename)
            shutil.copy(os.path.join(rpmdir, rpm_filename), os.path.join(rpm_destination, rpm_filename))


if __name__ == "__main__":
    main()
