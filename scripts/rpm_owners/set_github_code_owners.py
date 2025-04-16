#!/usr/bin/env python3

import argparse
import difflib
import json
import os
import re
import sys
from contextlib import suppress

import github as gh
from github.Repository import Repository

BRANCHES = ['master']
CODEOWNERS = '.github/CODEOWNERS'


def to_gh_team(maintainer: str):
    return '@xcp-ng-rpms/' + re.sub(r'\W+', '-', maintainer.lower())


def diff(current, expected):
    return '\n'.join(
        difflib.unified_diff(
            current.splitlines() if current is not None else [],
            expected.splitlines(),
            f'current/{CODEOWNERS}',
            f'expected/{CODEOWNERS}',
            lineterm='',
        )
    )


def set_gh_code_owners(repo: Repository, rpm, force: bool) -> bool:
    owners = [rpm['maintainer']]
    # make sure the platform team is owner of all the repositories
    if 'OS Platform & Release' not in owners:
        owners.append('OS Platform & Release')
    content = ''
    for owner in owners:
        content += f'* {to_gh_team(owner)}\n'
    ok = True
    for branch in BRANCHES:
        current_content = None
        with suppress(gh.UnknownObjectException):
            current_content = repo.get_contents(CODEOWNERS, branch).decoded_content.decode()  # type: ignore
        if current_content is None or (force and current_content != content):
            action = "creating" if current_content is None else "updating"
            print(f'{action} {pkg} CODEOWNERS file in {branch}...', end='', file=sys.stderr)
            repo.create_file(CODEOWNERS, "set team owner", content, branch)
            print(' done', file=sys.stderr)
        elif current_content == content:
            print(f'{pkg} CODEOWNERS is already OK in {branch}', file=sys.stderr)
        else:
            print(f'error: {pkg} CODEOWNERS is not synced in {branch}', file=sys.stderr)
            print(diff(current_content, content))
            ok = False
    return ok


parser = argparse.ArgumentParser(
    description="Set the code owner for the rpm repositories based on the packages.json file"
)
parser.add_argument('--force', help="Set the CODEOWNERS even if the file already exists", action='store_true')
args = parser.parse_args()

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

ok = True
for pkg in pkgs:
    repo = gh_repos[pkg]
    rpm = rpms[pkg]
    ok &= set_gh_code_owners(repo, rpm, args.force)
if not ok:
    exit(1)
