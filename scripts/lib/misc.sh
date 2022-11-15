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
	[ -z "$VERBOSE" ] || echo "Defauling to SRCURL '$SRCURL'"
    fi
}


# cleanup tempfiles on exit

CLEANUP_DIRS=()
CLEANUP_FILES=()
exitcleanup() {
    rm ${VERBOSE} -rf "${CLEANUP_DIRS[@]}"
    rm ${VERBOSE} -f "${CLEANUP_FILES[@]}"
}
trap 'exitcleanup' EXIT INT


# find rpm filename for package $pname in $repodir

rpmfile() {
    pname="$1"
    repodir="$2"

    for filename in $(cd "$repodir" && echo $pname-*); do
	NVRA=${filename%.rpm}
	NVR=${NVRA%.*}
	NV=${NVR%-*}
	N=${NV%-*}
	if [ "$N" = "$pname" ]; then
	    echo $repodir/$filename
	    return
	fi
	# $pname is just a prefix of $N, ignore
    done
}


# infrastructure for fetching RPMs from source repo

setup_dnf_download() {
    [ $# = 3 ] || die "setup_dnf_download: need exactly 3 arguments"
    DIST="$1"
    RPMARCH="$2"
    SRCURL="$3"

    DNFCONF=$(mktemp dnf-XXXXXX.conf)
    CLEANUP_FILES+=("$DNFCONF")
    DNFLOGDIR=$PWD/$(mktemp -d logs-XXXXXX)
    DUMMYROOT=$PWD/$(mktemp -d root-XXXXXX)
    CLEANUP_DIRS+=("$DNFLOGDIR" "$DUMMYROOT")
    
    # FIXME gpgcheck
    cat > "$DNFCONF" <<EOF
[main]
gpgcheck=0
repo_gpgcheck=0
plugins=1
installonlypkgs=
config_file_path=/dev/null
distroverpkg=xcp-ng-release
basearch=$RPMARCH
installroot=$DUMMYROOT
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
    DNF=(dnf
         ${VERBOSE}
         --config="$DNFCONF"
         --releasever="$DIST"
         --disablerepo="*"
         --enablerepo='xcpng-base,xcpng-updates,xcpng-testing'
        )
}
