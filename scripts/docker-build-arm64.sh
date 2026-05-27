#!/bin/sh
set -eu

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
image=${ZERO_DEFAULT_APPS_BUILD_IMAGE:-cardputer-zero-default-apps-build:bookworm-arm64}
out_dir="$repo_dir/.docker-out"
container=zero-default-apps-build-export-$$
tmp_dir=${TMPDIR:-/tmp}/zero-default-apps-build-export-$$

docker build --platform linux/arm64 -f "$repo_dir/docker/Dockerfile.arm64" -t "$image" "$repo_dir"
mkdir -p "$out_dir"
if [ ! -w "$out_dir" ]; then
  echo "Output directory is not writable: $out_dir" >&2
  echo "Remove and recreate it as the current user, then rerun this script." >&2
  exit 1
fi
mkdir -p "$tmp_dir"
docker rm -f "$container" >/dev/null 2>&1 || true
docker create --platform linux/arm64 --name "$container" "$image" >/dev/null
trap 'docker rm -f "$container" >/dev/null 2>&1 || true; rm -rf "$tmp_dir"' EXIT
docker cp "$container:/out/cardputer-zero-default-apps.tar.gz" "$tmp_dir/cardputer-zero-default-apps.tar.gz"
rm -f "$out_dir/cardputer-zero-default-apps.tar.gz"
cp "$tmp_dir/cardputer-zero-default-apps.tar.gz" "$out_dir/cardputer-zero-default-apps.tar.gz"
chmod 0644 "$out_dir/cardputer-zero-default-apps.tar.gz"

echo "$out_dir/cardputer-zero-default-apps.tar.gz"
