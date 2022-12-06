## How to build XCP-ng ISO

Note: some parts of this file are not up to date anymore, but it still contains
valuable information so it is kept for now.

### Splash image and other

In your ISO folder, you need to create a `boot/isolinux` and add:

* `pg_help`
* `pg_main`
* `splash.lss` (see below)

In the root SO folder:

* `.treeinfo`

To generate the splash image (`boot/isolinux/splash.lss`), you need:

* a 640x240 banner
* In Gimp: Image/mode/index colors/14 (=16 including B&W)
* export in gif format, ie `splash.gif`
* `giftopnm < splash.gif > splash.ppm`
* `ppmtolss16 < splash.ppm > splash.lss`

> Note: in Fedora/CentOS/RH like, those packages are needed to create the splash image:

* `syslinux-perl`
* `netpbm-progs`

### Create repodata

Go into the future ISO folder, and run `createrepo` using the `groups.xml` in this repo:


```
# createrepo . -o . -g ../groups.xml
```

### install.img modification

1. `bzip2 -d install.img`
2. `mkdir tmp && cd tmp && cpio -id < ../install.img.out`
3. Edit your files
4. As root (because of some read-protected files such as etc/gshadow-): `find . | cpio --create --format='newc' > /tmp/newinstall`
5. `bzip2 /tmp/newinstall`
6. `mv /tmp/newinstall /tmp/install.img`
7. Replace it into the ISO

### ISO generation

You need `genisoimage` program.

Usage:

```
# cd isofolder/
# genisoimage -o ../xcpng.iso -v -r -J -V "XCP-ng 7.4" -c boot/isolinux/boot.cat -b boot/isolinux/isolinux.bin -no-emul-boot -boot-load-size 4 -boot-info-table -eltorito-alt-boot -e boot/efiboot.img -no-emul-boot .
```

This will create a `xcpng.iso` file into your parent directory.

To get the ISO bootable on USB:

```
# isohybrid --uefi xcpng.iso
```
### Write the ISO to a USB key

```
# dd if=xcpng.iso of=/dev/sdX bs=4M status=progress oflag=direct && sync
```

### Misc

To get modify a package description without "rebuilding" it completely, you can use `rpmrebuild -e -p your.rpm`
