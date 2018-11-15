#!/bin/env python
from __future__ import print_function
import argparse
import re
import os
import subprocess
import glob
import shutil

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

def version_from_tag(tag):
    matches = re.match('\d+\.\d+', tag)
    return matches.group(0)

def repo_name_from_tag(tag):
    version = version_from_tag(tag)
    if tag == version:
        return 'base'
    else:
        return tag[len(version)+1:]

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

    # generate repodata
    subprocess.check_call(['createrepo_c', os.path.join(path_to_repo, 'x86_64')])
    subprocess.check_call(['createrepo_c', os.path.join(path_to_repo, 'Source')])

    # TODO: sign repomd.xml


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
                # export the RPMs from koji
                # FIXME: remove the --allow-missing-signatures option
                subprocess.check_call(['koji', 'dist-repo', tag, '--allow-missing-signatures', '--with-src', '--noinherit'])

                # write repo in work directory (we'll sync everything at the end)
                write_repo(tag, dest_dir)

                # update data
                with open(tag_builds_filepath, 'w') as f:
                    f.write(tag_builds_koji)
            else:
                print("Already up to date")

if __name__ == "__main__":
    main()
