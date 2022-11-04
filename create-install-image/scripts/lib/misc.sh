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


# infrastructure for fetching RPMs from source repo

yumdl_is_dnf() {
    yumdownloader --version | grep -q dnf
}

setup_yum_download() {
    [ $# = 3 ] || die "setup_yum_download: need exactly 3 arguments"
    DIST="$1"
    RPMARCH="$2"
    SRCURL="$3"

    YUMDLCONF=$(mktemp "$TMPDIR/yum-XXXXXX.conf")
    YUMLOGDIR=$(mktemp -d "$TMPDIR/logs-XXXXXX")
    DUMMYROOT=$(mktemp -d "$TMPDIR/root-XXXXXX")

    if yumdl_is_dnf; then
        enable_plugins=1
        echo >&2 "WARNING: yumdownloader is dnf wrapper, I have to enable dnf plugins!"
    else
        enable_plugins=0
    fi

    # FIXME gpgcheck
    cat > "$YUMDLCONF" <<EOF
[main]
reposdir=/dev/null
cachedir=$TMPDIR/yum-cache
persistdir=/dev/null
gpgcheck=0
repo_gpgcheck=0
plugins=${enable_plugins}
basearch=$RPMARCH
[xcpng-base]
name=xcpng-base
baseurl=$SRCURL/base/$RPMARCH/
[xcpng-updates]
name=xcpng-updates
baseurl=$SRCURL/updates/$RPMARCH/
[xcpng-testing]
name=xcpng-testing
baseurl=$SRCURL/testing/$RPMARCH/
EOF
    mkdir ${VERBOSE} "$DUMMYROOT/etc"
    YUMDLFLAGS=(
        # non-$VERBOSE is -q, $VERBOSE is default, yum's -v would be debug
        $([ -n "$VERBOSE" ] || printf -- "-q")
        --config="$YUMDLCONF"
        --releasever="$DIST"
        # --disablerepo="*" --enablerepo='xcpng-base'
    )

    # availability of yumdownloader does not imply that of yum
    local YUM=$(command -v yum || command -v dnf) || die "no yum or dnf found"
    # summary of repos
    "$YUM" ${YUMDLFLAGS[@]} repolist all
}

get_rpms() {
    local OPTS=""
    if [ "$1" = "--depends" ]; then
        OPTS="--resolve"
        shift
    fi
    local DESTDIR="$1"
    shift
    if [ -n "$YUMDLFLAGS" ]; then
        (cd "$DESTDIR" && yumdownloader $OPTS "${YUMDLFLAGS[@]}" --installroot="$DUMMYROOT" "$@")
    else
        die "Must configure yum download before attempting to download"
    fi
}
