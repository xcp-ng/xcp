#!/usr/bin/env python2
from __future__ import print_function
import argparse
import os
import subprocess
import re

def check_dir(dirpath):
    if not os.path.isdir(dirpath):
        raise Exception("Directory %s doesn't exist" % dirpath)
    return dirpath

def check_git_repo(dirpath):
    cwd = os.getcwd()
    os.chdir(dirpath)
    # check that the working copy is a working directory and is clean
    try:
        subprocess.check_call(['git', 'diff-index', '--quiet',  'HEAD', '--'])
        ret = True
    except:
        ret = False

    os.chdir(cwd)
    return ret

def get_repo_and_commit_info(dirpath):
    cwd = os.getcwd()
    os.chdir(dirpath)

    remote = subprocess.check_output(['git', 'config', '--get', 'remote.origin.url']).strip()

    # We want the exact hash for accurate build history
    hash = subprocess.check_output(['git', 'rev-parse', 'HEAD']).strip()

    os.chdir(cwd)
    return remote, hash

def koji_url(remote, hash):
    if remote.startswith('git@'):
        remote = re.sub(r'git@(.+):', r'git+https://\1/', remote)
    elif remote.startswith('https://'):
        remote = 'git+' + remote
    else:
        raise Exception("Unrecognized remote URL")
    return remote + "?#" + hash

def main():
    parser = argparse.ArgumentParser(description='Build a package or chain-build several from local git repos for RPM sources')
    parser.add_argument('target', help='Koji target for the build')
    parser.add_argument('git_repos', nargs='+',
                        help='local path to one or more git repositories. If several are provided, '
                             'a chained build will be started in the order of the arguments')
    parser.add_argument('--scratch', action="store_true", help='Perform scratch build')
    parser.add_argument('--nowait', action="store_true", help='Do not wait for the build to end')
    args = parser.parse_args()

    target = args.target
    git_repos = [os.path.abspath(check_dir(d)) for d in args.git_repos]
    is_scratch = args.scratch
    is_nowait = args.nowait

    if len(git_repos) > 1 and is_scratch:
        parser.error("--scratch is not compatible with chained builds.")

    for d in git_repos:
        if not check_git_repo(d):
            parser.error("%s is not in a clean state (or is not a git repository)." % d)

    if len(git_repos) == 1:
        remote, hash = get_repo_and_commit_info(git_repos[0])
        url = koji_url(remote, hash)
        command = ['koji', 'build'] + (['--scratch'] if is_scratch else []) + [target, url] + (['--nowait'] if is_nowait else [])
        subprocess.check_call(['echo'] + command)
        subprocess.check_call(command)
    else:
        urls = []
        for d in git_repos:
            remote, hash = get_repo_and_commit_info(d)
            urls.append(koji_url(remote, hash))
        command = ['koji', 'chain-build', target] + (' : '.join(urls)).split(' ') +  (['--nowait'] if is_nowait else [])
        subprocess.check_call(['echo'] + command)
        subprocess.check_call(command)

if __name__ == "__main__":
    main()
