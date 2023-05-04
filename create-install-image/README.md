# Generation of installation ISO

## individual scripts

Those scripts should be run in the xcp-ng-build-env docker container
for reproducibility.  They require some additional packages:

```
sudo yum install -y genisoimage syslinux grub-tools createrepo_c
sudo yum install -y --enablerepo=epel gnupg1
```

All script have a `--help` documenting all their options.

### `./scripts/create-install-iso.sh`

Creates `.iso` from:
- `install.img` (see below)
- yum repository for the product (or a local mirror) for boot files and
  local repository
- additional files from `./iso/$RELEASE/`

### `./scripts/create-installimg.sh`

Creates `install-$RELEASE.img` for input to `create-install-iso`, from:
- yum repository for the product (or a local mirror)
- a `packages.lst` file listing RPMs to be installed
- additional files from `./installimg/$RELEASE/`

### `./scripts/mirror-repos.sh`

Creates a local mirror of a subset of an official set of repositories
for a given XCP-ng version, suitable for building an installation ISO.
This scripts excludes from the mirror:
- source RPMs
- development RPMs
- debugging-symbols RPMs

### configuration layers and package repositories

Configuration layers are defined as a subdirectory of the `configs/`
directory.  Commands are given a layer search path as
`<base-config>[:<config-overlay>]* `.

Standard layers are organized such as two of the standard layers must be
used:

* The "version" layer (e.g. `8.2`) provides required files:
  - `packages.lst` and `yum.conf.tmpl` used to create the `install.img`
    filesystem
  - `yumdl.conf.tmpl` used to download files for the RPM repository
    included in the ISO

* The "repo" layers (e.g. `updates`) each provide a yum repo
  configuration file, and optionally an `INCLUDE` file to pull
  additional base repo layers.  The `base` layer will always be in the
  include chain.

XCP-ng official repositories are located at
https://updates.xcp-ng.org/ and most of them are available through
standard "repo" layers; e.g. the `testing` repository for `8.2` LTS can
be used as `8.2:testing`.

Custom repositories can be added with `--define-repo` flag (can be
used multiple times to define more than one custom repo).  They will
be used by `yum` using the first `CUSTOMREPO.tmpl` template found in
the layer search path (one is provided in `base`).

## examples

### 8.3 updates and testing

```
./scripts/mirror-repos.sh 8.3 ~/mirrors/xcpng

sudo ./scripts/create-installimg.sh \
    --srcurl file://$HOME/mirrors/xcpng/8.3 \
    --output install-8.3.testing.img \
    8.3:testing

./scripts/create-install-iso.sh \
    --srcurl file://$HOME/mirrors/xcpng/8.3 \
    -V "XCP-NG_830_TEST" \
    8.3:testing install-8.3-testing.img xcp-ng-8.3-testing.iso
```

### tip of 8.2 (8.2 + updates)

```
./scripts/mirror-repos.sh 8.2 ~/mirrors/xcpng

sudo ./scripts/create-installimg.sh \
    --srcurl file://$HOME/mirrors/xcpng/8.2 \
    --output install-8.2.updates.img \
    8.2:updates

./scripts/create-install-iso.sh \
    --srcurl file://$HOME/mirrors/xcpng/8.2 \
    -V "XCP-NG_82_TEST" \
    8.2:updates install-8.2.updates.img xcp-ng-8.2.updates.iso
```

### testing boot modes in qemu

PC BIOS:

```
qemu-system-x86_64 -serial stdio -m 1G -cdrom xcp-ng-8.3-install.iso
```

UEFI:

```
qemu-system-x86_64 -serial stdio -m 1G -cdrom xcp-ng-8.3-install.iso \
  --bios /usr/share/edk2/ovmf/OVMF_CODE.fd -net none
```

### testing that scripts run correctly

Minimal tests to generate install ISO for a few important
configurations are available in `tests/`.  They require one-time
initialization of the `tests/sharness/` submodule:

```
git submodule update --init tests/sharness/
```

They require setting a variable pointing to the repositories to be
used; it is recommended you use a local mirror for this.

Two common ways of running the tests are:

* just using `make`, which produce human-readable
  [TAP](http://testanything.org/) output:

  ```
  make -C tests/ XCPTEST_REPOROOT=file:///data/mirrors/xcpng
  ```

* through `prove` (in package `perl-Test-Harness` in
  CentOS/Fedora/RHEL, in `perl` for the rest of the world), which
  provides both options for e.g. parallel running, and global summary:

  ```
  XCPTEST_REPOROOT=file:///data/mirrors/xcpng prove tests/
  ```

The tests for producing `install.img` are tagged as expensive and not
run by default, to run them you must pass the `-l` flag to the test
script, which can be achieved respectively by:

```
make TEST_OPTS="-l"

prove tests/ :: -l
```


## still to be done (a bit outdated but not that much)

* [x] .treeinfo files have an unsubst'd `{{timestamp}}`
- [x] /etc/depmod.d/depmod.conf => add "override" (see build-scripts repo) => host-installer-startup owns the file
- [x] There's also another depmod conf file that we used to modify the same way: /etc/depmod.d/dist.conf. Which one is necessary?
- [x] remove unused modules from kernel-alt => as triggerin in host-installer too, so all is defined in the same place?
- [ ] make `-o` mandatory, `--force-overwrite`
- [ ] inverted updates and candidates

### post alpha3

* [x] how to deal with the fact we can only reproduce 8.x.0 and 8.x.updates
* [x] (^^ linked ^^) customizability of available repos
* [ ] multipath support ?
* [x] getty on tty2 is broken
* [x] document dependencies (as asserts)
* [x] check why the installed system is seen as 8.2 (comes from the installer's branding !?)
* [ ] extract `.treeinfo` data from branding
* [ ] let `--define-repo` also take a gpg-key

Work to reproduce install.img

* reproduce XCP-ng 8.2.1 ~+
  * known issues
    - [x] check for remaining host contaminations
    - [x] use debug hypervisor
  * still some packages missing
    - [x] host-installer-startup, not provided as RPM in CH, only as SRPM
    - [x] xen-installer-files
  * packages replaced in xcp-ng
    - [x] xsenserver-release* -> xcp-ng-release*
  * missing files:
    - [x] /opt/xensource/installer/version.py
    - [x] installer.service getty@tty2.service
    - [x] sshd.service.d/installer.conf (disables sshd by default, enables with sshpassword=xxxx)
    - [ ] ldconfig.service xenstored.service etc. links to /dev/null (those two at least seem
          unneeded)
    - [ ] /etc/udev/rules.d/: 11-dm-mpath.rules 62-multipath.rules 69-dm-lvm-metad.rules links to /dev/null
    - [ ] /etc/udev/rules.d/40-multipath.rules
    - [ ] /usr/lib/firmware/updates/intel/ice/ddp/ice-1.3.26.0.pkg (we have `ice.pkg`)
    - [ ] /usr/lib/modules/4.19.227/kernel/drivers/infiniband (removed by host-installer "%triggerin")
    - [x] /init -> /sbin/init
    - [x] ~~/bin/support.sh (trivial wrapper around xelogging.py - CH only ?)~~
  * missing files we don't care to add
    - /etc/sysconfig/network: no adverse effect noticed during netinstall
    - getty.target.wants/lvm2* broken links
    - /usr/sbin/scsi_id -> /lib/udev/scsi_id broken link
    - /run/reboot-required.d/: kernel/4.19.19-7.0.13 xen/4.13.4-9.17
  * extra files removed by CH, we don't care to remove (too small to matter)
    - /usr/lib/dracut
    - /etc/dracut.conf.d/ (not even removed in 8.3 any more)
  * missing in installed system
    - [ ] Citrix rpm keys (driver disks? sup packs?)
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
    - [ ] /var/cache
    - ...
  * file diffs:
   * kernel modules differ (!)
   * /etc/issue
   * host contamination:
     * ~~$B/etc/multipath.conf.disabled~~: not really, comes from BuildRequires
  * metadata diffs
    * removed locale files are not flagged as missing in CH8C install.img by "rpm -V", not clear now they achieved this
    * CH8C has changes to filemodes (w and s bits removed), visible with rpm -V.  No clue what they tried to achieve.


## checklist from contents review

Comparison of install.img between XCP-ng 8.2.0's official ISOs and newly generated install.img

### initialized in our installimg

- [ ] they remove files in fcoe-utils (/etc, /usr/libexec)

- [ ] We modify filemodes in /usr/lib/debug/usr, why?
- [ ] Also filemodes of /etc/fstab, /etc/hosts, /var/lib/yum/history

- [ ] We remove less modules than Citrix, so in results less firmware files are removed too? (triggerin in host-installer) => investigate

- [ ] i915 driver is removed by XenServer. Do the same.

- [ ] They remove built-in network drivers that are already provided as extra packages in lib/modules/.../updates. Worth it?

- [ ] There are two .rpmnew files we can delete, including /etc/hosts.rpmnew whose contents is better (includes localhost4)

- [x] ~~There's a /installation-homedir, why?~~

- [x] Clean-up /var/lib/yum, /var/cache/yum


### ISO image

- [x] Remove groups-XS.xml

- [x] kernel-alt is missing in Packages/

- [x] ~~Store quay.io image locally? Only if a simple file.~~

- [ ] Packages/ for 8.2.0 contains libverto-libevent instead of libverto-tevent (both fulfill the same Provides). Could it have adverse effects? Does this problem affect 8.3 ISOs? Create a yum conf, used when Packages/ is generated, where in case of doubt libverto-tevent be prefered?

- [x] If isohybrid is not installed, the iso creation script doesn't detect it (it does for genisoimage). Also document the prerequisites in the readme.
