#!/bin/sh
set -e

INSTALLIMG="$1"
HOSTINSTALLER=$HOME/src/host-installer

# copies a few files too much, but that's harmless
cp -rv "$HOSTINSTALLER"/* "$INSTALLIMG/opt/xensource/installer/"
