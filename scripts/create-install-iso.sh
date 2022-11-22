#! /bin/bash
set -e

mydir=$(dirname $0)
topdir=$mydir/..

. "$mydir/lib/misc.sh"

usage() {
    cat <<EOF
Usage: $0 [<options>] <dist> <install.img> <output-iso>

Options:
    -V <VOLID>                (mandatory) ISO volume ID
    --srcurl <URL>            get RPMs from repo at <URL>
    --netinstall              do not include repository in ISO
    --sign <NICK> <KEYID>     sign repomd with default gpg key <KEYID>, with readable <NICK>
    --verbose		      be talkative
EOF
}

VERBOSE=
DOREPO=1
KEYID=
KEYNICK=
SRCURL=
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

[ $# = 3 ] || die_usage "need exactly 3 non-option arguments"
[ -n "$VOLID" ] || die_usage "volume ID must be specified (-V)"
if [ $DOREPO = 0 -a -n "$KEYID" ]; then
    die_usage "signing key is useless on netinstall media"
fi

[ -z "$VERBOSE" ] || set -x

DIST="$1"
INSTALLIMG="$2"
OUTISO="$3"

maybe_set_srcurl "$DIST"
test -r "$INSTALLIMG" || die "cannot read '$INSTALLIMG' for install.img"

command -v genisoimage >/dev/null || die "required tool not found: genisoimage"

ISODIR=$(mktemp -d installiso.XXXXXX)
CLEANUP_DIRS+=("$ISODIR")

# temporary for storing downloaded files etc
SCRATCHDIR=$(mktemp -d tmp.XXXXXX)
CLEANUP_DIRS+=("$SCRATCHDIR")

setup_dnf_download "$DIST" "$RPMARCH" "$SRCURL"


## put all bits together

# bootloader config files etc. - like "cp -r", not forgetting .treeinfo
(cd "$topdir/iso/$DIST" && find .) | cpio -pdm -D "$topdir/iso/$DIST" ${VERBOSE} $ISODIR/

# initrd
cp ${VERBOSE} -a "$INSTALLIMG" $ISODIR/install.img

# kernel from rpm
"${DNF[@]}" --downloadonly --downloaddir="$SCRATCHDIR" \
        download kernel
rpm2cpio $SCRATCHDIR/kernel-*.rpm | (cd $ISODIR && cpio ${VERBOSE} -idm "*vmlinuz*")
rm ${VERBOSE} $ISODIR/boot/vmlinuz-*-xen
mv ${VERBOSE} $ISODIR/boot/vmlinuz-* $ISODIR/boot/vmlinuz

# alt kernel from rpm
"${DNF[@]}" --downloadonly --downloaddir="$SCRATCHDIR" \
        download kernel-alt
rpm2cpio $SCRATCHDIR/kernel-alt-*.rpm | (cd $ISODIR && cpio ${VERBOSE} -idm "*vmlinuz*")
rm ${VERBOSE} $ISODIR/boot/vmlinuz-*-xen
mkdir ${VERBOSE} $ISODIR/boot/alt
mv ${VERBOSE} $ISODIR/boot/vmlinuz-* $ISODIR/boot/alt/vmlinuz

# xen from rpm
"${DNF[@]}" --downloadonly --downloaddir="$SCRATCHDIR" \
        download xen-hypervisor
rpm2cpio $SCRATCHDIR/xen-hypervisor-*.rpm | (cd $ISODIR && cpio ${VERBOSE} -idm "*xen*gz")
rm ${VERBOSE} $ISODIR/boot/xen-*-d.gz
mv ${VERBOSE} $ISODIR/boot/xen-*.gz $ISODIR/boot/xen.gz


# Memtest86(+)
# FIXME use our own package

# FIXME does not boot in UEFI mode
"${DNF[@]}" --downloadonly --downloaddir="$SCRATCHDIR" \
	    download memtest86+
#(cd "$SCRATCHDIR" && wget http://www.rpmfind.net/linux/centos-stream/9-stream/AppStream/x86_64/os/Packages/memtest86+-5.31-0.4.beta.el9.x86_64.rpm)
rpm2cpio $SCRATCHDIR/memtest86+-*.rpm | (cd $ISODIR && cpio ${VERBOSE} -idm "./boot/*")
mv ${VERBOSE} $ISODIR/boot/memtest* $ISODIR/boot/isolinux/memtest
mv ${VERBOSE} $ISODIR/boot/elf-memtest* $ISODIR/boot/elf-memtest

#[ -z "$VERBOSE" ] || echo "fixing memtest path in boot/isolinux/isolinux.cfg"
#sed -i "s,KERNEL memtest,KERNEL /boot/memtest," \
#    $ISODIR/boot/isolinux/isolinux.cfg


# optional local repo

if [ $DOREPO = 1 ]; then
    mkdir ${VERBOSE} "$ISODIR/Packages"

    "${DNF[@]}" --downloadonly --downloaddir="$ISODIR/Packages" \
        download --resolve xcp-ng-deps

    createrepo ${VERBOSE} "$ISODIR"
    if [ -n "$KEYID" ]; then
        gpg1 ${VERBOSE} --default-key="$KEYID" --armor --sign "$ISODIR/repodata/repomd.xml"
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

"${DNF[@]}" --downloadonly --downloaddir="$SCRATCHDIR" \
	    download syslinux
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

    MKIMAGE=$(command -v grub2-mkimage || command -v grub-mkimage) || die "could not find grub[2]-mkimage"
    BOOTX64=$(mktemp bootx64-XXXXXX.efi)
    CLEANUP_FILES+=("$BOOTX64")

    # unpack grub-efi.rpm
    "${DNF[@]}" --downloadonly --downloaddir="$SCRATCHDIR" \
		download grub-efi
    mkdir "$SCRATCHDIR/grub"
    rpm2cpio $SCRATCHDIR/grub-efi-*.rpm | (cd "$SCRATCHDIR/grub" && cpio ${VERBOSE} -idm)

    "$MKIMAGE" --directory "$SCRATCHDIR/grub/usr/lib/grub/x86_64-efi" --prefix '()/boot/grub' \
	       $VERBOSE \
	       --output "$BOOTX64" \
	       --format 'x86_64-efi' --compression 'auto' \
	       'part_gpt' 'part_msdos' 'part_apple' 'iso9660'
    mformat -i "$ISODIR/boot/efiboot.img" -C -f 2880 -L 16 ::.
    mmd     -i "$ISODIR/boot/efiboot.img" ::/efi ::/efi/boot
    mcopy   -i "$ISODIR/boot/efiboot.img" "$BOOTX64" ::/efi/boot/bootx64.efi

    # grub modules
    # FIXME: too many modules?
    (cd "$SCRATCHDIR/grub/usr/lib" && find grub/x86_64-efi) |
	cpio -pdm -D "$SCRATCHDIR/grub/usr/lib" "$ISODIR/boot"

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
