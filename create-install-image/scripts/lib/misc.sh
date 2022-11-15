# consistent erroring out

die() {
    echo >&2
    echo >&2 "ERROR: $*"
    echo >&2
    exit 1
}

# usage() is script-specific, implement it yourself

die_usage() {
    usage >&2
    die "$*"
}


# default src URL depending on selected $DIST

maybe_set_srcurl() {
    [ $# = 1 ] || die "maybe_set_srcurl: need exactly 1 argument"
    DIST="$1"
    MINOR=${DIST%.*}
    MAJOR=${MINOR%.*}
    if [ "$MAJOR" = "$MINOR" ]; then
	# DIST only has 2 components
	MINOR="$DIST"
    fi
    SRCURL_DEFAULT="https://updates.xcp-ng.org/$MAJOR/$MINOR"
    if [ -z "$SRCURL" ]; then
	SRCURL="$SRCURL_DEFAULT"
	[ -z "$VERBOSE" ] || echo "Defaulting to SRCURL '$SRCURL'"
    fi
}


# cleanup tempfiles on exit

CLEANUP_DIRS=()
CLEANUP_FILES=()
exitcleanup() {
    rm -rf "${CLEANUP_DIRS[@]}"
    rm -f "${CLEANUP_FILES[@]}"
}
trap 'exitcleanup' EXIT INT


# Avoid yum keeping a cache in /var/tmp with a temporary name but
# getting reused between runs, and confusing yum about which rpm
# versions should be available.  Yeah that sucks hard.
# See https://unix.stackexchange.com/questions/92257/
export TMPDIR=$(mktemp -d "$PWD/tmpdir-XXXXXX")
CLEANUP_DIRS+=("$TMPDIR")
