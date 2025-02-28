#!/usr/bin/env python3
import argparse
import os
import subprocess
import re
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from specfile import Specfile

TIME_FORMAT = '%Y-%m-%d-%H-%M-%S'

@contextmanager
def cd(dir):
    """Change to a directory temporarily. To be used in a with statement"""
    prevdir = os.getcwd()
    os.chdir(dir)
    try:
        yield os.path.realpath(dir)
    finally:
        os.chdir(prevdir)

def check_dir(dirpath):
    if not os.path.isdir(dirpath):
        raise Exception("Directory %s doesn't exist" % dirpath)
    return dirpath

def check_git_repo(dirpath):
    with cd(dirpath):
        # check that the working copy is a working directory and is clean
        try:
            subprocess.check_call(['git', 'diff-index', '--quiet',  'HEAD', '--'])
            ret = True
        except:
            ret = False
    return ret

def get_repo_and_commit_info(dirpath):
    with cd(dirpath):
        remote = subprocess.check_output(['git', 'config', '--get', 'remote.origin.url']).decode().strip()
        # We want the exact hash for accurate build history
        hash = subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode().strip()
    return remote, hash

def koji_url(remote, hash):
    if remote.startswith('git@'):
        remote = re.sub(r'git@(.+):', r'git+https://\1/', remote)
    elif remote.startswith('https://'):
        remote = 'git+' + remote
    else:
        raise Exception("Unrecognized remote URL")
    return remote + "?#" + hash

@contextmanager
def local_branch(branch):
    prev_branch = subprocess.check_output(['git', 'branch', '--show-current']).strip()
    subprocess.check_call(['git', 'checkout', '-b', branch])
    try:
        yield branch
    finally:
        subprocess.check_call(['git', 'checkout', prev_branch])
        subprocess.check_call(['git', 'branch', '-D', branch])

def is_old_branch(b):
    branch_time = datetime.strptime(b.split('/')[-1], TIME_FORMAT)
    return branch_time < datetime.now() - timedelta(hours=3)

def clean_old_branches(git_repo):
    with cd(git_repo):
        subprocess.check_call(['git', 'fetch'])
        remote_branches = subprocess.check_output(['git', 'branch', '-rl', 'origin/koji/test/*/*']).decode().splitlines()
        remote_branches = [b.strip()[len('origin/'):] for b in remote_branches]
        old_branches = [b for b in remote_branches if is_old_branch(b)]
        if old_branches:
            print("removing outdated remote branch(es)", flush=True)
            subprocess.check_call(['git', 'push', '--delete', 'origin'] + old_branches)

def push_bumped_release(git_repo, test_build_id):
    t = datetime.now().strftime(TIME_FORMAT)
    branch = f'koji/test/{test_build_id}/{t}'
    with cd(git_repo), local_branch(branch):
        spec_paths = subprocess.check_output(['git', 'ls-files', 'SPECS/*.spec']).decode().splitlines()
        assert len(spec_paths) == 1
        spec_path = spec_paths[0]
        with Specfile(spec_path) as spec:
            # find the next build number
            package = Path(spec_path).stem
            builds = subprocess.check_output(['koji', 'list-builds', '--package', package]).decode().splitlines()[2:]
            base_nvr = f'{package}-{spec.version}-{spec.release}.0.{test_build_id}.'
            # use a regex to match %{macro} without actually expanding the macros
            base_nvr_re = re.escape(re.sub('%{.+}', "@@@", base_nvr)).replace('@@@', '.*') + r'(\d+)'
            build_matches = [re.match(base_nvr_re, b) for b in builds]
            build_ids = [int(m.group(1)) for m in build_matches if m]
            next_build_id = sorted(build_ids)[-1] + 1 if build_ids else 1
            spec.release = f'{spec.release}.0.{test_build_id}.{next_build_id}'
        subprocess.check_call(['git', 'commit', '-m', "bump release for test build", spec_path])
        subprocess.check_call(['git', 'push', 'origin', branch])
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode().strip()
        return commit

def main():
    parser = argparse.ArgumentParser(description='Build a package or chain-build several from local git repos for RPM sources')
    parser.add_argument('target', help='Koji target for the build')
    parser.add_argument('git_repos', nargs='+',
                        help='local path to one or more git repositories. If several are provided, '
                             'a chained build will be started in the order of the arguments')
    parser.add_argument('--scratch', action="store_true", help='Perform scratch build')
    parser.add_argument('--nowait', action="store_true", help='Do not wait for the build to end')
    parser.add_argument('--test-build', metavar="ID", help='Run a test build. The provided ID will be used to build a unique release tag.')
    args = parser.parse_args()

    target = args.target
    git_repos = [os.path.abspath(check_dir(d)) for d in args.git_repos]
    is_scratch = args.scratch
    is_nowait = args.nowait
    test_build = args.test_build

    if len(git_repos) > 1 and is_scratch:
        parser.error("--scratch is not compatible with chained builds.")

    for d in git_repos:
        if not check_git_repo(d):
            parser.error("%s is not in a clean state (or is not a git repository)." % d)

    if len(git_repos) == 1:
        clean_old_branches(git_repos[0])
        remote, hash = get_repo_and_commit_info(git_repos[0])
        if test_build:
            hash = push_bumped_release(git_repos[0], test_build)
        url = koji_url(remote, hash)
        command = ['koji', 'build'] + (['--scratch'] if is_scratch else []) + [target, url] + (['--nowait'] if is_nowait else [])
        print('  '.join(command), flush=True)
        subprocess.check_call(command)
    else:
        urls = []
        for d in git_repos:
            clean_old_branches(d)
            remote, hash = get_repo_and_commit_info(d)
            if test_build:
                hash = push_bumped_release(d, test_build)
            urls.append(koji_url(remote, hash))
        command = ['koji', 'chain-build', target] + (' : '.join(urls)).split(' ') +  (['--nowait'] if is_nowait else [])
        print('  '.join(command), flush=True)
        subprocess.check_call(command)

if __name__ == "__main__":
    main()
