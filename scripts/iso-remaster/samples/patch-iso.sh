#! /bin/bash
set -e

ISODIR="$1"

## remove existing repo sig
#rm -fv "$ISODIR/repodata/repomd.xml.asc"

## remove old repo metadata
#rm -r "$ISODIR/repodata/"


## example: customize theme
## remove old rpms
#for p in $(cat <<EOF
#                xcp-ng-plymouth-theme-1.0.0-7.xcpng8.3.noarch.rpm
#                xcp-ng-release-8.3.0-2.x86_64.rpm
#                xcp-ng-release-config-8.3.0-2.x86_64.rpm
#                xcp-ng-release-presets-8.3.0-2.x86_64.rpm
#                xsconsole-10.1.13-1.xcpng8.3.x86_64.rpm
#EOF
#          )
#do
#    rm "$ISODIR/Packages/$p"
#done
#
## add the new ones
#for p in $(cat <<EOF
#                xcp-ng-plymouth-theme-1.0.0-7.xcpng8.3+newtheme1.noarch.rpm
#                xcp-ng-release-8.3.0-2+newtheme1.x86_64.rpm
#                xcp-ng-release-config-8.3.0-2+newtheme1.x86_64.rpm
#                xcp-ng-release-presets-8.3.0-2+newtheme1.x86_64.rpm
#                xsconsole-10.1.13-1.xcpng8.3+newtheme2.x86_64.rpm
#EOF
#          )
#do
#    cp "$HOME/newtheme/$p" "$ISODIR/Packages/"
#done
#
## installer splash
#cp "$HOME/src/xcp/iso/8.3/boot/isolinux/splash.lss" "$ISODIR/boot/isolinux/"


## regenerate repodata
#createrepo_c "$ISODIR"

## patches to kernel commandline
SED_COMMANDS=()
# harmless no-op substitution in case no other is added
SED_COMMANDS+=(-e "s@^@@")

# add `no-repo-gpgcheck` so a modified repo will be accepted
#SED_COMMANDS+=(-e "s@/vmlinuz@/vmlinuz no-repo-gpgcheck@")
#SED_COMMANDS+=(-e "s@/vmlinuz@/vmlinuz network_device=lacp:members=eth0,eth1@")
#SED_COMMANDS+=(-e "s@/vmlinuz@/vmlinuz install answerfile=http://pxe/configs/custom/ydi/lacp.xml@")
#SED_COMMANDS+=(-e "s@/vmlinuz@/vmlinuz atexit=shell@")

sed -i "${SED_COMMANDS[@]}" \
    "$ISODIR"/*/*/grub*.cfg \
    "$ISODIR"/boot/isolinux/isolinux.cfg

## sign with a different key
#gpg1 --armor --detach-sign "$ISODIR/repodata/repomd.xml"
#gpg1 --armor --export > "$ISODIR/RPM-GPG-KEY-xcpng"
