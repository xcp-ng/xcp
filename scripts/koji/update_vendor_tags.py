#!/bin/env python
from __future__ import print_function
import argparse
import subprocess
import json
import os
import re

DEVNULL = open(os.devnull, 'w')

XS_buildhosts = [
    '1b68968c4e4e',
    '1f202679a186',
    'ebbce0ae9691',
    'f1152ddb2921',
    'f7d02093adae',
    'ba090b49143f',
    'a50e0282e69b',
    'eff2d405bb69',
    'b10e2867ff51',
]

XCPNG_buildhosts = [
    'koji.xcp-ng.org'
]

ALLOWED_TAGS = [
    'built-by-xcp-ng',
    'built-by-xs',
    'built-by-centos',
    'built-by-epel',
    'built-by-linbit'
]

def build_has_tag(build, tag):
    out = subprocess.check_output(['koji', 'buildinfo', build])
    matches = re.search(r'^Tags: .*\b%s\b' % tag, out, re.MULTILINE)
    return matches is not None

def update_vendor_tag_for_build(build, is_bootstrap=False):
    # get the first binary RPM found for the build
    output = subprocess.check_output(['koji', 'buildinfo', build])
    srpm_path = ""
    rpm_path = ""
    for line in output.splitlines():
        first_element = line.split()[0]
        if re.match('.+/src/.+\.src\.rpm', first_element):
            srpm_path = ""
        if re.match('.+\.rpm', first_element):
            rpm_path = first_element

    if not rpm_path:
        if is_bootstrap:
            if not srpm_path:
                raise Exception("No SRPM found for build %s" % build)
            # accept to use the SRPM instead of the missing RPM
            rpm_path = srpm_path
        else:
            raise Exception("No RPM found for build %s" % build)

    # get vendor information
    output = subprocess.check_output(['rpm', '-qp', rpm_path, '--qf', '%{vendor};;%{buildhost}'], stderr=DEVNULL)
    vendor, buildhost = output.split(';;')
    package = re.search('/packages/([^/]+)/', rpm_path).group(1)

    tag = None
    if buildhost in XS_buildhosts:
        tag = 'built-by-xs'
    elif buildhost in XCPNG_buildhosts:
        tag = 'built-by-xcp-ng'
    elif vendor == 'Citrix Systems, Inc.':
        tag = 'built-by-xs'
    elif vendor in ('XCP-ng', 'XCP-ng community'):
        tag = 'built-by-xcp-ng'
    elif vendor == 'CentOS':
        tag = 'built-by-centos'
    elif vendor == 'Fedora Project':
        tag = 'built-by-epel'

    if tag is None and is_bootstrap:
        tag = 'built-by-xcp-ng'

    print("%s: %s, %s => %s" % (os.path.basename(rpm_path), vendor, buildhost, tag))

    if tag is None:
        # maybe the build already has a tag, in which case we won't do anything
        for allowed_tag in ALLOWED_TAGS:
            if build_has_tag(build, allowed_tag):
                print("Build %s already has tag %s." % (build, allowed_tag))
                return
        # else raise
        raise Exception("Vendor and buildhost unknown: %s, %s" % (vendor, buildhost))

    subprocess.check_call(['koji', 'add-pkg', tag, package, '--owner=kojiadmin']) # otherwise we can't tag the build
    # check if build already has the tag, else it will fail
    if not build_has_tag(build, tag):
        subprocess.check_call(['koji', 'tag-build', tag, build])
    else:
        print("Build %s already has tag %s." % (build, tag))

def main():
    parser = argparse.ArgumentParser(description='Update vendor tags for builds without one')
    parser.add_argument('data_dir', help='directory where the script will write or read data from')
    parser.add_argument('--bootstrap', action='store_true',
                        help='accepts unknown vendors and builds without a binary RPM')
    parser.add_argument('--quiet', action='store_true',
                        help='do not output anything unless there are changes to be considered')
    args = parser.parse_args()
    quiet = args.quiet

    data_dir = os.path.join(args.data_dir, 'vendor_tags_update')
    if os.path.isdir(args.data_dir) and not os.path.exists(data_dir):
        print("Creating %s" % data_dir)
        os.mkdir(os.path.join(data_dir))

    # results in a dict similar to this: {"id": 2690, "ts": 1543249294.02143}
    last_event = json.loads(subprocess.check_output(['koji', 'call', 'getLastEvent']).replace("'", '"'))

    # read last known event from our data directory
    last_sync_event_filepath = os.path.join(data_dir, 'last_sync_event')

    need_update = True
    if os.path.exists(last_sync_event_filepath):
        with open(last_sync_event_filepath) as f:
            last_sync_event = json.loads(f.read())

        if last_sync_event == last_event:
            need_update = False
        else:
            timestamp = last_sync_event['ts']
    else:
        timestamp = 0 # first update ever


    if not need_update:
        if not quiet:
            print("No update needed.")
        return

    # get the list of builds since last event
    output = subprocess.check_output(['koji', 'list-builds', '--quiet', '--state=COMPLETE',
                                      '--type=rpm', '--after=%s' % timestamp])

    for line in output.splitlines():
        build = line.split()[0]
        update_vendor_tag_for_build(build, args.bootstrap)

    # store last update event info
    with open(last_sync_event_filepath, 'w') as f:
        f.write(json.dumps(last_event))

if __name__ == "__main__":
    main()
