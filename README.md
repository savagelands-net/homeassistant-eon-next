# Home Assistant E.ON Next

Home Assistant custom integration for E.ON Next.

> Note: This integration is being developed with the help of AI-assisted tooling, so parts of the project are intentionally being built in a fast-moving, "vibe coding" style while the integration matures.

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
```

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

Sync the integration into a Home Assistant config directory:

```bash
HA_CONFIG_DIR=/config ./scripts/sync_to_ha.sh
```

## Project layout

```text
custom_components/eon_next/
tests/components/eon_next/
```

## Status

This project is under active development.
