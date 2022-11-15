#!/bin/sh

test_description="check build for 8.2:updates"

DIR0="$(dirname "$0")"
TESTDIR="$(realpath "$DIR0")"
. $TESTDIR/sharness/sharness.sh

TOPDIR="$TESTDIR/.."

# yum cannot grok spaces in dir names
CLEANDIR=$(pwd | tr " " "_")
ln -s "$(basename "$PWD")" $CLEANDIR
cd $CLEANDIR
SHARNESS_TRASH_DIRECTORY="$CLEANDIR"
HOME="$CLEANDIR"
set|grep "trash dir"

test_expect_success EXPENSIVE "build install.img for 8.2:updates" "
    set -x &&
    sudo sh -c '
        set -x &&
        cd $SHARNESS_TRASH_DIRECTORY &&

        $TOPDIR/scripts/create-installimg.sh \
            --srcurl $XCPTEST_REPOROOT/8.2 \
            8.2.updates
    ' &&

    test -r install-8.2.updates-x86_64.img
"

test_done
