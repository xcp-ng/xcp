#!/bin/bash

set -ueE

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

if [ $# -lt 2 ]; then
    echo "Missing argument(s)"
    echo
    usage
    exit 1
fi

VERSION="$1"

if [ "$VERSION" != "8.3" ] && [ "$VERSION" != "8.2" ]; then
    echo "Unsupported version. Please choose between 8.2 and 8.3."
    exit
fi

REPOSITORY="$2"

THEDATE=$(date +%Y%m%d)

set -x

NAMEIMG="install-${VERSION}-${REPOSITORY}.img"
NAMEISO="xcp-ng-${VERSION}-${REPOSITORY}-nightly-${THEDATE}.iso"
NAMEISONI="xcp-ng-${VERSION}-${REPOSITORY}-netinstall-nightly-${THEDATE}.iso"

MNTVOL="XCP-ng ${VERSION} ${REPOSITORY} ${THEDATE}"

sudo yum install -y genisoimage syslinux grub-tools createrepo_c libfaketime

cd /data

sudo ./scripts/create-installimg.sh --srcurl "https://updates.xcp-ng.org/8/${VERSION}" -o "${NAMEIMG}" "${VERSION}":"${REPOSITORY}"

./scripts/create-install-iso.sh --netinstall --srcurl "https://updates.xcp-ng.org/8/${VERSION}" -V "${MNTVOL}" -o "${NAMEISONI}" "${VERSION}":"${REPOSITORY}" "${NAMEIMG}"

./scripts/create-install-iso.sh --srcurl "https://updates.xcp-ng.org/8/${VERSION}" -V "${MNTVOL}" -o "${NAMEISO}" "${VERSION}":"${REPOSITORY}" "${NAMEIMG}"
