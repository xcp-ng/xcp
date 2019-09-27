#!/bin/bash
# Must be run from the parent directory of the rsynced repositories
for version in "7.6" "8.0"; do
    MAJOR=${version:0:1}
    rsync -rlptv updates.xcp-ng.org::repo/$MAJOR/$version/*/Source/SPackages/*.src.rpm xcp-ng/$version/
    rsync -rlptv updates.xcp-ng.org::repo/$MAJOR/$version/*/x86_64/Packages/*.rpm xcp-ng_rpms/$version/
    mkdir -p workdir/$version
    for f in $(ls xcp-ng_rpms/${version}/*.rpm); do echo "$(basename $f),$(rpm -qp $f --qf '%{sourcerpm},%{name}' 2>/dev/null)"; done > workdir/$version/xcp-ng-rpms-srpms.txt
done
rsync -rlptv --delete-delay rsync://mirror.in2p3.fr/pub/epel/7/SRPMS/Packages/*/*.rpm epel/
rsync -rlptv --delete-delay mirror.nsc.liu.se::centos-store/centos/7/{os,updates}/Source/SPackages/*.src.rpm centos/
