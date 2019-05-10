#!/bin/env python
from __future__ import print_function
import argparse
import os
import subprocess
from github import Github

def main():
    parser = argparse.ArgumentParser(description='Retires a RPM source git repository that is not needed anymore')
    parser.add_argument('name', help='name of repository')
    parser.add_argument('version', help='version of XCP-ng in which the package was retired, in form X.Y, e.g. 8.0')
    parser.add_argument('reason', help='reason for retirement. Start with lowercase letter, no ending dot.')
    parser.add_argument('token_file',
                        help='file containing github authentication token',
                        nargs='?',
                        default=os.path.join(os.path.dirname(os.path.realpath(__file__)), 'github.txt'))
    args = parser.parse_args()
    name = args.name
    version = args.version
    reason = args.reason

    # authenticate to Github
    token = open(args.token_file).read().strip()
    g = Github(token)
    org = g.get_organization('xcp-ng-rpms')
    repo = org.get_repo(args.name)

    readme = """RPM sources for the %s package in XCP-ng (https://xcp-ng.org/).

**This package has been retired in XCP-ng %s.**

Reason: %s.
""" % (name, version, reason)

    os.chdir(args.name)
    subprocess.check_call(['git', 'checkout', 'master'])
    subprocess.check_call(['git', 'pull'])
    subprocess.check_call(['git', 'rm', '*'])
    open('README.md', 'w').write(readme)
    subprocess.check_call(['git', 'add', 'README.md'])
    open('.retired', 'w').close()
    subprocess.check_call(['git', 'add', '.retired'])
    subprocess.check_call(['git', 'commit', '-m', 'This package has been retired in XCP-ng %s' % version])
    subprocess.check_call(['git', 'push'])

    # update repository description
    repo.edit(name, description="[retired in %s] %s" % (version, repo.description))

if __name__ == "__main__":
    main()
