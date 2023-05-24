#!/bin/sh

test_description="sanity check before running real tests"

DIR0="$(dirname "$0")"
TESTDIR="$(realpath "$DIR0")"
. $TESTDIR/sharness/sharness.sh

test_expect_success "verify test environment" "
    echo \"XCPTEST_REPOROOT=$XCPTEST_REPOROOT\" | grep '://'
"

test_expect_success "verify lack of cache" "
    test ! -r /var/cache/yum/xcpng-base
"

test_done
