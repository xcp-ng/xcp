#!/usr/bin/env python3
import argparse
import logging
import os
import re
import subprocess
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

try:
    from specfile import Specfile
except ImportError:
    print("error: specfile module can't be imported. Please install it with 'pip install --user specfile'.")
    exit(1)

TIME_FORMAT = '%Y-%m-%d-%H-%M-%S'

@contextmanager
def cd(dir):
    """Change to a directory temporarily. To be used in a with statement."""
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
    """check that the working copy is a working directory and is clean."""
    with cd(dirpath):
        return subprocess.run(['git', 'diff-index', '--quiet', 'HEAD', '--']).returncode == 0

def check_commit_is_available_remotely(dirpath, hash):
    with cd(dirpath):
        if not subprocess.check_output(['git', 'branch', '-r', '--contains', hash]):
            raise Exception("The current commit is not available in the remote repository")

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
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode().strip()
    subprocess.check_call(['git', 'checkout', '--quiet', commit])
    try:
        yield branch
    finally:
        subprocess.check_call(['git', 'checkout', prev_branch])

def is_old_branch(b):
    branch_time = datetime.strptime(b.split('/')[-1], TIME_FORMAT)
    return branch_time < datetime.now() - timedelta(hours=3)

def clean_old_branches(git_repo):
    with cd(git_repo):
        remote_branches = [
            line.split()[-1] for line in subprocess.check_output(['git', 'ls-remote']).decode().splitlines()
        ]
        remote_branches = [b for b in remote_branches if b.startswith('refs/heads/koji/test/')]
        old_branches = [b for b in remote_branches if is_old_branch(b)]
        if old_branches:
            print("removing outdated remote branch(es)", flush=True)
            subprocess.check_call(['git', 'push', '--delete', 'origin'] + old_branches)

def xcpng_version(target):
    xcpng_version_match = re.match(r'^v(\d+\.\d+)-u-\S+$', target)
    if xcpng_version_match is None:
        raise Exception(f"Can't find XCP-ng version in {target}")
    return xcpng_version_match.group(1)

def find_next_release(package, spec, target, test_build_id, pre_build_id):
    assert test_build_id is not None or pre_build_id is not None
    builds = subprocess.check_output(['koji', 'list-builds', '--quiet', '--package', package]).decode().splitlines()
    if test_build_id:
        base_nvr = f'{package}-{spec.version}-{spec.release}.0.{test_build_id}.'
    else:
        base_nvr = f'{package}-{spec.version}-{spec.release}~{pre_build_id}.'
    # use a regex to match %{macro} without actually expanding the macros
    base_nvr_re = (
        re.escape(re.sub('%{.+}', "@@@", base_nvr)).replace('@@@', '.*')
        + r'(\d+)'
        + re.escape(f'.xcpng{xcpng_version(target)}')
    )
    build_matches = [re.match(base_nvr_re, b) for b in builds]
    build_nbs = [int(m.group(1)) for m in build_matches if m]
    build_nb = sorted(build_nbs)[-1] + 1 if build_nbs else 1
    if test_build_id:
        return f'{spec.release}.0.{test_build_id}.{build_nb}'
    else:
        return f'{spec.release}~{pre_build_id}.{build_nb}'

def push_bumped_release(git_repo, target, test_build_id, pre_build_id):
    t = datetime.now().strftime(TIME_FORMAT)
    branch = f'koji/test/{test_build_id or pre_build_id}/{t}'
    with cd(git_repo), local_branch(branch):
        spec_paths = subprocess.check_output(['git', 'ls-files', 'SPECS/*.spec']).decode().splitlines()
        assert len(spec_paths) == 1
        spec_path = spec_paths[0]
        with Specfile(spec_path) as spec:
            # find the next build number
            package = Path(spec_path).stem
            spec.release = find_next_release(package, spec, target, test_build_id, pre_build_id)
        subprocess.check_call(['git', 'commit', '--quiet', '-m', "bump release for test build", spec_path])
        subprocess.check_call(['git', 'push', 'origin', f'HEAD:refs/heads/{branch}'])
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode().strip()
        return commit

def main():
    parser = argparse.ArgumentParser(
        description='Build a package or chain-build several from local git repos for RPM sources'
    )
    parser.add_argument('target', help='Koji target for the build')
    parser.add_argument('git_repos', nargs='+',
                        help='local path to one or more git repositories. If several are provided, '
                             'a chained build will be started in the order of the arguments')
    parser.add_argument('--scratch', action="store_true", help='Perform scratch build')
    parser.add_argument('--nowait', action="store_true", help='Do not wait for the build to end')
    parser.add_argument(
        '--test-build',
        metavar="ID",
        help='Run a test build. The provided ID will be used to build a unique release tag.',
    )
    parser.add_argument(
        '--pre-build',
        metavar="ID",
        help='Run a pre build. The provided ID will be used to build a unique release tag.',
    )
    args = parser.parse_args()

    target = args.target
    git_repos = [os.path.abspath(check_dir(d)) for d in args.git_repos]
    is_scratch = args.scratch
    is_nowait = args.nowait
    test_build = args.test_build
    pre_build = args.pre_build
    if test_build and pre_build:
        logging.error("--pre-build and --test-build can't be used together")
        exit(1)
    if test_build is not None and re.match('^[a-zA-Z0-9]{1,16}$', test_build) is None:
        logging.error("The test build id must be 16 characters long maximum and only contain letters and digits")
        exit(1)
    if pre_build is not None and re.match('^[a-zA-Z0-9]{1,16}$', pre_build) is None:
        logging.error("The pre build id must be 16 characters long maximum and only contain letters and digits")
        exit(1)

    if len(git_repos) > 1 and is_scratch:
        parser.error("--scratch is not compatible with chained builds.")

    for d in git_repos:
        if not check_git_repo(d):
            parser.error("%s is not in a clean state (or is not a git repository)." % d)

    if len(git_repos) == 1:
        clean_old_branches(git_repos[0])
        remote, hash = get_repo_and_commit_info(git_repos[0])
        if test_build or pre_build:
            hash = push_bumped_release(git_repos[0], target, test_build, pre_build)
        else:
            check_commit_is_available_remotely(git_repos[0], hash)
        url = koji_url(remote, hash)
        command = (
            ['koji', 'build']
            + (['--scratch'] if is_scratch else [])
            + [target, url]
            + (['--nowait'] if is_nowait else [])
        )
        print('  '.join(command), flush=True)
        subprocess.check_call(command)
    else:
        urls = []
        for d in git_repos:
            clean_old_branches(d)
            remote, hash = get_repo_and_commit_info(d)
            if test_build or pre_build:
                hash = push_bumped_release(d, target, test_build, pre_build)
            else:
                check_commit_is_available_remotely(d, hash)
            urls.append(koji_url(remote, hash))
        command = ['koji', 'chain-build', target] + (' : '.join(urls)).split(' ') + (['--nowait'] if is_nowait else [])
        print('  '.join(command), flush=True)
        subprocess.check_call(command)

if __name__ == "__main__":
    main()
