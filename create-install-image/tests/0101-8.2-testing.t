#!/bin/sh

test_description="check build for 8.2:testing"

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

test_expect_success EXPENSIVE "build install.img for 8.2:testing" "
    set -x &&
    sudo sh -c '
        set -x &&
        cd $SHARNESS_TRASH_DIRECTORY &&

        $TOPDIR/scripts/create-installimg.sh \
            --srcurl $XCPTEST_REPOROOT/8.2 \
            8.2:testing
    ' &&

    test -r install-8.2-x86_64.img
"

test_expect_success "build ISO for 8.2:testing" "
    ( test -r install-8.2-x86_64.img || touch install-8.2-x86_64.img ) &&

    $TOPDIR/scripts/create-install-iso.sh \
        --srcurl $XCPTEST_REPOROOT/8.2 \
        -V 'XCP-NG_TEST' \
        8.2:testing install-8.2-x86_64.img xcp-ng-8.2-install.iso &&

    test -r xcp-ng-8.2-install.iso
"

test_done