#!/bin/sh
set -eu

ROOT=${DESTDIR:-}

if [ "$(id -u)" -ne 0 ] && [ -z "$ROOT" ]; then
  echo "uninstall.sh must run as root unless DESTDIR is set" >&2
  exit 1
fi

rm -f "$ROOT/usr/bin/zero-settings"
rm -f "$ROOT/usr/bin/zero-terminal"
rm -f "$ROOT/usr/bin/zero-files"
rm -f "$ROOT/usr/bin/zero-power-menu"
rm -f "$ROOT/usr/bin/zero-system-monitor"
rm -f "$ROOT/usr/bin/zero-app-store"
rm -f "$ROOT/usr/bin/zero-robot"

rm -rf "$ROOT/usr/lib/python3/dist-packages/czero_apps"

rm -f "$ROOT/usr/share/APPLaunch/applications/10-zero-settings.desktop"
rm -f "$ROOT/usr/share/APPLaunch/applications/20-zero-terminal.desktop"
rm -f "$ROOT/usr/share/APPLaunch/applications/30-zero-files.desktop"
rm -f "$ROOT/usr/share/APPLaunch/applications/40-zero-system-monitor.desktop"
rm -f "$ROOT/usr/share/APPLaunch/applications/50-zero-robot.desktop"
rm -f "$ROOT/usr/share/APPLaunch/applications/90-zero-power-menu.desktop"
rm -f "$ROOT/usr/share/APPLaunch/applications/100-zero-app-store.desktop"

rm -f "$ROOT/usr/share/APPLaunch/icons/settings.svg"
rm -f "$ROOT/usr/share/APPLaunch/icons/terminal.svg"
rm -f "$ROOT/usr/share/APPLaunch/icons/files.svg"
rm -f "$ROOT/usr/share/APPLaunch/icons/power.svg"
rm -f "$ROOT/usr/share/APPLaunch/icons/system-monitor.svg"
rm -f "$ROOT/usr/share/APPLaunch/icons/app-store.svg"
rm -f "$ROOT/usr/share/APPLaunch/icons/settings.png"
rm -f "$ROOT/usr/share/APPLaunch/icons/terminal.png"
rm -f "$ROOT/usr/share/APPLaunch/icons/files.png"
rm -f "$ROOT/usr/share/APPLaunch/icons/power.png"
rm -f "$ROOT/usr/share/APPLaunch/icons/system-monitor.png"
rm -f "$ROOT/usr/share/APPLaunch/icons/app-store.png"
rm -f "$ROOT/usr/share/APPLaunch/icons/robot.png"
rm -f "$ROOT/usr/share/APPLaunch/share/images/settings.svg"
rm -f "$ROOT/usr/share/APPLaunch/share/images/terminal.svg"
rm -f "$ROOT/usr/share/APPLaunch/share/images/files.svg"
rm -f "$ROOT/usr/share/APPLaunch/share/images/power.svg"
rm -f "$ROOT/usr/share/APPLaunch/share/images/system-monitor.svg"
rm -f "$ROOT/usr/share/APPLaunch/share/images/app-store.svg"
rm -f "$ROOT/usr/share/APPLaunch/share/images/settings.png"
rm -f "$ROOT/usr/share/APPLaunch/share/images/terminal.png"
rm -f "$ROOT/usr/share/APPLaunch/share/images/files.png"
rm -f "$ROOT/usr/share/APPLaunch/share/images/power.png"
rm -f "$ROOT/usr/share/APPLaunch/share/images/system-monitor.png"
rm -f "$ROOT/usr/share/APPLaunch/share/images/app-store.png"
rm -f "$ROOT/usr/share/APPLaunch/share/images/robot.png"

echo "cardputer-zero-default-apps uninstalled."
