# SmartFlex Live Query Remodel Design

## Goal

Fix the SmartFlex integration path so live vehicle and charger data is discovered from the real API schema, expose only concrete per-device SmartFlex entities that actually have values, and remove the ambiguous account-level completed-dispatch surface.

## Scope

This remodel includes:

- correcting the SmartFlex `devices(accountNumber)` query to the live GraphQL schema
- keeping SmartFlex support focused on per-device vehicle and charger data
- exposing per-device SmartFlex entities only when the underlying field exists
- keeping per-device next planned dispatch support
- supporting multiple SmartFlex devices in one account with distinct entity ids
- preserving late entity creation when SmartFlex data appears after setup

This remodel does not include:

- account-level completed-dispatch entities
- full charging-session history
- full planned-dispatch history
- OCPP credential fields such as generated URL or username
- onboarding, supported-device catalog, or registration-helper entities
- calculated charging windows, charging recommendations, or other derived behavior
- SmartFlex control or mutation features

## Existing Structure

The integration already has a SmartFlex slice in place, but the current device query shape does not match the live API schema. The shipped query asks SmartFlex status-only fields directly on `SmartFlexDeviceStatusInterface`, while the live API requires those fields to be requested through inline fragments on `SmartFlexVehicleStatus` and `SmartFlexChargePointStatus`.

That mismatch means the SmartFlex device query fails at runtime, so device-backed EV metrics never appear even when the account has a live SmartFlex vehicle. At the same time, the account-level completed-dispatch query still succeeds, which is why the integration can currently show only the three completed-dispatch entities.

The current sensor layer also creates a fixed SmartFlex entity set per device, even when some optional fields can never be populated for that specific device shape.

## Architecture

The remodel should keep the existing single-entry, single-coordinator architecture and the existing SmartFlex snapshot model, but it should tighten the SmartFlex surface around real live data.

The core changes are:

1. Correct the SmartFlex device query so it matches the live schema.
2. Continue normalizing raw GraphQL payloads into the current SmartFlex helper/snapshot contract.
3. Remove the account-level completed-dispatch path completely.
4. Build SmartFlex entities only for fields that actually exist in the current snapshot.

This keeps the integration truthful to the API:

- if the API returns vehicle state-of-charge, battery size, and latest charging session, those become entities
- if the API does not return a field, that entity does not exist
- if a user has multiple vehicles or chargers, each device still gets its own entity set

## Component Design

### `custom_components/eon_next/api.py`

- fix `SMARTFLEX_DEVICES_QUERY` so the `status` block only requests:
  - `current`
  - `isSuspended`
  - `currentState`
  at the interface level
- move these fields behind inline fragments on `SmartFlexVehicleStatus` and `SmartFlexChargePointStatus`:
  - `stateOfCharge`
  - `activePower`
  - `stateOfChargeLimit`
  - `testDispatchFailureReason`
- keep per-device planned-dispatch querying unchanged in principle
- remove the completed-dispatch query constant and the account-level completed-dispatch fetch path
- remove `latest_completed_dispatch` from the top-level SmartFlex enrichment flow
- keep SmartFlex-specific malformed-payload tolerance local to the SmartFlex helpers

### `custom_components/eon_next/sensor.py`

- keep the existing non-SmartFlex account sensors unchanged
- remove account-level completed-dispatch sensor descriptions
- keep per-device SmartFlex sensor descriptions, but only instantiate a sensor when its value path resolves to a real value
- keep dynamic per-device names and raw-device-id-based unique ids
- preserve the late-entity listener path so newly available SmartFlex values still create entities after setup

### `custom_components/eon_next/const.py`

- remove completed-dispatch attribute keys that are no longer used
- retain only per-device SmartFlex attribute keys still required by the remaining sensor surface

### `tests/components/eon_next/test_api.py`

- add or update query-shape coverage proving the SmartFlex status block uses inline fragments correctly
- remove completed-dispatch expectations from async SmartFlex snapshot tests
- keep live-device and planned-dispatch normalization coverage intact

### `tests/components/eon_next/test_sensor.py`

- remove account-level completed-dispatch sensor expectations
- prove only existing SmartFlex values create entities
- prove vehicle-only fields and charger-only fields do not create dead entities on the wrong device type
- keep multiple-device and late-entity coverage intact

## Data Flow

1. The integration authenticates as it does today.
2. The client fetches the current account/tariff payload.
3. The client builds the existing electricity, gas, billing, and meter fields.
4. The client fetches `devices(accountNumber)` using the corrected SmartFlex status fragments.
5. For each returned supported SmartFlex vehicle or charge point:
   - normalize identity and live status
   - normalize the latest charging session if present
   - fetch planned dispatches for that device and keep the next upcoming dispatch only
6. The client returns one combined snapshot containing the existing account data plus the SmartFlex device collection.
7. `sensor.py` builds the existing account sensors plus only those SmartFlex per-device entities whose values currently exist.
8. If a previously missing SmartFlex field appears later, the coordinator listener adds the new entity after setup.

## Error Handling

- If the SmartFlex `devices` query fails, the integration still loads and exposes only the existing non-SmartFlex sensors.
- If a per-device planned-dispatch query fails, that device still exists but its planned-dispatch entities do not.
- If a SmartFlex field is absent or `null`, the corresponding entity is not created.
- If a malformed SmartFlex list item appears, skip that item rather than fail the whole refresh.
- Shared non-SmartFlex parsing keeps its current stricter behavior; SmartFlex tolerance remains local to SmartFlex-specific helpers.

## Testing Strategy

Required API coverage:

- the SmartFlex `devices` query uses status inline fragments correctly
- live SmartFlex raw payloads still normalize into the expected per-device snapshot shape
- completed-dispatch support is removed from the async SmartFlex enrichment path
- non-SmartFlex account snapshot behavior does not regress

Required sensor coverage:

- per-device SmartFlex entities still appear for real vehicle and charger data
- vehicle-only and charger-only metrics create entities only on compatible devices
- missing optional SmartFlex fields do not create dead entities
- late-arriving SmartFlex entities still appear after setup
- distinct raw device ids still yield distinct SmartFlex entity unique ids
- non-SmartFlex sensors remain unchanged

Repository verification should still include the standard `./scripts/check.sh` flow before the fix is considered complete.

## Success Criteria

This remodel is complete when:

- live SmartFlex device discovery works against the real API schema
- per-vehicle and per-charger SmartFlex entities appear when their values exist
- the account-level completed-dispatch entities are removed
- absent optional SmartFlex fields no longer produce dead placeholder entities
- multiple SmartFlex devices still get separate entity ids
- existing non-SmartFlex entities continue to behave the same
- repository verification passes
