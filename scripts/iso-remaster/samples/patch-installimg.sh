#!/bin/sh
set -ex

#HOME=/data

# unpacked rootfs to modify
INSTALLIMG="$1"

# # Include a locally-modified version of the installer for testing
# HOSTINSTALLER=$HOME/src/xs/host-installer
# if [ -r "$HOSTINSTALLER"/Makefile ]; then
#     # >= 8.3
#     make -C "$HOSTINSTALLER" DESTDIR="$INSTALLIMG" XS_MPATH_CONF="$HOME/src/xapi/sm/multipath/multipath.conf"
# else
#     # if 8.2: Use cp until make install is available. It copies a few unnecessary files, but this is harmless.
#     cp -rv "$HOSTINSTALLER"/* "$INSTALLIMG/opt/xensource/installer/"
# fi

# # Install extra packages - use `rpm` not `yum`, as we had to use `rpm
# # --nodeps` during image creation and `yum` will now go on strike.
# # Luckily `yumdownloader` still works.
# # FIXME: in its current form, his hackish snippet is only expected to work
# # in the xcp-ng build-env container
# 
# DLDIR="$(cd $INSTALLIMG && mktemp -d)"
# trap "rm -r '$INSTALLIMG/$DLDIR'" EXIT INT
# 
# yumdownloader --installroot="$INSTALLIMG" --destdir="$INSTALLIMG/$DLDIR" --resolve yum-utils -y
# RPMS=$(cd $INSTALLIMG/$DLDIR && echo *.rpm)
# fakechroot sh -c "cd $INSTALLIMG/$DLDIR && rpm --root='$INSTALLIMG' --install $RPMS"
