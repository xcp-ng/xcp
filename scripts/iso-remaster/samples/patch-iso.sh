#! /bin/sh
set -e

ISODIR="$1"

## remove existing repo sig
#rm -fv "$ISODIR/repodata/repomd.xml.asc"

## remove old repo metadata
rm -r "$ISODIR/repodata/"


## example: customize theme
if false; then
    # remove old rpms
    for p in $(cat <<EOF
                    xcp-ng-plymouth-theme-1.0.0-7.xcpng8.3.noarch.rpm
                    xcp-ng-release-8.3.0-2.x86_64.rpm
                    xcp-ng-release-config-8.3.0-2.x86_64.rpm
                    xcp-ng-release-presets-8.3.0-2.x86_64.rpm
                    xsconsole-10.1.13-1.xcpng8.3.x86_64.rpm
EOF
              )
    do
        rm "$ISODIR/Packages/$p"
    done

    # add the new ones
    for p in $(cat <<EOF
                    xcp-ng-plymouth-theme-1.0.0-7.xcpng8.3+newtheme1.noarch.rpm
                    xcp-ng-release-8.3.0-2+newtheme1.x86_64.rpm
                    xcp-ng-release-config-8.3.0-2+newtheme1.x86_64.rpm
                    xcp-ng-release-presets-8.3.0-2+newtheme1.x86_64.rpm
                    xsconsole-10.1.13-1.xcpng8.3+newtheme2.x86_64.rpm
EOF
              )
    do
        cp "$HOME/newtheme/$p" "$ISODIR/Packages/"
    done

    # installer splash
    cp "$HOME/src/xcp/iso/8.3/boot/isolinux/splash.lss" "$ISODIR/boot/isolinux/"
fi


## regenerate repodata
createrepo "$ISODIR"

# FIXME: could patch isolinux and grub kernel cmdline to add
# `no-repo-gpgcheck` so a modified repo will be accepted


## sign with a different key
#gpg --armor --sign "$ISODIR/repodata/repomd.xml"
