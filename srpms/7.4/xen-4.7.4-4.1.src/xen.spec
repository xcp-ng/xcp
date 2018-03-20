# -*- rpm-spec -*-

%{!?python_sitearch: %define python_sitearch %(%{__python} -c "from distutils.sysconfig import get_python_lib; print get_python_lib(1)")}

%define with_sysv 0
%define with_systemd 1

%define COMMON_OPTIONS DESTDIR=%{buildroot} %{?_smp_mflags}

# For 32bit dom0 userspace, we need to cross compile a 64bit Xen
%ifarch %ix86
%define HVSOR_OPTIONS %{COMMON_OPTIONS} XEN_TARGET_ARCH=x86_64 CROSS_COMPILE=x86_64-linux-gnu-
%define TOOLS_OPTIONS %{COMMON_OPTIONS} XEN_TARGET_ARCH=x86_32 debug=n
%endif

# For 64bit
%ifarch x86_64
%define HVSOR_OPTIONS %{COMMON_OPTIONS} XEN_TARGET_ARCH=x86_64
%define TOOLS_OPTIONS %{COMMON_OPTIONS} XEN_TARGET_ARCH=x86_64 debug=n
%endif

%define base_cset RELEASE-%{version}
%define base_dir  %{name}-%{version}

Summary: Xen is a virtual machine monitor
Name:    xen
Version: 4.7.4
Release: 4.1
License: GPLv2+ and LGPLv2+ and BSD
URL:     http://www.xenproject.org
Patch0: build-disable-qemu-trad.patch
Patch1: build-tweaks.patch
Patch2: disable-efi.patch
Patch3: autoconf-libjson.patch
Patch4: configure-build.patch
Patch5: builder-makefiles.patch
Patch6: changeset-info.patch
Patch7: xenserver-configuration.patch
Patch8: coverity-model.patch
Patch9: backport-67966a98f8bb.patch
Patch10: backport-184f25969729.patch
Patch11: backport-b3981ea9e88b.patch
Patch12: backport-4133de769dd3.patch
Patch13: backport-4f34d9fa68af.patch
Patch14: backport-5a9915684010.patch
Patch15: backport-b9c150ecbbcd.patch
Patch16: backport-c3ddeca415a5.patch
Patch17: backport-1c58d74aff29.patch
Patch18: backport-bacbf0cb7349.patch
Patch19: backport-c9e5a6a232db.patch
Patch20: backport-212d27297af9.patch
Patch21: backport-289c53a49307.patch
Patch22: backport-635c5ec3f0ee.patch
Patch23: backport-cd42ccb27f4e.patch
Patch24: backport-ce34d6b036ed.patch
Patch25: backport-6e908ee108ca.patch
Patch26: backport-490a39a1dbc7.patch
Patch27: backport-31689dcb0fbf.patch
Patch28: backport-a2c8399a91bf.patch
Patch29: backport-d72fd26d5f17.patch
Patch30: backport-e2aba42bff72.patch
Patch31: backport-2511f89d9a5e.patch
Patch32: backport-b49839ef4e6b.patch
Patch33: backport-53c300ab1ca0.patch
Patch34: backport-45aa97876683.patch
Patch35: backport-d18224766fa2.patch
Patch36: backport-559f439bfa3b.patch
Patch37: backport-56fef9e367b2.patch
Patch38: backport-c6f7d2174780.patch
Patch39: backport-ee3fd57acd90.patch
Patch40: backport-509019f42dd5.patch
Patch41: backport-a6288d5bb8b9.patch
Patch42: backport-6a962ebddce8.patch
Patch43: backport-70dda5f4e9c9.patch
Patch44: backport-5efcebc66de0.patch
Patch45: backport-668ba1f85bf2.patch
Patch46: backport-7edc10831448.patch
Patch47: backport-f755485cbd2a.patch
Patch48: backport-e04b562377b3.patch
Patch49: backport-41b61be1c244.patch
Patch50: backport-2ad72c0b4676.patch
Patch51: backport-4ef815bf611d.patch
Patch52: backport-920234259475.patch
Patch53: backport-e3eb84e33c36.patch
Patch54: backport-7179cd39efdb.patch
Patch55: backport-cbfe4db8d750.patch
Patch56: backport-dcf22aa0dc08.patch
Patch57: backport-db6c2264e698.patch
Patch58: backport-698d0f377d72.patch
Patch59: backport-3adef8e3270f.patch
Patch60: backport-c99986fa168e.patch
Patch61: backport-51e5d6c7a296.patch
Patch62: backport-8695b556205f.patch
Patch63: backport-afb118e71967.patch
Patch64: backport-12b3174d945b.patch
Patch65: backport-d6be2cfccfff.patch
Patch66: backport-0831e9944612.patch
Patch67: backport-d45fae589b8d.patch
Patch68: backport-1ef5056bd627.patch
Patch69: backport-424fdc67e90b.patch
Patch70: backport-50a12dd59f23.patch
Patch71: backport-4f13e5b3f69a.patch
Patch72: backport-70c95ecd5c0e.patch
Patch73: backport-4abcd521bf46.patch
Patch74: backport-7cae6b6eb743.patch
Patch75: backport-9864841914c2.patch
Patch76: backport-ac6a4500b2be.patch
Patch77: backport-c88da9ec8852.patch
Patch78: backport-08fac63ec0b8.patch
Patch79: backport-1cb650c3191f.patch
Patch80: backport-44d3196903f3.patch
Patch81: backport-9bd6b01f9d46.patch
Patch82: backport-04dbb7109614.patch
Patch83: backport-d4a24c64b60d.patch
Patch84: backport-1edbf34e63c8.patch
Patch85: backport-7f8445d9678a.patch
Patch86: backport-195ca0e1de85.patch
Patch87: backport-d18216a0c03c.patch
Patch88: backport-62c7b99a1079.patch
Patch89: backport-9b93c6b3695b.patch
Patch90: backport-7f11aa4b2b1f.patch
Patch91: backport-d6e9f8d4f35d.patch
Patch92: backport-77751ed79e3c.patch
Patch93: backport-a013e1b9e95e.patch
Patch94: backport-e3f64938272e.patch
Patch95: backport-7ecd11c90a13.patch
Patch96: backport-5823d6eb40af.patch
Patch97: backport-9a7fbdd6925b.patch
Patch98: backport-4c8153d97efe.patch
Patch99: backport-72efb1df6294.patch
Patch100: backport-04f34e76ac50.patch
Patch101: backport-f97838bbd980.patch
Patch102: backport-1366a0e76db6.patch
Patch103: backport-461f0482033b.patch
Patch104: backport-1c5e242e6d6e.patch
Patch105: backport-0d1a96043a75.patch
Patch106: backport-d9eb706356ad.patch
Patch107: backport-20f1976b4419.patch
Patch108: backport-90288044a67a.patch
Patch109: backport-4c09689153c3.patch
Patch110: backport-6b792e28bca8.patch
Patch111: backport-143e0c2c2d64.patch
Patch112: backport-68209ad1d2a7.patch
Patch113: backport-82942526572c.patch
Patch114: backport-62999081ca27.patch
Patch115: backport-4da2fe19232e.patch
Patch116: backport-930f7879248e.patch
Patch117: backport-f0f1a778d4d5.patch
Patch118: backport-cd3ed39b9df0.patch
Patch119: backport-69d99d1b223f.patch
Patch120: backport-9e50d8adc945.patch
Patch121: backport-41d1fcb1c9bf.patch
Patch122: backport-4098b092e190.patch
Patch123: backport-4187f79dc718.patch
Patch124: backport-e7a370733bd2.patch
Patch125: backport-37f074a33831.patch
Patch126: backport-664adc5ccab1.patch
Patch127: backport-d73e68c08f1f.patch
Patch128: backport-f99b7b06378d.patch
Patch129: backport-4d69b3495986.patch
Patch130: backport-a08a9cd3afa6.patch
Patch131: backport-77690ea09ab2.patch
Patch132: backport-cd579578aac4.patch
Patch133: backport-ec832dddc4c5.patch
Patch134: backport-7b6546e83147.patch
Patch135: backport-a65a24209cd8.patch
Patch136: backport-6df4b481b0c5.patch
Patch137: backport-cf23c69fdd48.patch
Patch138: backport-23044a4e00c1.patch
Patch139: backport-f1a0a8c3fe2f.patch
Patch140: backport-d2f86bf60469.patch
Patch141: backport-24246e1fb749.patch
Patch142: backport-b90f86be161c.patch
Patch143: detect-nehalem-c-state.patch
Patch144: quirk-hp-gen8-rmrr.patch
Patch145: quirk-pci-phantom-function-devices.patch
Patch146: sched-credit1-use-per-pcpu-runqueue-count.patch
Patch147: 0001-x86-hpet-Pre-cleanup.patch
Patch148: 0002-x86-hpet-Use-singe-apic-vector-rather-than-irq_descs.patch
Patch149: 0003-x86-hpet-Post-cleanup.patch
Patch150: 0002-libxc-retry-shadow-ops-if-EBUSY-is-returned.patch
Patch151: avoid-gnt-unmap-tlb-flush-if-not-accessed.patch
Patch152: 0002-x86-boot-reloc-create-generic-alloc-and-copy-functio.patch
Patch153: 0003-x86-boot-use-ecx-instead-of-eax.patch
Patch154: 0004-xen-x86-add-multiboot2-protocol-support.patch
Patch155: 0005-efi-split-efi_enabled-to-efi_platform-and-efi_loader.patch
Patch156: 0007-efi-run-EFI-specific-code-on-EFI-platform-only.patch
Patch157: 0008-efi-build-xen.gz-with-EFI-code.patch
Patch158: 0017-x86-efi-create-new-early-memory-allocator.patch
Patch159: 0018-x86-add-multiboot2-protocol-support-for-EFI-platform.patch
Patch160: mkelf32-fixup.patch
Patch161: 0001-x86-efi-Find-memory-for-trampoline-relocation-if-nec.patch
Patch162: 0002-efi-Ensure-incorrectly-typed-runtime-services-get-ma.patch
Patch163: 0001-Fix-compilation-on-CentOS-7.1.patch
Patch164: 0001-x86-time-Don-t-use-EFI-s-GetTime-call.patch
Patch165: 0001-efi-Workaround-page-fault-during-runtime-service.patch
Patch166: efi-align-stack.patch
Patch167: 0001-x86-HVM-Avoid-cache-flush-operations-during-hvm_load.patch
Patch168: 0001-libxl-Don-t-insert-PCI-device-into-xenstore-for-HVM-.patch
Patch169: 0001-x86-PoD-Command-line-option-to-prohibit-any-PoD-oper.patch
Patch170: 0001-libxl-handle-an-INVALID-domain-when-removing-a-pci-d.patch
Patch171: fail-on-duplicate-symbol.patch
Patch172: livepatch-ignore-duplicate-new.patch
Patch173: default-log-level-info.patch
Patch174: livepach-Add-.livepatch.hooks-functions-and-test-cas.patch
Patch175: 0001-lib-Add-a-generic-implementation-of-current_text_add.patch
Patch176: 0002-sched-Remove-dependency-on-__LINE__-for-release-buil.patch
Patch177: 0003-mm-Use-statically-defined-locking-order.patch
Patch178: 0004-page-alloc-Remove-dependency-on-__LINE__-for-release.patch
Patch179: 0005-iommu-Remove-dependency-on-__LINE__-for-release-buil.patch
Patch180: 0001-tools-livepatch-Show-the-correct-expected-state-befo.patch
Patch181: 0002-tools-livepatch-Set-stdout-and-stderr-unbuffered.patch
Patch182: 0003-tools-livepatch-Improve-output.patch
Patch183: 0004-livepatch-Set-timeout-unit-to-nanoseconds.patch
Patch184: 0005-tools-livepatch-Remove-pointless-retry-loop.patch
Patch185: 0006-tools-livepatch-Remove-unused-struct-member.patch
Patch186: 0007-tools-livepatch-Exit-with-2-if-a-timeout-occurs.patch
Patch187: pygrub-Ignore-GRUB2-if-statements.patch
Patch188: libfsimage-Add-support-for-btrfs.patch
Patch189: 0001-xen-domctl-Implement-a-way-to-retrieve-a-domains-nom.patch
Patch190: quiet-broke-irq-affinity.patch
Patch191: quirk-dell-optiplex-9020-reboot.patch
Patch192: quirk-intel-purley.patch
Patch193: quirk-dell-r740.patch
Patch194: xsa226-cmdline-options.patch
Patch195: 0001-Kconfig-add-BROKEN-config.patch
Patch196: 0002-xen-delete-gcno-files-in-clean-target.patch
Patch197: 0003-xen-tools-rip-out-old-gcov-implementation.patch
Patch198: 0004-gcov-add-new-interface-and-new-formats-support.patch
Patch199: 0005-gcov-userspace-tools-to-extract-and-split-gcov-data.patch
Patch200: 0006-Config.mk-expand-cc-ver-a-bit.patch
Patch201: 0007-Config.mk-introduce-cc-ifversion.patch
Patch202: 0008-gcov-provide-the-capability-to-select-gcov-format-au.patch
Patch203: 0009-flask-add-gcov_op-check.patch
Patch204: 0001-x86-alt-Break-out-alternative-asm-into-a-separate-he.patch
Patch205: 0002-x86-alt-Introduce-ALTERNATIVE-_2-macros.patch
Patch206: 0003-x86-hvm-Rename-update_guest_vendor-callback-to-cpuid.patch
Patch207: 0004-x86-Introduce-a-common-cpuid_policy_updated.patch
Patch208: 0005-x86-entry-Remove-support-for-partial-cpu_user_regs-f.patch
Patch209: 0006-x86-entry-Rearrange-RESTORE_ALL-to-restore-register-.patch
Patch210: 0007-x86-hvm-Use-SAVE_ALL-to-construct-the-cpu_user_regs-.patch
Patch211: 0008-x86-entry-Erase-guest-GPR-state-on-entry-to-Xen.patch
Patch212: 0009-x86-Support-compiling-with-indirect-branch-thunks.patch
Patch213: 0010-common-wait-Clarifications-to-wait-infrastructure.patch
Patch214: 0011-x86-Support-indirect-thunks-from-assembly-code.patch
Patch215: 0012-x86-boot-Report-details-of-speculative-mitigations.patch
Patch216: 0013-x86-amd-Try-to-set-lfence-as-being-Dispatch-Serialis.patch
Patch217: 0014-x86-Introduce-alternative-indirect-thunks.patch
Patch218: 0015-x86-feature-Definitions-for-Indirect-Branch-Controls.patch
Patch219: 0016-x86-cmdline-Introduce-a-command-line-option-to-disab.patch
Patch220: 0017-x86-msr-Emulation-of-MSR_-SPEC_CTRL-PRED_CMD-for-gue.patch
Patch221: 0018-x86-migrate-Move-MSR_SPEC_CTRL-on-migrate.patch
Patch222: 0019-x86-hvm-Permit-guests-direct-access-to-MSR_-SPEC_CTR.patch
Patch223: 0020-x86-Protect-unaware-domains-from-meddling-hyperthrea.patch
Patch224: 0021-x86-entry-Use-MSR_SPEC_CTRL-at-each-entry-exit-point.patch
Patch225: 0022-x86-boot-Calculate-the-most-appropriate-BTI-mitigati.patch
Patch226: 0023-x86-entry-Clobber-the-Return-Stack-Buffer-on-entry-t.patch
Patch227: 0024-x86-ctxt-Issue-a-speculation-barrier-between-vcpu-co.patch
Patch228: 0025-x86-cpuid-Offer-Indirect-Branch-Controls-to-guests.patch
Patch229: 0026-x86-idle-Clear-SPEC_CTRL-while-idle.patch
Patch230: xen-tweak-cmdline-defaults.patch
Patch231: xen-tweak-debug-overhead.patch
Patch232: tweak-iommu-errata-policy.patch
Patch233: disable-core-parking.patch
Patch234: disable-runtime-microcode.patch
Patch235: xen-legacy-win-driver-version.patch
Patch236: xen-legacy-win-xenmapspace-quirks.patch
Patch237: xen-legacy-32bit_shinfo.patch
Patch238: xen-legacy-process-dying.patch
Patch239: xen-legacy-viridian-hypercalls.patch
Patch240: xen-legacy-hvm-console.patch
Patch241: livepatch-payload-in-header.patch
Patch242: xen-define-offsets-for-kdump.patch
Patch243: xen-scheduler-auto-privdom-weight.patch
Patch244: xen-hvm-disable-tsc-ramping.patch
Patch245: xen-default-cpufreq-governor-to-performance-on-intel.patch
Patch246: xen-override-caching-cp-26562.patch
Patch247: revert-ca2eee92df44.patch
Patch248: libxc-stubs-hvm_check_pvdriver.patch
Patch249: libxc-ext-6.patch
Patch250: libxc-ext-7.patch
Patch251: libxc-ext-8.patch
Patch252: restrict-privcmd.patch
Patch253: pygrub-add-default-and-extra-args.patch
Patch254: pygrub-always-boot-default.patch
Patch255: pygrub-friendly-no-fs.patch
Patch256: pygrub-image-max-size.patch
Patch257: pygrub-default-xenmobile-kernel.patch
Patch258: pygrub-blacklist-support.patch
Patch259: oem-bios-xensource.patch
Patch260: oem-bios-magic-from-xenstore.patch
Patch261: misc-log-guest-consoles.patch
Patch262: fix-ocaml-libs.patch
Patch263: ocaml-cpuid-helpers.patch
Patch264: xentop-display-correct-stats.patch
Patch265: xentop-vbd3.patch
Patch266: mixed-domain-runstates.patch
Patch267: mixed-xc-sockets-per-core.patch
Patch268: xenguest.patch
Patch269: xen-vmdebug.patch
Patch270: local-xen-vmdebug.patch
Patch271: oxenstore-update.patch
Patch272: oxenstore-censor-sensitive-data.patch
Patch273: oxenstore-large-packets.patch
Patch274: nvidia-hypercalls.patch
Patch275: nvidia-vga.patch
Patch276: hvmloader-disable-pci-option-rom-loading.patch
Patch277: xen-force-software-vmcs-shadow.patch
Patch278: 0001-x86-vvmx-add-initial-PV-EPT-support-in-L0.patch
Patch279: igd_passthru.patch
Patch280: allow-rombios-pci-config-on-any-host-bridge.patch
Patch281: add-p2m-write-dm-to-ram-types.patch
Patch282: add-pv-iommu-headers.patch
Patch283: add-iommu-lookup-core.patch
Patch284: add-iommu-lookup-intel.patch
Patch285: add-pv-iommu-local-domain-ops.patch
Patch286: add-m2b-support.patch
Patch287: add-pv-iommu-foreign-support.patch
Patch288: add-pv-iommu-premap-m2b-support.patch
Patch289: add-pv-iommu-to-spec.patch
Patch290: upstream-pv-iommu-tools.patch
Patch291: 0007-hypercall-XENMEM_get_mfn_from_pfn.patch
Patch292: 0012-resize-MAX_NR_IO_RANGES-to-512.patch
Patch293: 0015-xen-introduce-unlimited-rangeset.patch
Patch294: 0016-ioreq-server-allocate-unlimited-rangeset-for-memory-.patch
Patch295: gvt-g-hvmloader+rombios.patch
Patch296: revert-c858e932c1dd.patch
Patch297: amd-pci-hole.patch
Patch298: xen-introduce-cmdline-to-control-introspection-extensions.patch
Patch299: xen-domctl-set-privileged-domain.patch
Patch300: xen-x86-hvm-Allow-guest_request-vm_events-coming-from-us.patch
Patch301: x86-domctl-Don-t-pause-the-whole-domain-if-only-gett.patch
Patch302: xen-reexecute-instn-under-monitor-trap.patch
Patch303: xen-x86-emulate-syncrhonise-LOCKed-instruction-emulation.patch
Patch304: xen-emulate-Bypass-the-emulator-if-emulation-fails.patch
Patch305: xen-introspection-pause.patch
Patch306: xen-introspection-elide-cr4-pge.patch
Patch307: xen-xsm-default-policy.patch
Patch308: xen-xsm-allow-access-unlabeled-resources.patch
Patch309: xen-xsm-treat-unlabeled-domain-domU.patch
Patch310: xsa252-4.7.patch
Patch311: xsa255-4.7-1.patch
Patch312: xsa255-4.7-2.patch
Source0: https://code.citrite.net/rest/archive/latest/projects/XSU/repos/%{name}/archive?at=%{base_cset}&prefix=%{base_dir}&format=tar.gz#/%{base_dir}.tar.gz
Source1: sysconfig_kernel-xen
Source2: xl.conf
Source3: logrotate-xen-tools
#Patch0:  xen-development.patch

ExclusiveArch: i686 x86_64

#Cross complier
%ifarch %ix86
BuildRequires: gcc-x86_64-linux-gnu binutils-x86_64-linux-gnu
%endif

BuildRequires: gcc-xs

# For HVMLoader and 16/32bit firmware
BuildRequires: /usr/include/gnu/stubs-32.h
BuildRequires: dev86 iasl

# For the domain builder (decompression and hashing)
BuildRequires: zlib-devel bzip2-devel xz-devel
BuildRequires: openssl-devel

# For libxl
BuildRequires: yajl-devel libuuid-devel perl

# For python stubs
BuildRequires: python-devel

# For ocaml stubs
BuildRequires: ocaml ocaml-findlib

# For ipxe
BuildRequires: ipxe-source

BuildRequires: libblkid-devel

# For xentop
BuildRequires: ncurses-devel

# For the banner
BuildRequires: figlet

# For libfsimage
BuildRequires: e2fsprogs-devel
%if 0%{?centos}%{!?centos:5} < 6 && 0%{?rhel}%{!?rhel:5} < 6
#libext4fs
BuildRequires: e4fsprogs-devel
%endif
BuildRequires: lzo-devel

# For xenguest
BuildRequires: json-c-devel libempserver

# Misc
BuildRequires: libtool
%if %with_systemd
BuildRequires: systemd-devel
%endif

# To placate ./configure
BuildRequires: gettext-devel glib2-devel curl-devel gnutls-devel

%description
Xen Hypervisor.

%package hypervisor
Summary: The Xen Hypervisor
License: Various (See description)
Group: System/Hypervisor
Requires(post): coreutils grep
%description hypervisor
This package contains the Xen Project Hypervisor with extra patches.

%package hypervisor-debuginfo
Summary: The Xen Hypervisor debug information
Group: Development/Debug
%description hypervisor-debuginfo
This package contains the Xen Hypervisor debug information.

%package tools
Summary: Xen Hypervisor general tools
Requires: xen-libs = %{version}
Group: System/Base
%description tools
This package contains the Xen Hypervisor general tools for all domains.

%package devel
Summary: The Xen Hypervisor public headers
Group: Development/Libraries
%description devel
This package contains the Xen Hypervisor public header files.

%package libs
Summary: Xen Hypervisor general libraries
Group: System/Libraries
%description libs
This package contains the Xen Hypervisor general libraries for all domains.

%package libs-devel
Summary: Xen Hypervisor general development libraries
Requires: xen-libs = %{version}
Requires: xen-devel = %{version}
Group: Development/Libraries
%description libs-devel
This package contains the Xen Hypervisor general development for all domains.

%package dom0-tools
Summary: Xen Hypervisor Domain 0 tools
Requires: xen-dom0-libs = %{version}
Requires: xen-tools = %{version}
%if %with_systemd
Requires(post): systemd
Requires(preun): systemd
Requires(postun): systemd
BuildRequires: systemd
%endif
Group: System/Base
%description dom0-tools
This package contains the Xen Hypervisor control domain tools.

%package dom0-libs
Summary: Xen Hypervisor Domain 0 libraries
Requires: xen-hypervisor = %{version}
Group: System/Libraries
%description dom0-libs
This package contains the Xen Hypervisor control domain libraries.

%package dom0-libs-devel
Summary: Xen Hypervisor Domain 0 headers
Requires: xen-devel = %{version}
Requires: xen-dom0-libs = %{version}

# Temp until the build dependencies are properly propagated
Provides: xen-dom0-devel = %{version}
Group: Development/Libraries
%description dom0-libs-devel
This package contains the Xen Hypervisor control domain headers.

%package ocaml-libs
Summary: Xen Hypervisor ocaml libraries
Requires: xen-dom0-libs = %{version}
Group: System/Libraries
%description ocaml-libs
This package contains the Xen Hypervisor ocaml libraries.

%package ocaml-devel
Summary: Xen Hypervisor ocaml headers
Requires: xen-ocaml-libs = %{version}
Requires: xen-dom0-libs-devel = %{version}
Group: Development/Libraries
%description ocaml-devel
This package contains the Xen Hypervisor ocaml headers.

%package installer-files
Summary: Xen files for the XenServer installer
Group: System Environment/Base
%description installer-files
This package contains the minimal subset of libraries and binaries required in
the XenServer installer environment.

%prep
%autosetup -p1

mkdir -p tools/firmware/etherboot/ipxe/
cp /usr/src/ipxe-source.tar.gz tools/firmware/etherboot/ipxe.tar.gz
rm -f tools/firmware/etherboot/patches/series
#%patch0 -p1 -b ~development
base_cset=$(sed -ne 's/Changeset: \(.*\)/\1/p' < .gitarchive-info)
pq_cset=$(sed -ne 's/Changeset: \(.*\)/\1/p' < .gitarchive-info-pq)
echo "${base_cset:0:12}, pq ${pq_cset:0:12}" > .scmversion
cp %{SOURCE4} .

%build

# Placate ./configure, but don't pull in external content.
export WGET=/bin/false FETCHER=/bin/false

%configure \
        --disable-seabios --disable-stubdom --disable-xsmpolicy --disable-blktap2 \
	--with-system-qemu=%{_libdir}/xen/bin/qemu-system-i386 --with-xenstored=oxenstored \
	--enable-systemd

%install

# The existence of this directory causes ocamlfind to put things in it
mkdir -p %{buildroot}%{_libdir}/ocaml/stublibs

mkdir -p %{buildroot}/boot/

# Regular build of Xen
PATH=/opt/xensource/gcc/bin:$PATH %{__make} %{HVSOR_OPTIONS} -C xen XEN_VENDORVERSION=-%{release} \
    KCONFIG_CONFIG=../buildconfigs/config-release olddefconfig
PATH=/opt/xensource/gcc/bin:$PATH %{__make} %{HVSOR_OPTIONS} -C xen XEN_VENDORVERSION=-%{release} \
    KCONFIG_CONFIG=../buildconfigs/config-release build
PATH=/opt/xensource/gcc/bin:$PATH %{__make} %{HVSOR_OPTIONS} -C xen XEN_VENDORVERSION=-%{release} \
    KCONFIG_CONFIG=../buildconfigs/config-release MAP

cp xen/xen.gz %{buildroot}/boot/%{name}-%{version}-%{release}.gz
cp xen/System.map %{buildroot}/boot/%{name}-%{version}-%{release}.map
cp xen/xen-syms %{buildroot}/boot/%{name}-syms-%{version}-%{release}
cp buildconfigs/config-release %{buildroot}/boot/%{name}-%{version}-%{release}.config

# Debug build of Xen
PATH=/opt/xensource/gcc/bin:$PATH %{__make} %{HVSOR_OPTIONS} -C xen clean
PATH=/opt/xensource/gcc/bin:$PATH %{__make} %{HVSOR_OPTIONS} -C xen XEN_VENDORVERSION=-%{release}-d \
    KCONFIG_CONFIG=../buildconfigs/config-debug olddefconfig
PATH=/opt/xensource/gcc/bin:$PATH %{?cov_wrap} %{__make} %{HVSOR_OPTIONS} -C xen XEN_VENDORVERSION=-%{release}-d \
    KCONFIG_CONFIG=../buildconfigs/config-debug build
PATH=/opt/xensource/gcc/bin:$PATH %{__make} %{HVSOR_OPTIONS} -C xen XEN_VENDORVERSION=-%{release}-d \
    KCONFIG_CONFIG=../buildconfigs/config-debug MAP

cp xen/xen.gz %{buildroot}/boot/%{name}-%{version}-%{release}-d.gz
cp xen/System.map %{buildroot}/boot/%{name}-%{version}-%{release}-d.map
cp xen/xen-syms %{buildroot}/boot/%{name}-syms-%{version}-%{release}-d
cp buildconfigs/config-debug %{buildroot}/boot/%{name}-%{version}-%{release}-d.config

# do not strip the hypervisor-debuginfo targerts
chmod -x %{buildroot}/boot/xen-syms-*

# Build tools and man pages
%{?cov_wrap} %{__make} %{TOOLS_OPTIONS} -C tools install
%{__make} %{TOOLS_OPTIONS} -C docs install-man-pages
%{?cov_wrap} %{__make} %{TOOLS_OPTIONS} -C tools/tests/mce-test/tools install

%{__install} -D -m 644 %{SOURCE1} %{buildroot}%{_sysconfdir}/sysconfig/kernel-xen
%{__install} -D -m 644 %{SOURCE2} %{buildroot}%{_sysconfdir}/xen/xl.conf
%{__install} -D -m 644 %{SOURCE3} %{buildroot}%{_sysconfdir}/logrotate.d/xen-tools

%files hypervisor
/boot/%{name}-%{version}-%{release}.gz
/boot/%{name}-%{version}-%{release}.map
/boot/%{name}-%{version}-%{release}.config
/boot/%{name}-%{version}-%{release}-d.gz
/boot/%{name}-%{version}-%{release}-d.map
/boot/%{name}-%{version}-%{release}-d.config
%config %{_sysconfdir}/sysconfig/kernel-xen
%doc xcp-ng_logo.png
%ghost %attr(0644,root,root) %{_sysconfdir}/sysconfig/kernel-xen-args

%files hypervisor-debuginfo
/boot/%{name}-syms-%{version}-%{release}
/boot/%{name}-syms-%{version}-%{release}-d

%files tools
%{_bindir}/xenstore
%{_bindir}/xenstore-chmod
%{_bindir}/xenstore-control
%{_bindir}/xenstore-exists
%{_bindir}/xenstore-list
%{_bindir}/xenstore-ls
%{_bindir}/xenstore-read
%{_bindir}/xenstore-rm
%{_bindir}/xenstore-watch
%{_bindir}/xenstore-write
%{python_sitearch}/%{name}/__init__.py*
%{python_sitearch}/%{name}/lowlevel/__init__.py*
%{python_sitearch}/%{name}/lowlevel/xs.so

%files devel
%{_includedir}/%{name}/COPYING
%{_includedir}/%{name}/arch-arm.h
%{_includedir}/%{name}/arch-arm/hvm/save.h
%{_includedir}/%{name}/arch-x86/cpuid.h
%{_includedir}/%{name}/arch-x86/cpufeatureset.h
%{_includedir}/%{name}/arch-x86/hvm/save.h
%{_includedir}/%{name}/arch-x86/pmu.h
%{_includedir}/%{name}/arch-x86/xen-mca.h
%{_includedir}/%{name}/arch-x86/xen-x86_32.h
%{_includedir}/%{name}/arch-x86/xen-x86_64.h
%{_includedir}/%{name}/arch-x86/xen.h
%{_includedir}/%{name}/arch-x86_32.h
%{_includedir}/%{name}/arch-x86_64.h
%{_includedir}/%{name}/callback.h
%{_includedir}/%{name}/dom0_ops.h
%{_includedir}/%{name}/domctl.h
%{_includedir}/%{name}/elfnote.h
%{_includedir}/%{name}/errno.h
%{_includedir}/%{name}/event_channel.h
%{_includedir}/%{name}/features.h
%{_includedir}/%{name}/foreign/arm32.h
%{_includedir}/%{name}/foreign/arm64.h
%{_includedir}/%{name}/foreign/x86_32.h
%{_includedir}/%{name}/foreign/x86_64.h
%{_includedir}/%{name}/grant_table.h
%{_includedir}/%{name}/hvm/e820.h
%{_includedir}/%{name}/hvm/hvm_info_table.h
%{_includedir}/%{name}/hvm/hvm_op.h
%{_includedir}/%{name}/hvm/hvm_vcpu.h
%{_includedir}/%{name}/hvm/hvm_xs_strings.h
%{_includedir}/%{name}/hvm/ioreq.h
%{_includedir}/%{name}/hvm/params.h
%{_includedir}/%{name}/hvm/pvdrivers.h
%{_includedir}/%{name}/hvm/save.h
%{_includedir}/%{name}/io/blkif.h
%{_includedir}/%{name}/io/console.h
%{_includedir}/%{name}/io/fbif.h
%{_includedir}/%{name}/io/fsif.h
%{_includedir}/%{name}/io/kbdif.h
%{_includedir}/%{name}/io/libxenvchan.h
%{_includedir}/%{name}/io/netif.h
%{_includedir}/%{name}/io/pciif.h
%{_includedir}/%{name}/io/protocols.h
%{_includedir}/%{name}/io/ring.h
%{_includedir}/%{name}/io/tpmif.h
%{_includedir}/%{name}/io/usbif.h
%{_includedir}/%{name}/io/vscsiif.h
%{_includedir}/%{name}/io/xenbus.h
%{_includedir}/%{name}/io/xs_wire.h
%{_includedir}/%{name}/kexec.h
%{_includedir}/%{name}/memory.h
%{_includedir}/%{name}/nmi.h
%{_includedir}/%{name}/physdev.h
%{_includedir}/%{name}/platform.h
%{_includedir}/%{name}/pmu.h
%{_includedir}/%{name}/pv-iommu.h
%{_includedir}/%{name}/sched.h
%{_includedir}/%{name}/sys/evtchn.h
%{_includedir}/%{name}/sys/gntalloc.h
%{_includedir}/%{name}/sys/gntdev.h
%{_includedir}/%{name}/sys/privcmd.h
%{_includedir}/%{name}/sys/xenbus_dev.h
%{_includedir}/%{name}/sysctl.h
%{_includedir}/%{name}/tmem.h
%{_includedir}/%{name}/trace.h
%{_includedir}/%{name}/vcpu.h
%{_includedir}/%{name}/version.h
%{_includedir}/%{name}/vm_event.h
%{_includedir}/%{name}/xen-compat.h
%{_includedir}/%{name}/xen.h
%{_includedir}/%{name}/xencomm.h
%{_includedir}/%{name}/xenoprof.h
%{_includedir}/%{name}/xsm/flask_op.h

%files libs
%{_libdir}/libxenevtchn.so.1
%{_libdir}/libxenevtchn.so.1.0
%{_libdir}/libxengnttab.so.1
%{_libdir}/libxengnttab.so.1.0
%{_libdir}/libxenstore.so.3.0
%{_libdir}/libxenstore.so.3.0.3
%{_libdir}/libxenvchan.so.4.7
%{_libdir}/libxenvchan.so.4.7.0

%files libs-devel
# Lib Xen Evtchn
%{_includedir}/xenevtchn.h
%{_libdir}/libxenevtchn.a
%{_libdir}/libxenevtchn.so

# Lib Xen Gnttab
%{_includedir}/xengnttab.h
%{_libdir}/libxengnttab.a
%{_libdir}/libxengnttab.so

# Lib XenStore
%{_includedir}/xenstore.h
%{_includedir}/xenstore_lib.h
%{_libdir}/libxenstore.a
%{_libdir}/libxenstore.so
# Legacy XenStore header files, excluded to discourage their use
%exclude %{_includedir}/xs.h
%exclude %{_includedir}/xenstore-compat/xs.h
%exclude %{_includedir}/xs_lib.h
%exclude %{_includedir}/xenstore-compat/xs_lib.h
# Lib Xen Vchan
%{_includedir}/libxenvchan.h
%{_libdir}/libxenvchan.a
%{_libdir}/libxenvchan.so

%files dom0-tools
%{_sysconfdir}/bash_completion.d/xl.sh
%exclude %{_sysconfdir}/rc.d/init.d/xencommons
%exclude %{_sysconfdir}/rc.d/init.d/xendomains
%exclude %{_sysconfdir}/rc.d/init.d/xendriverdomain
%exclude %{_sysconfdir}/sysconfig/xendomains
%if %with_systemd
%exclude %{_sysconfdir}/rc.d/init.d/xen-watchdog
%else
%{_sysconfdir}/rc.d/init.d/xen-watchdog
%endif
%config %{_sysconfdir}/logrotate.d/xen-tools
%config %{_sysconfdir}/sysconfig/xencommons
%config %{_sysconfdir}/xen/oxenstored.conf
%{_sysconfdir}/xen/scripts/block
%{_sysconfdir}/xen/scripts/block-common.sh
%{_sysconfdir}/xen/scripts/block-drbd-probe
%{_sysconfdir}/xen/scripts/block-dummy
%{_sysconfdir}/xen/scripts/block-enbd
%{_sysconfdir}/xen/scripts/block-iscsi
%{_sysconfdir}/xen/scripts/block-nbd
%{_sysconfdir}/xen/scripts/block-tap
%{_sysconfdir}/xen/scripts/colo-proxy-setup
%{_sysconfdir}/xen/scripts/external-device-migrate
%{_sysconfdir}/xen/scripts/hotplugpath.sh
%{_sysconfdir}/xen/scripts/locking.sh
%{_sysconfdir}/xen/scripts/logging.sh
%{_sysconfdir}/xen/scripts/vif-bridge
%{_sysconfdir}/xen/scripts/vif-common.sh
%{_sysconfdir}/xen/scripts/vif-nat
%{_sysconfdir}/xen/scripts/vif-openvswitch
%{_sysconfdir}/xen/scripts/vif-route
%{_sysconfdir}/xen/scripts/vif-setup
%{_sysconfdir}/xen/scripts/vif2
%{_sysconfdir}/xen/scripts/vscsi
%{_sysconfdir}/xen/scripts/xen-hotplug-cleanup
%{_sysconfdir}/xen/scripts/xen-hotplug-common.sh
%{_sysconfdir}/xen/scripts/xen-network-common.sh
%{_sysconfdir}/xen/scripts/xen-script-common.sh
%exclude %{_sysconfdir}/%{name}/cpupool
%exclude %{_sysconfdir}/%{name}/README
%exclude %{_sysconfdir}/%{name}/README.incompatibilities
%exclude %{_sysconfdir}/%{name}/xlexample.hvm
%exclude %{_sysconfdir}/%{name}/xlexample.pvlinux
%config %{_sysconfdir}/xen/xl.conf
%{_bindir}/pygrub
%{_bindir}/xen-cpuid
%{_bindir}/xen-detect
%{_bindir}/xenalyze
%{_bindir}/xencons
%{_bindir}/xencov_split
%{_bindir}/xentrace_format
%{python_sitearch}/fsimage.so
%{python_sitearch}/grub/ExtLinuxConf.py*
%{python_sitearch}/grub/GrubConf.py*
%{python_sitearch}/grub/LiloConf.py*
%{python_sitearch}/grub/__init__.py*
%{python_sitearch}/pygrub-*.egg-info
%{python_sitearch}/xen-*.egg-info
#{python_sitearch}/xen/__init__.py*           - Must not duplicate xen-tools
#{python_sitearch}/xen/lowlevel/__init__.py*  - Must not duplicate xen-tools
%{python_sitearch}/xen/lowlevel/xc.so
%{python_sitearch}/xen/migration/__init__.py*
%{python_sitearch}/xen/migration/legacy.py*
%{python_sitearch}/xen/migration/libxc.py*
%{python_sitearch}/xen/migration/libxl.py*
%{python_sitearch}/xen/migration/public.py*
%{python_sitearch}/xen/migration/tests.py*
%{python_sitearch}/xen/migration/verify.py*
%{python_sitearch}/xen/migration/xl.py*
%{_libexecdir}/%{name}/bin/convert-legacy-stream
%{_libexecdir}/%{name}/bin/init-xenstore-domain
%{_libexecdir}/%{name}/bin/libxl-save-helper
%{_libexecdir}/%{name}/bin/lsevtchn
%{_libexecdir}/%{name}/bin/pygrub
%{_libexecdir}/%{name}/bin/readnotes
%{_libexecdir}/%{name}/bin/verify-stream-v2
%{_libexecdir}/%{name}/bin/xen-init-dom0
%{_libexecdir}/%{name}/bin/xenconsole
%{_libexecdir}/%{name}/bin/xenctx
%{_libexecdir}/%{name}/bin/xendomains
%{_libexecdir}/%{name}/bin/xenguest
%{_libexecdir}/%{name}/bin/xenpaging
%{_libexecdir}/%{name}/bin/xenpvnetboot
%{_libexecdir}/%{name}/boot/hvmloader
%{_sbindir}/flask-get-bool
%{_sbindir}/flask-getenforce
%{_sbindir}/flask-label-pci
%{_sbindir}/flask-loadpolicy
%{_sbindir}/flask-set-bool
%{_sbindir}/flask-setenforce
%{_sbindir}/gdbsx
%{_sbindir}/kdd
%{_sbindir}/oxenstored
%{_sbindir}/xen-hptool
%{_sbindir}/xen-hvmcrash
%{_sbindir}/xen-hvmctx
%{_sbindir}/xen-livepatch
%{_sbindir}/xen-lowmemd
%{_sbindir}/xen-mceinj
%{_sbindir}/xen-mfndump
%exclude %{_sbindir}/xen-ringwatch
%{_sbindir}/xen-vmdebug
%{_sbindir}/xenbaked
%{_sbindir}/xenconsoled
%{_sbindir}/xencov
%{_sbindir}/xenmon.py
%{_sbindir}/xenperf
%{_sbindir}/xenpm
%{_sbindir}/xenpmd
%{_sbindir}/xenstored
%{_sbindir}/xentop
%{_sbindir}/xentrace
%{_sbindir}/xentrace_setmask
%{_sbindir}/xentrace_setsize
%{_sbindir}/xenwatchdogd
%{_sbindir}/xl
%exclude %{_sbindir}/gtracestat
%exclude %{_sbindir}/gtraceview
%exclude %{_sbindir}/xen-bugtool
%exclude %{_sbindir}/xen-tmem-list-parse
%exclude %{_sbindir}/xenlockprof
%{_mandir}/man1/xentop.1.gz
%{_mandir}/man1/xentrace_format.1.gz
%{_mandir}/man1/xenstore-chmod.1.gz
%{_mandir}/man1/xenstore-ls.1.gz
%{_mandir}/man1/xenstore.1.gz
%{_mandir}/man1/xl.1.gz
%{_mandir}/man5/xl.cfg.5.gz
%{_mandir}/man5/xl.conf.5.gz
%{_mandir}/man5/xlcpupool.cfg.5.gz
%{_mandir}/man8/xentrace.8.gz
%dir /var/lib/xen
%dir /var/log/xen
%if %with_systemd
%{_unitdir}/proc-xen.mount
%{_unitdir}/var-lib-xenstored.mount
%{_unitdir}/xen-init-dom0.service
%{_unitdir}/xen-watchdog.service
%{_unitdir}/xenconsoled.service
%{_unitdir}/xenstored.service
%{_unitdir}/xenstored.socket
%{_unitdir}/xenstored_ro.socket
%exclude %{_prefix}/lib/modules-load.d/xen.conf
%exclude %{_unitdir}/xen-qemu-dom0-disk-backend.service
%exclude %{_unitdir}/xendomains.service
%endif

%files dom0-libs
%{_libdir}/fs/btrfs/fsimage.so
%{_libdir}/fs/ext2fs-lib/fsimage.so
%{_libdir}/fs/fat/fsimage.so
%{_libdir}/fs/iso9660/fsimage.so
%{_libdir}/fs/reiserfs/fsimage.so
%{_libdir}/fs/ufs/fsimage.so
%{_libdir}/fs/xfs/fsimage.so
%{_libdir}/fs/zfs/fsimage.so
%{_libdir}/libfsimage.so.1.0
%{_libdir}/libfsimage.so.1.0.0
%{_libdir}/libxencall.so.1
%{_libdir}/libxencall.so.1.0
%{_libdir}/libxenctrl.so.4.7
%{_libdir}/libxenctrl.so.4.7.0
%{_libdir}/libxenforeignmemory.so.1
%{_libdir}/libxenforeignmemory.so.1.2
%{_libdir}/libxenguest.so.4.7
%{_libdir}/libxenguest.so.4.7.0
%{_libdir}/libxenlight.so.4.7
%{_libdir}/libxenlight.so.4.7.0
%{_libdir}/libxenstat.so.0
%{_libdir}/libxenstat.so.0.0
%{_libdir}/libxentoollog.so.1
%{_libdir}/libxentoollog.so.1.0
%{_libdir}/libxlutil.so.4.7
%{_libdir}/libxlutil.so.4.7.0

%files dom0-libs-devel
%{_includedir}/fsimage.h
%{_includedir}/fsimage_grub.h
%{_includedir}/fsimage_plugin.h
%{_libdir}/libfsimage.so

%{_includedir}/xencall.h
%{_libdir}/libxencall.a
%{_libdir}/libxencall.so

%{_includedir}/xenctrl.h
%{_includedir}/xenctrl_compat.h
%{_libdir}/libxenctrl.a
%{_libdir}/libxenctrl.so

%{_includedir}/xenforeignmemory.h
%{_libdir}/libxenforeignmemory.a
%{_libdir}/libxenforeignmemory.so

%{_includedir}/xenguest.h
%{_libdir}/libxenguest.a
%{_libdir}/libxenguest.so

%{_includedir}/xentoollog.h
%{_libdir}/libxentoollog.a
%{_libdir}/libxentoollog.so

%{_includedir}/_libxl_list.h
%{_includedir}/_libxl_types.h
%{_includedir}/_libxl_types_json.h
%{_includedir}/libxl.h
%{_includedir}/libxl_event.h
%{_includedir}/libxl_json.h
%{_includedir}/libxl_utils.h
%{_includedir}/libxl_uuid.h
%{_includedir}/libxlutil.h
%{_libdir}/libxenlight.a
%{_libdir}/libxenlight.so
%{_libdir}/libxlutil.a
%{_libdir}/libxlutil.so
/usr/share/pkgconfig/xenlight.pc
/usr/share/pkgconfig/xlutil.pc

%{_includedir}/xenstat.h
%{_libdir}/libxenstat.a
%{_libdir}/libxenstat.so

%files ocaml-libs
%{_libdir}/ocaml/stublibs/dllxenbus_stubs.so
%{_libdir}/ocaml/stublibs/dllxenbus_stubs.so.owner
%{_libdir}/ocaml/stublibs/dllxenctrl_stubs.so
%{_libdir}/ocaml/stublibs/dllxenctrl_stubs.so.owner
%{_libdir}/ocaml/stublibs/dllxeneventchn_stubs.so
%{_libdir}/ocaml/stublibs/dllxeneventchn_stubs.so.owner
%{_libdir}/ocaml/stublibs/dllxenlight_stubs.so
%{_libdir}/ocaml/stublibs/dllxenlight_stubs.so.owner
%{_libdir}/ocaml/stublibs/dllxenmmap_stubs.so
%{_libdir}/ocaml/stublibs/dllxenmmap_stubs.so.owner
%{_libdir}/ocaml/stublibs/dllxentoollog_stubs.so
%{_libdir}/ocaml/stublibs/dllxentoollog_stubs.so.owner
%{_libdir}/ocaml/xenbus/META
%{_libdir}/ocaml/xenbus/xenbus.cma
%{_libdir}/ocaml/xenbus/xenbus.cmo
%{_libdir}/ocaml/xenctrl/META
%{_libdir}/ocaml/xenctrl/xenctrl.cma
%{_libdir}/ocaml/xeneventchn/META
%{_libdir}/ocaml/xeneventchn/xeneventchn.cma
%{_libdir}/ocaml/xenlight/META
%{_libdir}/ocaml/xenlight/xenlight.cma
%{_libdir}/ocaml/xenmmap/META
%{_libdir}/ocaml/xenmmap/xenmmap.cma
%exclude %{_libdir}/ocaml/xenstore/META
%exclude %{_libdir}/ocaml/xenstore/xenstore.cma
%exclude %{_libdir}/ocaml/xenstore/xenstore.cmo
%{_libdir}/ocaml/xentoollog/META
%{_libdir}/ocaml/xentoollog/xentoollog.cma

%files ocaml-devel
%{_libdir}/ocaml/xenbus/libxenbus_stubs.a
%{_libdir}/ocaml/xenbus/xenbus.a
%{_libdir}/ocaml/xenbus/xenbus.cmi
%{_libdir}/ocaml/xenbus/xenbus.cmx
%{_libdir}/ocaml/xenbus/xenbus.cmxa
%{_libdir}/ocaml/xenctrl/libxenctrl_stubs.a
%{_libdir}/ocaml/xenctrl/xenctrl.a
%{_libdir}/ocaml/xenctrl/xenctrl.cmi
%{_libdir}/ocaml/xenctrl/xenctrl.cmx
%{_libdir}/ocaml/xenctrl/xenctrl.cmxa
%{_libdir}/ocaml/xeneventchn/libxeneventchn_stubs.a
%{_libdir}/ocaml/xeneventchn/xeneventchn.a
%{_libdir}/ocaml/xeneventchn/xeneventchn.cmi
%{_libdir}/ocaml/xeneventchn/xeneventchn.cmx
%{_libdir}/ocaml/xeneventchn/xeneventchn.cmxa
%{_libdir}/ocaml/xenlight/libxenlight_stubs.a
%{_libdir}/ocaml/xenlight/xenlight.a
%{_libdir}/ocaml/xenlight/xenlight.cmi
%{_libdir}/ocaml/xenlight/xenlight.cmx
%{_libdir}/ocaml/xenlight/xenlight.cmxa
%{_libdir}/ocaml/xenmmap/libxenmmap_stubs.a
%{_libdir}/ocaml/xenmmap/xenmmap.a
%{_libdir}/ocaml/xenmmap/xenmmap.cmi
%{_libdir}/ocaml/xenmmap/xenmmap.cmx
%{_libdir}/ocaml/xenmmap/xenmmap.cmxa
%exclude %{_libdir}/ocaml/xenstore/xenstore.a
%exclude %{_libdir}/ocaml/xenstore/xenstore.cmi
%exclude %{_libdir}/ocaml/xenstore/xenstore.cmx
%exclude %{_libdir}/ocaml/xenstore/xenstore.cmxa
%{_libdir}/ocaml/xentoollog/libxentoollog_stubs.a
%{_libdir}/ocaml/xentoollog/xentoollog.a
%{_libdir}/ocaml/xentoollog/xentoollog.cmi
%{_libdir}/ocaml/xentoollog/xentoollog.cmx
%{_libdir}/ocaml/xentoollog/xentoollog.cmxa

%files installer-files
%{_libdir}/libxenctrl.so.4.7
%{_libdir}/libxenctrl.so.4.7.0
%{_libdir}/libxenguest.so.4.7
%{_libdir}/libxenguest.so.4.7.0
%{python_sitearch}/xen/__init__.py*
%{python_sitearch}/xen/lowlevel/__init__.py*
%{python_sitearch}/xen/lowlevel/xc.so

%doc

%post hypervisor
# Update the debug and release symlinks
ln -sf %{name}-%{version}-%{release}-d.gz /boot/xen-debug.gz
ln -sf %{name}-%{version}-%{release}.gz /boot/xen-release.gz

# Point /boot/xen.gz appropriately
if [ ! -e /boot/xen.gz ]; then
    # Use a release hypervisor by default
    ln -sf %{name}-%{version}-%{release}.gz /boot/xen.gz
else
    # Else look at the current link, and whether it is debug
    path="`readlink -f /boot/xen.gz`"
    if [ ${path} != ${path%%-d.gz} ]; then
        ln -sf %{name}-%{version}-%{release}-d.gz /boot/xen.gz
    else
        ln -sf %{name}-%{version}-%{release}.gz /boot/xen.gz
    fi
fi

if [ -e %{_sysconfdir}/sysconfig/kernel ] && ! grep -q '^HYPERVISOR' %{_sysconfdir}/sysconfig/kernel ; then
  cat %{_sysconfdir}/sysconfig/kernel-xen >> %{_sysconfdir}/sysconfig/kernel
fi

mkdir -p %{_rundir}/reboot-required.d/%{name}
touch %{_rundir}/reboot-required.d/%{name}/%{version}-%{release}

%if %with_systemd
%post dom0-tools
%systemd_post proc-xen.mount
%systemd_post var-lib-xenstored.mount
%systemd_post xen-init-dom0.service
%systemd_post xen-watchdog.service
%systemd_post xenconsoled.service
%systemd_post xenstored.service
%systemd_post xenstored.socket
%systemd_post xenstored_ro.socket

%preun dom0-tools
%systemd_preun proc-xen.mount
%systemd_preun var-lib-xenstored.mount
%systemd_preun xen-init-dom0.service
%systemd_preun xen-watchdog.service
%systemd_preun xenconsoled.service
%systemd_preun xenstored.service
%systemd_preun xenstored.socket
%systemd_preun xenstored_ro.socket

%postun dom0-tools
%systemd_postun proc-xen.mount
%systemd_postun var-lib-xenstored.mount
%systemd_postun xen-init-dom0.service
%systemd_postun xen-watchdog.service
%systemd_postun xenconsoled.service
%systemd_postun xenstored.service
%systemd_postun xenstored.socket
%systemd_postun xenstored_ro.socket
%endif

