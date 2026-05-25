#!/bin/sh
set -eu

ROOT=${DESTDIR:-}
REPO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON_DIR="$ROOT/usr/lib/python3/dist-packages"

if [ "$(id -u)" -ne 0 ] && [ -z "$ROOT" ]; then
  echo "install.sh must run as root unless DESTDIR is set" >&2
  exit 1
fi

install_file() {
  src=$1
  dst=$2
  mode=$3
  install -D -m "$mode" "$src" "$ROOT$dst"
}

copy_tree() {
  src_dir=$1
  dst_dir=$2
  mode=$3
  find "$src_dir" -type f | while IFS= read -r src; do
    rel=${src#"$src_dir"/}
    install_file "$src" "$dst_dir/$rel" "$mode"
  done
}

copy_tree "$REPO_DIR/src/czero_apps" /usr/lib/python3/dist-packages/czero_apps 0644

for bin in zero-settings zero-terminal zero-files zero-power-menu zero-system-monitor zero-app-store; do
  install_file "$REPO_DIR/bin/$bin" "/usr/bin/$bin" 0755
done

copy_tree "$REPO_DIR/applications" /usr/share/APPLaunch/applications 0644
copy_tree "$REPO_DIR/icons" /usr/share/APPLaunch/icons 0644
copy_tree "$REPO_DIR/icons" /usr/share/APPLaunch/share/images 0644

echo "cardputer-zero-default-apps installed."
echo "Installed apps: zero-settings zero-terminal zero-files zero-power-menu zero-system-monitor zero-app-store"
