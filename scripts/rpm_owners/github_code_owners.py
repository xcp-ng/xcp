#!/usr/bin/env python3

import json
import os
import re
import sys
from contextlib import suppress

import github as gh
from github.Repository import Repository

BRANCHES = ['master', '8.2']
CODEOWNERS = '.github/CODEOWNERS'


def to_gh_team(maintainer: str):
    return 'xcp-ng-rpms/' + re.sub(r'\W+', '-', maintainer.lower())


def create_gh_code_owners(repo: Repository, rpm):
    owners = {rpm['maintainer']}
    if 'OS Platform & Release' not in owners:
        owners.add('OS Platform & Release')
    content = ''
    for owner in owners:
        content += f'* {to_gh_team(owner)}\n'
    for branch in BRANCHES:
        current_content = None
        with suppress(gh.UnknownObjectException):
            current_content = repo.get_contents(CODEOWNERS, branch).decoded_content.decode()  # type: ignore
        if current_content != content:
            repo.create_file(CODEOWNERS, "set team owner", content, branch)

# load the rpm data from the ref file
with open('packages.json') as f:
    rpms = json.load(f)

auth = gh.Auth.Token(os.environ['GITHUB_TOKEN'])
g = gh.Github(auth=auth)
org = g.get_organization('xcp-ng-rpms')

gh_repos = dict((r.name, r) for r in org.get_repos())

# # do we have the same list of repositories than packages?
# missing_repos = set(rpms.keys()) - set(gh_repos.keys())
# print(missing_repos)

# # do we have repos without package?
# missing_pkgs = set(gh_repos.keys()) - set(rpms.keys())
# print(missing_repos)

pkgs = set(gh_repos.keys()).intersection(set(rpms.keys()))
# print(len(pkgs))

for pkg in pkgs:
    print(f'creating {pkg} CODEOWNERS file...', end='', file=sys.stderr)
    repo = gh_repos[pkg]
    rpm = rpms[pkg]
    create_gh_code_owners(repo, rpm)
    print(' done', file=sys.stderr)
