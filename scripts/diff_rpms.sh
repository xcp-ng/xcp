#!/bin/bash
# Compares 2 RPMs
set -e

if [ -z $2 ]
then
  echo "Usage: $0 RPM1 RPM2"
  exit
fi

rpm1=$(realpath $1)
rpm2=$(realpath $2)

TMPDIR=$(mktemp -d)
pushd "$TMPDIR"

mkdir rpm1
cd rpm1
rpm2cpio $rpm1 | cpio -idm
rpm -qp $rpm1 --scripts > scripts.txt
rpm -qp --qf "Name        : %{name}
License     : %{license}
URL         : %{url}
Summary     : %{summary}
Description : %{description}
" $rpm1 > info.txt
cd ..

mkdir rpm2
cd rpm2
rpm2cpio $rpm2 | cpio -idm
rpm -qp $rpm2 --scripts > scripts.txt
rpm -qp --qf "Name        : %{name}
License     : %{license}
URL         : %{url}
Summary     : %{summary}
Description : %{description}
" $rpm2 > info.txt
cd ..

meld rpm1 rpm2

popd

\rm -rv "$TMPDIR"