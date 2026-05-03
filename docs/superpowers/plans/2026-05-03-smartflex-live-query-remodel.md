# SmartFlex Live Query Remodel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix SmartFlex live vehicle discovery against the real GraphQL schema, remove the ambiguous account-level completed-dispatch surface, and only create per-device SmartFlex entities when the underlying value exists.

**Architecture:** Keep the current single-entry, single-coordinator model and the existing SmartFlex snapshot helper contract, but correct the raw GraphQL query shape and prune the account-level completed-dispatch path entirely. Then tighten `sensor.py` so SmartFlex entities are created only for fields that actually exist, while preserving dynamic late entity creation for multiple devices.

**Tech Stack:** Home Assistant custom integration, Python 3.13, `pytest`, `pytest-asyncio`, `ruff`

---

## File Structure

**Modify:**
- `custom_components/eon_next/api.py`
- `custom_components/eon_next/const.py`
- `custom_components/eon_next/sensor.py`
- `tests/components/eon_next/test_api.py`
- `tests/components/eon_next/test_sensor.py`

### Responsibilities

- `custom_components/eon_next/api.py`
  Owns the SmartFlex GraphQL query shape, optional-query degradation, normalization into the existing SmartFlex helper contract, and removal of the completed-dispatch enrichment path.
- `custom_components/eon_next/const.py`
  Owns the remaining SmartFlex attribute keys after the completed-dispatch surface is removed.
- `custom_components/eon_next/sensor.py`
  Keeps existing non-SmartFlex sensors unchanged, creates only real per-device SmartFlex entities, and preserves late SmartFlex entity addition after setup.
- `tests/components/eon_next/test_api.py`
  Proves the corrected query shape, removal of completed-dispatch enrichment, and non-regression of SmartFlex normalization.
- `tests/components/eon_next/test_sensor.py`
  Proves only existing SmartFlex values create entities, completed-dispatch entities are gone, and multiple-device / late-entity behavior still works.

---

### Task 1: Remodel the SmartFlex API query and remove completed-dispatch enrichment

**Files:**
- Modify: `tests/components/eon_next/test_api.py`
- Modify: `custom_components/eon_next/api.py`

- [ ] **Step 1: Write the failing API tests first**

In `tests/components/eon_next/test_api.py`, add `SMARTFLEX_DEVICES_QUERY` to the import block:

```python
from custom_components.eon_next.api import (
    AGREEMENTS_QUERY,
    LOGIN_MUTATION,
    REFRESH_MUTATION,
    SMARTFLEX_DEVICES_QUERY,
    VIEWER_QUERY,
    AccountSnapshot,
    EonNextRatesAuthError,
    EonNextRatesClient,
    EonNextRatesUnsupportedError,
    SmartFlexChargingSessionSnapshot,
    SmartFlexDeviceSnapshot,
    SmartFlexPlannedDispatchSnapshot,
    SmartFlexReadingSnapshot,
    SmartFlexSocLimitSnapshot,
    build_account_snapshot,
    build_smartflex_device_snapshot,
    select_account_number,
    select_active_half_hourly_agreement,
    select_next_planned_dispatch,
)
```

Add this failing query-shape test below `test_agreements_query_uses_charge_only_statement_fields_in_charge_fragment()`:

```python
def test_smartflex_devices_query_uses_status_inline_fragments() -> None:
    device_block = SMARTFLEX_DEVICES_QUERY.split(
        "devices(accountNumber: $accountNumber) {", 1
    )[1]
    status_block = device_block.split("status {", 1)[1].split(
        "... on SmartFlexVehicle {", 1
    )[0]
    top_level_status_block = status_block.split("... on SmartFlexVehicleStatus {", 1)[0]

    assert "current" in top_level_status_block
    assert "isSuspended" in top_level_status_block
    assert "currentState" in top_level_status_block
    assert "stateOfCharge" not in top_level_status_block
    assert "activePower" not in top_level_status_block
    assert "stateOfChargeLimit" not in top_level_status_block
    assert "testDispatchFailureReason" not in top_level_status_block
    assert "... on SmartFlexVehicleStatus {" in status_block
    assert "... on SmartFlexChargePointStatus {" in status_block
```

Replace `test_async_get_account_snapshot_includes_smartflex_devices_and_latest_completed_dispatch()` with this narrower completed-dispatch-free version:

```python
def test_async_get_account_snapshot_includes_smartflex_devices_and_planned_dispatches(
) -> None:
    agreement_payload = {
        "data": {
            "account": {
                "number": "A-PLACEHOLDER0001",
                "electricityAgreements": [
                    {
                        "id": "agreement-current",
                        "validFrom": "2026-04-01T00:00:00+00:00",
                        "validTo": None,
                        "meterPoint": {"mpan": "0012345678901", "unbilledReadings": []},
                        "tariff": {
                            "__typename": "HalfHourlyTariff",
                            "displayName": "Next Drive Smart V5.2",
                            "tariffCode": "E-TOU-NEXT_DRIVE_SMART_V5_2-N",
                            "standingCharge": 60.00015,
                            "preVatStandingCharge": 57.143,
                            "unitRates": [
                                {
                                    "value": 23.9022,
                                    "validFrom": "2026-05-01T12:00:00+00:00",
                                    "validTo": "2026-05-01T12:30:00+00:00",
                                },
                                {
                                    "value": 24.5,
                                    "validFrom": "2026-05-01T12:30:00+00:00",
                                    "validTo": "2026-05-01T13:00:00+00:00",
                                },
                            ],
                        },
                    }
                ],
            }
        }
    }
    session = _FakeSession(
        [
            _token_payload("access-1", "refresh-1", 2000000000),
            _viewer_payload(),
            agreement_payload,
            agreement_payload,
            _smartflex_devices_graphql_payload(
                _smartflex_vehicle_graphql_payload(
                    charging_sessions=[
                        _smartflex_graphql_charging_session_payload(
                            start="2026-05-01T18:00:00+00:00",
                            end="2026-05-01T19:00:00+00:00",
                            state_of_charge_change=18,
                            state_of_charge_final=42,
                            energy_added_value=3.2,
                            energy_added_unit="kWh",
                            cost_amount=0.64,
                            cost_currency="GBP",
                        )
                    ]
                ),
                _smartflex_charge_point_graphql_payload(
                    charging_sessions=[
                        _smartflex_graphql_charging_session_payload(
                            start="2026-05-01T20:00:00+00:00",
                            end=None,
                            state_of_charge_change=23,
                            state_of_charge_final=55,
                            energy_added_value=5.6,
                            energy_added_unit="kWh",
                            cost_amount=1.12,
                            cost_currency="GBP",
                        )
                    ]
                ),
                _smartflex_non_ev_graphql_payload(),
            ),
            _smartflex_planned_dispatches_graphql_payload(
                {
                    "start": "2026-05-01T22:00:00+00:00",
                    "end": "2026-05-01T22:30:00+00:00",
                    "type": "GRID_CHARGE",
                    "energyAddedKwh": 4.4,
                },
                {
                    "start": "2026-05-01T21:00:00+00:00",
                    "end": "2026-05-01T21:30:00+00:00",
                    "type": "GRID_CHARGE",
                    "energyAddedKwh": 2.5,
                },
            ),
            _smartflex_planned_dispatches_graphql_payload(
                {
                    "start": "2026-05-01T23:00:00+00:00",
                    "end": "2026-05-01T23:30:00+00:00",
                    "type": "GRID_CHARGE",
                    "energyAddedKwh": 3.3,
                }
            ),
        ]
    )
    client = EonNextRatesClient(
        session,
        email="placeholder_email",
        password="placeholder_password",
        now=lambda: datetime(2026, 5, 1, 12, 15, tzinfo=UTC),
    )

    snapshot = asyncio.run(client.async_get_account_snapshot())

    assert len(snapshot.smartflex_devices) == 2
    assert snapshot.smartflex_devices[0].device_type == "EV"
    assert snapshot.smartflex_devices[1].device_type == "EV_CHARGER"
    assert snapshot.smartflex_devices[0].next_planned_dispatch == SmartFlexPlannedDispatchSnapshot(
        start=datetime(2026, 5, 1, 21, 0, tzinfo=UTC),
        end=datetime(2026, 5, 1, 21, 30, tzinfo=UTC),
        dispatch_type="GRID_CHARGE",
        energy_added_kwh=2.5,
    )
    assert snapshot.smartflex_devices[1].next_planned_dispatch == SmartFlexPlannedDispatchSnapshot(
        start=datetime(2026, 5, 1, 23, 0, tzinfo=UTC),
        end=datetime(2026, 5, 1, 23, 30, tzinfo=UTC),
        dispatch_type="GRID_CHARGE",
        energy_added_kwh=3.3,
    )
    assert not hasattr(snapshot, "latest_completed_dispatch")
    assert session.requests[4]["json"]["variables"] == {"accountNumber": "A-PLACEHOLDER0001"}
    assert session.requests[5]["json"]["variables"] == {"deviceId": "vehicle-1"}
    assert session.requests[6]["json"]["variables"] == {"deviceId": "charger-1"}
    assert len(session.requests) == 7
```

Replace `test_async_get_account_snapshot_ignores_optional_smartflex_query_failures()` with a planned-dispatch-only degradation test:

```python
def test_async_get_account_snapshot_ignores_optional_planned_dispatch_query_failures() -> None:
    agreement_payload = {
        "data": {
            "account": {
                "number": "A-PLACEHOLDER0001",
                "electricityAgreements": [
                    {
                        "id": "agreement-current",
                        "validFrom": "2026-04-01T00:00:00+00:00",
                        "validTo": None,
                        "meterPoint": {"mpan": "0012345678901", "unbilledReadings": []},
                        "tariff": {
                            "__typename": "HalfHourlyTariff",
                            "displayName": "Next Drive Smart V5.2",
                            "tariffCode": "E-TOU-NEXT_DRIVE_SMART_V5_2-N",
                            "standingCharge": 60.00015,
                            "preVatStandingCharge": 57.143,
                            "unitRates": [
                                {
                                    "value": 23.9022,
                                    "validFrom": "2026-05-01T12:00:00+00:00",
                                    "validTo": "2026-05-01T12:30:00+00:00",
                                },
                                {
                                    "value": 24.5,
                                    "validFrom": "2026-05-01T12:30:00+00:00",
                                    "validTo": "2026-05-01T13:00:00+00:00",
                                },
                            ],
                        },
                    }
                ],
            }
        }
    }
    session = _FakeSession(
        [
            _token_payload("access-1", "refresh-1", 2000000000),
            _viewer_payload(),
            agreement_payload,
            agreement_payload,
            _smartflex_devices_graphql_payload(
                _smartflex_vehicle_graphql_payload(device_id="vehicle-1", charging_sessions=[])
            ),
            _graphql_error_payload("Planned dispatch query failed"),
        ]
    )
    client = EonNextRatesClient(
        session,
        email="placeholder_email",
        password="placeholder_password",
        now=lambda: datetime(2026, 5, 1, 12, 15, tzinfo=UTC),
    )

    snapshot = asyncio.run(client.async_get_account_snapshot())

    assert len(snapshot.smartflex_devices) == 1
    assert snapshot.smartflex_devices[0].next_planned_dispatch is None
    assert not hasattr(snapshot, "latest_completed_dispatch")
```

Add a direct devices-query failure branch test:

```python
def test_async_get_account_snapshot_returns_no_smartflex_devices_when_devices_query_fails(
) -> None:
    agreement_payload = {
        "data": {
            "account": {
                "number": "A-PLACEHOLDER0001",
                "electricityAgreements": [
                    {
                        "id": "agreement-current",
                        "validFrom": "2026-04-01T00:00:00+00:00",
                        "validTo": None,
                        "meterPoint": {"mpan": "0012345678901", "unbilledReadings": []},
                        "tariff": {
                            "__typename": "HalfHourlyTariff",
                            "displayName": "Next Drive Smart V5.2",
                            "tariffCode": "E-TOU-NEXT_DRIVE_SMART_V5_2-N",
                            "standingCharge": 60.00015,
                            "preVatStandingCharge": 57.143,
                            "unitRates": [
                                {
                                    "value": 23.9022,
                                    "validFrom": "2026-05-01T12:00:00+00:00",
                                    "validTo": "2026-05-01T12:30:00+00:00",
                                },
                                {
                                    "value": 24.5,
                                    "validFrom": "2026-05-01T12:30:00+00:00",
                                    "validTo": "2026-05-01T13:00:00+00:00",
                                },
                            ],
                        },
                    }
                ],
            }
        }
    }
    session = _FakeSession(
        [
            _token_payload("access-1", "refresh-1", 2000000000),
            _viewer_payload(),
            agreement_payload,
            agreement_payload,
            _graphql_error_payload("Devices query failed"),
        ]
    )
    client = EonNextRatesClient(
        session,
        email="placeholder_email",
        password="placeholder_password",
        now=lambda: datetime(2026, 5, 1, 12, 15, tzinfo=UTC),
    )

    snapshot = asyncio.run(client.async_get_account_snapshot())

    assert snapshot.smartflex_devices == ()
    assert not hasattr(snapshot, "latest_completed_dispatch")
```

- [ ] **Step 2: Run the API remodel tests and confirm they fail**

Run:

```bash
./.venv/bin/python -m pytest \
  tests/components/eon_next/test_api.py::test_smartflex_devices_query_uses_status_inline_fragments \
  tests/components/eon_next/test_api.py::test_async_get_account_snapshot_includes_smartflex_devices_and_planned_dispatches \
  tests/components/eon_next/test_api.py::test_async_get_account_snapshot_ignores_optional_planned_dispatch_query_failures \
  tests/components/eon_next/test_api.py::test_async_get_account_snapshot_returns_no_smartflex_devices_when_devices_query_fails \
  -q
```

Expected: FAIL because the current implementation still fetches account-level completed dispatches and still exposes `latest_completed_dispatch` on the account snapshot path.

- [ ] **Step 3: Remove completed-dispatch enrichment and keep the corrected device query**

In `custom_components/eon_next/api.py`, update `AccountSnapshot` so the SmartFlex tail looks like this:

```python
    gas_meter_point_mprn: str | None = None
    smartflex_devices: tuple[SmartFlexDeviceSnapshot, ...] = ()
```

Delete the completed-dispatch query constant entirely:

```python
SMARTFLEX_COMPLETED_DISPATCHES_QUERY = (
    """query SmartFlexCompletedDispatches($accountNumber: String!) {
  completedDispatches(accountNumber: $accountNumber) {
    start
    end
    delta
    meta {
      source
      location
    }
  }
}"""
)
```

Delete the completed-dispatch fetch method entirely:

```python
    async def _async_get_latest_completed_dispatch(
        self, account_number: str
    ) -> SmartFlexCompletedDispatchSnapshot | None:
        data = await self._async_optional_authenticated_graphql(
            SMARTFLEX_COMPLETED_DISPATCHES_QUERY,
            {"accountNumber": account_number},
        )
        completed_dispatches = (
            _normalize_completed_dispatches(data.get("completedDispatches"))
            if isinstance(data, dict)
            else []
        )
        return select_latest_completed_dispatch(completed_dispatches)
```

Delete the completed-dispatch normalizer and selector helpers entirely by removing both function blocks from `custom_components/eon_next/api.py`:

- `def _normalize_completed_dispatches(completed_dispatches: Any) -> list[dict[str, Any]]:`
- `def select_latest_completed_dispatch(completed_dispatches: list[dict[str, Any]]) -> SmartFlexCompletedDispatchSnapshot | None:`

Update `async_get_account_snapshot()` to stop fetching or returning completed-dispatch data:

```python
    async def async_get_account_snapshot(self) -> AccountSnapshot:
        if self._account_number is None:
            self._account_number = await self.async_discover_account_number()

        now = self._now()
        data = await self._async_authenticated_graphql(
            AGREEMENTS_QUERY,
            {"accountNumber": self._account_number},
        )
        account = data["account"]
        agreement = select_active_half_hourly_agreement(account, now)
        snapshot = build_account_snapshot(account, agreement, now)
        smartflex_devices = await self._async_get_smartflex_devices(self._account_number)
        return replace(snapshot, smartflex_devices=smartflex_devices)
```

Leave the corrected `SMARTFLEX_DEVICES_QUERY` status block in this exact shape:

```python
    status {
      current
      isSuspended
      currentState
      ... on SmartFlexVehicleStatus {
        stateOfCharge {
          timestamp
          value
        }
        activePower {
          timestamp
          value
        }
        stateOfChargeLimit {
          upperSocLimit
          timestamp
          isLimitViolated
        }
        testDispatchFailureReason
      }
      ... on SmartFlexChargePointStatus {
        stateOfCharge {
          timestamp
          value
        }
        activePower {
          timestamp
          value
        }
        stateOfChargeLimit {
          upperSocLimit
          timestamp
          isLimitViolated
        }
        testDispatchFailureReason
      }
    }
```

- [ ] **Step 4: Run the API remodel tests again**

Run:

```bash
./.venv/bin/python -m pytest \
  tests/components/eon_next/test_api.py::test_smartflex_devices_query_uses_status_inline_fragments \
  tests/components/eon_next/test_api.py::test_async_get_account_snapshot_includes_smartflex_devices_and_planned_dispatches \
  tests/components/eon_next/test_api.py::test_async_get_account_snapshot_ignores_optional_planned_dispatch_query_failures \
  tests/components/eon_next/test_api.py::test_async_get_account_snapshot_returns_no_smartflex_devices_when_devices_query_fails \
  -q
```

Expected: PASS.

- [ ] **Step 5: Commit the API remodel**

```bash
git add custom_components/eon_next/api.py tests/components/eon_next/test_api.py
git commit -m "fix: remove smartflex completed dispatch support"
```

---

### Task 2: Remove completed-dispatch sensors and create only real SmartFlex entities

**Files:**
- Modify: `tests/components/eon_next/test_sensor.py`
- Modify: `custom_components/eon_next/const.py`
- Modify: `custom_components/eon_next/sensor.py`

- [ ] **Step 1: Write the failing sensor tests first**

In `tests/components/eon_next/test_sensor.py`, replace `test_build_sensors_adds_smartflex_entities_for_each_device()` with:

```python
def test_build_sensors_adds_smartflex_entities_only_for_real_device_fields(
    sensor_module, snapshot
) -> None:
    smartflex_snapshot = replace(
        snapshot,
        smartflex_devices=(
            _build_smartflex_device_snapshot(),
            _build_smartflex_device_snapshot(
                device_id="vehicle-002",
                name="Family EV",
                device_type="EV",
                make="Kia",
                model="EV6",
                vehicle_battery_size_kwh=77.4,
                charge_point_power_output_kw=None,
            ),
        ),
    )

    entities = sensor_module._build_sensors("entry-123", _DummyCoordinator(smartflex_snapshot))

    assert _entity_by_suffix(
        entities, "smartflex_charger-001_current_state"
    ).name == "E.ON Driveway Charger Current State"
    assert _entity_by_suffix(
        entities, "smartflex_vehicle-002_current_state"
    ).name == "E.ON Family EV Current State"
    assert _entity_by_suffix(entities, "smartflex_vehicle-002_battery_size").native_value == 77.4
    assert not any(
        entity.unique_id == "entry-123_smartflex_vehicle-002_charge_point_power_output"
        for entity in entities
    )
    assert _entity_by_suffix(
        entities, "smartflex_charger-001_charge_point_power_output"
    ).native_value == 7.4
    assert not any(
        entity.unique_id == "entry-123_smartflex_charger-001_battery_size"
        for entity in entities
    )
    assert not any(entity.unique_id.startswith("entry-123_smartflex_latest_completed_dispatch") for entity in entities)
```

Replace `test_smartflex_sensors_return_none_for_missing_optional_surfaces()` with:

```python
def test_missing_optional_smartflex_fields_do_not_create_entities(
    sensor_module, snapshot
) -> None:
    smartflex_snapshot = replace(
        snapshot,
        smartflex_devices=(
            _build_smartflex_device_snapshot(
                state_of_charge=None,
                active_power=None,
                state_of_charge_limit=None,
                vehicle_battery_size_kwh=None,
                charge_point_power_output_kw=None,
                latest_charging_session=None,
                next_planned_dispatch=None,
            ),
        ),
    )

    entities = sensor_module._build_sensors("entry-123", _DummyCoordinator(smartflex_snapshot))
    unique_ids = {entity.unique_id for entity in entities}

    assert "entry-123_smartflex_charger-001_current_state" in unique_ids
    assert "entry-123_smartflex_charger-001_state_of_charge" not in unique_ids
    assert "entry-123_smartflex_charger-001_active_power" not in unique_ids
    assert "entry-123_smartflex_charger-001_battery_size" not in unique_ids
    assert "entry-123_smartflex_charger-001_charge_point_power_output" not in unique_ids
    assert "entry-123_smartflex_charger-001_latest_charging_session_start" not in unique_ids
    assert "entry-123_smartflex_charger-001_latest_charging_session_end" not in unique_ids
    assert "entry-123_smartflex_charger-001_latest_charging_session_energy_added" not in unique_ids
    assert "entry-123_smartflex_charger-001_latest_charging_session_cost" not in unique_ids
    assert "entry-123_smartflex_charger-001_next_planned_dispatch_start" not in unique_ids
    assert "entry-123_smartflex_charger-001_next_planned_dispatch_energy_added" not in unique_ids
    assert not any(unique_id.startswith("entry-123_smartflex_latest_completed_dispatch") for unique_id in unique_ids)
```

Delete `test_account_level_completed_dispatch_sensors_expose_expected_values()` entirely.

Update the late-entity tests so their counts and sets no longer include completed-dispatch sensors. The second batch in both tests should contain 10 entities, not 13 or 14:

```python
    assert len(added_batches) == 2
    assert len(added_batches[0]) == 30
    assert len(added_batches[1]) == 10
    assert {
        entity.unique_id for entity in added_batches[1]
    } == {
        "entry-123_smartflex_charger-001_current_state",
        "entry-123_smartflex_charger-001_state_of_charge",
        "entry-123_smartflex_charger-001_active_power",
        "entry-123_smartflex_charger-001_charge_point_power_output",
        "entry-123_smartflex_charger-001_latest_charging_session_start",
        "entry-123_smartflex_charger-001_latest_charging_session_end",
        "entry-123_smartflex_charger-001_latest_charging_session_energy_added",
        "entry-123_smartflex_charger-001_latest_charging_session_cost",
        "entry-123_smartflex_charger-001_next_planned_dispatch_start",
        "entry-123_smartflex_charger-001_next_planned_dispatch_energy_added",
    }
```

- [ ] **Step 2: Run the SmartFlex sensor remodel tests and confirm they fail**

Run:

```bash
./.venv/bin/python -m pytest \
  tests/components/eon_next/test_sensor.py::test_build_sensors_adds_smartflex_entities_only_for_real_device_fields \
  tests/components/eon_next/test_sensor.py::test_missing_optional_smartflex_fields_do_not_create_entities \
  tests/components/eon_next/test_sensor.py::test_async_setup_entry_adds_smartflex_entities_when_data_arrives_later \
  tests/components/eon_next/test_sensor.py::test_async_setup_entry_does_not_add_duplicate_smartflex_entities_on_repeated_updates \
  -q
```

Expected: FAIL because the current code still exposes account-level completed-dispatch sensors and still adds completed-dispatch entities in the late-entity path.

- [ ] **Step 3: Remove completed-dispatch constants and sensor surface**

In `custom_components/eon_next/const.py`, delete these lines entirely:

```python
ATTR_SMARTFLEX_COMPLETED_DISPATCH_SOURCE = "smartflex_completed_dispatch_source"
ATTR_SMARTFLEX_COMPLETED_DISPATCH_LOCATION = "smartflex_completed_dispatch_location"
```

In `custom_components/eon_next/sensor.py`, remove these imports from the SmartFlex block:

```python
    ATTR_SMARTFLEX_COMPLETED_DISPATCH_LOCATION,
    ATTR_SMARTFLEX_COMPLETED_DISPATCH_SOURCE,
```

Delete `NestedAccountSensorDescription` entirely:

```python
@dataclass(frozen=True, kw_only=True)
class NestedAccountSensorDescription(SensorEntityDescription):
    value_path: PathType
    unique_id_suffix: str
    attribute_paths: dict[str, PathType] | None = None
```

Delete `SMARTFLEX_ACCOUNT_SENSOR_DESCRIPTIONS` entirely by removing the whole tuple block that begins with:

```python
SMARTFLEX_ACCOUNT_SENSOR_DESCRIPTIONS = (
```

and ends at the matching closing `)` for that tuple.

Delete `SmartFlexAccountSensor` entirely by removing the full class block that begins with:

```python
class SmartFlexAccountSensor(CoordinatorEntity, SensorEntity):
```

and ends after its `extra_state_attributes` property.

Update `_build_smartflex_sensors(...)` so it only builds per-device SmartFlex sensors:

```python
def _build_smartflex_sensors(
    entry_id: str, coordinator: EonNextRatesCoordinator
) -> list[SensorEntity]:
    sensors: list[SensorEntity] = []

    snapshot: AccountSnapshot | None = coordinator.data
    if snapshot is None:
        return sensors

    for device in snapshot.smartflex_devices:
        sensors.extend(
            SmartFlexDeviceSensor(entry_id, coordinator, device.device_id, description)
            for description in SMARTFLEX_DEVICE_SENSOR_DESCRIPTIONS
            if _resolve_path(device, description.value_path) is not None
        )

    return sensors
```

- [ ] **Step 4: Run the SmartFlex sensor remodel tests again**

Run:

```bash
./.venv/bin/python -m pytest \
  tests/components/eon_next/test_sensor.py::test_build_sensors_adds_smartflex_entities_only_for_real_device_fields \
  tests/components/eon_next/test_sensor.py::test_missing_optional_smartflex_fields_do_not_create_entities \
  tests/components/eon_next/test_sensor.py::test_async_setup_entry_adds_smartflex_entities_when_data_arrives_later \
  tests/components/eon_next/test_sensor.py::test_async_setup_entry_does_not_add_duplicate_smartflex_entities_on_repeated_updates \
  -q
```

Expected: PASS.

- [ ] **Step 5: Run the full repository checks**

Run:

```bash
./scripts/check.sh
```

Expected: PASS.

- [ ] **Step 6: Commit the sensor remodel**

```bash
git add custom_components/eon_next/const.py custom_components/eon_next/sensor.py tests/components/eon_next/test_sensor.py
git commit -m "refactor: trim smartflex sensor surface"
```
