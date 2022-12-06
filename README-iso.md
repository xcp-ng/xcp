# Generation of installation ISO

## individual scripts

### `./scripts/create-install-iso.sh`

Creates `.iso` from:
- `install.img` (see below)
- yum repository for the product (FIXME: for now taken from a copy of existing ISO)
- additional files from `./iso/$RELEASE/`
- `grub[2]-mkrescue` (for now?), which (for now?) takes grub files from build host
- syslinux boot files from host (`/usr/share/syslinux/`)

### `./scripts/create-installimg.sh`

Creates `install-$RELEASE.img` for input to `create-install-iso`, from:
- `mock` config file (./mock-configs/$RELEASE.cfg`)
- (temporarily) extra RPMs for `host- installer` and its dependencies
  (`~/src/rpms/host-installer/RPMS-$RELEASE/x86_64/`)
- (temporarily) a couple of extra files (installer service files and
  EULA) from an unpacked tree of current ISO's install.img
  (`~/$RELEASE-installimg`)
- (temporarily) a `~/src/branding-xcp-ng/` tree


## examples

### 8.3.0

 ./scripts/mirror-repos.sh 8.3
 ./scripts/create-installimg.sh \
     --srcurl file://$HOME/mirrors/xcpng/8.3 \
     8.3.0
 ./scripts/create-install-iso.sh \
     --srcurl file://$HOME/mirrors/xcpng/8.3 \
     -V "XCP-NG_830_TEST" \
     8.3.0 install-8.3.0-x86_64.img xcp-ng-8.3-install.iso

### 8.2.1

 ./scripts/mirror-repos.sh 8.2
 ./scripts/create-installimg.sh \
     --srcurl file://$HOME/mirrors/xcpng/8.2 \
     8.2.1
 ./scripts/create-install-iso.sh \
     --srcurl file://$HOME/mirrors/xcpng/8.2 \
     -V "XCP-NG_821_TEST" \
     8.2.1 install-8.2.1-x86_64.img xcp-ng-8.2.1-install.iso

### testing boot modes in qemu

PC BIOS:

 qemu-system-x86_64 -serial stdio -m 1G -cdrom xcp-ng-8.3-install.iso

UEFI:

 qemu-system-x86_64 -serial stdio -m 1G -cdrom xcp-ng-8.3-install.iso \
   --bios /usr/share/edk2/ovmf/OVMF_CODE.fd -net none


## still to be done (a bit outdated but not that much)

* [ ] how to deal with the fact we can only reproduce 8.x.0 and 8.x.updates
* [ ] (^^ linked ^^) customizability of available repos
* [x] getty on tty2 is broken
* [x] document dependencies (as asserts)
* [x] check why the installed system is seen as 8.2 (comes from the installer's branding !?)

Work to reproduce install.img

* reproduce XCP-ng 8.2.1 ~+
  * known issues
    - [ ] `Displaying screen <function use_extra_media` ... with the dialog not visible
          in TUI, becomes visible after hitting <TAB>
    - [ ] check for remaining host contaminations
  * still some packages missing
    - [x] host-installer-startup, not provided as RPM in CH, only as SRPM
    - [x] xen-installer-files
  * packages replaced in xcp-ng
    - [x] xsenserver-release* -> xcp-ng-release*
  * missing files:
    - [x] /opt/xensource/installer/version.py
    - [ ] /etc/sysconfig/network
    - [.] installer.service getty@tty2.service
    - [ ] sshd.service.d/installer.conf (disables sshd by default, enables with sshpassword=xxxx)
    - [ ] getty.target.wants/lvm2* links [broken]
    - [ ] ldconfig.service xenstored.service etc. links to /dev/null
    - [ ] /etc/udev/rules.d/: 11-dm-mpath.rules 62-multipath.rules 69-dm-lvm-metad.rules links to /dev/null
    - [ ] /etc/udev/rules.d/40-multipath.rules
    - [ ] /run/reboot-required.d/: kernel/4.19.19-7.0.13 xen/4.13.4-9.17
    - [ ] /usr/lib/firmware/updates/intel/ice/ddp/ice-1.3.26.0.pkg
    - [ ] /usr/lib/modules/4.19.227/kernel/drivers/infiniband (removed by host-installer "%triggerin")
    - [x] /init -> /sbin/init
    - [ ] /usr/sbin/scsi_id -> /lib/udev/scsi_id [broken]
    - [ ] /bin/support.sh (trivial wrapper around xelogging.py - CH only ?)
  * still some packages to be cleaned up (50MB)
    - [x] binutils etc.
    - [x] python2.7 .pyc and .pyo
    - [ ] some extra service dependencies
    - [ ] some /usr/bin binaries from systemd (bootctl, etc.), [dp]gawk, oldfind, info(key), ssh-{agent,keyscan}, ...
    - [ ] some /usr/sbin binaries
    - [ ] firwmare: bnx2(x), i915, qed
    - [ ] drivers: some ethernet (bcom, intel, qlogic, etc), some scsi, some fs, gpu
    - [ ] udev hwdb files
    - [ ] /etc/openldap/certs/
    - ...
  * file diffs:
   * kernel modules differ (!)
   * mock leaves a "mockbuild" user and "mock" group behind
   * /etc/issue
   * /etc/localtime points to Paris not UTC
   * host contamination:
     * hostname leaks into $B/etc/hosts
     * $B/etc/multipath.conf.disabled
