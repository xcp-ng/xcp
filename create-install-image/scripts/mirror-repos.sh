#!/bin/bash
set -eE

mydir=$(dirname $0)
topdir=$mydir/..

. "$mydir/lib/misc.sh"

[ $# = 2 ] || die "Usage: $0 <version> <destination>"
DIST="$1"
TARGET="$2"
maybe_set_srcurl "$DIST"

command -v lftp >/dev/null || die "required tool not found: lftp"

lftp -c mirror \
     --verbose \
     --delete \
     --exclude="/Source/|-debuginfo-|-devel[-_]" \
     "$SRCURL" "$TARGET/$DIST"
