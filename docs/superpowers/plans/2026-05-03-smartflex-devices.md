# SmartFlex Devices Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first EV / charger slice by exposing SmartFlex vehicle and charge-point state, latest charging session, next planned dispatch, and latest account-level completed dispatch from direct API data.

**Architecture:** Keep the current single config entry, single coordinator, and single sensor platform. Extend `custom_components/eon_next/api.py` with SmartFlex query/normalization helpers and nested immutable snapshot types, then extend `custom_components/eon_next/sensor.py` with a second bounded sensor surface for per-device SmartFlex entities plus account-level completed-dispatch sensors. SmartFlex queries are optional and must degrade to no SmartFlex entities instead of breaking the existing electricity, gas, billing, and meter surfaces.

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
  Owns all SmartFlex GraphQL queries, optional-query degradation, latest-only selection rules, and immutable SmartFlex snapshot dataclasses.
- `custom_components/eon_next/const.py`
  Owns SmartFlex attribute key names that appear on new sensors.
- `custom_components/eon_next/sensor.py`
  Keeps the existing account sensor surface intact and adds per-device SmartFlex sensors plus account-level completed-dispatch sensors.
- `tests/components/eon_next/test_api.py`
  Proves pure SmartFlex normalization, latest-only selection rules, optional-query degradation, request sequencing, and non-regression for the existing account snapshot.
- `tests/components/eon_next/test_sensor.py`
  Proves SmartFlex entity creation, per-device state/session/dispatch values, `None` handling, and coexistence with the existing account sensors.

---

### Task 1: Add SmartFlex snapshot types and pure normalization helpers

**Files:**
- Modify: `tests/components/eon_next/test_api.py`
- Modify: `custom_components/eon_next/api.py`

- [ ] **Step 1: Write the failing pure-normalization tests first**

Add these imports and helper payload builders near the top of `tests/components/eon_next/test_api.py`:

```python
from custom_components.eon_next.api import (
    AGREEMENTS_QUERY,
    LOGIN_MUTATION,
    REFRESH_MUTATION,
    VIEWER_QUERY,
    AccountSnapshot,
    EonNextRatesAuthError,
    EonNextRatesClient,
    EonNextRatesUnsupportedError,
    SmartFlexChargingSessionSnapshot,
    SmartFlexCompletedDispatchSnapshot,
    SmartFlexDeviceSnapshot,
    SmartFlexPlannedDispatchSnapshot,
    SmartFlexReadingSnapshot,
    SmartFlexSocLimitSnapshot,
    build_account_snapshot,
    build_smartflex_device_snapshot,
    select_account_number,
    select_active_half_hourly_agreement,
    select_latest_completed_dispatch,
    select_next_planned_dispatch,
)


def _smartflex_session_node(
    *,
    start: str,
    end: str,
    soc_change: str | None,
    final_soc: str | None,
    energy_value: str | None,
    cost_amount: str | None,
    currency: str = "GBP",
) -> dict[str, Any]:
    return {
        "start": start,
        "end": end,
        "stateOfChargeChange": soc_change,
        "stateOfChargeFinal": final_soc,
        "energyAdded": (
            {"value": energy_value, "unit": "KILOWATT_HOUR"}
            if energy_value is not None
            else None
        ),
        "cost": (
            {"amount": cost_amount, "currency": currency}
            if cost_amount is not None
            else None
        ),
    }


def _smartflex_vehicle_payload(
    *,
    device_id: str = "vehicle-123",
    name: str = "Driveway EV",
    sessions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "__typename": "SmartFlexVehicle",
        "id": device_id,
        "name": name,
        "deviceType": "ELECTRIC_VEHICLES",
        "provider": "TESLA",
        "integrationDeviceId": "tesla-vehicle-123",
        "propertyId": "42",
        "status": {
            "current": "LIVE",
            "isSuspended": False,
            "currentState": "SMART_CONTROL_CAPABLE",
            "stateOfCharge": {
                "timestamp": "2026-05-03T08:15:00+00:00",
                "value": "67.5",
            },
            "activePower": {
                "timestamp": "2026-05-03T08:16:00+00:00",
                "value": "7.4",
            },
            "stateOfChargeLimit": {
                "upperSocLimit": 80,
                "timestamp": "2026-05-03T07:00:00+00:00",
                "isLimitViolated": False,
            },
            "testDispatchFailureReason": None,
        },
        "make": "Tesla",
        "model": "Model 3",
        "vehicleBatterySize": "75.0",
        "chargePointPowerOutput": "7.4",
        "chargingSessions": {
            "edges": [{"node": session, "cursor": session["end"]} for session in (sessions or [])]
        },
    }


def _smartflex_charge_point_payload(
    *,
    device_id: str = "charge-point-123",
    name: str = "Driveway Charger",
    sessions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "__typename": "SmartFlexChargePoint",
        "id": device_id,
        "name": name,
        "deviceType": "ELECTRIC_VEHICLES",
        "provider": "OHME",
        "integrationDeviceId": "ohme-charge-point-123",
        "propertyId": "42",
        "status": {
            "current": "LIVE",
            "isSuspended": False,
            "currentState": "SMART_CONTROL_IN_PROGRESS",
            "stateOfCharge": {
                "timestamp": "2026-05-03T08:30:00+00:00",
                "value": "71.0",
            },
            "activePower": {
                "timestamp": "2026-05-03T08:31:00+00:00",
                "value": "6.8",
            },
            "stateOfChargeLimit": {
                "upperSocLimit": 85,
                "timestamp": "2026-05-03T07:00:00+00:00",
                "isLimitViolated": False,
            },
            "testDispatchFailureReason": None,
        },
        "make": "Ohme",
        "model": "Home Pro",
        "vehicleBatterySize": None,
        "chargePointPowerOutput": "7.0",
        "chargingSessions": {
            "edges": [{"node": session, "cursor": session["end"]} for session in (sessions or [])]
        },
        "chargingPreferences": {
            "weekdayTargetTime": "07:00:00",
            "weekdayTargetSoc": 80,
            "weekendTargetTime": "09:00:00",
            "weekendTargetSoc": 80,
            "minimumSoc": 30,
            "maximumSoc": 85,
        },
    }


def _smartflex_unsupported_device_payload() -> dict[str, Any]:
    return {
        "__typename": "SmartFlexDevice",
        "id": "battery-ignored",
        "name": "Battery",
        "deviceType": "BATTERIES",
        "provider": "BYD",
        "integrationDeviceId": "battery-ignored",
        "propertyId": "42",
        "status": {
            "current": "LIVE",
            "isSuspended": False,
            "currentState": "SMART_CONTROL_CAPABLE",
        },
    }


def _smartflex_planned_dispatch(
    *, start: str, end: str, dispatch_type: str, energy_added_kwh: str | None
) -> dict[str, Any]:
    return {
        "start": start,
        "end": end,
        "type": dispatch_type,
        "energyAddedKwh": energy_added_kwh,
    }


def _smartflex_completed_dispatch(
    *, start: str, end: str, delta: str | None, source: str, location: str
) -> dict[str, Any]:
    return {
        "start": start,
        "end": end,
        "delta": delta,
        "meta": {"source": source, "location": location},
    }
```

Add these failing tests below the existing `build_account_snapshot(...)` tests:

```python
def test_build_account_snapshot_defaults_smartflex_surfaces_to_empty() -> None:
    snapshot = build_account_snapshot(
        _account_payload(),
        _agreement_payload_with_meter_readings(),
        datetime(2026, 5, 1, 12, 15, tzinfo=UTC),
    )

    assert snapshot.smartflex_devices == ()
    assert snapshot.latest_completed_dispatch is None


def test_build_smartflex_device_snapshot_selects_latest_session_and_planned_dispatch() -> None:
    device = _smartflex_vehicle_payload(
        sessions=[
            _smartflex_session_node(
                start="2026-05-01T00:00:00+00:00",
                end="2026-05-01T02:00:00+00:00",
                soc_change="18.5",
                final_soc="72.0",
                energy_value="12.4",
                cost_amount="3.21",
            ),
            _smartflex_session_node(
                start="2026-05-02T00:00:00+00:00",
                end="2026-05-02T03:00:00+00:00",
                soc_change="22.0",
                final_soc="80.0",
                energy_value="14.8",
                cost_amount="4.56",
            ),
        ]
    )
    next_dispatch = select_next_planned_dispatch(
        [
            _smartflex_planned_dispatch(
                start="2026-05-03T04:00:00+00:00",
                end="2026-05-03T05:00:00+00:00",
                dispatch_type="BOOST",
                energy_added_kwh="9.5",
            ),
            _smartflex_planned_dispatch(
                start="2026-05-03T01:00:00+00:00",
                end="2026-05-03T03:00:00+00:00",
                dispatch_type="SMART",
                energy_added_kwh="14.5",
            ),
        ]
    )

    snapshot = build_smartflex_device_snapshot(device, next_dispatch)

    assert snapshot == SmartFlexDeviceSnapshot(
        device_id="vehicle-123",
        name="Driveway EV",
        device_type="ELECTRIC_VEHICLES",
        provider="TESLA",
        integration_device_id="tesla-vehicle-123",
        property_id="42",
        make="Tesla",
        model="Model 3",
        vehicle_battery_size_kwh=75.0,
        charge_point_power_output_kw=7.4,
        lifecycle_status="LIVE",
        current_state="SMART_CONTROL_CAPABLE",
        is_suspended=False,
        state_of_charge=SmartFlexReadingSnapshot(
            timestamp=datetime(2026, 5, 3, 8, 15, tzinfo=UTC),
            value=67.5,
        ),
        active_power=SmartFlexReadingSnapshot(
            timestamp=datetime(2026, 5, 3, 8, 16, tzinfo=UTC),
            value=7.4,
        ),
        state_of_charge_limit=SmartFlexSocLimitSnapshot(
            upper_soc_limit=80,
            timestamp=datetime(2026, 5, 3, 7, 0, tzinfo=UTC),
            is_limit_violated=False,
        ),
        test_dispatch_failure_reason=None,
        latest_charging_session=SmartFlexChargingSessionSnapshot(
            start=datetime(2026, 5, 2, 0, 0, tzinfo=UTC),
            end=datetime(2026, 5, 2, 3, 0, tzinfo=UTC),
            state_of_charge_change=22.0,
            state_of_charge_final=80.0,
            energy_added_value=14.8,
            energy_added_unit="KILOWATT_HOUR",
            cost_amount=4.56,
            cost_currency="GBP",
        ),
        next_planned_dispatch=SmartFlexPlannedDispatchSnapshot(
            start=datetime(2026, 5, 3, 1, 0, tzinfo=UTC),
            end=datetime(2026, 5, 3, 3, 0, tzinfo=UTC),
            dispatch_type="SMART",
            energy_added_kwh=14.5,
        ),
    )


def test_select_latest_completed_dispatch_uses_most_recent_dispatch() -> None:
    dispatch = select_latest_completed_dispatch(
        [
            _smartflex_completed_dispatch(
                start="2026-05-01T00:00:00+00:00",
                end="2026-05-01T01:00:00+00:00",
                delta="4.2",
                source="smartflex",
                location="home",
            ),
            _smartflex_completed_dispatch(
                start="2026-05-02T00:00:00+00:00",
                end="2026-05-02T01:30:00+00:00",
                delta="7.1",
                source="smartflex",
                location="driveway",
            ),
        ]
    )

    assert dispatch == SmartFlexCompletedDispatchSnapshot(
        start=datetime(2026, 5, 2, 0, 0, tzinfo=UTC),
        end=datetime(2026, 5, 2, 1, 30, tzinfo=UTC),
        delta=7.1,
        source="smartflex",
        location="driveway",
    )
```

- [ ] **Step 2: Run the new API tests and confirm they fail**

Run:

```bash
./.venv/bin/python -m pytest \
  tests/components/eon_next/test_api.py::test_build_account_snapshot_defaults_smartflex_surfaces_to_empty \
  tests/components/eon_next/test_api.py::test_build_smartflex_device_snapshot_selects_latest_session_and_planned_dispatch \
  tests/components/eon_next/test_api.py::test_select_latest_completed_dispatch_uses_most_recent_dispatch \
  -q
```

Expected: FAIL because `AccountSnapshot` does not yet have SmartFlex fields and the new SmartFlex helper functions/types do not exist.

- [ ] **Step 3: Add the SmartFlex dataclasses and pure helper functions**

In `custom_components/eon_next/api.py`, update the dataclass import and add these new immutable types immediately above `AccountSnapshot`:

```python
from dataclasses import dataclass, replace


@dataclass(frozen=True, slots=True)
class SmartFlexReadingSnapshot:
    timestamp: datetime
    value: float


@dataclass(frozen=True, slots=True)
class SmartFlexSocLimitSnapshot:
    upper_soc_limit: int | None
    timestamp: datetime | None
    is_limit_violated: bool | None


@dataclass(frozen=True, slots=True)
class SmartFlexChargingSessionSnapshot:
    start: datetime
    end: datetime
    state_of_charge_change: float | None
    state_of_charge_final: float | None
    energy_added_value: float | None
    energy_added_unit: str | None
    cost_amount: float | None
    cost_currency: str | None


@dataclass(frozen=True, slots=True)
class SmartFlexPlannedDispatchSnapshot:
    start: datetime
    end: datetime
    dispatch_type: str
    energy_added_kwh: float | None


@dataclass(frozen=True, slots=True)
class SmartFlexCompletedDispatchSnapshot:
    start: datetime
    end: datetime
    delta: float | None
    source: str | None
    location: str | None


@dataclass(frozen=True, slots=True)
class SmartFlexDeviceSnapshot:
    device_id: str
    name: str | None
    device_type: str
    provider: str
    integration_device_id: str | None
    property_id: str | None
    make: str | None
    model: str | None
    vehicle_battery_size_kwh: float | None
    charge_point_power_output_kw: float | None
    lifecycle_status: str | None
    current_state: str | None
    is_suspended: bool | None
    state_of_charge: SmartFlexReadingSnapshot | None
    active_power: SmartFlexReadingSnapshot | None
    state_of_charge_limit: SmartFlexSocLimitSnapshot | None
    test_dispatch_failure_reason: str | None
    latest_charging_session: SmartFlexChargingSessionSnapshot | None
    next_planned_dispatch: SmartFlexPlannedDispatchSnapshot | None
```

Extend `AccountSnapshot` with SmartFlex defaults at the end of the dataclass:

```python
    gas_meter_point_mprn: str | None = None
    smartflex_devices: tuple[SmartFlexDeviceSnapshot, ...] = ()
    latest_completed_dispatch: SmartFlexCompletedDispatchSnapshot | None = None
```

Add these helper functions below `_parse_decimal_string(...)` and above the billing/gas helpers:

```python
def _parse_floatish(value: Any) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _reading_snapshot(reading: dict[str, Any] | None) -> SmartFlexReadingSnapshot | None:
    if not isinstance(reading, dict):
        return None

    timestamp = _parse_datetime(reading.get("timestamp"))
    value = _parse_floatish(reading.get("value"))
    if timestamp is None or value is None:
        return None

    return SmartFlexReadingSnapshot(timestamp=timestamp, value=value)


def _soc_limit_snapshot(limit_data: dict[str, Any] | None) -> SmartFlexSocLimitSnapshot | None:
    if not isinstance(limit_data, dict):
        return None

    timestamp = _parse_datetime(limit_data.get("timestamp"))
    return SmartFlexSocLimitSnapshot(
        upper_soc_limit=limit_data.get("upperSocLimit"),
        timestamp=timestamp,
        is_limit_violated=limit_data.get("isLimitViolated"),
    )


def _latest_charging_session(
    connection: dict[str, Any] | None,
) -> SmartFlexChargingSessionSnapshot | None:
    if not isinstance(connection, dict):
        return None

    edges = connection.get("edges")
    if not isinstance(edges, list):
        return None

    latest_snapshot = None
    latest_end = None

    for edge in edges:
        if not isinstance(edge, dict):
            continue
        node = edge.get("node")
        if not isinstance(node, dict):
            continue

        start = _parse_datetime(node.get("start"))
        end = _parse_datetime(node.get("end"))
        if start is None or end is None:
            continue

        energy_added = node.get("energyAdded")
        cost = node.get("cost")
        snapshot = SmartFlexChargingSessionSnapshot(
            start=start,
            end=end,
            state_of_charge_change=_parse_floatish(node.get("stateOfChargeChange")),
            state_of_charge_final=_parse_floatish(node.get("stateOfChargeFinal")),
            energy_added_value=_parse_floatish(
                energy_added.get("value") if isinstance(energy_added, dict) else None
            ),
            energy_added_unit=(
                energy_added.get("unit") if isinstance(energy_added, dict) else None
            ),
            cost_amount=_parse_floatish(cost.get("amount") if isinstance(cost, dict) else None),
            cost_currency=cost.get("currency") if isinstance(cost, dict) else None,
        )

        if latest_end is None or end > latest_end:
            latest_end = end
            latest_snapshot = snapshot

    return latest_snapshot


def select_next_planned_dispatch(
    dispatches: list[dict[str, Any]] | None,
) -> SmartFlexPlannedDispatchSnapshot | None:
    if not isinstance(dispatches, list):
        return None

    earliest_snapshot = None
    earliest_start = None

    for dispatch in dispatches:
        if not isinstance(dispatch, dict):
            continue

        start = _parse_datetime(dispatch.get("start"))
        end = _parse_datetime(dispatch.get("end"))
        dispatch_type = dispatch.get("type")
        if start is None or end is None or not isinstance(dispatch_type, str):
            continue

        snapshot = SmartFlexPlannedDispatchSnapshot(
            start=start,
            end=end,
            dispatch_type=dispatch_type,
            energy_added_kwh=_parse_floatish(dispatch.get("energyAddedKwh")),
        )
        if earliest_start is None or start < earliest_start:
            earliest_start = start
            earliest_snapshot = snapshot

    return earliest_snapshot


def select_latest_completed_dispatch(
    dispatches: list[dict[str, Any]] | None,
) -> SmartFlexCompletedDispatchSnapshot | None:
    if not isinstance(dispatches, list):
        return None

    latest_snapshot = None
    latest_end = None

    for dispatch in dispatches:
        if not isinstance(dispatch, dict):
            continue

        start = _parse_datetime(dispatch.get("start"))
        end = _parse_datetime(dispatch.get("end"))
        if start is None or end is None:
            continue

        meta = dispatch.get("meta")
        snapshot = SmartFlexCompletedDispatchSnapshot(
            start=start,
            end=end,
            delta=_parse_floatish(dispatch.get("delta")),
            source=meta.get("source") if isinstance(meta, dict) else None,
            location=meta.get("location") if isinstance(meta, dict) else None,
        )
        if latest_end is None or end > latest_end:
            latest_end = end
            latest_snapshot = snapshot

    return latest_snapshot


def build_smartflex_device_snapshot(
    device: dict[str, Any],
    next_planned_dispatch: SmartFlexPlannedDispatchSnapshot | None,
) -> SmartFlexDeviceSnapshot:
    status = device.get("status") if isinstance(device.get("status"), dict) else {}

    device_id = device.get("id")
    device_type = device.get("deviceType")
    provider = device.get("provider")
    if not isinstance(device_id, str) or not isinstance(device_type, str) or not isinstance(provider, str):
        raise EonNextRatesUnsupportedError(
            "SmartFlex device payload missing required field(s): id, deviceType, provider"
        )

    return SmartFlexDeviceSnapshot(
        device_id=device_id,
        name=device.get("name"),
        device_type=device_type,
        provider=provider,
        integration_device_id=device.get("integrationDeviceId"),
        property_id=device.get("propertyId"),
        make=device.get("make"),
        model=device.get("model"),
        vehicle_battery_size_kwh=_parse_floatish(device.get("vehicleBatterySize")),
        charge_point_power_output_kw=_parse_floatish(device.get("chargePointPowerOutput")),
        lifecycle_status=status.get("current"),
        current_state=status.get("currentState"),
        is_suspended=status.get("isSuspended"),
        state_of_charge=_reading_snapshot(status.get("stateOfCharge")),
        active_power=_reading_snapshot(status.get("activePower")),
        state_of_charge_limit=_soc_limit_snapshot(status.get("stateOfChargeLimit")),
        test_dispatch_failure_reason=status.get("testDispatchFailureReason"),
        latest_charging_session=_latest_charging_session(device.get("chargingSessions")),
        next_planned_dispatch=next_planned_dispatch,
    )
```

- [ ] **Step 4: Run the pure-normalization tests again**

Run:

```bash
./.venv/bin/python -m pytest \
  tests/components/eon_next/test_api.py::test_build_account_snapshot_defaults_smartflex_surfaces_to_empty \
  tests/components/eon_next/test_api.py::test_build_smartflex_device_snapshot_selects_latest_session_and_planned_dispatch \
  tests/components/eon_next/test_api.py::test_select_latest_completed_dispatch_uses_most_recent_dispatch \
  -q
```

Expected: PASS.

- [ ] **Step 5: Commit the SmartFlex model layer**

```bash
git add custom_components/eon_next/api.py tests/components/eon_next/test_api.py
git commit -m "feat: model smartflex device snapshots"
```

---

### Task 2: Fetch SmartFlex devices and latest dispatch data in the client

**Files:**
- Modify: `tests/components/eon_next/test_api.py`
- Modify: `custom_components/eon_next/api.py`

- [ ] **Step 1: Write the failing client-integration tests first**

Add these helper payload wrappers in `tests/components/eon_next/test_api.py` below the new SmartFlex helper builders:

```python
def _smartflex_devices_payload(*devices: dict[str, Any]) -> dict[str, Any]:
    return {"data": {"devices": list(devices)}}


def _smartflex_planned_dispatches_payload(*dispatches: dict[str, Any]) -> dict[str, Any]:
    return {"data": {"flexPlannedDispatches": list(dispatches)}}


def _smartflex_completed_dispatches_payload(*dispatches: dict[str, Any]) -> dict[str, Any]:
    return {"data": {"completedDispatches": list(dispatches)}}
```

Add these two failing tests near the existing `async_get_account_snapshot()` client tests:

```python
def test_async_get_account_snapshot_includes_smartflex_devices_and_latest_completed_dispatch() -> None:
    agreement_payload = {
        "data": {
            "account": {
                **_account_payload(balance=12345, bills=_bills_payload(_statement_node())),
                "electricityAgreements": [_agreement_payload_with_meter_readings()],
                "gasAgreements": [_gas_agreement_payload_with_meter_readings()],
            }
        }
    }
    session = _FakeSession(
        [
            _token_payload("access-1", "refresh-1", 2000000000),
            _viewer_payload(),
            agreement_payload,
            agreement_payload,
            _smartflex_devices_payload(
                _smartflex_vehicle_payload(
                    sessions=[
                        _smartflex_session_node(
                            start="2026-05-02T00:00:00+00:00",
                            end="2026-05-02T03:00:00+00:00",
                            soc_change="22.0",
                            final_soc="80.0",
                            energy_value="14.8",
                            cost_amount="4.56",
                        )
                    ]
                ),
                _smartflex_charge_point_payload(
                    sessions=[
                        _smartflex_session_node(
                            start="2026-05-02T04:00:00+00:00",
                            end="2026-05-02T05:00:00+00:00",
                            soc_change="8.0",
                            final_soc="88.0",
                            energy_value="6.2",
                            cost_amount="1.74",
                        )
                    ]
                ),
                _smartflex_unsupported_device_payload(),
            ),
            _smartflex_planned_dispatches_payload(
                _smartflex_planned_dispatch(
                    start="2026-05-03T01:00:00+00:00",
                    end="2026-05-03T03:00:00+00:00",
                    dispatch_type="SMART",
                    energy_added_kwh="14.5",
                )
            ),
            _smartflex_planned_dispatches_payload(
                _smartflex_planned_dispatch(
                    start="2026-05-03T02:00:00+00:00",
                    end="2026-05-03T04:00:00+00:00",
                    dispatch_type="BOOST",
                    energy_added_kwh="6.0",
                )
            ),
            _smartflex_completed_dispatches_payload(
                _smartflex_completed_dispatch(
                    start="2026-05-01T00:00:00+00:00",
                    end="2026-05-01T01:00:00+00:00",
                    delta="4.2",
                    source="smartflex",
                    location="home",
                ),
                _smartflex_completed_dispatch(
                    start="2026-05-02T00:00:00+00:00",
                    end="2026-05-02T01:30:00+00:00",
                    delta="7.1",
                    source="smartflex",
                    location="driveway",
                ),
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

    assert [device.device_id for device in snapshot.smartflex_devices] == [
        "vehicle-123",
        "charge-point-123",
    ]
    assert snapshot.smartflex_devices[0].latest_charging_session is not None
    assert snapshot.smartflex_devices[0].next_planned_dispatch is not None
    assert snapshot.smartflex_devices[1].next_planned_dispatch is not None
    assert snapshot.latest_completed_dispatch == SmartFlexCompletedDispatchSnapshot(
        start=datetime(2026, 5, 2, 0, 0, tzinfo=UTC),
        end=datetime(2026, 5, 2, 1, 30, tzinfo=UTC),
        delta=7.1,
        source="smartflex",
        location="driveway",
    )
    assert session.requests[4]["json"]["variables"] == {"accountNumber": "A-PLACEHOLDER0001"}
    assert session.requests[5]["json"]["variables"] == {"deviceId": "vehicle-123"}
    assert session.requests[6]["json"]["variables"] == {"deviceId": "charge-point-123"}
    assert session.requests[7]["json"]["variables"] == {"accountNumber": "A-PLACEHOLDER0001"}


def test_async_get_account_snapshot_ignores_optional_smartflex_query_failures() -> None:
    agreement_payload = {
        "data": {
            "account": {
                **_account_payload(),
                "electricityAgreements": [_agreement_payload_with_meter_readings()],
            }
        }
    }
    session = _FakeSession(
        [
            _token_payload("access-1", "refresh-1", 2000000000),
            _viewer_payload(),
            agreement_payload,
            agreement_payload,
            _smartflex_devices_payload(
                _smartflex_vehicle_payload(sessions=[]),
            ),
            {"errors": [{"message": "Unable to fetch planned dispatches."}]},
            {"errors": [{"message": "Disabled GraphQL field requested."}]},
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
    assert snapshot.latest_completed_dispatch is None
```

- [ ] **Step 2: Run the new client tests and confirm they fail**

Run:

```bash
./.venv/bin/python -m pytest \
  tests/components/eon_next/test_api.py::test_async_get_account_snapshot_includes_smartflex_devices_and_latest_completed_dispatch \
  tests/components/eon_next/test_api.py::test_async_get_account_snapshot_ignores_optional_smartflex_query_failures \
  -q
```

Expected: FAIL because `async_get_account_snapshot()` still only fetches the account/tariff payload and does not issue SmartFlex queries.

- [ ] **Step 3: Add SmartFlex queries and optional-query client helpers**

In `custom_components/eon_next/api.py`, add these query constants below `AGREEMENTS_QUERY`:

```python
SMARTFLEX_DEVICES_QUERY = """query GetSmartFlexDevices($accountNumber: String!) {
  devices(accountNumber: $accountNumber) {
    __typename
    id
    name
    deviceType
    provider
    integrationDeviceId
    propertyId
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
    ... on SmartFlexVehicle {
      chargingSessions(last: 1) {
        edges {
          cursor
          node {
            start
            end
            stateOfChargeChange
            stateOfChargeFinal
            energyAdded {
              value
              unit
            }
            cost {
              amount
              currency
            }
          }
        }
      }
      make
      model
      vehicleBatterySize
      chargePointPowerOutput
    }
    ... on SmartFlexChargePoint {
      chargingSessions(last: 1) {
        edges {
          cursor
          node {
            start
            end
            stateOfChargeChange
            stateOfChargeFinal
            energyAdded {
              value
              unit
            }
            cost {
              amount
              currency
            }
          }
        }
      }
      make
      model
      vehicleBatterySize
      chargePointPowerOutput
    }
  }
}"""

SMARTFLEX_PLANNED_DISPATCHES_QUERY = """query GetSmartFlexPlannedDispatches($deviceId: String!) {
  flexPlannedDispatches(deviceId: $deviceId) {
    start
    end
    type
    energyAddedKwh
  }
}"""

SMARTFLEX_COMPLETED_DISPATCHES_QUERY = """query GetSmartFlexCompletedDispatches($accountNumber: String!) {
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
```

Add these methods inside `EonNextRatesClient` below `_async_authenticated_graphql(...)`:

```python
    async def _async_optional_authenticated_graphql(
        self, query: str, variables: dict | None = None
    ) -> dict | None:
        try:
            return await self._async_authenticated_graphql(query, variables)
        except EonNextRatesConnectionError:
            return None

    async def _async_get_smartflex_devices(
        self, account_number: str
    ) -> tuple[SmartFlexDeviceSnapshot, ...]:
        data = await self._async_optional_authenticated_graphql(
            SMARTFLEX_DEVICES_QUERY,
            {"accountNumber": account_number},
        )
        if data is None:
            return ()

        devices = data.get("devices")
        if not isinstance(devices, list):
            return ()

        snapshots: list[SmartFlexDeviceSnapshot] = []
        for device in devices:
            if not isinstance(device, dict):
                continue

            if device.get("__typename") not in {"SmartFlexVehicle", "SmartFlexChargePoint"}:
                continue

            next_planned_dispatch = None
            device_id = device.get("id")
            if isinstance(device_id, str):
                planned_data = await self._async_optional_authenticated_graphql(
                    SMARTFLEX_PLANNED_DISPATCHES_QUERY,
                    {"deviceId": device_id},
                )
                next_planned_dispatch = select_next_planned_dispatch(
                    planned_data.get("flexPlannedDispatches") if planned_data else None
                )

            snapshots.append(build_smartflex_device_snapshot(device, next_planned_dispatch))

        return tuple(snapshots)

    async def _async_get_latest_completed_dispatch(
        self, account_number: str
    ) -> SmartFlexCompletedDispatchSnapshot | None:
        data = await self._async_optional_authenticated_graphql(
            SMARTFLEX_COMPLETED_DISPATCHES_QUERY,
            {"accountNumber": account_number},
        )
        return select_latest_completed_dispatch(
            data.get("completedDispatches") if data else None
        )
```

Update `async_get_account_snapshot()` to fetch SmartFlex data after the existing account snapshot is built:

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
        smartflex_devices = await self._async_get_smartflex_devices(snapshot.account_number)
        latest_completed_dispatch = await self._async_get_latest_completed_dispatch(
            snapshot.account_number
        )
        return replace(
            snapshot,
            smartflex_devices=smartflex_devices,
            latest_completed_dispatch=latest_completed_dispatch,
        )
```

- [ ] **Step 4: Run the client tests again**

Run:

```bash
./.venv/bin/python -m pytest \
  tests/components/eon_next/test_api.py::test_async_get_account_snapshot_includes_smartflex_devices_and_latest_completed_dispatch \
  tests/components/eon_next/test_api.py::test_async_get_account_snapshot_ignores_optional_smartflex_query_failures \
  -q
```

Expected: PASS.

- [ ] **Step 5: Commit the SmartFlex client integration**

```bash
git add custom_components/eon_next/api.py tests/components/eon_next/test_api.py
git commit -m "feat: fetch smartflex device data"
```

---

### Task 3: Add SmartFlex sensors and verify the full slice

**Files:**
- Modify: `tests/components/eon_next/test_sensor.py`
- Modify: `custom_components/eon_next/const.py`
- Modify: `custom_components/eon_next/sensor.py`
- Modify: `tests/components/eon_next/test_api.py`

- [ ] **Step 1: Write the failing SmartFlex sensor tests first**

In `tests/components/eon_next/test_sensor.py`, extend the imports to include the new SmartFlex dataclasses:

```python
from custom_components.eon_next.api import (
    AccountSnapshot,
    SmartFlexChargingSessionSnapshot,
    SmartFlexCompletedDispatchSnapshot,
    SmartFlexDeviceSnapshot,
    SmartFlexPlannedDispatchSnapshot,
    SmartFlexReadingSnapshot,
    SmartFlexSocLimitSnapshot,
)
```

Add these helper builders below `_entity_by_suffix(...)`:

```python
def _smartflex_device_snapshot(device_id: str = "vehicle-123") -> SmartFlexDeviceSnapshot:
    return SmartFlexDeviceSnapshot(
        device_id=device_id,
        name="Driveway EV",
        device_type="ELECTRIC_VEHICLES",
        provider="TESLA",
        integration_device_id="tesla-vehicle-123",
        property_id="42",
        make="Tesla",
        model="Model 3",
        vehicle_battery_size_kwh=75.0,
        charge_point_power_output_kw=7.4,
        lifecycle_status="LIVE",
        current_state="SMART_CONTROL_CAPABLE",
        is_suspended=False,
        state_of_charge=SmartFlexReadingSnapshot(
            timestamp=datetime(2026, 5, 3, 8, 15, tzinfo=UTC),
            value=67.5,
        ),
        active_power=SmartFlexReadingSnapshot(
            timestamp=datetime(2026, 5, 3, 8, 16, tzinfo=UTC),
            value=7.4,
        ),
        state_of_charge_limit=SmartFlexSocLimitSnapshot(
            upper_soc_limit=80,
            timestamp=datetime(2026, 5, 3, 7, 0, tzinfo=UTC),
            is_limit_violated=False,
        ),
        test_dispatch_failure_reason=None,
        latest_charging_session=SmartFlexChargingSessionSnapshot(
            start=datetime(2026, 5, 2, 0, 0, tzinfo=UTC),
            end=datetime(2026, 5, 2, 3, 0, tzinfo=UTC),
            state_of_charge_change=22.0,
            state_of_charge_final=80.0,
            energy_added_value=14.8,
            energy_added_unit="KILOWATT_HOUR",
            cost_amount=4.56,
            cost_currency="GBP",
        ),
        next_planned_dispatch=SmartFlexPlannedDispatchSnapshot(
            start=datetime(2026, 5, 3, 1, 0, tzinfo=UTC),
            end=datetime(2026, 5, 3, 3, 0, tzinfo=UTC),
            dispatch_type="SMART",
            energy_added_kwh=14.5,
        ),
    )
```

Add these failing tests near the bottom of the file:

```python
def test_build_sensors_adds_smartflex_entities_for_each_device(sensor_module, snapshot) -> None:
    smartflex_snapshot = replace(
        snapshot,
        smartflex_devices=(
            _smartflex_device_snapshot("vehicle-123"),
            replace(_smartflex_device_snapshot("charge-point-123"), name="Driveway Charger"),
        ),
        latest_completed_dispatch=SmartFlexCompletedDispatchSnapshot(
            start=datetime(2026, 5, 2, 0, 0, tzinfo=UTC),
            end=datetime(2026, 5, 2, 1, 30, tzinfo=UTC),
            delta=7.1,
            source="smartflex",
            location="driveway",
        ),
    )
    entities = sensor_module._build_sensors("entry-123", _DummyCoordinator(smartflex_snapshot))
    unique_ids = {entity.unique_id for entity in entities}

    assert "entry-123_smartflex_vehicle_123_current_state" in unique_ids
    assert "entry-123_smartflex_vehicle_123_latest_charging_session_energy_added" in unique_ids
    assert "entry-123_smartflex_vehicle_123_latest_charging_session_cost" in unique_ids
    assert "entry-123_smartflex_charge_point_123_next_planned_dispatch_start" in unique_ids
    assert "entry-123_smartflex_charge_point_123_next_planned_dispatch_energy_added" in unique_ids
    assert "entry-123_latest_smartflex_completed_dispatch_delta" in unique_ids


def test_smartflex_device_sensors_expose_expected_values_and_attributes(
    sensor_module, snapshot
) -> None:
    smartflex_snapshot = replace(
        snapshot,
        smartflex_devices=(_smartflex_device_snapshot(),),
        latest_completed_dispatch=SmartFlexCompletedDispatchSnapshot(
            start=datetime(2026, 5, 2, 0, 0, tzinfo=UTC),
            end=datetime(2026, 5, 2, 1, 30, tzinfo=UTC),
            delta=7.1,
            source="smartflex",
            location="driveway",
        ),
    )
    entities = sensor_module._build_sensors("entry-123", _DummyCoordinator(smartflex_snapshot))

    current_state_sensor = _entity_by_suffix(entities, "smartflex_vehicle_123_current_state")
    soc_sensor = _entity_by_suffix(entities, "smartflex_vehicle_123_state_of_charge")
    active_power_sensor = _entity_by_suffix(entities, "smartflex_vehicle_123_active_power")
    session_energy_sensor = _entity_by_suffix(
        entities, "smartflex_vehicle_123_latest_charging_session_energy_added"
    )
    session_cost_sensor = _entity_by_suffix(
        entities, "smartflex_vehicle_123_latest_charging_session_cost"
    )
    dispatch_start_sensor = _entity_by_suffix(
        entities, "smartflex_vehicle_123_next_planned_dispatch_start"
    )
    dispatch_energy_sensor = _entity_by_suffix(
        entities, "smartflex_vehicle_123_next_planned_dispatch_energy_added"
    )

    assert current_state_sensor.name == "E.ON Driveway EV State"
    assert current_state_sensor.native_value == "SMART_CONTROL_CAPABLE"
    assert current_state_sensor.extra_state_attributes == {
        "smartflex_lifecycle_status": "LIVE",
        "smartflex_is_suspended": False,
        "smartflex_device_type": "ELECTRIC_VEHICLES",
        "smartflex_provider": "TESLA",
        "smartflex_integration_device_id": "tesla-vehicle-123",
        "smartflex_property_id": "42",
        "smartflex_make": "Tesla",
        "smartflex_model": "Model 3",
        "smartflex_test_dispatch_failure_reason": None,
    }

    assert soc_sensor.native_value == 67.5
    assert soc_sensor.native_unit_of_measurement == "%"
    assert soc_sensor.extra_state_attributes == {
        "smartflex_reading_timestamp": datetime(2026, 5, 3, 8, 15, tzinfo=UTC),
        "smartflex_state_of_charge_upper_limit": 80,
        "smartflex_state_of_charge_limit_timestamp": datetime(
            2026, 5, 3, 7, 0, tzinfo=UTC
        ),
        "smartflex_state_of_charge_limit_is_violated": False,
    }

    assert active_power_sensor.native_value == 7.4
    assert active_power_sensor.native_unit_of_measurement == "kW"
    assert active_power_sensor.extra_state_attributes == {
        "smartflex_reading_timestamp": datetime(2026, 5, 3, 8, 16, tzinfo=UTC),
    }

    assert session_energy_sensor.native_value == 14.8
    assert session_energy_sensor.native_unit_of_measurement == "kWh"
    assert session_energy_sensor.extra_state_attributes == {
        "smartflex_latest_charging_session_start": datetime(2026, 5, 2, 0, 0, tzinfo=UTC),
        "smartflex_latest_charging_session_end": datetime(2026, 5, 2, 3, 0, tzinfo=UTC),
        "smartflex_latest_charging_session_state_of_charge_change": 22.0,
        "smartflex_latest_charging_session_final_state_of_charge": 80.0,
    }

    assert session_cost_sensor.native_value == 4.56
    assert session_cost_sensor.native_unit_of_measurement == "GBP"
    assert session_cost_sensor.extra_state_attributes == {
        "smartflex_latest_charging_session_start": datetime(2026, 5, 2, 0, 0, tzinfo=UTC),
        "smartflex_latest_charging_session_end": datetime(2026, 5, 2, 3, 0, tzinfo=UTC),
        "smartflex_latest_charging_session_state_of_charge_change": 22.0,
        "smartflex_latest_charging_session_final_state_of_charge": 80.0,
    }

    assert dispatch_start_sensor.native_value == datetime(2026, 5, 3, 1, 0, tzinfo=UTC)
    assert dispatch_start_sensor.extra_state_attributes == {
        "smartflex_next_planned_dispatch_end": datetime(2026, 5, 3, 3, 0, tzinfo=UTC),
        "smartflex_next_planned_dispatch_type": "SMART",
    }

    assert dispatch_energy_sensor.native_value == 14.5
    assert dispatch_energy_sensor.native_unit_of_measurement == "kWh"
    assert dispatch_energy_sensor.extra_state_attributes == {
        "smartflex_next_planned_dispatch_start": datetime(2026, 5, 3, 1, 0, tzinfo=UTC),
        "smartflex_next_planned_dispatch_end": datetime(2026, 5, 3, 3, 0, tzinfo=UTC),
        "smartflex_next_planned_dispatch_type": "SMART",
        "smartflex_next_planned_dispatch_energy_added_kwh": 14.5,
    }


def test_account_level_completed_dispatch_sensors_expose_expected_values(
    sensor_module, snapshot
) -> None:
    smartflex_snapshot = replace(
        snapshot,
        smartflex_devices=(_smartflex_device_snapshot(),),
        latest_completed_dispatch=SmartFlexCompletedDispatchSnapshot(
            start=datetime(2026, 5, 2, 0, 0, tzinfo=UTC),
            end=datetime(2026, 5, 2, 1, 30, tzinfo=UTC),
            delta=7.1,
            source="smartflex",
            location="driveway",
        ),
    )
    entities = sensor_module._build_sensors("entry-123", _DummyCoordinator(smartflex_snapshot))

    completed_delta_sensor = _entity_by_suffix(
        entities, "latest_smartflex_completed_dispatch_delta"
    )
    completed_start_sensor = _entity_by_suffix(
        entities, "latest_smartflex_completed_dispatch_start"
    )

    assert completed_start_sensor.native_value == datetime(2026, 5, 2, 0, 0, tzinfo=UTC)
    assert completed_delta_sensor.native_value == 7.1
    assert completed_delta_sensor.extra_state_attributes == {
        "smartflex_latest_completed_dispatch_source": "smartflex",
        "smartflex_latest_completed_dispatch_location": "driveway",
    }


def test_smartflex_sensors_return_none_for_missing_optional_surfaces(
    sensor_module, snapshot
) -> None:
    smartflex_snapshot = replace(
        snapshot,
        smartflex_devices=(
            replace(
                _smartflex_device_snapshot(),
                vehicle_battery_size_kwh=None,
                charge_point_power_output_kw=None,
                state_of_charge=None,
                active_power=None,
                state_of_charge_limit=None,
                latest_charging_session=None,
                next_planned_dispatch=None,
            ),
        ),
        latest_completed_dispatch=None,
    )
    entities = sensor_module._build_sensors("entry-123", _DummyCoordinator(smartflex_snapshot))

    assert _entity_by_suffix(entities, "smartflex_vehicle_123_state_of_charge").native_value is None
    assert _entity_by_suffix(entities, "smartflex_vehicle_123_active_power").native_value is None
    assert _entity_by_suffix(entities, "smartflex_vehicle_123_battery_size").native_value is None
    assert (
        _entity_by_suffix(entities, "smartflex_vehicle_123_latest_charging_session_start").native_value
        is None
    )
    assert _entity_by_suffix(entities, "smartflex_vehicle_123_next_planned_dispatch_start").native_value is None
    assert _entity_by_suffix(entities, "latest_smartflex_completed_dispatch_delta").native_value is None
    assert _entity_by_suffix(
        entities, "latest_smartflex_completed_dispatch_delta"
    ).extra_state_attributes == {
        "smartflex_latest_completed_dispatch_source": None,
        "smartflex_latest_completed_dispatch_location": None,
    }
```

- [ ] **Step 2: Run the SmartFlex sensor tests and confirm they fail**

Run:

```bash
./.venv/bin/python -m pytest \
  tests/components/eon_next/test_sensor.py::test_build_sensors_adds_smartflex_entities_for_each_device \
  tests/components/eon_next/test_sensor.py::test_smartflex_device_sensors_expose_expected_values_and_attributes \
  tests/components/eon_next/test_sensor.py::test_account_level_completed_dispatch_sensors_expose_expected_values \
  tests/components/eon_next/test_sensor.py::test_smartflex_sensors_return_none_for_missing_optional_surfaces \
  -q
```

Expected: FAIL because `sensor.py` and `const.py` do not yet define any SmartFlex sensor descriptions, attribute keys, or entity builders.

- [ ] **Step 3: Add SmartFlex attribute keys and sensor descriptions**

In `custom_components/eon_next/const.py`, add these SmartFlex attribute constants after the existing gas meter-reading constants:

```python
ATTR_SMARTFLEX_LIFECYCLE_STATUS = "smartflex_lifecycle_status"
ATTR_SMARTFLEX_IS_SUSPENDED = "smartflex_is_suspended"
ATTR_SMARTFLEX_DEVICE_TYPE = "smartflex_device_type"
ATTR_SMARTFLEX_PROVIDER = "smartflex_provider"
ATTR_SMARTFLEX_INTEGRATION_DEVICE_ID = "smartflex_integration_device_id"
ATTR_SMARTFLEX_PROPERTY_ID = "smartflex_property_id"
ATTR_SMARTFLEX_MAKE = "smartflex_make"
ATTR_SMARTFLEX_MODEL = "smartflex_model"
ATTR_SMARTFLEX_TEST_DISPATCH_FAILURE_REASON = "smartflex_test_dispatch_failure_reason"
ATTR_SMARTFLEX_READING_TIMESTAMP = "smartflex_reading_timestamp"
ATTR_SMARTFLEX_STATE_OF_CHARGE_UPPER_LIMIT = "smartflex_state_of_charge_upper_limit"
ATTR_SMARTFLEX_STATE_OF_CHARGE_LIMIT_TIMESTAMP = "smartflex_state_of_charge_limit_timestamp"
ATTR_SMARTFLEX_STATE_OF_CHARGE_LIMIT_IS_VIOLATED = (
    "smartflex_state_of_charge_limit_is_violated"
)
ATTR_SMARTFLEX_LATEST_CHARGING_SESSION_START = "smartflex_latest_charging_session_start"
ATTR_SMARTFLEX_LATEST_CHARGING_SESSION_END = "smartflex_latest_charging_session_end"
ATTR_SMARTFLEX_LATEST_CHARGING_SESSION_STATE_OF_CHARGE_CHANGE = (
    "smartflex_latest_charging_session_state_of_charge_change"
)
ATTR_SMARTFLEX_LATEST_CHARGING_SESSION_FINAL_STATE_OF_CHARGE = (
    "smartflex_latest_charging_session_final_state_of_charge"
)
ATTR_SMARTFLEX_NEXT_PLANNED_DISPATCH_START = "smartflex_next_planned_dispatch_start"
ATTR_SMARTFLEX_NEXT_PLANNED_DISPATCH_END = "smartflex_next_planned_dispatch_end"
ATTR_SMARTFLEX_NEXT_PLANNED_DISPATCH_TYPE = "smartflex_next_planned_dispatch_type"
ATTR_SMARTFLEX_NEXT_PLANNED_DISPATCH_ENERGY_ADDED_KWH = (
    "smartflex_next_planned_dispatch_energy_added_kwh"
)
ATTR_SMARTFLEX_LATEST_COMPLETED_DISPATCH_SOURCE = "smartflex_latest_completed_dispatch_source"
ATTR_SMARTFLEX_LATEST_COMPLETED_DISPATCH_LOCATION = "smartflex_latest_completed_dispatch_location"
```

In `custom_components/eon_next/sensor.py`, add these unit constants near the existing unit constants:

```python
POWER_UNIT = "kW"
PERCENT_UNIT = "%"
ENERGY_UNIT = "kWh"
```

Add this nested-path helper and the new description types below `EonRateSensorDescription`:

```python
def _resolve_path(root: Any, path: tuple[str, ...]) -> Any:
    current = root
    for part in path:
        if current is None:
            return None
        current = getattr(current, part, None)
    return current


@dataclass(frozen=True, kw_only=True)
class SmartFlexDeviceSensorDescription(SensorEntityDescription):
    unique_id_suffix: str
    value_path: tuple[str, ...]
    attribute_paths: dict[str, tuple[str, ...]] | None = None
    unit_path: tuple[str, ...] | None = None


@dataclass(frozen=True, kw_only=True)
class NestedAccountSensorDescription(SensorEntityDescription):
    unique_id_suffix: str
    value_path: tuple[str, ...]
    attribute_paths: dict[str, tuple[str, ...]] | None = None
    unit_path: tuple[str, ...] | None = None
```

Add these SmartFlex description tuples below `SENSOR_DESCRIPTIONS`:

```python
SMARTFLEX_DEVICE_SENSOR_DESCRIPTIONS = (
    SmartFlexDeviceSensorDescription(
        key="smartflex_current_state",
        name="State",
        unique_id_suffix="current_state",
        value_path=("current_state",),
        attribute_paths={
            ATTR_SMARTFLEX_LIFECYCLE_STATUS: ("lifecycle_status",),
            ATTR_SMARTFLEX_IS_SUSPENDED: ("is_suspended",),
            ATTR_SMARTFLEX_DEVICE_TYPE: ("device_type",),
            ATTR_SMARTFLEX_PROVIDER: ("provider",),
            ATTR_SMARTFLEX_INTEGRATION_DEVICE_ID: ("integration_device_id",),
            ATTR_SMARTFLEX_PROPERTY_ID: ("property_id",),
            ATTR_SMARTFLEX_MAKE: ("make",),
            ATTR_SMARTFLEX_MODEL: ("model",),
            ATTR_SMARTFLEX_TEST_DISPATCH_FAILURE_REASON: ("test_dispatch_failure_reason",),
        },
    ),
    SmartFlexDeviceSensorDescription(
        key="smartflex_state_of_charge",
        name="State of Charge",
        native_unit_of_measurement=PERCENT_UNIT,
        unique_id_suffix="state_of_charge",
        value_path=("state_of_charge", "value"),
        attribute_paths={
            ATTR_SMARTFLEX_READING_TIMESTAMP: ("state_of_charge", "timestamp"),
            ATTR_SMARTFLEX_STATE_OF_CHARGE_UPPER_LIMIT: (
                "state_of_charge_limit",
                "upper_soc_limit",
            ),
            ATTR_SMARTFLEX_STATE_OF_CHARGE_LIMIT_TIMESTAMP: (
                "state_of_charge_limit",
                "timestamp",
            ),
            ATTR_SMARTFLEX_STATE_OF_CHARGE_LIMIT_IS_VIOLATED: (
                "state_of_charge_limit",
                "is_limit_violated",
            ),
        },
    ),
    SmartFlexDeviceSensorDescription(
        key="smartflex_active_power",
        name="Active Power",
        native_unit_of_measurement=POWER_UNIT,
        unique_id_suffix="active_power",
        value_path=("active_power", "value"),
        attribute_paths={
            ATTR_SMARTFLEX_READING_TIMESTAMP: ("active_power", "timestamp"),
        },
    ),
    SmartFlexDeviceSensorDescription(
        key="smartflex_battery_size",
        name="Battery Size",
        native_unit_of_measurement=ENERGY_UNIT,
        unique_id_suffix="battery_size",
        value_path=("vehicle_battery_size_kwh",),
    ),
    SmartFlexDeviceSensorDescription(
        key="smartflex_charge_point_power_output",
        name="Charge Point Power Output",
        native_unit_of_measurement=POWER_UNIT,
        unique_id_suffix="charge_point_power_output",
        value_path=("charge_point_power_output_kw",),
    ),
    SmartFlexDeviceSensorDescription(
        key="smartflex_latest_charging_session_start",
        name="Latest Charging Session Start",
        device_class=SensorDeviceClass.TIMESTAMP,
        unique_id_suffix="latest_charging_session_start",
        value_path=("latest_charging_session", "start"),
    ),
    SmartFlexDeviceSensorDescription(
        key="smartflex_latest_charging_session_end",
        name="Latest Charging Session End",
        device_class=SensorDeviceClass.TIMESTAMP,
        unique_id_suffix="latest_charging_session_end",
        value_path=("latest_charging_session", "end"),
    ),
    SmartFlexDeviceSensorDescription(
        key="smartflex_latest_charging_session_energy_added",
        name="Latest Charging Session Energy Added",
        native_unit_of_measurement=ENERGY_UNIT,
        unique_id_suffix="latest_charging_session_energy_added",
        value_path=("latest_charging_session", "energy_added_value"),
        attribute_paths={
            ATTR_SMARTFLEX_LATEST_CHARGING_SESSION_START: (
                "latest_charging_session",
                "start",
            ),
            ATTR_SMARTFLEX_LATEST_CHARGING_SESSION_END: (
                "latest_charging_session",
                "end",
            ),
            ATTR_SMARTFLEX_LATEST_CHARGING_SESSION_STATE_OF_CHARGE_CHANGE: (
                "latest_charging_session",
                "state_of_charge_change",
            ),
            ATTR_SMARTFLEX_LATEST_CHARGING_SESSION_FINAL_STATE_OF_CHARGE: (
                "latest_charging_session",
                "state_of_charge_final",
            ),
        },
    ),
    SmartFlexDeviceSensorDescription(
        key="smartflex_latest_charging_session_cost",
        name="Latest Charging Session Cost",
        unique_id_suffix="latest_charging_session_cost",
        value_path=("latest_charging_session", "cost_amount"),
        unit_path=("latest_charging_session", "cost_currency"),
        attribute_paths={
            ATTR_SMARTFLEX_LATEST_CHARGING_SESSION_START: (
                "latest_charging_session",
                "start",
            ),
            ATTR_SMARTFLEX_LATEST_CHARGING_SESSION_END: (
                "latest_charging_session",
                "end",
            ),
            ATTR_SMARTFLEX_LATEST_CHARGING_SESSION_STATE_OF_CHARGE_CHANGE: (
                "latest_charging_session",
                "state_of_charge_change",
            ),
            ATTR_SMARTFLEX_LATEST_CHARGING_SESSION_FINAL_STATE_OF_CHARGE: (
                "latest_charging_session",
                "state_of_charge_final",
            ),
        },
    ),
    SmartFlexDeviceSensorDescription(
        key="smartflex_next_planned_dispatch_start",
        name="Next Planned Dispatch Start",
        device_class=SensorDeviceClass.TIMESTAMP,
        unique_id_suffix="next_planned_dispatch_start",
        value_path=("next_planned_dispatch", "start"),
        attribute_paths={
            ATTR_SMARTFLEX_NEXT_PLANNED_DISPATCH_END: ("next_planned_dispatch", "end"),
            ATTR_SMARTFLEX_NEXT_PLANNED_DISPATCH_TYPE: (
                "next_planned_dispatch",
                "dispatch_type",
            ),
        },
    ),
    SmartFlexDeviceSensorDescription(
        key="smartflex_next_planned_dispatch_energy_added",
        name="Next Planned Dispatch Energy Added",
        native_unit_of_measurement=ENERGY_UNIT,
        unique_id_suffix="next_planned_dispatch_energy_added",
        value_path=("next_planned_dispatch", "energy_added_kwh"),
        attribute_paths={
            ATTR_SMARTFLEX_NEXT_PLANNED_DISPATCH_START: (
                "next_planned_dispatch",
                "start",
            ),
            ATTR_SMARTFLEX_NEXT_PLANNED_DISPATCH_END: ("next_planned_dispatch", "end"),
            ATTR_SMARTFLEX_NEXT_PLANNED_DISPATCH_TYPE: (
                "next_planned_dispatch",
                "dispatch_type",
            ),
            ATTR_SMARTFLEX_NEXT_PLANNED_DISPATCH_ENERGY_ADDED_KWH: (
                "next_planned_dispatch",
                "energy_added_kwh",
            ),
        },
    ),
)

SMARTFLEX_ACCOUNT_SENSOR_DESCRIPTIONS = (
    NestedAccountSensorDescription(
        key="latest_smartflex_completed_dispatch_start",
        name="E.ON Latest SmartFlex Completed Dispatch Start",
        device_class=SensorDeviceClass.TIMESTAMP,
        unique_id_suffix="latest_smartflex_completed_dispatch_start",
        value_path=("latest_completed_dispatch", "start"),
    ),
    NestedAccountSensorDescription(
        key="latest_smartflex_completed_dispatch_end",
        name="E.ON Latest SmartFlex Completed Dispatch End",
        device_class=SensorDeviceClass.TIMESTAMP,
        unique_id_suffix="latest_smartflex_completed_dispatch_end",
        value_path=("latest_completed_dispatch", "end"),
    ),
    NestedAccountSensorDescription(
        key="latest_smartflex_completed_dispatch_delta",
        name="E.ON Latest SmartFlex Completed Dispatch Delta",
        unique_id_suffix="latest_smartflex_completed_dispatch_delta",
        value_path=("latest_completed_dispatch", "delta"),
        attribute_paths={
            ATTR_SMARTFLEX_LATEST_COMPLETED_DISPATCH_SOURCE: (
                "latest_completed_dispatch",
                "source",
            ),
            ATTR_SMARTFLEX_LATEST_COMPLETED_DISPATCH_LOCATION: (
                "latest_completed_dispatch",
                "location",
            ),
        },
    ),
)
```

- [ ] **Step 4: Add the SmartFlex entity builders and entity classes**

Still in `custom_components/eon_next/sensor.py`, add a unique-id helper, extend `_build_sensors(...)`, and add the SmartFlex sensor classes below `EonNextRatesSensor`:

```python
def _device_unique_id_fragment(device_id: str) -> str:
    return "".join(char.lower() if char.isalnum() else "_" for char in device_id).strip("_")


def _build_sensors(
    entry_id: str, coordinator: EonNextRatesCoordinator
) -> list[SensorEntity]:
    entities: list[SensorEntity] = [
        EonNextRatesSensor(entry_id, coordinator, description)
        for description in SENSOR_DESCRIPTIONS
    ]
    snapshot = coordinator.data
    if snapshot is None:
        return entities

    if snapshot.smartflex_devices or snapshot.latest_completed_dispatch is not None:
        entities.extend(
            SmartFlexAccountSensor(entry_id, coordinator, description)
            for description in SMARTFLEX_ACCOUNT_SENSOR_DESCRIPTIONS
        )

    for device in snapshot.smartflex_devices:
        fragment = _device_unique_id_fragment(device.device_id)
        entities.extend(
            SmartFlexDeviceSensor(entry_id, coordinator, device.device_id, fragment, description)
            for description in SMARTFLEX_DEVICE_SENSOR_DESCRIPTIONS
        )

    return entities


class SmartFlexDeviceSensor(CoordinatorEntity, SensorEntity):
    entity_description: SmartFlexDeviceSensorDescription

    def __init__(
        self,
        entry_id: str,
        coordinator: EonNextRatesCoordinator,
        device_id: str,
        device_fragment: str,
        description: SmartFlexDeviceSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._device_id = device_id
        self._attr_name = f"E.ON {self._device_name(coordinator) or device_id} {description.name}"
        self._attr_unique_id = (
            f"{entry_id}_smartflex_{device_fragment}_{description.unique_id_suffix}"
        )

    def _device_name(self, coordinator: EonNextRatesCoordinator) -> str | None:
        device = self._device_snapshot(coordinator.data)
        return device.name if device is not None else None

    def _device_snapshot(self, snapshot: AccountSnapshot | None):
        if snapshot is None:
            return None
        return next(
            (device for device in snapshot.smartflex_devices if device.device_id == self._device_id),
            None,
        )

    @property
    def native_value(self) -> float | str | datetime | None:
        return _resolve_path(self._device_snapshot(self.coordinator.data), self.entity_description.value_path)

    @property
    def native_unit_of_measurement(self):
        if self.entity_description.unit_path is None:
            return self.entity_description.native_unit_of_measurement
        return _resolve_path(self._device_snapshot(self.coordinator.data), self.entity_description.unit_path)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        attribute_paths = self.entity_description.attribute_paths
        if attribute_paths is None:
            return None
        device = self._device_snapshot(self.coordinator.data)
        return {
            attribute_name: _resolve_path(device, path)
            for attribute_name, path in attribute_paths.items()
        }


class SmartFlexAccountSensor(CoordinatorEntity, SensorEntity):
    entity_description: NestedAccountSensorDescription

    def __init__(
        self,
        entry_id: str,
        coordinator: EonNextRatesCoordinator,
        description: NestedAccountSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry_id}_{description.unique_id_suffix}"

    @property
    def name(self):
        return self.entity_description.name

    @property
    def native_value(self) -> float | str | datetime | None:
        return _resolve_path(self.coordinator.data, self.entity_description.value_path)

    @property
    def native_unit_of_measurement(self):
        if self.entity_description.unit_path is None:
            return self.entity_description.native_unit_of_measurement
        return _resolve_path(self.coordinator.data, self.entity_description.unit_path)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        attribute_paths = self.entity_description.attribute_paths
        if attribute_paths is None:
            return None
        return {
            attribute_name: _resolve_path(self.coordinator.data, path)
            for attribute_name, path in attribute_paths.items()
        }
```

- [ ] **Step 5: Run the SmartFlex sensor tests again**

Run:

```bash
./.venv/bin/python -m pytest \
  tests/components/eon_next/test_sensor.py::test_build_sensors_adds_smartflex_entities_for_each_device \
  tests/components/eon_next/test_sensor.py::test_smartflex_device_sensors_expose_expected_values_and_attributes \
  tests/components/eon_next/test_sensor.py::test_account_level_completed_dispatch_sensors_expose_expected_values \
  tests/components/eon_next/test_sensor.py::test_smartflex_sensors_return_none_for_missing_optional_surfaces \
  -q
```

Expected: PASS.

- [ ] **Step 6: Run the full repository checks**

Run:

```bash
./scripts/check.sh
```

Expected: PASS.

- [ ] **Step 7: Commit the SmartFlex sensor slice**

```bash
git add custom_components/eon_next/api.py custom_components/eon_next/const.py custom_components/eon_next/sensor.py tests/components/eon_next/test_api.py tests/components/eon_next/test_sensor.py
git commit -m "feat: add smartflex device sensors"
```
