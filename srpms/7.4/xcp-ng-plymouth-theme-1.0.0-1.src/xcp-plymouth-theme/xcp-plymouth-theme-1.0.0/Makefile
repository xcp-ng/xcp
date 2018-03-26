include $(B_BASE)/common.mk
include $(B_BASE)/rpmbuild.mk

include $(PROJECT_OUTPUTDIR)/kernel-dom0/kernel.inc

RPM_EXTRA_RPMBUILD_OPTIONS += --define "kernel_version $(LINUX_KABI_VERSION)"

VERSION := 1.0
$(eval $(shell $(call git_cset_number,xcp-ng-plymouth-theme)))
RELEASE := $(CSET_NUMBER)

SPEC := $(RPM_SPECSDIR)/xcp-ng-plymouth-theme.spec
SRPM := $(RPM_SRPMSDIR)/xcp-ng-plymouth-theme-$(VERSION)-$(RELEASE).src.rpm

build: $(SPEC) $(MY_SOURCES)/MANIFEST
	cp *.png xcp-ng.plymouth xcp-ng.script $(RPM_SOURCESDIR)/
	$(RPMBUILD) -ba $(SPEC)

$(SPEC): xcp-ng-plymouth-theme.spec.in $(RPM_DIRECTORIES) Makefile
	sed -e 's/@XS_VERSION@/$(VERSION)/; s/@XS_RELEASE@/$(RELEASE)/' < $< > $@.tmp
	mv -f $@.tmp $@

$(MY_SOURCES)/MANIFEST: $(MY_SOURCES)/.dirstamp
	echo "$(COMPONENT) gpl file $(SRPM)" > $@.tmp
	mv -f $@.tmp $@

