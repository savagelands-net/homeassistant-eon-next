# E.ON Next Electricity Rename Slice Design

## Goal

Rename the electricity entities and electricity-specific metadata so they are explicitly labeled as electricity, while preserving gas and billing names and migrating existing entity IDs cleanly for installed users.

## Scope

This slice includes:

- electricity entity display-name renames
- electricity sensor key and unique-id suffix renames
- electricity-specific attribute label renames
- entity-registry migration from old electricity unique IDs to the new electricity-prefixed ones

This slice does not include:

- API or snapshot behavior changes
- gas naming changes
- billing naming changes
- fixes to billing semantics, which will be handled in a later slice

## Existing Structure

The integration currently has a mixed naming model:

- gas entities are explicitly labeled with `Gas`
- electricity entities still use generic names such as `E.ON Current Import Rate`, `E.ON Standing Charge`, and `E.ON Latest Meter Reading`
- electricity-specific attributes also use generic names such as `tariff_name` and `standing_charge_gbp_per_day`

This makes the gas/electricity split hard to read once both fuel types are present in the same account.

## Architecture

This is a naming-and-migration slice, not a data-model slice.

The integration should keep the current coordinator and snapshot behavior unchanged. The work is limited to the sensor naming surface plus entity-registry migration support so existing installs do not end up with duplicate electricity entities.

Underlying snapshot field names can remain unchanged if that keeps the code smaller and avoids unnecessary churn, because the goal is explicit user-facing electricity naming rather than an internal model rewrite.

## Component Design

### `custom_components/eon_next/sensor.py`

- rename electricity display names to include `Electricity`
- rename electricity sensor keys and unique-id suffixes to match
- rename electricity-specific attribute labels to explicit electricity-prefixed labels
- leave gas and billing sensor names unchanged

Planned electricity display names:

- `E.ON Electricity Current Import Rate`
- `E.ON Electricity Next Import Rate`
- `E.ON Electricity Next Rate Change`
- `E.ON Electricity Standing Charge`
- `E.ON Electricity Standing Charge Ex VAT`
- `E.ON Latest Electricity Meter Reading`
- `E.ON Latest Electricity Meter Reading Time`

### `custom_components/eon_next/const.py`

- rename electricity-specific attribute constants so they become explicitly electricity-prefixed
- keep account-wide names such as `account_number` unchanged

### `custom_components/eon_next/__init__.py`

- add a small entity-registry migration step during setup
- migrate old electricity unique IDs to their new electricity-prefixed unique IDs before platform setup runs

### `tests/components/eon_next/test_sensor.py`

- update expected electricity names, unique IDs, and electricity-specific attribute labels
- assert that gas and billing names remain unchanged

### `tests/components/eon_next/test_init.py`

- add migration coverage for the old-to-new electricity unique-id map

## Data Flow

1. `async_setup_entry()` runs.
2. The integration checks the entity registry for the current config entry.
3. If old electricity unique IDs exist, it rewrites them to the new electricity-prefixed unique IDs.
4. Coordinator setup and refresh continue as today.
5. `sensor.py` creates the renamed electricity entities plus the existing gas and billing entities.

Rules for what gets renamed:

- electricity-specific things are renamed
- gas-specific things stay as they are
- account-wide things stay neutral

## Error Handling

The rename slice should introduce as little operational risk as possible.

- if an old electricity unique ID exists, migrate it
- if an old unique ID does not exist, create the new electricity entity normally
- if migration would collide with an already-existing target unique ID, avoid guessing or destructive cleanup; keep the behavior visible and testable instead of silently discarding an entity
- no auth, API, billing, or gas behavior changes are introduced in this slice

## Testing Strategy

Implementation follows test-first development and should concentrate on the sensor/setup layer.

Required coverage:

- renamed electricity display names
- renamed electricity unique IDs
- renamed electricity-specific attribute labels
- unchanged gas names
- unchanged billing names
- entity-registry migration from an old electricity unique ID such as `entry-123_current_import_rate` to its new electricity-prefixed replacement
- full `./scripts/check.sh` verification before completion

## Success Criteria

This slice is complete when:

- every electricity entity name is explicitly labeled as electricity
- electricity unique IDs and keys are renamed consistently
- electricity-specific attribute labels are explicit
- gas and billing names remain unchanged
- existing installs migrate old electricity entity IDs instead of creating duplicate electricity entities
- tests pass
