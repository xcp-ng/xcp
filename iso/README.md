## How to

To generate this splash image, you need:

* a 640x240 banner
* In Gimp: Image/mode/index colors/14 (=16 including B&W)
* export in gif format, ie `splash.gif`
* `giftopnm < splash.gif > splash.ppm`
* `ppmtolss16 < splash.ppm > splash.lss`

#### Requirements

In Fedora/CentOS/RH like, those packages are needed:

* `syslinux-perl`
* `netpbm-progs`
