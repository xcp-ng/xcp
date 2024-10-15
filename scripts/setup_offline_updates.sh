#!/usr/bin/env bash

usage() {
    echo
    echo "Usage: $0 <repo-type> <tar-file>"
    echo
    echo "Creates or updates an XCP-ng offline <repo-type> repository from the <tar-file> archive."
    echo
    echo "Arguments:"
    echo "  repo-type   The repository type, based on its name on online mirrors. Example : 'updates'."
    echo "  tar-file    The path to the archive containing the repository files."
}

if [ -z "$2" ]; then
    echo "Error: argument(s) missing."
    usage
    exit 1
fi

set -eu

REPO_TYPE="$1"
TAR_FILE="$2"
REPOS_DIR="/var/local/xcp-ng-repos"
REPONAME="xcp-ng-offline-$REPO_TYPE"

if [ ! -e "$TAR_FILE" ]; then
    echo "Error: file $TAR_FILE not found."
    exit 2
fi

echo "- Checking the integrity of $TAR_FILE"
if ! tar xOf "$TAR_FILE" >/dev/null 2>&1; then
    echo "Error: Tar file $TAR_FILE failed the integrity check."
    exit 3
fi

if ! tar -tf "$TAR_FILE" | grep -q "^${REPO_TYPE}/$"; then
    echo "Error: directory $REPO_TYPE/ not found in archive $TAR_FILE."
    exit 4
fi

mkdir -p "$REPOS_DIR"

if [ -d "$REPOS_DIR/$REPO_TYPE" ]; then
    echo "- Deleting old repo at $REPOS_DIR/$REPO_TYPE"
    rm "$REPOS_DIR/$REPO_TYPE" -r
fi

echo "- Extracting $TAR_FILE to $REPOS_DIR/$REPO_TYPE"
tar -xf "$TAR_FILE" -C "$REPOS_DIR"

echo "- Writing /etc/yum.repos.d/$REPONAME.repo"
cat <<EOF > "/etc/yum.repos.d/$REPONAME.repo"
[xcp-ng-offline-$REPO_TYPE]
name=XCP-ng Offline ${REPO_TYPE^} Repository
baseurl=file://$REPOS_DIR/$REPO_TYPE/x86_64/
enabled=1
gpgcheck=1
gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-xcpng
EOF

echo "- Deleting yum cache"
rm /var/cache/yum -r

echo
echo "Success. The $REPONAME yum repository is available locally."
