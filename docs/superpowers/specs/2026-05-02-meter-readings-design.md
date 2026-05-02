# E.ON Next Meter Readings Slice Design

## Goal

Implement the next roadmap slice by exposing the latest available electricity meter reading for the selected E.ON account, plus timestamp and reading metadata, without introducing history, export-specific logic, or a second subsystem.

## Scope

This slice includes:

- latest electricity meter reading value for the selected supported account
- timestamp for that latest usable reading
- metadata that naturally travels with that reading, such as source, status, or register details when present; the integration only exposes fields that exist in the upstream payload and does not invent derived meter metadata
- README updates only if implementation materially changes the shipped feature list

This slice does not include:

- historical meter-reading entries
- export-specific meter logic unless the upstream payload already exposes the same shape cleanly
- EV, charger, or smart-tariff entities
- historical counters or persistence

## Existing Structure

The integration currently uses:

- one config entry per E.ON account
- one coordinator polling an `AccountSnapshot`
- one sensor platform driven by `SENSOR_DESCRIPTIONS`
- `api.py` as the main normalization boundary for GraphQL payloads

The current code exposes six entities for tariff and account metadata. There is no meter-reading query or model yet, so this slice is a real API expansion rather than a hidden entity toggle.

## Architecture

The design keeps the existing single-entry, single-coordinator architecture. Meter readings are added to the same account snapshot rather than creating a new coordinator or platform.

The slice targets the latest electricity meter reading only. If the upstream payload later proves to expose both import and export readings in a clean shared shape, that can be extended in a later slice, but the first implementation is intentionally narrower.

## Component Design

### `custom_components/eon_next/api.py`

- widen the existing account query so it requests the meter-reading fields from the same account payload
- add a helper that selects the latest usable meter-reading entry
- normalize the reading into a small set of optional fields on `AccountSnapshot`
- keep all GraphQL-specific fallback and field-interpretation logic in `api.py`

### `custom_components/eon_next/sensor.py`

- keep the current single sensor platform and description-driven pattern
- add one meter-reading value sensor
- add one meter-reading timestamp sensor
- attach optional reading metadata from the upstream payload as attributes on the value sensor rather than creating a large number of extra entities

### `tests/components/eon_next/`

- extend API tests around latest-reading selection, malformed-reading skipping, and no-usable-reading fallback
- extend sensor tests for the additional entity count and meter-reading attributes

## Data Flow

1. The config flow authenticates and discovers the supported account as it does today.
2. The coordinator fetches the widened account snapshot query.
3. `api.py` selects the active half-hourly tariff agreement and independently selects the latest usable meter reading from the account payload.
4. `api.py` returns one `AccountSnapshot` containing tariff/account fields plus optional meter-reading fields.
5. `sensor.py` maps those normalized meter-reading fields into the new entities.

If meter-reading data is absent or no usable reading can be selected, the integration remains loaded and the meter-reading sensors resolve to `None`.

## Error Handling

The existing auth and transport failure model stays unchanged.

Meter-reading behavior is best-effort inside an otherwise supported account:

- no meter-reading entries present means the meter sensors are `None`
- a candidate reading missing required fields such as value or timestamp is skipped during latest-reading selection
- if all candidates are unusable, the meter sensors are `None`
- only a clearly incompatible upstream container shape should raise an unsupported/schema error

This keeps optional meter data from breaking working tariff support.

## Testing Strategy

Implementation follows test-first development and should concentrate most of the confidence in API-level tests.

Required test coverage:

- selecting the latest usable reading from multiple entries
- skipping malformed candidates
- returning `None` when no usable reading remains
- preserving existing tariff/account snapshot behavior while meter data is present
- exposing the two new sensor entities and their metadata attributes
- full `./scripts/check.sh` verification before completion

## Success Criteria

This slice is complete when:

- the coordinator still returns a valid `AccountSnapshot` for supported accounts
- the integration exposes a latest meter-reading sensor and a reading timestamp sensor
- the reading sensor carries the available metadata attributes from the chosen reading
- accounts without usable meter-reading data do not fail setup and simply expose meter sensors with `None` state
- the existing tariff/account entities continue to work
- tests pass
