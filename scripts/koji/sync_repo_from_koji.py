#!/bin/env python
from __future__ import print_function
import argparse
import re
import os
import sys
import subprocess
import glob
import shutil
import tempfile
import atexit

RELEASE_VERSIONS = [
    '7.6',
    '8.0',
    '8.1',
    '8.2',
]

DEV_VERSIONS = [
    '8.3'
]

VERSIONS = DEV_VERSIONS + RELEASE_VERSIONS

# Not used, just here as memory and in the unlikely case we might need to update their repos again
DEAD_TAGS = [
    'v7.6-base',
    'v7.6-updates',
    'v7.6-testing',
    'v8.0-base',
    'v8.0-updates',
    'v8.0-testing',
    'v8.1-base',
    'v8.1-updates',
    'v8.1-testing',
]

TAGS = [
    'v8.2-base',
    'v8.2-updates',
    'v8.2-candidates',
    'v8.2-testing',
    'v8.2-ci',
    'v8.2-incoming',
    'v8.2-lab',
    'v8.3-base',
    'v8.3-updates',
    'v8.3-candidates',
    'v8.3-testing',
    'v8.3-ci',
    'v8.3-incoming',
    'v8.3-lab',
]

# tags in which we only keep the latest build for each package
RELEASE_TAGS = [
    'v7.6-base',
    'v8.0-base',
    'v8.1-base',
    'v8.2-base',
]

# Additional "user" tags. For them, repos are generated at a different place.
# Initialized empty: user tags are autodetected based on their name
U_TAGS = []

# Additional V-tags (V stands for "vates" or for "vendor"). For them, repos also are generated at a different place.
# Initialized empty: V-tags are autodetected based on their name
V_TAGS = []

KOJI_ROOT_DIR = '/mnt/koji'

KEY_ID = "3fd3ac9e"

DEVNULL = open(os.devnull, 'w')

def version_from_tag(tag):
    matches = re.match(r'v(\d+\.\d+)', tag)
    return matches.group(1)

def repo_name_from_tag(tag):
    version = version_from_tag(tag)
    name = tag[len("v%s-" % version):]
    if name.startswith('u-') or name.startswith('v-'):
        name = name[2:]
    return name

def sign_rpm(rpm):
    # create temporary work directory
    tmpdir = tempfile.mkdtemp(prefix=rpm)
    current_dir = os.getcwd()

    try:
        os.chdir(tmpdir)

        # download from koji
        subprocess.check_call(['koji', 'download-build', '--debuginfo', '--rpm', rpm])

        # sign: requires a sign-rpm executable or alias in the PATH
        subprocess.check_call(['sign-rpm', rpm], stdout=DEVNULL)

        # import signature
        subprocess.check_call(['koji', 'import-sig', rpm])

    finally:
        # clean up
        os.chdir(current_dir)
        shutil.rmtree(tmpdir)

def write_repo(tag, dest_dir, tmp_root_dir):
    version = version_from_tag(tag)
    major = version.split('.')[0]
    repo_name = repo_name_from_tag(tag)

    # Hack for 7.6 because koji only handles its updates and updates_testing repos:
    if version == '7.6':
        if repo_name == 'testing':
            repo_name = 'updates_testing'
        elif repo_name != 'updates':
            raise Exception("Fatal: koji should not have any changes outside testing and updates for 7.6!")

    path_to_repo = os.path.join(dest_dir, major, version, repo_name)
    path_to_tmp_repo = os.path.join(tmp_root_dir, major, version, repo_name)

    # remove temporary repo if exists
    if os.path.isdir(path_to_tmp_repo):
        shutil.rmtree(path_to_tmp_repo)

    # create empty structure
    print("\n-- Copy the RPMs from %s to %s" % (KOJI_ROOT_DIR, path_to_tmp_repo))
    for d in ['x86_64/Packages', 'Source/SPackages']:
        os.makedirs(os.path.join(path_to_tmp_repo, d))

    print("Link to latest dist-repo: %s" % os.readlink('%s/repos-dist/%s/latest' % (KOJI_ROOT_DIR, tag)))

    # copy RPMs from koji
    for f in glob.glob('%s/repos-dist/%s/latest/x86_64/Packages/*/*.rpm' % (KOJI_ROOT_DIR, tag)):
        shutil.copy(f, os.path.join(path_to_tmp_repo, 'x86_64', 'Packages'))

    # and source RPMs
    for f in glob.glob('%s/repos-dist/%s/latest/src/Packages/*/*.rpm' % (KOJI_ROOT_DIR, tag)):
        shutil.copy(f, os.path.join(path_to_tmp_repo, 'Source', 'SPackages'))

    # generate repodata and sign
    for path in [os.path.join(path_to_tmp_repo, 'x86_64'), os.path.join(path_to_tmp_repo, 'Source')]:
        print("\n-- Generate repodata for %s" % path)
        subprocess.check_call(['createrepo_c', path], stdout=DEVNULL)
        subprocess.check_call(['sign-file', os.path.join(path, 'repodata', 'repomd.xml')], stdout=DEVNULL)

    # Synchronize to our final repository:
    # - add new RPMs
    # - remove RPMs that are not present anymore (for tags in RELEASE_TAGS)
    # - do NOT change the creation nor modification stamps for existing RPMs that have not been modified
    #   (and usually there's no reason why they would have been modified without changing names)
    #   => using -c and omitting -t
    # - sync updated repodata
    print("\n-- Syncing to final repository %s" % path_to_repo)
    if not os.path.exists(path_to_repo):
        os.makedirs(path_to_repo)
    subprocess.check_call(['rsync', '-crlpi', '--delete-after', path_to_tmp_repo + '/', path_to_repo])
    print()
    shutil.rmtree(path_to_tmp_repo)

def sign_unsigned_rpms(tag):
    # get list of RPMs not signed by us by comparing the list that is signed with the full list

    # all RPMs for the tag
    output = subprocess.check_output(['koji', 'list-tagged', tag, '--rpms'])
    rpms = set(output.strip().splitlines())

    # only signed RPMs
    # koji list-tagged v7.6-base --sigs | grep "^3fd3ac9e" | cut -c 10-
    signed_rpms = set()
    output = subprocess.check_output(['koji', 'list-tagged', tag, '--sigs'])
    for line in output.strip().splitlines():
        try:
            key, rpm = line.split(' ')
        except:
            # couldn't unpack values... no signature.
            continue
        if key == KEY_ID:
            signed_rpms.add(rpm)

    # diff and sort
    unsigned_rpms = sorted(list(rpms.difference(signed_rpms)))

    if unsigned_rpms:
        print("\nSigning unsigned RPMs first\n")

    for rpm in unsigned_rpms:
        sign_rpm(rpm + '.rpm')

    for rpm in unsigned_rpms:
        if rpm.endswith('.src'):
            nvr = rpm[:-4]
            # write signed file to koji's own repositories
            subprocess.check_call(['koji', 'write-signed-rpm', KEY_ID, nvr])

def atexit_remove_lock(lock_file):
    os.unlink(lock_file)

def main():
    parser = argparse.ArgumentParser(description='Detect package changes in koji and update repository')
    parser.add_argument('dest_dir', help='root directory of the destination repository')
    parser.add_argument('u_dest_dir', help='root directory of the destination repository for user tags')
    parser.add_argument('v_dest_dir', help='root directory of the destination repository for V-tags')
    parser.add_argument('data_dir', help='directory where the script will write or read data from')
    parser.add_argument('--quiet', action='store_true',
                        help='do not output anything unless there are changes to be considered')
    parser.add_argument('--modify-stable-base', action='store_true',
                        help='allow modifying the base repository of a stable release')
    args = parser.parse_args()
    dest_dir = args.dest_dir
    u_dest_dir = args.u_dest_dir
    v_dest_dir = args.v_dest_dir
    data_dir = args.data_dir
    tmp_root_dir = os.path.join(data_dir, 'tmproot')
    quiet = args.quiet

    lock_file = os.path.join(data_dir, 'lock')

    if os.path.exists(lock_file):
        print("Lock file %s already exists. Aborting." % lock_file)
        return
    else:
        open(lock_file, 'w').close()
        atexit.register(atexit_remove_lock, lock_file)

    global U_TAGS, V_TAGS
    U_TAGS += subprocess.check_output(['koji', 'list-tags', 'v*.*-u-*']).strip().splitlines()
    V_TAGS += subprocess.check_output(['koji', 'list-tags', 'v*.*-v-*']).strip().splitlines()

    def dest_dir_for_tag(tag):
        if tag in U_TAGS:
            return u_dest_dir
        if tag in V_TAGS:
            return v_dest_dir
        return dest_dir

    for version in VERSIONS:
        for tag in TAGS + U_TAGS + V_TAGS:
            if version_from_tag(tag) != version:
                continue

            needs_update = False

            # get current list of packages from koji for this tag
            tag_builds_koji = subprocess.check_output(['koji', 'list-tagged', '--quiet', tag])

            # read latest known list of builds in the tag if exists
            tag_builds_filepath = os.path.join(data_dir, "%s-builds.txt" % tag)
            if os.path.exists(tag_builds_filepath):
                with open(tag_builds_filepath, 'r') as f:
                    tag_builds_txt = f.read()
                    if tag_builds_koji != tag_builds_txt:
                        needs_update = True
            else:
                needs_update = True

            msgs = ["\n*** %s" % tag]
            if needs_update:
                msgs.append("Repository update needed")

                if tag in RELEASE_TAGS and version not in DEV_VERSIONS:
                    if args.modify_stable_base:
                        msgs.append("Modification of base repository for stable release %s " % version
                                    + "allowed through the --modify-stable-base switch.")
                    else:
                        if not quiet:
                            msgs.append("Not modifying base repository for stable release %s..." % version)
                            print('\n'.join(msgs))
                        continue

                print('\n'.join(msgs))

                # sign RPMs in the tag if needed
                sign_unsigned_rpms(tag)

                # export the RPMs from koji
                print ("\n-- Make koji write the repository for tag %s" % tag)
                with_non_latest = [] if tag in RELEASE_TAGS else ['--non-latest']
                sys.stdout.flush()
                subprocess.check_call(['koji', 'dist-repo', tag, '3fd3ac9e',  '--with-src', '--noinherit'] + with_non_latest)

                # write repository to the appropriate destination directory for the tag
                write_repo(tag, dest_dir_for_tag(tag), tmp_root_dir)

                # update data
                with open(tag_builds_filepath, 'w') as f:
                    f.write(tag_builds_koji)
            elif not quiet:
                print('\n'.join(msgs))
                print("Already up to date")

if __name__ == "__main__":
    main()
