#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
INTEGRATION_DIR="$REPO_ROOT/custom_components/eon_next"
TESTS_DIR="$REPO_ROOT/tests/components/eon_next"
ALLOW_MISSING_DEV_TOOLS="${ALLOW_MISSING_DEV_TOOLS:-0}"

if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
  PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
else
  PYTHON_BIN="python3"
fi

if [[ -x "$REPO_ROOT/.venv/bin/ruff" ]]; then
  RUFF_BIN="$REPO_ROOT/.venv/bin/ruff"
else
  RUFF_BIN="ruff"
fi

"$PYTHON_BIN" -m json.tool "$INTEGRATION_DIR/manifest.json" >/dev/null
"$PYTHON_BIN" -m json.tool "$INTEGRATION_DIR/strings.json" >/dev/null
"$PYTHON_BIN" -m json.tool "$INTEGRATION_DIR/translations/en.json" >/dev/null
"$PYTHON_BIN" -m compileall "$INTEGRATION_DIR" "$TESTS_DIR"

if "$PYTHON_BIN" -m pytest --version >/dev/null 2>&1; then
  "$PYTHON_BIN" -m pytest "$TESTS_DIR" -q
elif [[ "$ALLOW_MISSING_DEV_TOOLS" == "1" ]]; then
  printf 'Skipping pytest: install it with pip install -r %s/requirements_dev.txt\n' "$REPO_ROOT"
else
  printf 'Missing pytest: install it with pip install -r %s/requirements_dev.txt, or set ALLOW_MISSING_DEV_TOOLS=1 to skip.\n' "$REPO_ROOT" >&2
  exit 1
fi

if command -v "$RUFF_BIN" >/dev/null 2>&1; then
  "$RUFF_BIN" check "$INTEGRATION_DIR" "$TESTS_DIR"
elif [[ "$ALLOW_MISSING_DEV_TOOLS" == "1" ]]; then
  printf 'Skipping ruff: install it with pip install -r %s/requirements_dev.txt\n' "$REPO_ROOT"
else
  printf 'Missing ruff: install it with pip install -r %s/requirements_dev.txt, or set ALLOW_MISSING_DEV_TOOLS=1 to skip.\n' "$REPO_ROOT" >&2
  exit 1
fi
