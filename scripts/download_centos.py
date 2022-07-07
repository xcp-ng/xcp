#!/usr/bin/env python3
import argparse
import os
import sys
import glob
import subprocess
import csv
import shutil

def build_url(path):
    if path.startswith('7/'):
        return "http://mirror.centos.org/centos/" + path
    else:
        return "http://vault.centos.org/" + path

def download_rpm(rpm, downloaddir, vendor, local_centos, local_epel):
    if vendor == "CentOS":
        if local_centos is not None:
            shutil.copy2(os.path.join(local_centos, rpm), downloaddir)
            print("%s: copied from %s" % (rpm, local_centos))
            return
        else:
            for version in ['7.2.1511', '7.3.1611', '7.4.1708', '7.5.1804', '7']:
                for repodir in ['os', 'updates']:
                    url = build_url('%s/%s/x86_64/Packages/%s' % (version, repodir, rpm))
                    try:
                        subprocess.check_call(['wget', '-q', '-O', os.path.join(downloaddir, rpm), url])
                        print("%s: fetched from %s" % (rpm, url))
                        return
                    except:
                        pass
    if vendor == "Fedora Project":
        if local_epel is not None:
            shutil.copy2(os.path.join(local_epel, rpm), downloaddir)
            print("%s: copied from %s" % (rpm, local_epel))
            return
        else:
            url = 'http://mirror.in2p3.fr/pub/epel/7/x86_64/Packages/%s/%s' % (rpm[0], rpm)
            try:
                subprocess.check_call(['wget', '-q', '-O', os.path.join(downloaddir, rpm), url])
                print("%s: fetched from %s" % (rpm, url))
                return
            except:
                pass

    print("%s: NOT FOUND" % rpm)
    sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description='Looks for missing RPMs based on their SRPMs and downloads if it can')
    parser.add_argument('rpmdir', help='directory that contains the RPMs')
    parser.add_argument('srpmdir', help='directory that contains the source RPMs')
    parser.add_argument('centos_rpms_and_srpms',
                        help='file that contains a list of x86_64 and noarch packages with their source RPM')
    parser.add_argument('downloaddir', help='where to download the missing RPMs to')
    parser.add_argument('--local-centos', help='path to a local directory containing all the CentOS RPMs')
    parser.add_argument('--local-epel', help='path to a local directory containing all the EPEL RPMs')
    args = parser.parse_args()

    DEVNULL = open(os.devnull, 'w')

    rpmdir = os.path.abspath(args.rpmdir)
    srpmdir = os.path.abspath(args.srpmdir)
    downloaddir = os.path.abspath(args.downloaddir)
    if not os.path.isdir(downloaddir):
        os.makedirs(downloaddir)

    local_centos = None
    local_epel = None
    if args.local_centos:
        local_centos=os.path.abspath(args.local_centos)
    if args.local_epel:
        local_epel=os.path.abspath(args.local_epel)

    srpms_to_rpms = {}
    with open(args.centos_rpms_and_srpms, 'rb') as csvfile:
        for row in csv.reader(csvfile, delimiter=','):
            if row[1] not in srpms_to_rpms:
                srpms_to_rpms[row[1]] = []
            srpms_to_rpms[row[1]].append(row[0])

    srpms = {}
    for filepath in sorted(glob.glob(os.path.join(srpmdir, '*.src.rpm'))):
        filename = os.path.basename(filepath)

        vendor = subprocess.check_output(['rpm', '-qp', filepath, '--qf', '%{vendor}'], stderr=DEVNULL)
        if vendor not in ("CentOS", "Fedora Project"):
            print("Skipping %s due to unknown vendor %s" % (filename, vendor))
            continue

        print("\n*** %s" % filename)
        if filename not in srpms_to_rpms:
            print("Warning: SRPM not found in reference file")
        else:
            for rpm in srpms_to_rpms[filename]:
                if os.path.exists(os.path.join(rpmdir, rpm)):
                    print("%s: OK" % rpm)
                else:
                    if os.path.exists(os.path.join(downloaddir, rpm)):
                        print("%s: already downloaded" % rpm)
                    else:
                        download_rpm(rpm, downloaddir, vendor, local_centos, local_epel)

if __name__ == "__main__":
    main()
