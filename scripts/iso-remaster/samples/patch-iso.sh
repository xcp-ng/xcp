#! /bin/sh
set -e

ISODIR="$1"

# remove existing repo sig (if we want to modify the repo)
rm -fv "$ISODIR/repodata/repomd.xml.asc"

# sign with a different key
gpg --armor --sign "$ISODIR/repodata/repomd.xml"
