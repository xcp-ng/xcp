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


# populates CFG_SEARCH_PATH array
parse_config_search_path() {
    CFG_SEARCH_PATH=()
    _parse_config_search_path "$1"
}

_parse_config_search_path() {
    local pathstr="$1"
    while true; do
        local dir=${pathstr%%:*}
        local absdir
        case "$dir" in
            /*) absdir="$dir" ;;
            *) absdir=$(realpath "$topdir/configs/$dir") ;;
        esac
        [ -d "$absdir" ] || die "directory not found: $absdir"
        CFG_SEARCH_PATH+=("$absdir")

        if [ -r "$absdir/INCLUDE" ]; then
            while read include; do
                _parse_config_search_path "$include"
            done < "$absdir/INCLUDE"
        fi

        [ "$pathstr" != "$dir" ] || break # was last component in search path
        pathstr=${pathstr#${dir}:}        # strip this dir and loop
    done
}

find_config() {
    local filename="$1"
    for dir in "${CFG_SEARCH_PATH[@]}"; do
        try="$dir/$filename"
        if [ -r "$try" ]; then
            echo "$try"
            return
        fi
    done
    die "cannot find '$filename' in ${CFG_SEARCH_PATH[*]}"
}

find_all_configs() {
    local filename="$1"
    for dir in "${CFG_SEARCH_PATH[@]}"; do
        try="$dir/$filename"
        if [ -r "$try" ]; then
            echo "$try"
        fi
    done
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

    YUMDLCONF_TMPL=$(find_config yumdl.conf.tmpl)

    YUMDLCONF=$(mktemp "$TMPDIR/yum-XXXXXX.conf")
    YUMREPOSD=$(mktemp -d "$TMPDIR/yum-repos-XXXXXX.d")
    YUMLOGDIR=$(mktemp -d "$TMPDIR/logs-XXXXXX")
    DUMMYROOT=$(mktemp -d "$TMPDIR/root-XXXXXX")

    if yumdl_is_dnf; then
        enable_plugins=1
        echo >&2 "WARNING: yumdownloader is dnf wrapper, I have to enable dnf plugins!"
    else
        enable_plugins=0
    fi

    cat "$YUMDLCONF_TMPL" |
        sed \
            -e "s,@@ENABLE_PLUGINS@@,$enable_plugins," \
            -e "s,@@YUMREPOSD@@,$YUMREPOSD," \
            -e "s,@@CACHEDIR@@,$TMPDIR/yum-cache," \
            > "$YUMDLCONF"
    mkdir ${VERBOSE} "$DUMMYROOT/etc"
    YUMDLFLAGS=(
        # non-$VERBOSE is -q, $VERBOSE is default, yum's -v would be debug
        $([ -n "$VERBOSE" ] || printf -- "-q")
        --config="$YUMDLCONF"
        --releasever="$DIST"
    )

    find_all_configs yum-repos.conf.tmpl | while read YUMREPOSCONF_TMPL; do
        reponame=$(basename $(dirname "$YUMREPOSCONF_TMPL"))
        cat "$YUMREPOSCONF_TMPL" |
            sed \
                -e "s,@@SRCURL@@,$SRCURL," \
                -e "s,@@RPMARCH@@,$RPMARCH," \
                > "$YUMREPOSD/$reponame.repo"
    done

    # availability of yumdownloader does not imply that of yum
    local YUM=$(command -v yum || command -v dnf) || die "no yum or dnf found"
    # summary of repos
    test ! -r /var/cache/yum/xcpng-base || die "yum system cache should not be there to start with"
    "$YUM" ${YUMDLFLAGS[@]} repolist all
    # double-check we don't let yum reintroduce that cache by mistake
    test ! -r /var/cache/yum/xcpng-base || die "yum system cache should not have been created"
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
