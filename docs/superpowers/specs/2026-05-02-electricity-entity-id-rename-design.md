# E.ON Next Electricity Entity ID Rename Design

## Goal

Rename the electricity `entity_id`s to explicit electricity-prefixed forms, while preserving the already-renamed electricity display names and `unique_id`s, and then perform a separate live Home Assistant remediation pass to update helpers that still reference the old electricity `entity_id`s.

## Scope

This work is intentionally split into two phases.

Phase 1 includes:

- entity-registry migration for electricity `entity_id`s
- code and tests needed to safely rename the electricity `entity_id`s in the integration

Phase 2 includes:

- authenticating to the user’s Home Assistant instance with a long-lived token
- scanning helpers and other editable Home Assistant objects for old electricity `entity_id` references
- rewriting those references to the new electricity `entity_id`s

This work does not include:

- any API or snapshot changes
- gas or billing renames
- speculative edits to unrelated Home Assistant configuration

## Existing Structure

The integration already renamed electricity display names and migrated electricity `unique_id`s, but it leaves `entity_id`s stable. That is why Home Assistant currently shows the new electricity names while keeping the old generic `entity_id`s.

The current migration logic lives in `custom_components/eon_next/__init__.py` and only updates `new_unique_id`. The rename surface for electricity entities lives in `custom_components/eon_next/sensor.py`.

## Architecture

Phase 1 is an entity-registry migration slice, not a data-model slice.

The integration should update electricity `entity_id`s during setup using the same old-to-new suffix map already used for electricity `unique_id` migration. The electricity entities, gas entities, billing entities, coordinator behavior, and API model remain otherwise unchanged.

Phase 2 is operational follow-up against the live Home Assistant instance. Once the updated integration is installed, the Home Assistant API is used to discover and patch helpers and related objects that still reference the old electricity `entity_id`s.

## Component Design

### `custom_components/eon_next/__init__.py`

- extend the existing migration helper so it can rename `entity_id` as well as `unique_id`
- keep one migration map as the source of truth for old-to-new electricity suffixes

### `tests/components/eon_next/test_init.py`

- extend the entity-registry stub so it can model `entity_id` updates as well as `unique_id` updates
- add tests for migration success, missing-old-entry no-op behavior, and new-target collision no-op behavior

### Live Home Assistant remediation

- after the user installs the updated integration and provides a long-lived token, query Home Assistant for helpers and other editable objects
- search for exact references to the old electricity `entity_id`s
- rewrite those references to the new electricity `entity_id`s where the API allows updates
- report any ambiguous or read-only cases rather than guessing

## Data Flow

Phase 1 runtime flow:

1. `async_setup_entry()` starts.
2. The integration loads the entity registry.
3. For each electricity suffix mapping, it looks up the old entry.
4. If the old entry exists and the new target identifiers are free, the integration updates the registry entry to the new electricity-prefixed `entity_id` and `unique_id`.
5. Normal coordinator and platform setup continue.

Phase 2 remediation flow:

1. The updated integration is installed and Home Assistant is restarted or reloaded.
2. The user provides a long-lived access token for their Home Assistant instance.
3. Home Assistant API calls enumerate helpers and other editable objects.
4. Old electricity `entity_id` references are located.
5. Exact matches are rewritten to the new electricity `entity_id`s.
6. The affected objects are re-read to confirm the updates stuck.

## Error Handling

Phase 1 should be conservative:

- migrate only when the old electricity entry exists
- skip migration if the target `entity_id` or `unique_id` already exists
- treat missing old entries as a no-op
- avoid destructive cleanup or guesses on collisions

Phase 2 should also be conservative:

- rewrite only exact old electricity `entity_id` matches
- report ambiguous matches rather than guessing
- report read-only or unsupported objects for manual follow-up instead of forcing writes

## Testing Strategy

Phase 1 follows test-first development and should focus on setup and registry behavior.

Required coverage:

- electricity `entity_id` migration from old generic IDs to new electricity-prefixed IDs
- missing-old-entry no-op behavior
- collision/no-op behavior when the new target already exists
- proof that gas and billing entities are unaffected
- full `./scripts/check.sh` verification before completion

Phase 2 verification is operational rather than repository-based:

- confirm the new electricity `entity_id`s exist in the live Home Assistant instance
- confirm affected helpers no longer reference the old electricity `entity_id`s
- confirm those helpers now reference the new electricity `entity_id`s

## Success Criteria

This work is complete when:

- the integration migrates old electricity `entity_id`s to explicit electricity-prefixed forms
- electricity display names and `unique_id`s remain aligned with those new `entity_id`s
- gas and billing entities remain untouched
- repository tests pass
- after installation, helper references in the live Home Assistant instance can be scanned and updated to the new electricity `entity_id`s
