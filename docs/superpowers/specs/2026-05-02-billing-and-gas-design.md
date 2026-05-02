# E.ON Next Billing And Gas Slice Design

## Goal

Implement the next bounded combined slice by adding account-level billing amounts and gas support alongside the existing electricity features, without forcing false gas parity for electricity-only smart-tariff behavior.

## Scope

This slice includes:

- current account balance
- latest statement closing balance when available
- latest statement charges total when available
- gas unit rate and standing charge data when a gas agreement exists
- gas tariff and account metadata that naturally fits the current entity model
- latest gas meter reading and reading timestamp when available

This slice does not include:

- EV, charger, or smart-tariff entities
- historical cost counters or persistence
- electricity-style gas next-rate and next-rate-change entities unless the upstream schema later proves that gas exposes true windowed rates
- generic bill-history browsing or statement-history entities

## Existing Structure

The integration currently exposes electricity tariff/account data and the latest electricity meter reading from one config entry, one coordinator, and one sensor platform.

The current model is centered on `AccountSnapshot` in `api.py`, with `sensor.py` acting as a thin description-driven mapping layer. That structure is still appropriate for the next slice, because both billing and gas data live under the same authenticated account in the upstream schema.

## Architecture

The design keeps the single-entry, single-coordinator architecture and broadens `AccountSnapshot` from an electricity-focused account view into a whole-account view.

The combined snapshot will have three bounded areas:

- account finance fields
  - current balance
  - latest statement closing balance
  - latest statement charges total
- electricity fields
  - keep the existing electricity tariff and latest electricity meter-reading behavior unchanged
- gas fields
  - gas unit rate
  - gas standing charge and pre-VAT standing charge
  - gas tariff metadata
  - latest gas meter reading and timestamp

Gas is intentionally not modeled as a clone of electricity. The current schema shows scalar gas `unitRate` and standing-charge fields, but not the same half-hourly current/next window model used for electricity.

## Component Design

### `custom_components/eon_next/api.py`

- widen the authenticated account query to include billing and gas fields
- add account-finance extraction helpers
- add latest-statement extraction helpers using the upstream bill/statement path
- add gas agreement selection and gas tariff normalization helpers
- add gas latest-meter-reading normalization parallel to the electricity meter-reading path
- keep all schema interpretation and fallback logic in `api.py`

### `custom_components/eon_next/sensor.py`

- keep the current single sensor platform and description-driven pattern
- add billing sensors for current balance and statement amounts
- add gas sensors for unit rate, standing charge, latest meter reading, and timestamp
- attach gas and billing metadata as attributes only where it improves clarity, rather than exploding the entity count

### `custom_components/eon_next/const.py`

- define the new attribute names required for billing and gas metadata

### `tests/components/eon_next/`

- extend API tests for billing and gas extraction, fallback rules, and electricity non-regression
- extend sensor tests for the wider entity set and `None` behavior when optional billing/gas data is absent

## Data Flow

1. The config flow authenticates and discovers a supported account using electricity support as it does today.
2. The coordinator fetches one widened account query.
3. `api.py`:
   - selects the active electricity agreement and builds the existing electricity fields
   - selects the active gas agreement, if present, and builds gas fields
   - extracts account-level finance fields from `AccountType`
   - extracts the latest usable statement values from the account billing path
4. `api.py` returns one normalized `AccountSnapshot` containing electricity, billing, and optional gas fields.
5. `sensor.py` maps those normalized fields into entities.

Interpretation rules for this slice:

- billing is account-level, not fuel-specific
- gas is optional and must not block electricity support
- if no gas agreement exists, gas sensors resolve to `None`
- if statement data is missing or the latest bill cannot be safely interpreted as a statement amount, the statement sensors resolve to `None`

## Error Handling

Required for the integration to remain supported:

- authentication succeeds
- the account exists
- the existing supported electricity agreement path still works

Best-effort data in this slice:

- current balance
- latest statement amounts
- gas agreement and gas tariff fields
- gas latest-meter-reading fields

Behavior rules:

- missing or malformed optional billing data resolves to `None` in billing sensors
- no gas agreement resolves to `None` in gas sensors
- malformed optional gas meter-reading payloads resolve to `None` in gas reading sensors
- malformed electricity-critical tariff payloads continue to fail as unsupported, matching current behavior

This preserves the existing electricity integration even when billing or gas data is incomplete.

## Testing Strategy

Implementation follows test-first development. Most confidence should come from API-level tests because the complexity is in schema interpretation across electricity, billing, and gas in one snapshot.

Required coverage:

- current balance extraction
- latest statement closing balance extraction
- latest statement charges extraction
- gas agreement selection and gas tariff normalization
- gas latest-meter-reading selection and malformed-payload fallback
- proof that the existing electricity fields still work while billing and gas data are present
- widened sensor coverage and `None` behavior for absent gas/statement data
- full `./scripts/check.sh` verification before completion

## Success Criteria

This slice is complete when:

- the integration still exposes the existing electricity entities unchanged in supported electricity accounts
- the integration exposes current balance and, when available, the latest statement closing balance and statement charges
- the integration exposes bounded gas support for gas unit rate, standing charge, and latest gas meter reading when a gas agreement exists
- missing optional billing or gas data does not block setup and instead resolves to `None`
- no fake gas next-rate behavior is introduced
- tests pass
