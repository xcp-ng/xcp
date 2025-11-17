#!/usr/bin/env python3
import argparse
import logging
import os
import shutil
import subprocess
from glob import glob


def call_process(args):
    logging.debug("$ %s", args)
    subprocess.check_call(args)

def pipe_commands(*commands: list[str]) -> bytes:
    if not commands:
        raise ValueError("The 'commands' list cannot be empty.")
    if any(not cmd for cmd in commands):
        raise ValueError("All commands in the list must be non-empty.")

    processes: list[subprocess.Popen[bytes]] = []
    next_process_stdin = None

    for command in commands:
        process = subprocess.Popen(
            command,
            stdin=next_process_stdin,
            stdout=subprocess.PIPE,
        )
        processes.append(process)
        next_process_stdin = process.stdout

    final_stdout, _final_stderr = processes[-1].communicate()

    for cmd, process in zip(commands, processes):
        process.wait()
        if process.returncode != 0:
            raise subprocess.CalledProcessError(returncode=process.returncode, cmd=cmd)

    return final_stdout

def main():
    parser = argparse.ArgumentParser(description='Imports the contents of a source RPM into a git repository')
    parser.add_argument('source_rpm', help='local path to source RPM')
    parser.add_argument('repository', help='local path to the repository')
    parser.add_argument('parent_branch', help='git parent branch from which to branch')
    parser.add_argument('branch', help='destination branch')
    parser.add_argument('tag', nargs='?', help='tag')
    parser.add_argument('-v', '--verbose', action='count', default=0)
    parser.add_argument('-p', '--push', action='store_true', help='pull and push')
    parser.add_argument('-m', '--master', action='store_true', help='merge to master afterwards')
    args = parser.parse_args()

    if args.verbose > 2:
        args.verbose = 2
    loglevel = {0: logging.WARNING,
                1: logging.INFO,
                2: logging.DEBUG,
                }[args.verbose]
    logging.basicConfig(format='[%(levelname)s] %(message)s', level=loglevel)

    for dep in ['cpio', 'rpm2cpio']:
        if shutil.which(dep) is None:
            parser.error(f"{dep} can't be found.")

    # check that the source RPM file exists
    if not os.path.isfile(args.source_rpm):
        parser.error("File %s does not exist." % args.source_rpm)
    if not args.source_rpm.endswith('.src.rpm'):
        parser.error("File %s does not appear to be a source RPM." % args.source_rpm)
    source_rpm_abs = os.path.abspath(args.source_rpm)

    # enter repository directory
    if not os.path.isdir(args.repository):
        parser.error("Repository directory %s does not exist." % args.repository)
    os.chdir(args.repository)

    # check that the working copy is clean
    try:
        call_process(['git', 'diff-index', '--quiet',  'HEAD', '--'])
        print("Working copy is clean.")
    except:
        raise
        parser.error("Git repository seems to have local modifications.")

    # check that there are no untracked files
    if len(subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard'])):
        parser.error("There are untracked files.")

    print(" checking out parent ref...")

    if args.push:
        call_process(['git', 'fetch'])
    call_process(['git', 'checkout', args.parent_branch])
    if args.push:
        call_process(['git', 'pull'])

    print(" removing everything from SOURCES and SPECS...")

    if os.path.isdir('SOURCES') and len(os.listdir('SOURCES')) > 0:
        call_process(['git', 'rm', 'SOURCES/*', '-r'])
    if os.path.isdir('SOURCES') and len(os.listdir('SOURCES')) > 0:
        parser.error("Files remaining in SOURCES/ after removing the tracked ones. ")
        parser.error("Delete them (including hidden files), reset --hard.")
    os.mkdir('SOURCES')

    if os.path.isdir('SPECS'):
        call_process(['git', 'rm', 'SPECS/*', '-r'])
    os.mkdir('SPECS')

    print(" extracting SRPM...")

    os.chdir('SOURCES')
    pipe_commands(['rpm2cpio', source_rpm_abs], ['cpio', '-idmv'])
    os.chdir('..')
    for f in glob('SOURCES/*.spec'):
        shutil.move(f, 'SPECS')

    print(" removing trademarked or copyrighted files...")

    sources = os.listdir('SOURCES')
    deletemsg = "File deleted from the original sources for trademark-related or copyright-related legal reasons.\n"
    deleted = []
    for f in ['Citrix_Logo_Black.png', 'COPYING.CitrixCommercial']:
        if f in sources:
            os.unlink(os.path.join('SOURCES', f))
            open(os.path.join('SOURCES', "%s.deleted-by-XCP-ng.txt" % f), 'w').write(deletemsg)
            deleted.append(f)

    if subprocess.call(['git', 'rev-parse', '--quiet', '--verify', args.branch]) != 0:
        call_process(['git', 'checkout', '-b', args.branch])
    else:
        call_process(['git', 'checkout', args.branch])
    call_process(['git', 'add', '--all'])

    print(" committing...")
    has_changes = False
    try:
        call_process(['git', 'diff-index', '--quiet',  'HEAD', '--'])
    except:
        has_changes = True

    if not has_changes:
        print("\nWorking copy has no modifications. Nothing to commit. No changes from previous release?\n")
    else:
        msg = 'Import %s' % os.path.basename(args.source_rpm)
        if deleted:
            msg += "\n\nFiles deleted for legal reasons:\n - " + '\n - '.join(deleted)
        call_process(['git', 'commit', '-s', '-m', msg])

    # tag
    if args.tag is not None:
        call_process(['git', 'tag', args.tag])

    # push to remote
    if args.push:
        call_process(['git', 'push', '--set-upstream', 'origin', args.branch])
        if args.tag is not None:
            call_process(['git', 'push', 'origin', args.tag])

    print(" switching to master before leaving...")

    call_process(['git', 'checkout', 'master'])

    # merge to master if needed
    if args.push and args.master:
        print(" merging to master...")
        call_process(['git', 'push', 'origin', '%s:master' % args.branch])
        call_process(['git', 'pull'])


if __name__ == "__main__":
    main()
