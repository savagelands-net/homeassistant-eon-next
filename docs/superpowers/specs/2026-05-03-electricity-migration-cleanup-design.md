# Electricity Migration Cleanup Design

## Goal

Remove the now-obsolete electricity entity migration code from the integration, while keeping the current electricity entity surface unchanged for new installs and leaving historical planning docs in place.

## Scope

This cleanup includes:

- removing the runtime entity-registry migration path from `custom_components/eon_next/__init__.py`
- removing migration-specific tests and test-only registry behavior from `tests/components/eon_next/test_init.py`
- verifying normal setup behavior still works and repository checks still pass

This cleanup does not include:

- changing any current electricity sensor keys, names, or unique IDs
- changing gas or billing behavior
- deleting historical `docs/superpowers` migration specs or plans
- adding replacement compatibility code or version gates

## Existing Structure

The integration currently performs a setup-time entity-registry cleanup in `custom_components/eon_next/__init__.py`. That code exists only to migrate older electricity entity IDs and unique IDs to the new electricity-prefixed forms introduced in earlier work.

The associated tests live in `tests/components/eon_next/test_init.py`. They add registry stub behavior such as entity update tracking and collision checks that are only needed to exercise the migration path.

## Architecture

After cleanup, `custom_components/eon_next/__init__.py` returns to a simple role: create the API client, create the coordinator, refresh data, store integration state, and forward platform setup. No entity-registry mutation should happen during setup.

This is a dead-code removal change, not a behavior redesign. The current steady-state entity definitions remain owned by `sensor.py` and related constants; only the one-time legacy migration path is removed.

## Component Design

### `custom_components/eon_next/__init__.py`

- remove `ELECTRICITY_ENTITY_MIGRATIONS`
- remove `_async_migrate_electricity_unique_ids()`
- remove the migration call from `async_setup_entry()`
- keep setup and unload logic otherwise unchanged

### `tests/components/eon_next/test_init.py`

- remove migration-focused tests covering legacy, stale, customized, missing, and collision cases
- simplify the entity-registry stub to the minimum needed by the remaining tests
- keep existing non-migration setup, unload, and config-flow coverage intact

## Data Flow

Runtime flow after cleanup:

1. `async_setup_entry()` starts.
2. The integration creates the HTTP client.
3. The integration creates the coordinator.
4. The coordinator performs the first refresh.
5. The integration stores runtime objects in `hass.data`.
6. Platform setup is forwarded.

No registry lookup or entity mutation occurs during this flow.

## Error Handling

The cleanup should not introduce any new branches or recovery paths. By removing the migration hook, setup no longer needs to handle registry collisions, stale legacy entries, or partial rename cases. Existing setup error behavior for refresh and platform forwarding remains unchanged.

## Testing Strategy

Required verification:

- existing entry setup test still proves normal setup success
- existing unload and config-flow tests remain green
- migration-specific tests are removed rather than rewritten
- full repository verification passes via `./scripts/check.sh`

## Success Criteria

This cleanup is complete when:

- `custom_components/eon_next/__init__.py` contains no electricity migration map or helper
- `async_setup_entry()` no longer performs a pre-setup migration step
- `tests/components/eon_next/test_init.py` no longer contains migration-only tests or stub behavior
- repository checks pass
- historical migration docs remain in `docs/superpowers`
