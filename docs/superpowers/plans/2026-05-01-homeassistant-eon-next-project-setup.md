# Home Assistant E.ON Next Project Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn this empty repository into a proper HACS-compatible Home Assistant custom integration project under the `eon_next` domain, seeded from the existing live-rate prototype.

**Architecture:** Keep the current E.ON GraphQL client inside the integration package and migrate the working `eon_next_rates` prototype into `custom_components/eon_next/` plus `tests/components/eon_next/`. Add lightweight project tooling (`pytest`, `pytest-asyncio`, `ruff`), HACS metadata, local brand assets, and helper scripts so the repository is ready for continued feature development beyond live rates.

**Tech Stack:** Home Assistant custom integration, Python, `pytest`, `pytest-asyncio`, `ruff`, HACS metadata, shell helper scripts

---

## File Structure

**Create:**
- `custom_components/eon_next/__init__.py`
- `custom_components/eon_next/api.py`
- `custom_components/eon_next/config_flow.py`
- `custom_components/eon_next/const.py`
- `custom_components/eon_next/coordinator.py`
- `custom_components/eon_next/manifest.json`
- `custom_components/eon_next/sensor.py`
- `custom_components/eon_next/strings.json`
- `custom_components/eon_next/translations/en.json`
- `custom_components/eon_next/brand/.gitkeep`
- `tests/components/eon_next/test_api.py`
- `tests/components/eon_next/test_init.py`
- `tests/components/eon_next/test_sensor.py`
- `.gitignore`
- `README.md`
- `hacs.json`
- `pyproject.toml`
- `requirements_dev.txt`
- `scripts/check.sh`
- `scripts/sync_to_ha.sh`

**Delete:**
- `README.md` GitLab boilerplate contents

**Source prototype to copy from:**
- `/path/to/eon-next-prototype/homeassistant/custom_components/eon_next_rates/`
- `/path/to/eon-next-prototype/homeassistant/tests/components/eon_next_rates/`

---

### Task 1: Scaffold repository metadata and developer tooling

**Files:**
- Create: `.gitignore`
- Modify: `README.md`
- Create: `hacs.json`
- Create: `pyproject.toml`
- Create: `requirements_dev.txt`
- Create: `scripts/check.sh`
- Create: `scripts/sync_to_ha.sh`

- [ ] **Step 1: Replace the boilerplate README with a project README**

Write `README.md` with:

~~~markdown
# Home Assistant E.ON Next

Home Assistant custom integration for E.ON Next.

## Current features

- Live VAT-inclusive import rate
- Next import rate when E.ON publishes a later tariff window
- Next rate change timestamp when available

## Planned features

- Meter readings and account sensors
- Standing charge and tariff metadata improvements
- EV / charger / smart-tariff related entities
- Historical cost counters for Prometheus and Grafana

## Installation

### Manual

Copy `custom_components/eon_next` into your Home Assistant config directory under:

```text
/config/custom_components/eon_next
~~~

Restart Home Assistant, then add the `E.ON Next` integration from **Settings > Devices & services**.

### HACS

Add this repository as a custom repository in HACS and install the `E.ON Next` integration.

## Development

Create a virtual environment and install developer dependencies:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements_dev.txt
```

Run checks:

```bash
./scripts/check.sh
```

## Project layout

```text
custom_components/eon_next/
tests/components/eon_next/
```

## Status

This project is under active development.
```

- [ ] **Step 2: Validate the new README is no longer boilerplate**

Run:

```bash
grep -q "GitLab" README.md && exit 1 || exit 0
```

Expected:

```text
exit code 0
```

- [ ] **Step 3: Create `.gitignore`**

Write `.gitignore` with:

```gitignore
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
.mypy_cache/
.coverage
htmlcov/
.venv/
venv/
.DS_Store
```

- [ ] **Step 4: Create HACS metadata**

Write `hacs.json` with:

```json
{
  "name": "E.ON Next",
  "content_in_root": false,
  "render_readme": true,
  "homeassistant": "2026.4.0"
}
```

- [ ] **Step 5: Validate `hacs.json`**

Run:

```bash
python3 -m json.tool hacs.json
```

Expected:

```text
valid JSON output
```

- [ ] **Step 6: Create `pyproject.toml`**

Write `pyproject.toml` with:

```toml
[project]
name = "homeassistant-eon-next"
version = "0.1.0"
description = "Home Assistant custom integration for E.ON Next"
readme = "README.md"
requires-python = ">=3.13"

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.ruff]
target-version = "py313"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```

- [ ] **Step 7: Create `requirements_dev.txt`**

Write `requirements_dev.txt` with:

```text
pytest
pytest-asyncio
ruff
aiohttp
voluptuous
```

- [ ] **Step 8: Create `scripts/check.sh`**

Write `scripts/check.sh` with:

```bash
#!/usr/bin/env bash
set -euo pipefail

python3 -m json.tool custom_components/eon_next/manifest.json >/dev/null
python3 -m json.tool custom_components/eon_next/strings.json >/dev/null
python3 -m json.tool custom_components/eon_next/translations/en.json >/dev/null
python3 -m compileall custom_components/eon_next tests/components/eon_next
python3 -m pytest tests/components/eon_next -q
ruff check custom_components/eon_next tests/components/eon_next
```

- [ ] **Step 9: Create `scripts/sync_to_ha.sh`**

Write `scripts/sync_to_ha.sh` with:

```bash
#!/usr/bin/env bash
set -euo pipefail

HA_CONFIG_DIR="${HA_CONFIG_DIR:-/config}"
TARGET_DIR="$HA_CONFIG_DIR/custom_components/eon_next"

mkdir -p "$TARGET_DIR"

if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete custom_components/eon_next/ "$TARGET_DIR/"
else
  rm -rf "$TARGET_DIR"
  mkdir -p "$TARGET_DIR"
  cp -R custom_components/eon_next/. "$TARGET_DIR/"
fi

printf 'Synced integration to %s\n' "$TARGET_DIR"
```

- [ ] **Step 10: Make helper scripts executable**

Run:

```bash
chmod +x scripts/check.sh scripts/sync_to_ha.sh
```

- [ ] **Step 11: Commit scaffolding**

```bash
git add README.md .gitignore hacs.json pyproject.toml requirements_dev.txt scripts/check.sh scripts/sync_to_ha.sh
git commit -m "chore: scaffold HACS integration project"
```

---

### Task 2: Migrate the generated custom integration into the new domain

**Files:**
- Create: `custom_components/eon_next/__init__.py`
- Create: `custom_components/eon_next/api.py`
- Create: `custom_components/eon_next/config_flow.py`
- Create: `custom_components/eon_next/const.py`
- Create: `custom_components/eon_next/coordinator.py`
- Create: `custom_components/eon_next/manifest.json`
- Create: `custom_components/eon_next/sensor.py`
- Create: `custom_components/eon_next/strings.json`
- Create: `custom_components/eon_next/translations/en.json`
- Create: `custom_components/eon_next/brand/.gitkeep`

- [ ] **Step 1: Create the integration directory tree**

Run:

```bash
mkdir -p custom_components/eon_next/translations custom_components/eon_next/brand
```

- [ ] **Step 2: Copy the generated prototype source files into the repo**

Run:

```bash
cp \
  /path/to/eon-next-prototype/homeassistant/custom_components/eon_next_rates/__init__.py \
  /path/to/eon-next-prototype/homeassistant/custom_components/eon_next_rates/api.py \
  /path/to/eon-next-prototype/homeassistant/custom_components/eon_next_rates/config_flow.py \
  /path/to/eon-next-prototype/homeassistant/custom_components/eon_next_rates/const.py \
  /path/to/eon-next-prototype/homeassistant/custom_components/eon_next_rates/coordinator.py \
  /path/to/eon-next-prototype/homeassistant/custom_components/eon_next_rates/manifest.json \
  /path/to/eon-next-prototype/homeassistant/custom_components/eon_next_rates/sensor.py \
  /path/to/eon-next-prototype/homeassistant/custom_components/eon_next_rates/strings.json \
  custom_components/eon_next/
```

- [ ] **Step 3: Rewrite the manifest for the new domain**

Write `custom_components/eon_next/manifest.json` with:

```json
{
  "domain": "eon_next",
  "name": "E.ON Next",
  "version": "0.1.0",
  "config_flow": true,
  "integration_type": "service",
  "iot_class": "cloud_polling",
  "requirements": []
}
```

- [ ] **Step 4: Rewrite the integration constants for the new domain**

Write `custom_components/eon_next/const.py` with:

```python
from __future__ import annotations

from datetime import timedelta

DOMAIN = "eon_next"
PLATFORMS = ["sensor"]
GRAPHQL_URL = "https://api.eonnext-kraken.energy/v1/graphql/"
DEFAULT_SCAN_INTERVAL = timedelta(minutes=1)

ATTR_TARIFF_NAME = "tariff_name"
ATTR_TARIFF_CODE = "tariff_code"
ATTR_STANDING_CHARGE_GBP_PER_DAY = "standing_charge_gbp_per_day"
ATTR_CURRENT_WINDOW_END = "current_window_end"
ATTR_NEXT_WINDOW_START = "next_window_start"
```

- [ ] **Step 5: Replace old package imports and domain references**

Run:

```bash
python3 - <<'PY'
from pathlib import Path

for path in Path("custom_components/eon_next").glob("*.py"):
    text = path.read_text()
    text = text.replace("eon_next_rates", "eon_next")
    text = text.replace("E.ON Next Rates", "E.ON Next")
    path.write_text(text)
PY
```

- [ ] **Step 6: Create the user-facing English translation file**

Write `custom_components/eon_next/translations/en.json` with:

```json
{
  "config": {
    "step": {
      "user": {
        "title": "Connect E.ON Next",
        "data": {
          "username": "Email",
          "password": "Password"
        }
      }
    },
    "error": {
      "invalid_auth": "Invalid authentication",
      "cannot_connect": "Failed to connect",
      "unsupported_tariff": "This account does not expose a supported half-hourly tariff"
    },
    "abort": {
      "already_configured": "Account is already configured"
    }
  }
}
```

- [ ] **Step 7: Add the local brand directory placeholder**

Run:

```bash
touch custom_components/eon_next/brand/.gitkeep
```

- [ ] **Step 8: Validate the migrated integration source tree**

Run:

```bash
python3 -m json.tool custom_components/eon_next/manifest.json >/dev/null
python3 -m json.tool custom_components/eon_next/strings.json >/dev/null
python3 -m json.tool custom_components/eon_next/translations/en.json >/dev/null
python3 -m compileall custom_components/eon_next
```

Expected:

```text
JSON validation succeeds and compileall completes without syntax errors
```

- [ ] **Step 9: Commit the migrated integration source**

```bash
git add custom_components/eon_next
git commit -m "feat: migrate E.ON live rate integration to eon_next domain"
```

---

### Task 3: Migrate and adapt the test suite

**Files:**
- Create: `tests/components/eon_next/test_api.py`
- Create: `tests/components/eon_next/test_init.py`
- Create: `tests/components/eon_next/test_sensor.py`

- [ ] **Step 1: Create the test directory tree**

Run:

```bash
mkdir -p tests/components/eon_next
```

- [ ] **Step 2: Copy the generated tests into the repo**

Run:

```bash
cp \
  /path/to/eon-next-prototype/homeassistant/tests/components/eon_next_rates/test_api.py \
  /path/to/eon-next-prototype/homeassistant/tests/components/eon_next_rates/test_init.py \
  /path/to/eon-next-prototype/homeassistant/tests/components/eon_next_rates/test_sensor.py \
  tests/components/eon_next/
```

- [ ] **Step 3: Rewrite the test import paths and domain references**

Run:

```bash
python3 - <<'PY'
from pathlib import Path

for path in Path("tests/components/eon_next").glob("test_*.py"):
    text = path.read_text()
    text = text.replace("custom_components.eon_next_rates", "custom_components.eon_next")
    text = text.replace('DOMAIN = "eon_next_rates"', 'DOMAIN = "eon_next"')
    text = text.replace('"eon_next_rates"', '"eon_next"')
    path.write_text(text)
PY
```

- [ ] **Step 4: Run the tests to verify the renamed package fails if the source tree is incomplete**

Run:

```bash
python3 -m pytest tests/components/eon_next -q
```

Expected:

```text
If dependencies are not installed yet, this fails with missing pytest/homeassistant modules.
If dependencies are installed, failures should identify any remaining rename mismatches.
```

- [ ] **Step 5: Run syntax-only verification for the migrated tests**

Run:

```bash
python3 -m compileall tests/components/eon_next
```

Expected:

```text
All test files compile successfully
```

- [ ] **Step 6: Commit the migrated tests**

```bash
git add tests/components/eon_next
git commit -m "test: migrate live rate integration tests to eon_next domain"
```

---

### Task 4: Add installation and validation workflow helpers

**Files:**
- Modify: `scripts/check.sh`
- Modify: `scripts/sync_to_ha.sh`
- Modify: `README.md`

- [ ] **Step 1: Make `scripts/check.sh` tolerate missing pytest during the earliest bootstrap**

Replace `scripts/check.sh` with:

```bash
#!/usr/bin/env bash
set -euo pipefail

python3 -m json.tool custom_components/eon_next/manifest.json >/dev/null
python3 -m json.tool custom_components/eon_next/strings.json >/dev/null
python3 -m json.tool custom_components/eon_next/translations/en.json >/dev/null
python3 -m compileall custom_components/eon_next tests/components/eon_next

if python3 -c 'import pytest' >/dev/null 2>&1; then
  python3 -m pytest tests/components/eon_next -q
else
  printf 'pytest not installed; skipping runtime tests\n'
fi

if python3 -c 'import ruff' >/dev/null 2>&1; then
  ruff check custom_components/eon_next tests/components/eon_next
else
  printf 'ruff not installed; skipping lint\n'
fi
```

- [ ] **Step 2: Make the sync script target the final domain**

Ensure `scripts/sync_to_ha.sh` contains:

```bash
#!/usr/bin/env bash
set -euo pipefail

HA_CONFIG_DIR="${HA_CONFIG_DIR:-/config}"
TARGET_DIR="$HA_CONFIG_DIR/custom_components/eon_next"

mkdir -p "$TARGET_DIR"

if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete custom_components/eon_next/ "$TARGET_DIR/"
else
  rm -rf "$TARGET_DIR"
  mkdir -p "$TARGET_DIR"
  cp -R custom_components/eon_next/. "$TARGET_DIR/"
fi

printf 'Synced integration to %s\n' "$TARGET_DIR"
```

- [ ] **Step 3: Update the README development section to match the final scripts**

Ensure `README.md` includes:

~~~markdown
## Development

Create a virtual environment and install developer dependencies:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements_dev.txt
```

Run project checks:

```bash
./scripts/check.sh
```

Sync the integration to a Home Assistant config directory:

```bash
HA_CONFIG_DIR=/config ./scripts/sync_to_ha.sh
```
~~~

- [ ] **Step 4: Verify the helper scripts work syntactically**

Run:

```bash
bash -n scripts/check.sh
bash -n scripts/sync_to_ha.sh
```

Expected:

```text
no output
```

- [ ] **Step 5: Commit the helper workflow updates**

```bash
git add scripts/check.sh scripts/sync_to_ha.sh README.md
git commit -m "chore: add local validation and sync workflow"
```

---

### Task 5: Verify the repository is ready for continued E.ON Next development

**Files:**
- Modify: none
- Test: repository tree and project commands

- [ ] **Step 1: Install development dependencies**

Run:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements_dev.txt
```

Expected:

```text
pytest, pytest-asyncio, ruff, aiohttp, and voluptuous install successfully
```

- [ ] **Step 2: Run the repository validation script**

Run:

```bash
./scripts/check.sh
```

Expected:

```text
JSON validation passes, Python files compile, and tests/lint run when dependencies are present
```

- [ ] **Step 3: Verify the key repository layout exists**

Run:

```bash
python3 - <<'PY'
from pathlib import Path

required = [
    Path('custom_components/eon_next/__init__.py'),
    Path('custom_components/eon_next/manifest.json'),
    Path('custom_components/eon_next/api.py'),
    Path('custom_components/eon_next/sensor.py'),
    Path('custom_components/eon_next/translations/en.json'),
    Path('tests/components/eon_next/test_api.py'),
    Path('tests/components/eon_next/test_init.py'),
    Path('tests/components/eon_next/test_sensor.py'),
    Path('hacs.json'),
    Path('pyproject.toml'),
]

missing = [str(path) for path in required if not path.exists()]
if missing:
    raise SystemExit(f'Missing required files: {missing}')

print('Repository layout verified')
PY
```

Expected:

```text
Repository layout verified
```

- [ ] **Step 4: Commit the completed project setup**

```bash
git add .
git commit -m "feat: create HACS-ready E.ON Next integration project"
```
