#!/bin/sh
set -eu

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
projects_dir=$(CDPATH= cd -- "$repo_dir/.." && pwd)

sh "$projects_dir/cardputer-zero-shell/scripts/docker-build-arm64.sh"
sh "$repo_dir/scripts/docker-build-arm64.sh"
sh "$projects_dir/cardputer-zero-fcitx5-ui/scripts/docker-build-arm64.sh"
