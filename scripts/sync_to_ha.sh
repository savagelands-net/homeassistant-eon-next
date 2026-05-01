#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
HA_CONFIG_DIR="${HA_CONFIG_DIR:-}"
SOURCE_DIR="$REPO_ROOT/custom_components/eon_next"

if [[ -z "$HA_CONFIG_DIR" ]]; then
  printf 'HA_CONFIG_DIR must be set to your Home Assistant config directory.\n' >&2
  exit 1
fi

if [[ ! -d "$HA_CONFIG_DIR" ]]; then
  printf 'HA_CONFIG_DIR does not exist or is not a directory: %s\n' "$HA_CONFIG_DIR" >&2
  exit 1
fi

if [[ ! -d "$SOURCE_DIR" ]]; then
  printf 'Source integration directory does not exist: %s\n' "$SOURCE_DIR" >&2
  exit 1
fi

TARGET_DIR="$HA_CONFIG_DIR/custom_components/eon_next"

mkdir -p "$HA_CONFIG_DIR/custom_components"

if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete "$SOURCE_DIR/" "$TARGET_DIR/"
else
  rm -rf "$TARGET_DIR"
  mkdir -p "$TARGET_DIR"
  cp -R "$SOURCE_DIR/." "$TARGET_DIR/"
fi

printf 'Synced integration to %s\n' "$TARGET_DIR"
