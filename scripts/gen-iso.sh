#!/bin/bash

set -uxeE

usage()
{
    echo "----------------------------------------------------------------------------------------"
    echo "- The purpose of this script is to be executed inside the container of our development environment to generate ISO files for XCP-ng."
    echo "- Usage: $0 <XCP-ng version> <REPOSITORY>"
    echo "- All options are mandatory."
    echo "- VERSION of XCP-ng: 8.2 or 8.3"
    echo "- REPOSITORY: update, testing, ci, ..."
    echo "- Example: $0 8.3 testing"
    echo "----------------------------------------------------------------------------------------"
}


VERSION="$1"

if [ "$VERSION" != "8.3" ] && [ "$VERSION" != "8.2" ]; then
	echo "Unsupported version. Please choose between 8.2 or 8.3."
	exit
fi

REPOSITORY="$2"

THEDATE=$(date +%Y%m%d)

NAMEIMG="install-${VERSION}-${REPOSITORY}.img"
NAMEISO="xcp-ng-${VERSION}-${REPOSITORY}-nightly-${THEDATE}.iso"
NAMEISONI="xcp-ng-${VERSION}-${REPOSITORY}-netinstall-nightly-${THEDATE}.iso"

if [ "$VERSION" = "8.3" ]; then
    MNTVOL="XCP-NG_83"
elif [ "$VERSION" = "8.2" ]; then
    MNTVOL="XCP-NG_82"
else
    MNTVOL="XCP-NG"
fi

sudo yum install -y genisoimage syslinux grub-tools createrepo_c

cd /data

sudo ./scripts/create-installimg.sh --srcurl http://mirrors.xcp-ng.org/8/${VERSION} -o ${NAMEIMG} ${VERSION}:${REPOSITORY}

./scripts/create-install-iso.sh --netinstall --srcurl http://mirrors.xcp-ng.org/8/${VERSION} -V "${MNTVOL}" -o ${NAMEISONI} ${VERSION}:${REPOSITORY} ${NAMEIMG}

./scripts/create-install-iso.sh --srcurl http://mirrors.xcp-ng.org/8/${VERSION} -V "${MNTVOL}" -o ${NAMEISO} ${VERSION}:${REPOSITORY} ${NAMEIMG}
