## How to generate XCP-ng ISO

You need `mkisofs` program.

Usage:

```
# cd isofolder/
# mkisofs -no-emul-boot -boot-load-size 4 -boot-info-table -r -b boot/isolinux/isolinux.bin -c boot/isolinux/boot.cat -o ~/xcpng.iso .
```

This will create a `xcpng.iso` file into your home directory.

### Splash image

To generate this splash image (`boot/isolinux/splash.lss`), you need:

* a 640x240 banner
* In Gimp: Image/mode/index colors/14 (=16 including B&W)
* export in gif format, ie `splash.gif`
* `giftopnm < splash.gif > splash.ppm`
* `ppmtolss16 < splash.ppm > splash.lss`

#### Requirements

In Fedora/CentOS/RH like, those packages are needed:

* `syslinux-perl`
* `netpbm-progs`
