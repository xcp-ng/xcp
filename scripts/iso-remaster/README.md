# ISO remastering script for XCP-ng and XenServer

This script allows to produce a customized installation ISO, using
"patcher" scripts to automate the task.

Two levels of customization are provided:

* `--iso-patcher` lets you provide a script that will act on the
  unpacked ISO contents (after which the ISO will be rebuilt from the
  modified contents)
* `--install-patcher` will similarly unpack the `install.img` (ramdisk
  root filesystem) and lets you provide a script acting on his
  contents, from which a new `install.img` will be produced and
  included in the repacked ISO

Example usages are provided in `scripts/iso-remaster/samples/`

## Prerequisites

A few tools are required to run, the script will tell you if you miss
some, but you may want to install those first. Depending on your OS
you may use something like:

```
apt-get install fakeroot genisoimage syslinux-utils p7zip-full
```

```
dnf install fakeroot genisoimage syslinux cdrkit-isotools p7zip-plugins
```
