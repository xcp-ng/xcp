#!/usr/bin/env python3
from __future__ import print_function

import argparse
import os
import subprocess

from github import Github


def main():
    parser = argparse.ArgumentParser(description='Creates a git repository in current directory for RPM spec file and'
                                                 ' sources')
    parser.add_argument('name', help='name of repository')
    parser.add_argument('--local',
                        help='do not create github repository',
                        action='store_true')
    parser.add_argument('token_file',
                        help='file containing github authentication token',
                        nargs='?',
                        default=os.path.join(os.path.dirname(os.path.realpath(__file__)), 'github.txt'))
    args = parser.parse_args()

    if not args.local:
        # authenticate to Github
        with open(args.token_file) as f:
            token = f.read().strip()
        g = Github(token)

        # create repository
        org = g.get_organization('xcp-ng-rpms')
        org.create_repo(args.name, "RPM sources for %s" % args.name)

    # initial commit to master
    gitignore = """BUILD
BUILDROOT
RPMS
SRPMS
"""
    readme = """RPM sources for the %s package in XCP-ng (https://xcp-ng.org/).

Make sure to have `git-lfs` installed before cloning. It is used for handling source archives separately.

Branches:
* `master` contains sources for the next `x.y` release of XCP-ng.
* `x.y` (e.g. `7.5`) contains sources for the `x.y` release of XCP-ng, with their bugfix and/or security updates.
* `XS-x.y` (e.g. `XS-7.5`), when they exist, contain sources from the `x.y` release of XenServer, with trademarked
  or copyrighted material stripped if needed.

Built RPMs and source RPMs are available on https://updates.xcp-ng.org.
""" % args.name
    if args.local:
        subprocess.check_call(['git', 'init', args.name])
        subprocess.check_call(['git', '-C', args.name,
                               'remote', 'add', 'origin',
                               'https://github.com/xcp-ng-rpms/%s.git' % args.name])
    else:
        subprocess.check_call(['git', 'clone', 'https://github.com/xcp-ng-rpms/%s.git' % args.name])
    os.chdir(args.name)
    if "git@github.com" not in subprocess.check_output(
            ['git', 'remote', 'get-url', '--push', 'origin'],
            universal_newlines=True):
        # only set if pushInsteadOf was not configured
        subprocess.check_call(['git', 'remote', 'set-url', '--push', 'origin',
                               'git@github.com:xcp-ng-rpms/%s.git' % args.name])
    with open('.gitignore', 'w') as f:
        f.write(gitignore)
    subprocess.check_call(['git', 'add', '.gitignore'])
    with open('README.md', 'w') as f:
        f.write(readme)
    subprocess.check_call(['git', 'add', 'README.md'])
    subprocess.check_call(['git', 'lfs', 'install'])
    subprocess.check_call(['git', 'lfs', 'track', '*.gz'])
    subprocess.check_call(['git', 'lfs', 'track', '*.bz2'])
    subprocess.check_call(['git', 'lfs', 'track', '*.xz'])
    subprocess.check_call(['git', 'lfs', 'track', '*.zip'])
    subprocess.check_call(['git', 'lfs', 'track', '*.tar'])
    subprocess.check_call(['git', 'lfs', 'track', '*.tgz'])
    subprocess.check_call(['git', 'lfs', 'track', '*.tbz'])
    subprocess.check_call(['git', 'add', '.gitattributes'])
    subprocess.check_call(['git', 'commit', '-s', '-m', 'Initial commit'])
    if not args.local:
        subprocess.check_call(['git', 'push'])

if __name__ == "__main__":
    main()
