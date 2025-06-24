#! /bin/bash
set -e

ISODIR="$1"

# patches to kernel commandline
SED_COMMANDS=()
# harmless no-op substitution in case no other is added
SED_COMMANDS+=(-e "s@^@@")

# # update some RPMs:
# # * remove old repo metadata
# rm -r "$ISODIR/repodata/"
# # * replace RPMs
# cp -p ~/my/Packages/*.rpm "$ISODIR/Packages/"
# # * regenerate repo metadata
# createrepo_c "$ISODIR"
# # * add `no-repo-gpgcheck` so a modified repo will be accepted
# SED_COMMANDS+=(-e "s@/vmlinuz@/vmlinuz no-repo-gpgcheck@")

# # prevent any reboot on installer error to allow investigating
# SED_COMMANDS+=(-e "s@/vmlinuz@/vmlinuz atexit=shell@")

# # activate ssh to installer with given password, eg. to collect logs
# SED_COMMANDS+=(-e "s@/vmlinuz@/vmlinuz network_device=all sshpassword=passw0rd@")

# # get an answerfile over the network
# SED_COMMANDS+=(-e "s@/vmlinuz@/vmlinuz install answerfile=http://pxe/configs/preset.xml@")

sed -i "${SED_COMMANDS[@]}" \
    "$ISODIR"/*/*/grub*.cfg \
    "$ISODIR"/boot/isolinux/isolinux.cfg

# # sign with a different key (needs more work)
# gpg1 --armor --detach-sign "$ISODIR/repodata/repomd.xml"
# gpg1 --armor --export > "$ISODIR/RPM-GPG-KEY-xcpng"
