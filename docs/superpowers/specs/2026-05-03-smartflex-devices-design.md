# SmartFlex Devices Design

## Goal

Add the first EV / charger slice by exposing direct SmartFlex API data for registered devices, their live status, each device's latest charging session, each device's next planned dispatch, and the account's latest completed dispatch, while keeping the existing electricity, gas, billing, and meter entities unchanged.

## Scope

This slice includes:

- SmartFlex device discovery for the configured account
- per-device identity fields such as name, type, provider, make, and model
- per-device live status fields such as lifecycle status, current state, suspension state, state of charge, active power, and state-of-charge limit data when present
- per-device latest charging session only
- per-device next planned dispatch only
- latest completed dispatch at account level only
- support for multiple SmartFlex devices in one account

This slice does not include:

- full charging-session history
- full planned-dispatch history
- per-device completed dispatch entities unless the API later proves a reliable device link
- OCPP credential fields such as generated URL or username
- onboarding, supported-device catalog, or registration-helper entities
- calculated charging windows, charging recommendations, or any other derived behavior
- control or mutation features for SmartFlex devices or preferences

## Existing Structure

The integration currently refreshes one account snapshot through one coordinator and exposes one description-driven sensor platform. The existing `AccountSnapshot` in `custom_components/eon_next/api.py` carries account, electricity, gas, billing, and meter data, and `custom_components/eon_next/sensor.py` maps those top-level fields into account-oriented sensors.

The current client fetches one authenticated account/tariff payload and does not query any SmartFlex device surfaces.

Schema exploration against the live GraphQL endpoint proved that the upstream API exposes dedicated SmartFlex device and charging fields beyond tariff data, including:

- `devices(accountNumber)`
- `flexPlannedDispatches(deviceId)`
- `completedDispatches(accountNumber)`
- `SmartFlexVehicle` and `SmartFlexChargePoint`
- status fields including state of charge and active power
- `chargingSessions(last: 1)` on each device

## Architecture

The integration should keep the current single-entry, single-coordinator model and extend the snapshot rather than creating a separate SmartFlex platform or coordinator.

The client should fetch SmartFlex data in a bounded second phase after the existing account snapshot is built:

1. Fetch the current account/tariff payload as today.
2. Build the existing account snapshot fields.
3. Fetch SmartFlex devices for the same account number.
4. For each discovered device, normalize direct device fields and the latest charging session.
5. For each discovered device, fetch its planned dispatch list and keep only the first dispatch returned in time order as the next planned dispatch.
6. Fetch completed dispatches once at account level and keep only the first dispatch returned in reverse time order as the latest completed dispatch.
7. Publish one combined snapshot containing the existing account data plus normalized SmartFlex data.

The design intentionally mirrors the upstream API shape:

- device state and latest session are device-level
- planned dispatches are device-level
- completed dispatches are account-level in the proven API surface, so the first slice should keep them account-level instead of guessing a device link

## Component Design

### `custom_components/eon_next/api.py`

- add one SmartFlex device query rooted at `devices(accountNumber)`
- add one planned-dispatch query rooted at `flexPlannedDispatches(deviceId)`
- add one completed-dispatch query rooted at `completedDispatches(accountNumber)`
- introduce immutable nested snapshot dataclasses for SmartFlex data rather than flattening everything into the existing top-level account fields
- extend the top-level account snapshot with:
  - a collection of SmartFlex device snapshots
  - one optional latest completed dispatch snapshot
- keep all SmartFlex selection rules in `api.py`, including:
  - latest charging session selection
  - first planned dispatch selection
  - latest completed dispatch selection
  - partial-field fallback behavior

Recommended SmartFlex snapshot structure:

- `SmartFlexReadingSnapshot`
  - timestamp
  - value
- `SmartFlexSocLimitSnapshot`
  - upper limit
  - timestamp
  - violation flag
- `SmartFlexChargingSessionSnapshot`
  - start
  - end
  - state-of-charge change
  - final state of charge
  - energy value and unit
  - cost amount and currency
- `SmartFlexPlannedDispatchSnapshot`
  - start
  - end
  - dispatch type
  - energy added in kWh when present
- `SmartFlexCompletedDispatchSnapshot`
  - start
  - end
  - delta
  - source
  - location
- `SmartFlexDeviceSnapshot`
  - device id
  - name
  - device type
  - provider
  - integration device id
  - property id
  - make
  - model
  - vehicle battery size when present
  - charge-point power output when present
  - lifecycle status
  - current state
  - suspended flag
  - latest state-of-charge reading when present
  - latest active-power reading in kW when present
  - latest state-of-charge limit when present
  - latest charging session when present
  - next planned dispatch when present

### `custom_components/eon_next/coordinator.py`

- keep one coordinator and one refresh cadence
- continue returning one combined snapshot object
- keep auth and transport error handling unchanged at the coordinator boundary

### `custom_components/eon_next/sensor.py`

- keep the current account-level description-driven sensor surface intact
- add a bounded second sensor builder for SmartFlex entities
- create per-device sensors for direct fields that naturally behave as current state, including:
  - lifecycle status
  - current state
  - suspension state
  - state of charge
  - active power
  - battery size when present
  - charge-point power output when present
  - latest charging session fields
  - next planned dispatch fields
- create account-level sensors for latest completed dispatch fields
- keep identifiers and less important metadata as attributes where that keeps entity count reasonable
- derive stable unique IDs from the config entry id, SmartFlex device id where applicable, and the field purpose

### `custom_components/eon_next/const.py`

- add any new attribute keys and units needed for SmartFlex metadata
- keep names explicit and fuel/domain specific where that improves clarity

### `tests/components/eon_next/test_api.py`

- add SmartFlex query and normalization coverage
- prove multiple-device handling
- prove latest-only and next-only selection rules
- prove graceful handling of absent optional data
- prove existing account snapshot behavior does not regress

### `tests/components/eon_next/test_sensor.py`

- add per-device SmartFlex sensor coverage
- prove account sensors and SmartFlex sensors coexist in one config entry
- prove stable unique IDs across multiple devices
- prove `None` behavior for missing latest session, planned dispatch, and completed dispatch data

## Data Flow

1. The integration authenticates as it does today.
2. The client fetches the current account/tariff payload.
3. The client builds the existing electricity, gas, billing, and meter fields.
4. The client fetches `devices(accountNumber)` for the same account.
5. For each returned SmartFlex device:
   - normalize identity and capability fields
   - normalize live status fields
   - request only the latest charging session from the device connection
   - fetch planned dispatches for that device and keep the first dispatch in time order as the next planned dispatch
6. The client fetches `completedDispatches(accountNumber)` once and keeps the first dispatch in reverse time order as the latest completed dispatch.
7. The client returns one combined snapshot.
8. The coordinator publishes that snapshot.
9. `sensor.py` builds the existing account sensors plus new SmartFlex sensors from the same refresh result.

Selection rules:

- latest charging session: newest session returned for the device
- next planned dispatch: first planned dispatch returned in time order for the device
- latest completed dispatch: first completed dispatch returned in reverse time order for the account
- missing optional surfaces: expose `None` instead of removing the sensor

## Error Handling

This slice should stay conservative and should not let optional SmartFlex surfaces break the existing account sensor experience.

- If an account has no SmartFlex devices, setup and refresh still succeed and the integration exposes only the existing account sensors.
- If a SmartFlex device omits optional fields such as make, model, state-of-charge limit, battery size, or charge-point power output, that device still exists and only those values become `None`.
- If a device has no charging sessions or no planned dispatches, the related latest-only or next-only sensors remain present and report `None`.
- If the account has no completed dispatches, the account-level completed-dispatch sensors remain present and report `None`.
- If a SmartFlex field is malformed inside an otherwise valid response, fallback should be contained to that field or device where possible instead of failing the whole snapshot.
- If SmartFlex-specific queries are unavailable, disabled, or unsupported for an otherwise valid energy account, the integration should degrade to no SmartFlex entities rather than failing the entire refresh.
- Authentication failures and account-level transport failures remain fatal in the same way they are today.

## Testing Strategy

Required API coverage:

- no SmartFlex devices
- one SmartFlex vehicle
- one SmartFlex charge point
- multiple devices in one account
- latest charging session selection from device session lists
- next planned dispatch selection from device planned-dispatch lists
- latest completed dispatch selection from account completed-dispatch lists
- partial or missing optional SmartFlex fields without breaking the whole snapshot
- SmartFlex-query degradation behavior for unsupported or unavailable optional surfaces
- non-regression for existing electricity, gas, billing, and meter extraction

Required sensor coverage:

- per-device SmartFlex sensor creation
- account-level latest completed dispatch sensor creation
- coexistence of existing account sensors and new SmartFlex sensors
- stable unique IDs for multiple devices
- `None` behavior for missing optional SmartFlex surfaces
- non-regression for the existing account sensor names, IDs, and core values

Repository verification should still include the project's standard `./scripts/check.sh` flow before the slice is considered complete.

## Success Criteria

This first EV / charger slice is complete when:

- the integration fetches SmartFlex devices for the configured account
- it exposes per-device identity and live-status fields from direct API data
- it exposes each device's latest charging session only
- it exposes each device's next planned dispatch only
- it exposes the account's latest completed dispatch only
- existing electricity, gas, billing, and meter entities continue to behave the same
- repository verification passes
