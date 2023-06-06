#!/bin/bash

set -ueE

usage()
{
    echo "----------------------------------------------------------------------------------------"
    echo "- This script is for internal use at Vates to transfer and manage ISOs generated automatically by our Jenkins server and to store them on our PXE server and ISO SR."
    echo "- Usage: $0 <XCP-ng version> <Repository> <PXE Server> <Path on the PXE server> <ISO SR Server> <Path on the ISO SR Server> <Path on the PXE Server for the installer>"
    echo "- All options are mandatory."
    echo "- Repository: updates, ci, testing..."
    echo "- Version of XCP-ng: 8.2 or 8.3"
    echo "- Example: $0 8.3 updates myuser@my_pxe /my/path/pxe/ iso_user@srv-sr-iso /my/path/on/sriso/ /my/path/pxe/installers/"
    echo "----------------------------------------------------------------------------------------"
}

if [ $# -lt 7 ]; then
    echo "Missing parameter(s)."
    echo
    usage
    exit 1
fi

VERSION="$1"
REPO="$2"
PXESERVER="$3"
PXEPATH="${4%/}/" # ensure there's a trailing slash
ISOSR="$5"
ISOSRPATH="${6%/}/"
PXEPATHINST="${7%/}/"

if [ "$VERSION" != "8.3" ] && [ "$VERSION" != "8.2" ]; then
    echo "Unsupported version. Please choose between 8.2 and 8.3."
    echo
    usage
    exit 1
fi

# get file names
ISO_FILE_NAME_NI=$(ls *.iso | grep netinstall)
ISO_FILE_NAME=$(ls *.iso | grep -v netinstall)

# defined early so that the cleanup function doesn't fail due to undefined variable
LOCAL_DIRECTORY_NAME="/tmp/${ISO_FILE_NAME%.*}"

function cleanup_files () {
    #clean files
    echo "We clean the temp directory, if it exists."
    if [ -d "${LOCAL_DIRECTORY_NAME}" ]; then
        rm -Rf ${LOCAL_DIRECTORY_NAME}
    fi
    echo "We clean the img and iso files."
    rm -f *.img *.iso
}

trap cleanup_files EXIT INT

set -x

#scp to the pxe server
echo "We're doing the scp to the pxe server for the two ISOs."
scp *.iso "${PXESERVER}":"${PXEPATH}"
echo "Creating or changing the '-latest' link on the PXE server."
ssh "${PXESERVER}" "ln -sf '${PXEPATH}${ISO_FILE_NAME}' '${PXEPATH}xcp-ng-${VERSION}-${REPO}-latest'"
echo "Cleaning ISOs older than 10 days on the pxe."
ssh "${PXESERVER}" "find '${PXEPATH}' -mtime +9 -name *nightly*.iso -delete"

# For ci and updates repos, uncompress to an internal netinstall repo on PXE server
if [ "$REPO" == "ci" ] || [ "$REPO" == "updates" ]; then
    echo "Repo: ${REPO}: copy the iso content (${ISO_FILE_NAME}) into a directory of the pxe server."
    DISTANT_DIRECTORY_NAME="${PXEPATHINST}${VERSION}-${REPO}/"
    mkdir "${LOCAL_DIRECTORY_NAME}"
    7z x -o"${LOCAL_DIRECTORY_NAME}/" "${ISO_FILE_NAME}"
    if [ ! -z "${DISTANT_DIRECTORY_NAME}" ]; then
        rsync -av --delete "${LOCAL_DIRECTORY_NAME}/" "${PXESERVER}":"${DISTANT_DIRECTORY_NAME}"
        ssh "${PXESERVER}" "chmod -R 755 '${DISTANT_DIRECTORY_NAME}'"
    fi
fi

# Create a hardlink for a monthly ISO each month. We keep it three months.
MONTH=$(date +%Y%m)
THEDATE=$(date +%Y%m%d)
MONTHLY_ISO_NAME="${ISO_FILE_NAME/nightly/monthly}"
MONTHLY_ISO_NAME="${MONTHLY_ISO_NAME/${THEDATE}/${MONTH}}"
if ssh -q "${PXESERVER}" [[ ! -f "${PXEPATH}${MONTHLY_ISO_NAME}" ]]; then
    ssh "${PXESERVER}" "ln '${PXEPATH}${ISO_FILE_NAME}' '${PXEPATH}${MONTHLY_ISO_NAME}'"
    ssh "${PXESERVER}" "find '${PXEPATH}' -type f -mtime +182 -name '*monthly*.iso' -delete"
fi

# scp to the ISO SR
echo "Copy the ISO files to the ISO SR."
scp *.iso "${ISOSR}":"${ISOSRPATH}"
ssh "${ISOSR}" "find '${ISOSRPATH}' -mtime +2 -name '*nightly*.iso' -delete"
