#! /bin/bash
set -eE
set -o pipefail

mydir=$(dirname $0)
topdir=$mydir/..

. "$mydir/lib/misc.sh"

usage() {
    cat <<EOF
Usage: $0 [<options>] <base-config>[:<config-overlay>]*

Options:
    --srcurl <URL>            get RPMs from repo at <URL>
    -D|--define-repo <NICK>!<URL>
                              add yum repo with name <NICK> and base URL <URL>
    --output|-o <OUTPUT.IMG>  choose a different output name
    --force-overwrite         don't abort if output file already exists
    -v|--verbose	      be talkative
EOF
}

VERBOSE=
OUTPUT_IMG=
FORCE_OVERWRITE=0
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
        --output|-o)
            [ $# -ge 2 ] || die_usage "$1 needs an argument"
            OUTPUT_IMG="$2"
            shift
            ;;
        --force-overwrite)
            FORCE_OVERWRITE=1
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
parse_config_search_path "$1"
DIST="$(basename ${CFG_SEARCH_PATH[0]})"

[ -z "$VERBOSE" ] || set -x

maybe_set_srcurl "$DIST"
[ -n "$OUTPUT_IMG" ] || die_usage "output filename must be specified (--output)"
if [ "$FORCE_OVERWRITE" = 0 -a -e "$OUTPUT_IMG" ]; then
    die "'$OUTPUT_IMG' exists, use --force-overwrite to proceed regardless"
fi
[ ! -d "$OUTPUT_IMG" ] || die "'$OUTPUT_IMG' exists and is a directory"

command -v yum >/dev/null || die "required tool not found: yum"
#command -v fakeroot >/dev/null || die "required tool not found: fakeroot"


#### create base rootfs

# expand template
YUMCONF=$(mktemp "$TMPDIR/yum-XXXXXX.conf")
YUMREPOSD=$(mktemp -d "$TMPDIR/yum-repos-XXXXXX.d")
YUMCONF_TMPL=$(find_config yum.conf.tmpl)
cat "$YUMCONF_TMPL" |
    sed \
    -e "s,@@YUMREPOSD@@,$YUMREPOSD," \
    > "$YUMCONF"
[ -z "$VERBOSE" ] || cat "$YUMCONF"

find_all_configs yum-repos.conf.tmpl | while read YUMREPOSCONF_TMPL; do
    reponame=$(basename $(dirname "$YUMREPOSCONF_TMPL"))
    cat "$YUMREPOSCONF_TMPL" |
        sed \
            -e "s,@@SRCURL@@,$SRCURL," \
            -e "s,@@RPMARCH@@,$RPMARCH," \
            > "$YUMREPOSD/$reponame.repo"
done
[ -z "$VERBOSE" ] || ls "$YUMREPOSD"

ROOTFS=$(mktemp -d "$TMPDIR/rootfs-XXXXXX")
YUMFLAGS=(
    --config="$YUMCONF"
    --installroot="$ROOTFS"
    # non-$VERBOSE is -q, $VERBOSE is default, yum's -v would be debug
    $([ -n "$VERBOSE" ] || printf -- "-q")
)

# summary of repos
yum ${YUMFLAGS[@]} repolist all

PACKAGES_LST=$(find_config packages.lst)
xargs < "$PACKAGES_LST" \
    yum ${YUMFLAGS[@]} install \
        --assumeyes \
        --noplugins

### removal of abusively-pulled packages (list manually extracted as
### packages not in 8.2.1 install.img)

rpm --root="$ROOTFS" --nodeps --erase \
    binutils dracut gpg-pubkey pkgconfig xen-hypervisor


### removal of misc stuff

# > 100KB
BINS="systemd-analyze systemd-nspawn journalctl machinectl dgawk loginctl ssh-keyscan pgawk busctl systemd-run"
BINS+=" ssh-agent timedatectl systemd-cgls localectl hostnamectl systemd-inhibit info oldfind coredumpctl"
SBINS="pdata_tools oxenstored ldconfig build-locale-archive glibc_post_upgrade.x86_64 sln install-info"
MOREFILES=" \
	/boot \
	/usr/share/locale /usr/lib/locale /usr/share/i18n/locales \
        /usr/libexec/xen/boot \
        /usr/share/bash-completion \
"

# FIXME decide what to do with those doubtbul ones:

# if we want to use craklib why remove this, if we don't why not remove the rest
MOREFILES+=" /usr/share/cracklib"
# similarly, there are other files - maybe those are just the source file?
MOREFILES+=" /usr/lib/udev/hwdb.d/"

RMPATHS=$(
    for i in $BINS; do echo $ROOTFS/usr/bin/$i; done
    for i in $SBINS; do echo $ROOTFS/usr/sbin/$i; done
    for i in $MOREFILES; do echo $ROOTFS/$i; done
       )

rm -r $VERBOSE $RMPATHS
find $ROOTFS/usr -name "*.py[co]" -delete


### extra stuff

# /init for initrd
ln -sf /sbin/init $ROOTFS/init

# files specific to the install image
(cd "$topdir/templates/installimg/$DIST" && find . | cpio -o) | (cd $ROOTFS && cpio -idm --owner=root:root ${VERBOSE})

# FIXME ignored
: > $ROOTFS/etc/yum/yum.conf

# installer branding - FIXME should be part of host-installer.rpm
ln -s ../../../EULA "$ROOTFS/opt/xensource/installer/"
ln -s ../../../usr/lib/python2.7/site-packages/xcp/branding.py \
	   "$ROOTFS/opt/xensource/installer/version.py"


### services

case "$DIST" in
    8.2)
	INSTALLERGETTY=getty@tty2.service
	;;
    *)
	INSTALLERGETTY=installer-getty@tty2.service
	;;
esac

systemctl --root=$ROOTFS enable installer "$INSTALLERGETTY"

systemctl --root=$ROOTFS disable \
	   getty@tty1 fcoe lldpad xen-init-dom0 xenconsoled xenstored chronyd chrony-wait

### final cleanups
rm -rf $ROOTFS/var/lib/yum/{yumdb,history} $ROOTFS/var/cache/yum

### repack cache into .img
# make sure bzip2 doesn't leave an invalid output if its input command fails
trap "rm -f $OUTPUT_IMG" ERR
# FIXME replace bzip with better algo
(
    set -o pipefail
    cd "$ROOTFS"
    find . | cpio -o -H newc
) | bzip2 > "$OUTPUT_IMG"
