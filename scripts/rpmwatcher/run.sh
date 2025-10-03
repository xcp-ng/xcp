#!/bin/sh
CENTOS_VERSION=7.5.1804

if [ -z "$3" ]; then
    echo "Usage: $0 VERSION BASEDIR PATH_TO_GIT_REPO"
    exit 1
fi
VERSION=$1
BASEDIR=$2
PATH_TO_GIT_REPO=$3
PATH_TO_SCRIPTS=$PATH_TO_GIT_REPO/scripts/rpmwatcher

set -xe
cd $BASEDIR

# sync repos and produce some data
$PATH_TO_SCRIPTS/sync_repos.sh

# gather data and produce WIP files for the next scripts to use
$PATH_TO_SCRIPTS/rpmwatcher_update.py $VERSION .

# get information about the dependencies, from within a CentOS docker container
# using "host" network because "bridge" may fail in some hosting environments
DOCKER_NETWORK=host
docker run --rm -t --privileged --network $DOCKER_NETWORK \
    -v ~/data:/data -v ~/git/xcp/scripts/rpmwatcher:/scripts centos:$CENTOS_VERSION \
    /scripts/rpmwatcher_extract_deps.py $VERSION /data

# compute roles
$PATH_TO_SCRIPTS/rpmwatcher_extract_roles.py $VERSION .

# produce reports
$PATH_TO_SCRIPTS/rpmwatcher_format_reports.py $VERSION . html
$PATH_TO_SCRIPTS/rpmwatcher_format_reports.py $VERSION . markdown
$PATH_TO_SCRIPTS/rpmwatcher_format_reports.py $VERSION . csv
