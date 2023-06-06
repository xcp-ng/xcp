#! /bin/bash
set -e
set -o pipefail

mydir=$(dirname $0)
topdir=$mydir/..

. "$mydir/lib/misc.sh"

[ "$(id -u)" != 0 ] || die "should not run as root"

usage() {
    cat <<EOF
Usage: $0 [<options>] <base-config>[:<config-overlay>]* <install.img>

Options:
    -o|--output <output-iso>  (mandatory) output filename
    -V <VOLID>                (mandatory) ISO volume ID
    --srcurl <URL>            get RPMs from base-config and overlays from <URL>
                              default: https://updates.xcp-ng.org/<MAJOR>/<DIST>
    -D|--define-repo <NICK>!<URL>
                              add yum repo with name <NICK> and base URL <URL>
    --netinstall              do not include repository in ISO
    --sign <NICK> <KEYID>     sign repomd with default gpg key <KEYID>, with readable <NICK>
    --force-overwrite         don't abort if output file already exists
    --verbose		      be talkative
EOF
}

VERBOSE=
OUTISO=
FORCE_OVERWRITE=0
DOREPO=1
KEYID=
KEYNICK=
SRCURL=
declare -A CUSTOM_REPOS=()
RPMARCH="x86_64"
while [ $# -ge 1 ]; do
    case "$1" in
        --help|-h)
            usage
            exit 0
            ;;
        --verbose|-v)
            VERBOSE=-v
            ;;
        --output|-o)
            [ $# -ge 2 ] || die_usage "$1 needs an argument"
            OUTISO="$2"
            shift
            ;;
        --force-overwrite)
            FORCE_OVERWRITE=1
            ;;
        -V)
            [ $# -ge 2 ] || die_usage "$1 needs an argument"
            VOLID="$2"
            shift
            ;;
        --netinstall)
            DOREPO=0
            ;;
        --srcurl)
            [ $# -ge 2 ] || die_usage "$1 needs an argument"
            SRCURL="$2"
            shift
            ;;
        -D|--define-repo)
            [ $# -ge 2 ] || die_usage "$1 needs an argument"
            case "$2" in
                *!*)
                    nick="${2%!*}"
                    url="${2#*!}"
                    ;;
                *)
                    die "$1 argument must have 2 parts separated by a '!'"
                    ;;
            esac
            CUSTOM_REPOS["$nick"]="$url"
            shift
            ;;
        --sign)
            [ $# -ge 3 ] || die_usage "$1 needs 2 arguments"
            KEYNICK="$2"
            KEYID="$3"
            shift 2
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
[ -n "$VOLID" ] || die_usage "volume ID must be specified (-V)"
[ -n "$OUTISO" ] || die_usage "output filename must be specified (--output)"
if [ "$FORCE_OVERWRITE" = 0 -a -e "$OUTISO" ]; then
    die "'$OUTISO' exists, use --force-overwrite to proceed regardless"
fi
[ ! -d "$OUTISO" ] || die "'$OUTISO' exists and is a directory"

if [ $DOREPO = 0 -a -n "$KEYID" ]; then
    die_usage "signing key is useless on netinstall media"
fi

parse_config_search_path "$1"
DIST="$(basename ${CFG_SEARCH_PATH[0]})"
INSTALLIMG="$2"

[ -z "$VERBOSE" ] || set -x

maybe_set_srcurl "$DIST"
test -r "$INSTALLIMG" || die "cannot read '$INSTALLIMG' for install.img"

command -v genisoimage >/dev/null || die "required tool not found: genisoimage"
command -v isohybrid >/dev/null || die "required tool not found: isohybrid (syslinux)"
command -v createrepo_c >/dev/null || die "required tool not found: createrepo_c"
[ -z "$KEYID" ] || command -v gpg1 >/dev/null || die "required tool not found: gpg1 (gnupg1)"

MKIMAGE=$(command -v grub2-mkimage || command -v grub-mkimage) || die "could not find grub[2]-mkimage"
if [[ "$($MKIMAGE --version)" =~ ".*2.02" ]]; then
    die "$MKIMAGE is too old, make sure to have 2.06 installed (XCP-ng package grub-tools)"
fi

if command -v faketime >/dev/null; then
    FAKETIME=(faketime "2000-01-01 00:00:00")
else
    echo 2>&1 "WARNING: tool not found, disabling support: faketime (libfaketime)"
    FAKETIME=()
fi

ISODIR=$(mktemp -d "$TMPDIR/installiso.XXXXXX")

# temporary for storing downloaded files etc
SCRATCHDIR=$(mktemp -d "$TMPDIR/tmp.XXXXXX")

setup_yum_download "$DIST" "$RPMARCH" "$SRCURL"


## put all bits together

test -d "$topdir/templates/iso/$DIST" || die "cannot find dir '$topdir/templates/iso/$DIST'"

# bootloader config files etc. - like "cp -r *", not forgetting .treeinfo
tar -C "$topdir/templates/iso/$DIST" -cf - . | tar -C "$ISODIR/" -xf - ${VERBOSE}

# initrd
cp ${VERBOSE} -a "$INSTALLIMG" $ISODIR/install.img

# kernel from rpm
get_rpms "$SCRATCHDIR" kernel
rpm2cpio $SCRATCHDIR/kernel-*.rpm | (cd $ISODIR && cpio ${VERBOSE} -idm "*vmlinuz*")
rm ${VERBOSE} $ISODIR/boot/vmlinuz-*-xen
mv ${VERBOSE} $ISODIR/boot/vmlinuz-* $ISODIR/boot/vmlinuz

# alt kernel from rpm
get_rpms "$SCRATCHDIR" kernel-alt
rpm2cpio $SCRATCHDIR/kernel-alt-*.rpm | (cd $ISODIR && cpio ${VERBOSE} -idm "*vmlinuz*")
rm ${VERBOSE} $ISODIR/boot/vmlinuz-*-xen
mkdir ${VERBOSE} $ISODIR/boot/alt
mv ${VERBOSE} $ISODIR/boot/vmlinuz-* $ISODIR/boot/alt/vmlinuz

# xen from rpm
get_rpms "$SCRATCHDIR" xen-hypervisor
rpm2cpio $SCRATCHDIR/xen-hypervisor-*.rpm | (cd $ISODIR && cpio ${VERBOSE} -idm "*xen*gz")
mv ${VERBOSE} $ISODIR/boot/xen-*-d.gz $ISODIR/boot/xen.gz
rm ${VERBOSE} $ISODIR/boot/xen-*.gz


# Memtest86
get_rpms "$SCRATCHDIR" memtest86+
rpm2cpio $SCRATCHDIR/memtest86+-*.rpm | (cd $ISODIR && cpio ${VERBOSE} -idm "./boot/*")
if [ ! -r $ISODIR/boot/memtest.bin ]; then
    # older 5.x packaging
    mv ${VERBOSE} $ISODIR/boot/memtest86+-* $ISODIR/boot/memtest.bin
fi


# optional local repo

sed -i "s,@@TIMESTAMP@@,$(date +%s.00)," \
    $ISODIR/.treeinfo

if [ $DOREPO = 1 ]; then
    mkdir ${VERBOSE} "$ISODIR/Packages"

    get_rpms --depends "$ISODIR/Packages" xcp-ng-deps kernel-alt

    createrepo_c ${VERBOSE} "$ISODIR"
    if [ -n "$KEYID" ]; then
        gpg1 ${VERBOSE} --default-key="$KEYID" --armor --detach-sign "$ISODIR/repodata/repomd.xml"
	gpg1 ${VERBOSE} --armor -o "$ISODIR/RPM-GPG-KEY-$KEYNICK" --export "$KEYID"
	[ -z "$VERBOSE" ] || echo "using key RPM-GPG-KEY-$KEYNICK in .treeinfo"
	sed -i "s,key1 = .*,key1 = RPM-GPG-KEY-$KEYNICK," \
	    $ISODIR/.treeinfo
    else
	# installer checks if keys are here even when verification is disabled
	[ -z "$VERBOSE" ] || echo "disabling keys in .treeinfo"
	sed -i "s,^key,#key," \
	    $ISODIR/.treeinfo

	# don't try to validate repo sig if we put none
	[ -z "$VERBOSE" ] || echo "adding no-repo-gpgcheck to boot/isolinux/isolinux.cfg boot/grub/grub*.cfg"
	sed -i "s,/vmlinuz,/vmlinuz no-repo-gpgcheck," \
	    $ISODIR/boot/isolinux/isolinux.cfg \
	    $ISODIR/boot/grub/grub*.cfg
    fi
else
    # no repo
    # FIXME: should be generated above instead?
    rm ${VERBOSE} "$ISODIR/.treeinfo"

    # FIXME: trigger netinstall mode?
fi


# BIOS bootloader: isolinux from rpm

get_rpms "$SCRATCHDIR" syslinux
mkdir "$SCRATCHDIR/syslinux"
rpm2cpio $SCRATCHDIR/syslinux-*.rpm | (cd "$SCRATCHDIR/syslinux" && cpio ${VERBOSE} -idm "./usr/share/syslinux/*")

cp ${VERBOSE} -p \
   "$SCRATCHDIR/syslinux/usr/share/syslinux/isolinux.bin" \
   "$SCRATCHDIR/syslinux/usr/share/syslinux/mboot.c32" \
   "$SCRATCHDIR/syslinux/usr/share/syslinux/menu.c32" \
   \
   $ISODIR/boot/isolinux/


## create final ISO

if false; then
    # grub-mkrescue is "the reference", providing largest platform
    # support for booting, but OTOH adds tons of stuff we don't need
    # at all. It was used as a reference to implement UEFI boot, and
    # is kept handy for when we need it, since the command options are
    # not that obvious. Eg. we may want to add support for x86 Macs
    # some day.

    MKRESCUE=$(command -v grub2-mkrescue || command -v grub-mkrescue) || die "could not find grub[2]-mkrescue"
    # grub2-mkrescue (centos) vs. grub-mkrescue (debian, RoW?)
    #strace -f -o /tmp/log -s 4096
    "$MKRESCUE" \
	--locales= \
	--modules= \
	--product-name="XCP-ng" --product-version="$DIST" \
	\
	-v \
	-follow-links \
	-r -J --joliet-long -V "$VOLID" -input-charset utf-8 \
	-c boot/isolinux/boot.cat -b boot/isolinux/isolinux.bin \
	-no-emul-boot -boot-load-size 4 -boot-info-table \
    \
	-o "$OUTISO" $ISODIR

else
    # UEFI bootloader

    BOOTX64=$(mktemp "$TMPDIR/bootx64-XXXXXX.efi")

    # unpack grub-efi.rpm
    get_rpms "$SCRATCHDIR" grub-efi
    mkdir "$SCRATCHDIR/grub"
    rpm2cpio $SCRATCHDIR/grub-efi-*.rpm | (cd "$SCRATCHDIR/grub" && cpio ${VERBOSE} -idm)

    "$MKIMAGE" --directory "$SCRATCHDIR/grub/usr/lib/grub/x86_64-efi" --prefix '()/boot/grub' \
	       $VERBOSE \
	       --output "$BOOTX64" \
	       --format 'x86_64-efi' --compression 'auto' \
	       'part_gpt' 'part_msdos' 'part_apple' 'iso9660'
    "${FAKETIME[@]}" mformat -i "$ISODIR/boot/efiboot.img" -N 0 -C -f 2880 -L 16 ::.
    "${FAKETIME[@]}" mmd     -i "$ISODIR/boot/efiboot.img" ::/efi ::/efi/boot
    "${FAKETIME[@]}" mcopy   -i "$ISODIR/boot/efiboot.img" "$BOOTX64" ::/efi/boot/bootx64.efi

    # grub modules
    # FIXME: too many modules?
    tar -C "$SCRATCHDIR/grub/usr/lib" -cf - grub/x86_64-efi | tar -C "$ISODIR/boot" -xf - ${VERBOSE}

    genisoimage \
        -o "$OUTISO" \
	${VERBOSE:- -quiet} \
        -r -J --joliet-long -V "$VOLID" -input-charset utf-8 \
        -c boot/isolinux/boot.cat -b boot/isolinux/isolinux.bin \
        -no-emul-boot -boot-load-size 4 -boot-info-table \
        -no-emul-boot \
	-eltorito-alt-boot --efi-boot boot/efiboot.img \
        $ISODIR
    isohybrid ${VERBOSE} --uefi "$OUTISO"
fi
