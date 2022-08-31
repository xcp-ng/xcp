#!/usr/bin/env python3
import argparse
import os
import subprocess

def main():
    parser = argparse.ArgumentParser(description='Imports the contents of a source RPM into a git repository')
    parser.add_argument('source_rpm', help='local path to source RPM')
    parser.add_argument('repository', help='local path to the repository')
    parser.add_argument('parent_branch', help='git parent branch from which to branch')
    parser.add_argument('branch', help='destination branch')
    parser.add_argument('tag', nargs='?', help='tag')
    parser.add_argument('-c', '--commit', action='store_true', help='commit the changes')
    parser.add_argument('-p', '--push', action='store_true', help='commit and push')
    parser.add_argument('-m', '--master', action='store_true', help='merge to master afterwards')
    args = parser.parse_args()

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
        subprocess.check_call(['git', 'diff-index', '--quiet',  'HEAD', '--'])
        print("Working copy is clean.")
    except:
        parser.error("Git repository seems to have local modifications.")

    # check that there are no untracked files
    if len(subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard'])):
        parser.error("There are untracked files.")

    # checkout parent ref
    subprocess.check_call(['git', 'fetch'])
    subprocess.check_call(['git', 'checkout', args.parent_branch])
    subprocess.check_call(['git', 'pull'])

    # remove everything from SOURCES and SPECS
    if os.path.isdir('SOURCES') and len(os.listdir('SOURCES')) > 0:
        subprocess.check_call(['git', 'rm', 'SOURCES/*', '-r'])
    if os.path.isdir('SOURCES') and len(os.listdir('SOURCES')) > 0:
        parser.error("Files remaining in SOURCES/ after removing the tracked ones. ")
        parser.error("Delete them (including hidden files), reset --hard.")
    os.mkdir('SOURCES')

    if os.path.isdir('SPECS'):
        subprocess.check_call(['git', 'rm', 'SPECS/*', '-r'])
    os.mkdir('SPECS')

    # extract SRPM
    os.chdir('SOURCES')
    os.system('rpm2cpio "%s" | cpio -idmv' % source_rpm_abs)
    os.chdir('..')
    os.system('mv SOURCES/*.spec SPECS/')

    # remove trademarked or copyrighted files
    sources = os.listdir('SOURCES')
    deletemsg = "File deleted from the original sources for trademark-related or copyright-related legal reasons.\n"
    deleted = []
    for f in ['Citrix_Logo_Black.png', 'COPYING.CitrixCommercial']:
        if f in sources:
            os.unlink(os.path.join('SOURCES', f))
            open(os.path.join('SOURCES', "%s.deleted-by-XCP-ng.txt" % f), 'w').write(deletemsg)
            deleted.append(f)

    # commit
    if subprocess.call(['git', 'rev-parse', '--quiet', '--verify', args.branch]) != 0:
        subprocess.check_call(['git', 'checkout', '-b', args.branch])
    else:
        subprocess.check_call(['git', 'checkout', args.branch])
    subprocess.check_call(['git', 'add', '--all'])
    if args.commit or args.push:
        has_changes = False
        try:
            subprocess.check_call(['git', 'diff-index', '--quiet',  'HEAD', '--'])
        except:
            has_changes = True

        if not has_changes:
            print("\nWorking copy has no modifications. Nothing to commit. No changes from previous release?\n")
        else:
            msg = 'Import %s' % os.path.basename(args.source_rpm)
            if deleted:
                msg += "\n\nFiles deleted for legal reasons:\n - " + '\n - '.join(deleted)
            subprocess.check_call(['git', 'commit', '-s', '-m', msg])

        # tag
        if args.tag is not None:
            subprocess.check_call(['git', 'tag', args.tag])

        # push to remote
        if args.push:
            subprocess.check_call(['git', 'push', '--set-upstream', 'origin', args.branch])
            if args.tag is not None:
                subprocess.check_call(['git', 'push', 'origin', args.tag])

    # switch to master before leaving
    subprocess.check_call(['git', 'checkout', 'master'])

    # merge to master if needed
    if args.push and args.master:
        subprocess.check_call(['git', 'push', 'origin', '%s:master' % args.branch])
        subprocess.check_call(['git', 'pull'])


if __name__ == "__main__":
    main()
