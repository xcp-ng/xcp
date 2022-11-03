#! /bin/bash
set -eE

# TODO:
# - new mode using `udiskctl loop-setup` instead of `fuseiso`
# - maybe find workaround for iso-patcher to work in fuse mode
#   despite https://github.com/containers/fuse-overlayfs/issues/377

die() {
    echo >&2
    echo >&2 "ERROR: $*"
    echo >&2
    exit 1
}

usage() {
    cat <<EOF
Usage: $0 [<options>] <input-iso> <output-iso>

Options:
  --mode <mode>   Force specified operation mode (default: use best available)
         fuse     : more resource-friendly, needs fuseiso and fuse-overlayfs
         copy     : more portable, needs more disk space, wears disk more
  --install-patcher, -l <script>
         Unpack install.img, run <script> with its location as single argument,
         and repack install.img for the output ISO
  --iso-patcher, -s <script>
         Run <script> with ISO contents location as single argument,
         before repacking output ISO.
         Forces `--mode copy` to avoid fuse-overlay bug
         https://github.com/containers/fuse-overlayfs/issues/377
EOF
}

die_usage() {
    usage >&2
    die "$*"
}

[ $(whoami) != root ] || die "not meant to run as root"


# select default operating mode
OPMODE=fuse
command -v fuseiso >/dev/null || { echo >&2 "fuseiso not found"; OPMODE=copy; }
command -v fuse-overlayfs >/dev/null || { echo >&2 "fuse-overlayfs not found"; OPMODE=copy; }

ISOPATCHER=""
IMGPATCHER=""
while [ $# -ge 1 ]; do
    case "$1" in
        --mode)
            [ $# -ge 2 ] || die_usage "--mode needs an argument"
            OPMODE="$2"
            shift
            ;;
        --iso-patcher|-s)
            [ $# -ge 2 ] || die_usage "--iso-patcher needs an argument"
            ISOPATCHER="$2"
            echo >&2 "NOTE: iso-patcher use, forcing 'copy' mode"
            OPMODE=copy
            shift
            ;;
        --install-patcher|-l)
            [ $# -ge 2 ] || die_usage "--install-patcher needs an argument"
            IMGPATCHER="$2"
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        -*)
            die_usage "unknown flag '$1'"
            ;;
        *)
            break
            ;;
    esac
    shift
done

[ $# = 2 ] || die_usage "need exactly 2 non-option arguments"

INISO="$1"
OUTISO="$2"

umountrm() {
    sync "$1"
    fusermount -u -z "$1"
    rmdir "$1"
}

exitcleanup() {
    set +e
    case $OPMODE in
        copy)
            rm -rf "$RWISO"
            ;;
        fuse)
            umountrm "$MNT"
            umountrm "$RWISO"
            rm -rf "$OVLRW" "$OVLWD"
            ;;
        *)
            die "unknown mode '$OPMODE'"
            ;;
    esac
    rm -rf "$INSTALLIMG"
    rm "$FAKEROOTSAVE"
}

trap 'exitcleanup' EXIT INT

# where we unpack install.img
INSTALLIMG=$(mktemp -d installimg.XXXXXX)

# where we get a RW copy of input ISO contents
RWISO=$(mktemp -d isorw.XXXXXX)


# allow successive fakeroot calls to act as a single session
FAKEROOTSAVE=$(realpath $(mktemp fakerootsave.XXXXXX))
touch "$FAKEROOTSAVE" # avoid "does not exist" warning on first use
FAKEROOT=(fakeroot -i "$FAKEROOTSAVE" -s "$FAKEROOTSAVE" --)


### produce patched iso contents in $RWISO

# provide a RW view of ISO

case $OPMODE in
copy)
    7z x "$INISO" -o"$RWISO"
    SRCISO="$RWISO"
    DESTISO="$RWISO"
    ;;
fuse)
    MNT=$(mktemp -d isomnt.XXXXXX)
    OVLRW=$(mktemp -d ovlfs-upper.XXXXXX)
    OVLWD=$(mktemp -d ovlfs-work.XXXXXX)
    fuseiso "$INISO" "$MNT"

    # genisoimage apparently needs write access to those
    mkdir -p "$OVLRW/boot/isolinux"
    cp "$MNT/boot/isolinux/isolinux.bin" "$OVLRW/boot/isolinux/"
    chmod +w "$OVLRW/boot/isolinux/isolinux.bin"

    SRCISO="$MNT"
    DESTISO="$OVLRW"
    ;;
*)
    die "unknown mode '$OPMODE'"
    ;;
esac

# maybe run install.img patcher

if [ -n "$IMGPATCHER" ]; then
    bzcat "$SRCISO/install.img" | (cd "$INSTALLIMG" && "${FAKEROOT[@]}" cpio -idm)

    # patch install.img contents
    "${FAKEROOT[@]}" "$IMGPATCHER" "$INSTALLIMG"

    # repack install.img
    (cd "$INSTALLIMG" && "${FAKEROOT[@]}" sh -c "find . | cpio -o -H newc") |
        bzip2 > "$DESTISO/install.img"
fi

# produce merged view

case $OPMODE in
copy)
    ;;
fuse)
    # produce a merged iso tree
    fuse-overlayfs -o lowerdir="$MNT" -o upperdir="$OVLRW" -o workdir="$OVLWD" "$RWISO"
    ;;
*)
    die "unknown mode '$OPMODE'"
    ;;
esac

if [ -n "$ISOPATCHER" ]; then
    "${FAKEROOT[@]}" "$ISOPATCHER" "$RWISO"
fi

VOLID=$(isoinfo -i "$INISO" -d | grep "Volume id"| sed "s/Volume id: //")

"${FAKEROOT[@]}" genisoimage \
    -o "$OUTISO" \
    -v -r -J --joliet-long -V "$VOLID" -input-charset utf-8 \
    -c boot/isolinux/boot.cat -b boot/isolinux/isolinux.bin \
    -no-emul-boot -boot-load-size 4 -boot-info-table -eltorito-alt-boot -e boot/efiboot.img \
    -no-emul-boot \
    $RWISO
isohybrid --uefi "$OUTISO"
