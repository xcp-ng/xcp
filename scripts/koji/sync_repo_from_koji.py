#!/bin/env python
from __future__ import print_function
import argparse
import re
import os
import subprocess
import glob
import shutil
import tempfile

VERSIONS = [
    '7.6',
]

DEV_VERSIONS = [
]

TAGS = [
    'v7.6-base',
    'v7.6-updates',
    'v7.6-testing',
]

# tags in which we only keep the latest build for each package
RELEASE_TAGS = [
    'v7.6-base',
]

KOJI_ROOT_DIR = '/mnt/koji'

KEY_ID = "3fd3ac9e"

def version_from_tag(tag):
    matches = re.match(r'v(\d+\.\d+)', tag)
    return matches.group(1)

def repo_name_from_tag(tag):
    version = version_from_tag(tag)
    return tag[len("v%s-" % version):]

def sign_rpm(rpm):
    # create temporary work directory
    tmpdir = tempfile.mkdtemp(prefix=rpm)
    current_dir = os.getcwd()

    try:
        os.chdir(tmpdir)

        # download from koji
        subprocess.check_call(['koji', 'download-build', '--debuginfo', '--rpm', rpm])

        # sign: requires a sign-rpm executable or alias in the PATH
        subprocess.check_call(['sign-rpm', rpm])

        # import signature
        subprocess.check_call(['koji', 'import-sig', rpm])

    finally:
        # clean up
        os.chdir(current_dir)
        shutil.rmtree(tmpdir)

def sign_file(filepath):
    subprocess.check_call('sign-file', filepath)

def write_repo(tag, dest_dir):
    version = version_from_tag(tag)
    major = version.split('.')[0]
    repo_name = repo_name_from_tag(tag)
    path_to_repo = os.path.join(dest_dir, major, version, repo_name)

    # Temporary hack to write 7.6 packages in a different directory,
    # because the main source for 7.6 packages is not koji yet and we don't
    # want to override the repo.
    path_to_repo = path_to_repo.replace('/7.6/', '/7.6-test/')

    path_to_tmp_repo = path_to_repo + '-tmp'

    print(path_to_repo)

    # remove temporary repo if exists
    if os.path.isdir(path_to_tmp_repo):
        shutil.rmtree(path_to_tmp_repo)

    # create empty structure
    print("\n-- Copy the RPMs from %s to %s" % (KOJI_ROOT_DIR, path_to_tmp_repo))
    for d in ['x86_64/Packages', 'Source/SPackages']:
        os.makedirs(os.path.join(path_to_tmp_repo, d))

    # copy RPMs from koji
    for f in glob.glob('%s/repos-dist/%s/latest/x86_64/Packages/*/*.rpm' % (KOJI_ROOT_DIR, tag)):
        shutil.copy(f, os.path.join(path_to_tmp_repo, 'x86_64', 'Packages'))

    # and source RPMs
    for f in glob.glob('%s/repos-dist/%s/latest/src/Packages/*/*.rpm' % (KOJI_ROOT_DIR, tag)):
        shutil.copy(f, os.path.join(path_to_tmp_repo, 'Source', 'SPackages'))

    # Synchronize to our final repository:
    # - add new RPMs
    # - remove RPMs that are not present anymore (for tags in RELEASE_TAGS)
    # - do NOT change the creation nor modification stamps for existing RPMs that have not been modified
    #   (and usually there's no reason why they would have been modified without changing names)
    #   => using -c and omitting -t
    print("\n-- Syncing to final repository %s" % path_to_repo)
    if not os.path.exists(path_to_repo):
        os.makedirs(path_to_repo)
    subprocess.check_call(['rsync', '-crlpvP', '--exclude=repodata/', '--delete-after',
                           path_to_tmp_repo + '/', path_to_repo])
    print()
    shutil.rmtree(path_to_tmp_repo)

    # generate repodata and sign
    for path in [os.path.join(path_to_repo, 'x86_64'), os.path.join(path_to_repo, 'Source')]:
        print("\n-- Generate repodata for %s" % path)
        subprocess.check_call(['createrepo_c', path])
        subprocess.check_call(['sign-file', os.path.join(path, 'repodata', 'repomd.xml')])

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

def main():
    parser = argparse.ArgumentParser(description='Detect package changes in koji and update repository')
    parser.add_argument('dest_dir', help='root directory of the destination repository')
    parser.add_argument('data_dir', help='directory where the script will write or read data from')
    parser.add_argument('--modify-stable-base', action='store_true',
                        help='allow modifying the base repository of a stable release')
    args = parser.parse_args()
    dest_dir = args.dest_dir
    data_dir = args.data_dir

    for version in VERSIONS:
        for tag in TAGS:
            if version_from_tag(tag) != version:
                continue

            print("\n*** %s" % tag)

            if tag in RELEASE_TAGS and version not in DEV_VERSIONS:
                if args.modify_stable_base:
                    print("Modification of base repository for stable release %s " % version
                          + "allowed through the --modify-stable-base switch.")
                else:
                    print("Not modifying base repository for stable release %s..." % version)
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

            if needs_update:
                print("Repository update needed")

                # sign RPMs in the tag if needed
                sign_unsigned_rpms(tag)

                # export the RPMs from koji
                print ("\n-- Make koji write the repository for tag %s" % tag)
                with_non_latest = [] if tag in RELEASE_TAGS else ['--non-latest']
                subprocess.check_call(['koji', 'dist-repo', tag, '3fd3ac9e',  '--with-src', '--noinherit'] + with_non_latest)

                # write repository to dest_dir
                write_repo(tag, dest_dir)

                # update data
                with open(tag_builds_filepath, 'w') as f:
                    f.write(tag_builds_koji)
            else:
                print("Already up to date")

if __name__ == "__main__":
    main()
