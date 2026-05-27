#!/bin/sh
set -eu

archive=${1:-/tmp/czero-appfiles-fix.tar.gz}
work=/tmp/czero-appfiles-fix

if [ "$(id -u)" -ne 0 ]; then
  echo "run with sudo: sudo sh /tmp/repair-applaunch-assets.sh" >&2
  exit 1
fi

if [ ! -s "$archive" ]; then
  echo "missing or empty archive: $archive" >&2
  exit 1
fi

rm -rf "$work"
mkdir -p "$work"
tar -xzf "$archive" -C "$work"

for file in "$work"/applications/*.desktop "$work"/icons/*; do
  if [ ! -s "$file" ]; then
    echo "refusing empty source: $file" >&2
    exit 1
  fi
done

mkdir -p \
  /usr/share/APPLaunch/applications \
  /usr/share/APPLaunch/icons \
  /usr/share/APPLaunch/share/images

cp -f "$work"/applications/*.desktop /usr/share/APPLaunch/applications/
cp -f "$work"/icons/* /usr/share/APPLaunch/icons/
cp -f "$work"/icons/* /usr/share/APPLaunch/share/images/

chmod 0644 \
  /usr/share/APPLaunch/applications/*.desktop \
  /usr/share/APPLaunch/icons/* \
  /usr/share/APPLaunch/share/images/*

find /usr/share/APPLaunch/applications -maxdepth 1 -type f -name "*.desktop" -printf "%f %s\n" | sort
