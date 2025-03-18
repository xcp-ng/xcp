#!/bin/sh
set -e

# unpacked rootfs to modify
INSTALLIMG="$1"

## Include a locally-modified version of the installer for testing
#HOSTINSTALLER=$HOME/src/xs/host-installer
## - if 8.2: copies a few files too much until we can "make install", but that's harmless
#cp -rv "$HOSTINSTALLER"/* "$INSTALLIMG/opt/xensource/installer/"
## - if 8.3
#make -C "$HOSTINSTALLER" DESTDIR="$INSTALLIMG" XS_MPATH_CONF="$HOME/src/xapi/sm/multipath/multipath.conf"

## Install extra packages - use `rpm` not `yum`, as we had to use `rpm
## --nodeps` during image creation and `yum` will now go on strike.
## Luckily `yumdownloader` still works.
#
#DLDIR="$(mktemp -d)"
#trap "rm -r '$DLDIR'" EXIT INT
#
#yumdownloader --installroot="$INSTALLIMG" --destdir="$DLDIR" --resolve --enablerepo=epel ndisc6 -y
#fakechroot rpm --root="$INSTALLIMG" --install "$DLDIR/*.rpm"
