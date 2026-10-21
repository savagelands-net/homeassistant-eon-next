# Home Assistant E.ON Next

Home Assistant custom integration for E.ON Next.

> Note: This integration is being developed with the help of AI-assisted tooling, so parts of the project are intentionally being built in a fast-moving, "vibe coding" style while the integration matures.

## Current features

- Live VAT-inclusive electricity import rate
- Next electricity import rate when E.ON publishes a later tariff window
- Next electricity rate change timestamp when available
- Electricity standing charge sensors including pre-VAT standing charge
- Active electricity tariff and account metadata, including account number and agreement window attributes
- Latest electricity meter reading and reading timestamp when available
- Current account balance, latest statement totals, fuel breakdown, and latest direct debit when available
- Gas unit rate, standing charge, tariff metadata, and latest gas meter reading when available

## Planned features

- EV / charger / smart-tariff related entities
- Historical cost counters for Prometheus and Grafana

## Authentication

E.ON Next no longer accepts an account email and password through the Kraken API. This
integration uses the account's durable `sk_live_...` API key instead. The API key is exchanged
for short-lived Kraken tokens; your E.ON password and browser session are never stored in Home
Assistant.

E.ON currently provides no third-party OAuth/device-login flow, so a local helper is included to
create the API key from a one-time login on E.ON's own website.

## Installation

### Manual

Copy `custom_components/eon_next` into your Home Assistant config directory under:

```text
/config/custom_components/eon_next
```

Restart Home Assistant, then add the `E.ON Next` integration from **Settings > Devices & services**.

### HACS

Add this repository as a custom repository in HACS and install the `E.ON Next` integration.

## Getting an API key

Run the helper on a desktop with Python 3.11 or newer, [`uv`](https://docs.astral.sh/uv/), and a
Chromium-based browser installed. Run it from a clone or extracted release of this repository:

```bash
uv run tools/get_api_key.py
```

Alternatively, download the standalone script, review it, and run it:

```bash
curl --fail --remote-name \
  https://raw.githubusercontent.com/savagelands-net/homeassistant-eon-next/main/tools/get_api_key.py
uv run get_api_key.py
```

The helper:

1. Starts Chrome/Chromium with a throwaway browser profile.
2. Opens E.ON's official sign-in page. You complete the login, CAPTCHA, and any verification step
   yourself.
3. Reads the Auth0 ID token from that temporary E.ON page and closes the browser.
4. Uses the token in memory to create the `sk_live_...` key.
5. Deletes the temporary browser profile and copies the key to your clipboard.

It never receives or stores your password, and it never prints or saves the Auth0 token. Use
`--browser /path/to/chrome` if no browser is found, or `--print` if clipboard copying is not
available.

Save the API key in a password manager before pasting it into Home Assistant. E.ON displays the
full value only when it is created.

> **Important:** E.ON permits only one live API key per account. If a key already exists, the
> helper does not replace it unless you type `REGENERATE` exactly. Regenerating immediately
> invalidates the key used by every other third-party app or integration. Reuse the existing key
> if you still have its full value.

### Migrating an existing installation

Do **not** delete the integration: deleting it can disrupt entity identity and recorder history.
After updating and restarting Home Assistant:

1. Open **Settings > Devices & services > E.ON Next**.
2. Select **Reconfigure** or follow the **Re-authentication required** prompt.
3. Paste the API key from the helper.

The existing config entry, account unique ID, entities, and history are retained. Once validation
succeeds, the obsolete saved email and password are removed from the config entry.

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

## Releasing for HACS

HACS updates are published as GitHub releases so it does not mistake a short commit SHA for
a branch name. Keep the versions in `pyproject.toml` and
`custom_components/eon_next/manifest.json` aligned, run `./scripts/check.sh`, then create a
full GitHub release named `v<version>` from `main`. Creating only a Git tag is not sufficient.
The standard GitHub source archive is used; no custom zip asset is required.

## Credits

The temporary-browser bootstrap approach was adapted from
[`h0me5k1n/eon-next-prepay`](https://github.com/h0me5k1n/eon-next-prepay). See
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) for its MIT license notice.

## Status

This project is under active development.
