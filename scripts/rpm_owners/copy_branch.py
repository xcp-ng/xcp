#!/usr/bin/env python3

import argparse
import json
import os

import github as gh
from github.Repository import Repository


def copy_branch(repo: Repository, source: str, dest: str) -> bool:
    source_branch = repo.get_branch(source)
    try:
        repo.create_git_ref(ref=f'refs/heads/{dest}', sha=source_branch.commit.sha)
    except Exception as e:
        print(f"Error creating branch {dest} in {repo.name}: {e}")
        return False

    return True

parser = argparse.ArgumentParser(description="Copy a branch to another branch in all the active rpm repositories")
parser.add_argument("source", help="Source branch name")
parser.add_argument("dest", help="Destination branch name")
args = parser.parse_args()

# load the rpm data from the ref file
with open('packages.json') as f:
    rpms = json.load(f)

auth = gh.Auth.Token(os.environ['GITHUB_TOKEN'])
g = gh.Github(auth=auth)
org = g.get_organization('xcp-ng-rpms')

gh_repos = dict((r.name, r) for r in org.get_repos())

pkgs = set(gh_repos.keys()).intersection(set(rpms.keys()))

ok = True
for pkg in pkgs:
    repo = gh_repos[pkg]
    ok &= copy_branch(repo, args.source, args.dest)
if not ok:
    exit(1)
