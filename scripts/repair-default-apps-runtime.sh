#!/bin/sh
set -eu

archive=${1:-/tmp/czero-default-apps-runtime-fix.tar.gz}
work=/tmp/czero-default-apps-runtime-fix

if [ "$(id -u)" -ne 0 ]; then
  echo "run with sudo: sudo sh /tmp/repair-default-apps-runtime.sh" >&2
  exit 1
fi

if [ ! -s "$archive" ]; then
  echo "missing or empty archive: $archive" >&2
  exit 1
fi

rm -rf "$work"
mkdir -p "$work"
tar -xzf "$archive" -C "$work"

for app in zero-settings zero-terminal zero-files zero-power-menu zero-system-monitor zero-app-store zero-robot; do
  src="$work/bin/$app"
  if [ ! -s "$src" ]; then
    echo "refusing empty launcher: $src" >&2
    exit 1
  fi
  install -D -m 0755 "$src" "/usr/bin/$app"
done

if [ ! -s "$work/src/czero_apps/apps/robot/app.py" ]; then
  echo "refusing empty Python source tree" >&2
  exit 1
fi

rm -rf /usr/lib/python3/dist-packages/czero_apps
mkdir -p /usr/lib/python3/dist-packages/czero_apps
cp -a "$work/src/czero_apps/." /usr/lib/python3/dist-packages/czero_apps/
find /usr/lib/python3/dist-packages/czero_apps -type f -name "*.py" -exec chmod 0644 {} +

find /usr/bin -maxdepth 1 -type f -name "zero-*" -printf "%f %s\n" | sort
find /usr/lib/python3/dist-packages/czero_apps/apps -maxdepth 2 -type f -name "app.py" -printf "%p %s\n" | sort
