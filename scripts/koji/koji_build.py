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

# target -> allowed branch(es)
# To lock a target, just assign an empty set: "{}"
# Unlisted targets are not protected then any branch will be allowed
PROTECTED_TARGETS = {
    "v8.2-ci": {"8.2"},
    "v8.2-fasttrack": {"8.2"},
    "v8.2-incoming": {"8.2"},
    "v8.3-ci": {"master", "8.3"},
    "v8.3-fasttrack": {"master", "8.3"},
    "v8.3-incoming": {"master", "8.3"},
}

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

def check_commit_is_available_remotely(dirpath, sha, target, warn):
    with cd(dirpath):
        output = subprocess.check_output(['git', 'branch', '-r', '--contains', sha])
        if not output:
            raise Exception("The current commit is not available in the remote repository")
        logging.debug('Commit %s is contained in remote branch: %s', sha, output.decode().strip())
        
        if target is not None and re.match(r'v\d+\.\d+-u-.+', target):
            raise Exception("Building with a user target requires using --pre-build or --test-build.\n")
        try:
            allowed_branches = PROTECTED_TARGETS.get(target)
            if allowed_branches is None:
                logging.debug('Target %s is not protected, any branch is allowed', target)
            else:
                for branch in allowed_branches:
                    try:
                        if is_remote_branch_commit(dirpath, sha, branch):
                            logging.debug('Commit %s is on top of branch %s (target: %s)', sha, branch, target)
                            break
                    except Exception as e:
                        logging.debug('Ignoring %s', e)
                else:
                    raise Exception(f"The current commit is not the last commit of any remote allowed branches: {allowed_branches}.\n"
                                    f"This is required when using the protected target {target}.")
        except Exception as e:
            if warn:
                print(f"warning: {e}", flush=True)
            else:
                raise e

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
        # prev_branch is empty when the head was detached
        subprocess.check_call(['git', 'checkout', prev_branch or commit])

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
    xcpng_version_match = re.match(r'^v(\d+\.\d+)-\S+$', target)
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

def is_remote_branch_commit(git_repo, sha, branch):
    """ Args:
           git_repo: URL of git repository
           sha: Git hash
           branch: remote branch in repository
        Returns:
           True if commit is on top of an assumed remote branch, false otherwise
        Raises:
           Exception: If branch is missing from repo, or not reachable
    """
    with cd(git_repo):
        references = subprocess.check_output(['git', 'ls-remote', 'origin', f'refs/heads/{branch}']).decode().strip().split()
        if not references:
            raise Exception(f'Remote branch "{branch}" missing or unreachable')
        remote_sha = references[0]
    return sha == remote_sha

def build_id_of(name, candidate):
    if candidate is None:
        return None

    length = len(candidate)
    if length > 16:
        logging.error(f"The {name} build id must be at most 16 characters long, it's {length} characters long")
        exit(1)

    invalid_chars = any(re.match(r'[a-zA-Z0-9]', char) is None for char in candidate)

    if invalid_chars:
        pp_invalid = ''.join("^" if re.match(r'[a-zA-Z0-9]', char) is None else " " for char in candidate)
        logging.error(f"The {name} build id must only contain letters and digits:")
        logging.error(f"    {candidate}")
        logging.error(f"    {pp_invalid}")
        exit(1)

    return candidate

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
    parser.add_argument('--force', action="store_true", help='Bypass sanity checks')
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

    test_build = build_id_of("test", args.test_build)
    pre_build = build_id_of("pre", args.pre_build)

    if test_build and pre_build:
        logging.error("--pre-build and --test-build can't be used together")
        exit(1)

    if len(git_repos) > 1 and is_scratch:
        parser.error("--scratch is not compatible with chained builds.")

    for d in git_repos:
        if not check_git_repo(d):
            parser.error("%s is not in a clean state (or is not a git repository)." % d)

    if len(git_repos) == 1:
        remote, hash = get_repo_and_commit_info(git_repos[0])
        if test_build or pre_build:
            clean_old_branches(git_repos[0])
            hash = push_bumped_release(git_repos[0], target, test_build, pre_build)
        else:
            check_commit_is_available_remotely(git_repos[0], hash, None if is_scratch else target, args.force)
        url = koji_url(remote, hash)
        command = (
            ['koji', 'build', '--wait-repo']
            + (['--scratch'] if is_scratch else [])
            + [target, url]
            + (['--nowait'] if is_nowait else [])
        )
        print('  '.join(command), flush=True)
        subprocess.check_call(command)
    else:
        urls = []
        for d in git_repos:
            remote, hash = get_repo_and_commit_info(d)
            if test_build or pre_build:
                clean_old_branches(d)
                hash = push_bumped_release(d, target, test_build, pre_build)
            else:
                check_commit_is_available_remotely(d, hash, None if is_scratch else target, args.force)
            urls.append(koji_url(remote, hash))
        command = ['koji', 'chain-build', target] + (' : '.join(urls)).split(' ') + (['--nowait'] if is_nowait else [])
        print('  '.join(command), flush=True)
        subprocess.check_call(command)

if __name__ == "__main__":
    main()
