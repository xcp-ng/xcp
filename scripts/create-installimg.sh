#! /bin/bash
set -eE

mydir=$(dirname $0)
topdir=$mydir/..

. "$mydir/lib/misc.sh"

usage() {
    cat <<EOF
Usage: $0 [<options>] <dist>

Options:
    --srcurl <URL>            get RPMs from repo at <URL>
    -o <OUTPUT.IMG>	      choose a different output name
    -v|--verbose	      be talkative
EOF
}

mockdir=$topdir/mock-configs

VERBOSE=
OUTPUTIMG=
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
        --srcurl)
            [ $# -ge 2 ] || die_usage "$1 needs an argument"
            SRCURL="$2"
            shift
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

[ $# = 1 ] || die_usage "need exactly 1 non-option argument"

[ -z "$VERBOSE" ] || set -x

DIST="$1"
[ -r "$mockdir/$DIST-$RPMARCH.cfg" ] || die "cannot find config for '$DIST-$RPMARCH'"
maybe_set_srcurl "$DIST"
[ -n "$OUTPUT_IMG" ] || OUTPUT_IMG="install-$DIST-$RPMARCH.img"

command -v mock >/dev/null || die "required tool not found: mock"
command -v bsdtar >/dev/null || die "required tool not found: bsdtar"


#### create base rootfs

# FIXME should allow to select repos - use jinja tricks?
MOCK=(
    mock
    --configdir="$topdir/mock-configs"
    --config-opts=srcurl="$SRCURL"
    --config-opts=target_arch="$RPMARCH"
    -r "$DIST-$RPMARCH"
    # non-$VERBOSE is -q, $VERBOSE is default, mock's -v would be debug
    $([ -n "$VERBOSE" ] || printf -- "-q")
)

${MOCK[@]} --clean
${MOCK[@]} --scrub=root-cache
${MOCK[@]} --init


### removal of abusively-pulled packages (list manually extracted as
### packages not in 8.2.1 install.img)

${MOCK[@]} --shell -- rpm --nodeps --erase binutils dracut gpg-pubkey pkgconfig xen-hypervisor


### removal of misc stuff

# > 100KB
BINS="systemd-analyze systemd-nspawn journalctl machinectl dgawk loginctl ssh-keyscan pgawk busctl systemd-run"
BINS+=" ssh-agent timedatectl systemd-cgls localectl hostnamectl systemd-inhibit info oldfind coredumpctl"
SBINS="pdata_tools oxenstored ldconfig build-locale-archive glibc_post_upgrade.x86_64 sln install-info"
BINPATHS=$(
    for i in $BINS; do echo /usr/bin/$i; done
    for i in $SBINS; do echo /usr/sbin/$i; done
	)


# FIXME decide what to do with those
DOUBTFUL=""
# if we want to use craklib why remove this, if we don't why not remove the rest
DOUBTFUL+=" /usr/share/cracklib"
# similarly, there are other files - maybe those are just the source file?
DOUBTFUL+=" /usr/lib/udev/hwdb.d/"

${MOCK[@]} --shell -- find /usr -name "*.py[co]" -delete
${MOCK[@]} --shell -- rm -r \
      /usr/share/locale /usr/lib/locale /usr/share/i18n/locales \
      /usr/libexec/xen/boot \
      $BINPATHS \
      $DOUBTFUL \
      /usr/share/bash-completion


### extra stuff

# /init for initrd
${MOCK[@]} --shell -- ln -s /sbin/init /init

# files specific to the install image
(cd "$topdir/installimg/$DIST" && find . | cpio -o) | ${MOCK[@]} --shell -- "cd / && cpio -idm ${VERBOSE}"

# FIXME why ?
${MOCK[@]} --shell -- ": > /etc/yum/yum.conf"

# installer branding - FIXME should be part of host-installer.rpm
${MOCK[@]} --shell -- ln -sr /EULA "/opt/xensource/installer/"
${MOCK[@]} --shell -- ln -sr /usr/lib/python2.7/site-packages/xcp/branding.py \
	   "/opt/xensource/installer/version.py"


### services

case "$DIST" in
    8.2.1)
	# FIXME do we really want to stick to 8.2.1 here?
	INSTALLERGETTY=getty@tty2.service
	;;
    *)
	INSTALLERGETTY=installer-getty@tty2.service
	;;
esac

${MOCK[@]} --shell -- systemctl enable installer "$INSTALLERGETTY"

${MOCK[@]} --shell -- systemctl disable \
	   getty@tty1 fcoe lldpad xen-init-dom0 xenconsoled xenstored chronyd chrony-wait


### repack cache into .img

# send all our changes to cache (yes the bad doc says it is not necessary)
${MOCK[@]} --cache-alterations --shell -- true

# note: no official mock interface
CACHE="/var/cache/mock/$DIST-$RPMARCH/root_cache/cache.tar.gz"

# convert tarball into compressed-cpio
ROOTFS=$(mktemp -d)
CLEANUP_DIRS+=("$ROOTFS")
# FIXME replace bzip with better algo
fakeroot sh -c "cd '$ROOTFS' && tar -xf '$CACHE' && find . | cpio -o -H newc" | bzip2 > "$OUTPUT_IMG"

# cleanup for disk space
${MOCK[@]} --clean
