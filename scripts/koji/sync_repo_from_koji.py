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
    '7.6'
]

TAGS = [
    '7.6',
    '7.6-updates',
    '7.6-updates_testing',
    '7.6-extras',
    '7.6-extras_testing'
]

KOJI_ROOT_DIR = '/mnt/koji'

KEY_ID = "3fd3ac9e"

def version_from_tag(tag):
    matches = re.match('\d+\.\d+', tag)
    return matches.group(0)

def repo_name_from_tag(tag):
    version = version_from_tag(tag)
    if tag == version:
        return 'base'
    else:
        return tag[len(version)+1:]

def sign_rpm(rpm):
    # create temporary work directory
    tmpdir = tempfile.mkdtemp(prefix=rpm)
    current_dir = os.getcwd()

    try:
        os.chdir(tmpdir)

        # download from koji
        subprocess.check_call(['koji', 'download-build', '--rpm', rpm])

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
    path_to_repo = os.path.join(dest_dir, 'repo', major, version, repo_name)

    # Temporary hack to write 7.6 packages in a different directory,
    # because the main source for 7.6 packages is not koji yet and we don't
    # want to override the repo.
    path_to_repo = path_to_repo.replace('/7.6/', '/7.6-test/')

    print(path_to_repo)

    # remove repo if exists
    if os.path.isdir(path_to_repo):
        shutil.rmtree(path_to_repo)

    # create empty structure
    for d in ['x86_64/Packages', 'Source/SPackages']:
        os.makedirs(os.path.join(path_to_repo, d))

    # copy RPMs from koji
    for f in glob.glob('%s/repos-dist/%s/latest/x86_64/Packages/*/*.rpm' % (KOJI_ROOT_DIR, tag)):
        shutil.copy(f, os.path.join(path_to_repo, 'x86_64', 'Packages'))

    # and source RPMs
    for f in glob.glob('%s/repos-dist/%s/latest/src/Packages/*/*.rpm' % (KOJI_ROOT_DIR, tag)):
        shutil.copy(f, os.path.join(path_to_repo, 'Source', 'SPackages'))

    # generate repodata and sign
    for path in [os.path.join(path_to_repo, 'x86_64'), os.path.join(path_to_repo, 'Source')]:
        subprocess.check_call(['createrepo_c', path])
        subprocess.check_call(['sign-file', os.path.join(path, 'repodata', 'repomd.xml')])

def sign_unsigned_rpms(tag):
    # get list of RPMs not signed by us by comparing the list that is signed with the full list

    # all RPMs for the tag
    output = subprocess.check_output(['koji', 'list-tagged', tag, '--rpms'])
    rpms = set(output.strip().splitlines())

    # only signed RPMs
    # koji list-tagged 7.6 --sigs | grep "^3fd3ac9e" | cut -c 10-
    signed_rpms = set()
    output = subprocess.check_output(['koji', 'list-tagged', tag, '--sigs'])
    for line in output.strip().splitlines():
        key, rpm = line.split(' ')
        if key == KEY_ID:
            signed_rpms.add(rpm)

    # diff and sort
    unsigned_rpms = sorted(list(rpms.difference(signed_rpms)))

    if unsigned_rpms:
        print("\nSigning unsigned RPMs first\n")

    for rpm in unsigned_rpms:
        sign_rpm(rpm + '.rpm')


def main():
    parser = argparse.ArgumentParser(description='Detect package changes in koji and update repository')
    parser.add_argument('dest_dir', help='root directory of the destination repository')
    parser.add_argument('data_dir', help='directory where the script will write or read data from')
    args = parser.parse_args()
    dest_dir = args.dest_dir
    data_dir = args.data_dir

    for version in VERSIONS:
        for tag in TAGS:
            print("\n*** %s" % tag)
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

            if needs_update:
                print("Repository update needed")

                # sign RPMs in the tag if needed
                sign_unsigned_rpms(tag)

                # export the RPMs from koji
                subprocess.check_call(['koji', 'dist-repo', tag, '--with-src', '--noinherit'])

                # write repo in work directory (we'll sync everything at the end)
                write_repo(tag, dest_dir)

                # update data
                with open(tag_builds_filepath, 'w') as f:
                    f.write(tag_builds_koji)
            else:
                print("Already up to date")

if __name__ == "__main__":
    main()
