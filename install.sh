#!/bin/sh
set -eu

ROOT=${DESTDIR:-}
REPO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON_DIR="$ROOT/usr/lib/python3/dist-packages"
SKIP_ROBOT_RUNTIME=${SKIP_ROBOT_RUNTIME:-0}

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

for bin in zero-settings zero-terminal zero-files zero-power-menu zero-system-monitor zero-app-store zero-robot; do
  install_file "$REPO_DIR/bin/$bin" "/usr/bin/$bin" 0755
done

copy_tree "$REPO_DIR/applications" /usr/share/APPLaunch/applications 0644
copy_tree "$REPO_DIR/icons" /usr/share/APPLaunch/icons 0644
copy_tree "$REPO_DIR/icons" /usr/share/APPLaunch/share/images 0644

install_robot_runtime() {
  if [ -n "$ROOT" ] || [ "$SKIP_ROBOT_RUNTIME" = "1" ]; then
    return
  fi

  pi_path() {
    if command -v pi >/dev/null 2>&1; then
      command -v pi
      return 0
    fi
    for candidate in \
      /usr/local/bin/pi \
      /usr/bin/pi \
      /opt/homebrew/bin/pi \
      "$HOME/.npm-global/bin/pi" \
      "$HOME/.local/bin/pi"
    do
      if [ -x "$candidate" ]; then
        printf '%s\n' "$candidate"
        return 0
      fi
    done
    return 1
  }

  node_major_version() {
    if command -v node >/dev/null 2>&1; then
      node -p "Number.parseInt(process.versions.node.split('.')[0], 10)" 2>/dev/null || printf '0\n'
    else
      printf '0\n'
    fi
  }

  require_apt_get() {
    if ! command -v apt-get >/dev/null 2>&1; then
      echo "Robot runtime: apt-get is unavailable; cannot prepare pi agent automatically." >&2
      exit 1
    fi
  }

  install_node_and_npm() {
    require_apt_get
    echo "Robot runtime: installing nodejs and npm via apt-get."
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y nodejs npm
  }

  ensure_pi_on_common_path() {
    if pi_bin=$(pi_path); then
      if [ "$pi_bin" != "/usr/local/bin/pi" ] && [ -d /usr/local/bin ]; then
        ln -sf "$pi_bin" /usr/local/bin/pi
      fi
      return 0
    fi

    if command -v npm >/dev/null 2>&1; then
      prefix=$(npm config get prefix 2>/dev/null || true)
      if [ -n "$prefix" ] && [ -x "$prefix/bin/pi" ]; then
        ln -sf "$prefix/bin/pi" /usr/local/bin/pi
        return 0
      fi
    fi
    return 1
  }

  if pi_bin=$(pi_path); then
    echo "Robot runtime: pi agent already installed at $pi_bin"
    ensure_pi_on_common_path || true
    return
  fi

  echo "Robot runtime: pi agent not found; preparing pi coding agent."
  if ! command -v npm >/dev/null 2>&1; then
    install_node_and_npm
  fi

  node_major=$(node_major_version)
  if [ "$node_major" -lt 16 ]; then
    install_node_and_npm
    node_major=$(node_major_version)
  fi
  if [ "$node_major" -lt 16 ]; then
    echo "Robot runtime: Node.js 16 or newer is required for pi agent; found major version $node_major." >&2
    exit 1
  fi

  echo "Robot runtime: installing @earendil-works/pi-coding-agent via npm."
  npm install -g --ignore-scripts @earendil-works/pi-coding-agent@latest
  ensure_pi_on_common_path || true

  if pi_bin=$(pi_path); then
    echo "Robot runtime: pi agent installed at $pi_bin"
    "$pi_bin" --version >/dev/null 2>&1 || echo "Robot runtime: pi installed, but version check returned non-zero." >&2
  else
    echo "Robot runtime: pi installation did not produce a pi command in PATH or /usr/local/bin." >&2
    exit 1
  fi
}

install_robot_runtime

echo "cardputer-zero-default-apps installed."
echo "Installed apps: zero-settings zero-terminal zero-files zero-power-menu zero-system-monitor zero-app-store zero-robot"
