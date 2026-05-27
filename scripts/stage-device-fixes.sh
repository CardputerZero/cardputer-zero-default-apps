#!/bin/sh
set -eu

target=${1:-pi@192.168.50.35}
remote_dir=${ZERO_DEPLOY_REMOTE_DIR:-/tmp/czero-deploy-fixes}

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
projects_dir=$(CDPATH= cd -- "$repo_dir/.." && pwd)
shell_dir=$projects_dir/cardputer-zero-shell
ime_dir=$projects_dir/cardputer-zero-fcitx5-ui

default_apps_tar=$repo_dir/.docker-out/cardputer-zero-default-apps.tar.gz
shell_bin=$shell_dir/.docker-out/zero-shell-wayland
ime_panel=$ime_dir/.docker-out/cardputer-zero-ime-panel
ime_addon=$ime_dir/.docker-out/libcardputerzero-ui.so
ime_conf=$ime_dir/.docker-out/cardputerzero-ui.conf
ime_session=$ime_dir/.docker-out/cardputer-zero-ime-session
ime_service=$ime_dir/.docker-out/cardputer-zero-ime.service

for artifact in "$default_apps_tar" "$shell_bin" "$ime_panel" "$ime_addon" "$ime_conf" "$ime_session" "$ime_service"; do
  if [ ! -s "$artifact" ]; then
    echo "Missing artifact: $artifact" >&2
    echo "Run the docker-build-arm64.sh scripts first." >&2
    exit 1
  fi
done

ssh "$target" "rm -rf '$remote_dir' && mkdir -p '$remote_dir'"
scp \
  "$default_apps_tar" \
  "$shell_bin" \
  "$ime_panel" \
  "$ime_addon" \
  "$ime_conf" \
  "$ime_session" \
  "$ime_service" \
  "$target:$remote_dir/"

ssh "$target" "cat > '$remote_dir/install-as-root.sh' <<'REMOTE_INSTALL'
#!/bin/sh
set -eu

staging=$remote_dir

if [ \"\$(id -u)\" -ne 0 ]; then
  echo \"Run as root: sh \$staging/install-as-root.sh\" >&2
  exit 1
fi

rm -rf /tmp/cardputer-zero-default-apps-src
mkdir -p /tmp/cardputer-zero-default-apps-src
tar -xzf \"\$staging/cardputer-zero-default-apps.tar.gz\" -C /tmp/cardputer-zero-default-apps-src

for artifact in \
  \"\$staging/zero-shell-wayland\" \
  \"\$staging/cardputer-zero-ime-panel\" \
  \"\$staging/libcardputerzero-ui.so\" \
  \"\$staging/cardputerzero-ui.conf\" \
  \"\$staging/cardputer-zero-ime-session\" \
  \"\$staging/cardputer-zero-ime.service\"; do
  if [ ! -s \"\$artifact\" ]; then
    echo \"Refusing to install empty or missing artifact: \$artifact\" >&2
    exit 1
  fi
done

for app in zero-settings zero-terminal zero-files zero-power-menu zero-system-monitor zero-app-store zero-robot; do
  src=/tmp/cardputer-zero-default-apps-src/bin/\$app
  if [ ! -s \"\$src\" ]; then
    echo \"Refusing to install empty launcher: \$src\" >&2
    exit 1
  fi
done
if [ ! -s /tmp/cardputer-zero-default-apps-src/src/czero_apps/apps/robot/app.py ]; then
  echo \"Refusing to install empty Python source tree\" >&2
  exit 1
fi
for file in /tmp/cardputer-zero-default-apps-src/applications/*.desktop /tmp/cardputer-zero-default-apps-src/icons/*; do
  if [ ! -s \"\$file\" ]; then
    echo \"Refusing to install empty APPLaunch asset: \$file\" >&2
    exit 1
  fi
done

for app in zero-settings zero-terminal zero-files zero-power-menu zero-system-monitor zero-app-store zero-robot; do
  install -D -m 0755 /tmp/cardputer-zero-default-apps-src/bin/\$app /usr/bin/\$app
done

rm -rf /usr/lib/python3/dist-packages/czero_apps
mkdir -p /usr/lib/python3/dist-packages/czero_apps
cp -a /tmp/cardputer-zero-default-apps-src/src/czero_apps/. /usr/lib/python3/dist-packages/czero_apps/
find /usr/lib/python3/dist-packages/czero_apps -type f -name '*.py' -exec chmod 0644 {} +

mkdir -p /usr/share/APPLaunch/applications /usr/share/APPLaunch/icons /usr/share/APPLaunch/share/images
cp -f /tmp/cardputer-zero-default-apps-src/applications/*.desktop /usr/share/APPLaunch/applications/
cp -f /tmp/cardputer-zero-default-apps-src/icons/* /usr/share/APPLaunch/icons/
cp -f /tmp/cardputer-zero-default-apps-src/icons/* /usr/share/APPLaunch/share/images/
chmod 0644 /usr/share/APPLaunch/applications/*.desktop /usr/share/APPLaunch/icons/* /usr/share/APPLaunch/share/images/*

install -D -m 0755 \"\$staging/zero-shell-wayland\" /opt/cardputer-zero-shell/bin/zero-shell-wayland.new
mv /opt/cardputer-zero-shell/bin/zero-shell-wayland.new /opt/cardputer-zero-shell/bin/zero-shell-wayland

install -D -m 0755 \"\$staging/cardputer-zero-ime-panel\" /usr/bin/cardputer-zero-ime-panel
install -D -m 0755 \"\$staging/cardputer-zero-ime-session\" /usr/bin/cardputer-zero-ime-session
install -D -m 0644 \"\$staging/libcardputerzero-ui.so\" /usr/lib/aarch64-linux-gnu/fcitx5/libcardputerzero-ui.so
install -D -m 0644 \"\$staging/cardputerzero-ui.conf\" /usr/share/fcitx5/addon/cardputerzero-ui.conf
install -D -m 0644 \"\$staging/cardputer-zero-ime.service\" /usr/lib/systemd/user/cardputer-zero-ime.service
rm -f /usr/local/lib/fcitx5/libcardputerzero-ui.so /usr/local/share/fcitx5/addon/cardputerzero-ui.conf

su - pi -c 'XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus systemctl --user daemon-reload' >/dev/null 2>&1 || true
su - pi -c 'XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus systemctl --user restart cardputer-zero-ime.service' >/dev/null 2>&1 || true
pkill -TERM -u pi -f 'python3 -m czero_apps.main robot|sh -lc /usr/bin/zero-robot|python3 -m czero_apps.main terminal|sh -lc /usr/bin/zero-terminal' >/dev/null 2>&1 || true

find /usr/share/APPLaunch/applications -maxdepth 1 -type f -name '*.desktop' -printf '%f %s\n' | sort

echo \"Installed Cardputer Zero staged fixes.\"
REMOTE_INSTALL
chmod 0755 '$remote_dir/install-as-root.sh'
printf '%s\n' \"Staged artifacts in $remote_dir.\" 'Run on the device with root privileges:' \"  sh $remote_dir/install-as-root.sh\""
