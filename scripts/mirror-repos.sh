#!/bin/bash
set -eE

mydir=$(dirname $0)
topdir=$mydir/..

. "$mydir/lib/misc.sh"

[ $# = 1 ] || die "need exactly 1 non-option argument"
DIST="$1"
maybe_set_srcurl "$DIST"

command -v lftp >/dev/null || die "required tool not found: lftp"

#lftp -c mirror -x "\.src\.rpm$" https://updates.xcp-ng.org/$MAJOR/$DIST/ ~/mirrors/xcpng/$DIST
lftp -c mirror -x "/Source/|-debuginfo-|-devel-" $SRCURL ~/mirrors/xcpng/$DIST
#lftp -c mirror -x "/Source/" https://updates.xcp-ng.org/$MAJOR/$DIST/ ~/mirrors/xcpng/$DIST
