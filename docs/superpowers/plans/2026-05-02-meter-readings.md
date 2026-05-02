# E.ON Next Meter Readings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the latest available electricity meter reading and its timestamp for the selected E.ON account, with upstream reading metadata attached as sensor attributes.

**Architecture:** Keep the existing single config entry, single coordinator, and single sensor platform. Extend `AccountSnapshot` in `api.py` with optional meter-reading fields populated from `electricityAgreements[].meterPoint.unbilledReadings[].registers[]`, then project those fields through two new description-driven sensors in `sensor.py`. For this first slice, a reading is considered usable when `readAt` is present and at least one register has a parseable numeric `value`; if a reading contains multiple usable registers, use the first usable register in that reading and expose its identifier metadata as attributes.

**Tech Stack:** Home Assistant custom integration, Python 3.13, `pytest`, `pytest-asyncio`, `ruff`, E.ON Next GraphQL

---

## File Structure

**Modify:**
- `custom_components/eon_next/api.py`
- `custom_components/eon_next/const.py`
- `custom_components/eon_next/sensor.py`
- `tests/components/eon_next/test_api.py`
- `tests/components/eon_next/test_sensor.py`
- `tests/components/eon_next/test_init.py`
- `README.md`

### Responsibilities

- `custom_components/eon_next/api.py`
  Adds the meter-reading GraphQL fields, normalizes the latest usable reading, and stores optional meter-reading fields on `AccountSnapshot`.
- `custom_components/eon_next/const.py`
  Defines the new attribute names for meter-reading metadata.
- `custom_components/eon_next/sensor.py`
  Adds two new sensors for latest meter reading value and reading timestamp, and exposes reading metadata as attributes on the value sensor.
- `tests/components/eon_next/test_api.py`
  Proves latest-reading selection, malformed-reading skipping, no-usable-reading fallback, and the widened account snapshot query shape.
- `tests/components/eon_next/test_sensor.py`
  Proves the entity count rises from 6 to 8 and the new meter-reading entities expose the expected values and attributes.
- `tests/components/eon_next/test_init.py`
  Keeps the snapshot fixture aligned with the expanded `AccountSnapshot` dataclass.
- `README.md`
  Moves meter readings into shipped features and narrows the remaining roadmap.

---

### Task 1: Normalize the latest usable meter reading in `AccountSnapshot`

**Files:**
- Modify: `custom_components/eon_next/api.py`
- Modify: `tests/components/eon_next/test_api.py`
- Modify: `tests/components/eon_next/test_sensor.py`
- Modify: `tests/components/eon_next/test_init.py`

- [ ] **Step 1: Write the failing API tests first**

Add the meter-reading fixture helpers and failing tests to `tests/components/eon_next/test_api.py`:

```python
def _agreement_payload_with_meter_readings(*readings: dict[str, Any]) -> dict[str, Any]:
    return {
        "validFrom": "2026-04-01T00:00:00+00:00",
        "validTo": None,
        "meterPoint": {
            "mpan": "0012345678901",
            "unbilledReadings": list(readings),
        },
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


def test_build_account_snapshot_selects_latest_usable_meter_reading() -> None:
    agreement = _agreement_payload_with_meter_readings(
        {
            "readAt": "2026-05-01T11:00:00+00:00",
            "readingSource": "CUSTOMER",
            "source": "self-service",
            "readingType": "actual",
            "registers": [
                {
                    "identifier": "00001",
                    "name": "IMP",
                    "value": "12345.0",
                    "digits": 5,
                    "isQuarantined": False,
                }
            ],
        },
        {
            "readAt": "2026-05-02T11:00:00+00:00",
            "readingSource": "SMART",
            "source": "smart-meter",
            "readingType": "actual",
            "registers": [
                {
                    "identifier": "00001",
                    "name": "IMP",
                    "value": "12346.0",
                    "digits": 5,
                    "isQuarantined": False,
                }
            ],
        },
    )

    snapshot = build_account_snapshot(
        _account_payload(),
        agreement,
        datetime(2026, 5, 2, 12, 0, tzinfo=UTC),
    )

    assert snapshot.latest_meter_reading_kwh == 12346.0
    assert snapshot.latest_meter_reading_at == datetime(2026, 5, 2, 11, 0, tzinfo=UTC)
    assert snapshot.latest_meter_reading_source == "SMART"
    assert snapshot.latest_meter_reading_type == "actual"
    assert snapshot.latest_meter_reading_register_identifier == "00001"
    assert snapshot.latest_meter_reading_register_name == "IMP"
    assert snapshot.latest_meter_reading_register_digits == 5
    assert snapshot.latest_meter_reading_register_is_quarantined is False
    assert snapshot.meter_point_mpan == "0012345678901"


def test_build_account_snapshot_returns_none_when_no_usable_meter_reading_exists() -> None:
    agreement = _agreement_payload_with_meter_readings(
        {
            "readAt": "2026-05-02T11:00:00+00:00",
            "readingSource": "SMART",
            "source": "smart-meter",
            "readingType": "actual",
            "registers": [
                {
                    "identifier": "00001",
                    "name": "IMP",
                    "value": None,
                    "digits": 5,
                    "isQuarantined": False,
                }
            ],
        },
        {
            "readAt": None,
            "readingSource": "CUSTOMER",
            "source": "self-service",
            "readingType": "actual",
            "registers": [
                {
                    "identifier": "00001",
                    "name": "IMP",
                    "value": "12345.0",
                    "digits": 5,
                    "isQuarantined": False,
                }
            ],
        },
    )

    snapshot = build_account_snapshot(
        _account_payload(),
        agreement,
        datetime(2026, 5, 2, 12, 0, tzinfo=UTC),
    )

    assert snapshot.latest_meter_reading_kwh is None
    assert snapshot.latest_meter_reading_at is None
    assert snapshot.latest_meter_reading_source is None
    assert snapshot.latest_meter_reading_type is None
    assert snapshot.latest_meter_reading_register_identifier is None
    assert snapshot.latest_meter_reading_register_name is None
    assert snapshot.latest_meter_reading_register_digits is None
    assert snapshot.latest_meter_reading_register_is_quarantined is None
    assert snapshot.meter_point_mpan == "0012345678901"


def test_build_account_snapshot_raises_when_unbilled_readings_is_not_a_list() -> None:
    agreement = _agreement_payload_with_meter_readings()
    agreement["meterPoint"]["unbilledReadings"] = {"bad": "shape"}

    with pytest.raises(
        EonNextRatesUnsupportedError,
        match="unbilledReadings",
    ):
        build_account_snapshot(
            _account_payload(),
            agreement,
            datetime(2026, 5, 2, 12, 0, tzinfo=UTC),
        )
```

Update the round-trip client payload in the same file to include meter-point data and assert the new snapshot fields:

```python
"meterPoint": {
    "mpan": "0012345678901",
    "unbilledReadings": [
        {
            "readAt": "2026-05-02T11:00:00+00:00",
            "readingSource": "SMART",
            "source": "smart-meter",
            "readingType": "actual",
            "registers": [
                {
                    "identifier": "00001",
                    "name": "IMP",
                    "value": "12346.0",
                    "digits": 5,
                    "isQuarantined": False,
                }
            ],
        }
    ],
},

assert snapshot == AccountSnapshot(
    current_rate_gbp_per_kwh=0.239022,
    next_rate_gbp_per_kwh=0.245,
    next_rate_change_at=datetime(2026, 5, 1, 12, 30, tzinfo=UTC),
    account_number="A-TEST0001",
    current_window_end=datetime(2026, 5, 1, 12, 30, tzinfo=UTC),
    next_window_start=datetime(2026, 5, 1, 12, 30, tzinfo=UTC),
    agreement_valid_from=datetime(2026, 4, 1, 0, 0, tzinfo=UTC),
    agreement_valid_to=datetime(2026, 6, 1, 0, 0, tzinfo=UTC),
    pre_vat_standing_charge_gbp_per_day=0.57143,
    tariff_name="Next Drive Smart V5.2",
    tariff_code="E-TOU-NEXT_DRIVE_SMART_V5_2-N",
    standing_charge_gbp_per_day=0.6000015,
    latest_meter_reading_kwh=12346.0,
    latest_meter_reading_at=datetime(2026, 5, 2, 11, 0, tzinfo=UTC),
    latest_meter_reading_source="SMART",
    latest_meter_reading_type="actual",
    latest_meter_reading_register_identifier="00001",
    latest_meter_reading_register_name="IMP",
    latest_meter_reading_register_digits=5,
    latest_meter_reading_register_is_quarantined=False,
    meter_point_mpan="0012345678901",
)
```

- [ ] **Step 2: Run the new API tests and confirm they fail**

Run:

```bash
python3 -m pytest \
  tests/components/eon_next/test_api.py::test_build_account_snapshot_selects_latest_usable_meter_reading \
  tests/components/eon_next/test_api.py::test_build_account_snapshot_returns_none_when_no_usable_meter_reading_exists \
  tests/components/eon_next/test_api.py::test_build_account_snapshot_raises_when_unbilled_readings_is_not_a_list \
  -q
```

Expected: FAIL because `AccountSnapshot` does not yet expose meter-reading fields and `build_account_snapshot()` does not yet inspect `meterPoint.unbilledReadings`.

- [ ] **Step 3: Extend the query, snapshot model, and meter-reading selector**

Replace `AGREEMENTS_QUERY` in `custom_components/eon_next/api.py` with:

```python
AGREEMENTS_QUERY = """query GetHalfHourlyTariff($accountNumber: String!) {
  account(accountNumber: $accountNumber) {
    number
    electricityAgreements {
      id
      validFrom
      validTo
      meterPoint {
        mpan
        unbilledReadings {
          readAt
          readingSource
          source
          readingType
          registers {
            identifier
            name
            value
            digits
            isQuarantined
          }
        }
      }
      tariff {
        __typename
        ... on HalfHourlyTariff {
          displayName
          tariffCode
          standingCharge
          preVatStandingCharge
          unitRates {
            value
            validFrom
            validTo
          }
        }
      }
    }
  }
}"""
```

Broaden `AccountSnapshot` in the same file to include optional meter-reading fields:

```python
@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    current_rate_gbp_per_kwh: float
    next_rate_gbp_per_kwh: float | None
    next_rate_change_at: datetime | None
    account_number: str
    current_window_end: datetime
    next_window_start: datetime | None
    agreement_valid_from: datetime
    agreement_valid_to: datetime | None
    pre_vat_standing_charge_gbp_per_day: float | None
    tariff_name: str
    tariff_code: str
    standing_charge_gbp_per_day: float
    latest_meter_reading_kwh: float | None
    latest_meter_reading_at: datetime | None
    latest_meter_reading_source: str | None
    latest_meter_reading_type: str | None
    latest_meter_reading_register_identifier: str | None
    latest_meter_reading_register_name: str | None
    latest_meter_reading_register_digits: int | None
    latest_meter_reading_register_is_quarantined: bool | None
    meter_point_mpan: str | None
```

Add the normalization helpers and update `build_account_snapshot()`:

```python
def _parse_meter_reading_value(value: str | None) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _empty_meter_reading_fields(mpan: str | None) -> dict[str, Any]:
    return {
        "latest_meter_reading_kwh": None,
        "latest_meter_reading_at": None,
        "latest_meter_reading_source": None,
        "latest_meter_reading_type": None,
        "latest_meter_reading_register_identifier": None,
        "latest_meter_reading_register_name": None,
        "latest_meter_reading_register_digits": None,
        "latest_meter_reading_register_is_quarantined": None,
        "meter_point_mpan": mpan,
    }


def _latest_meter_reading_fields(meter_point: dict | None) -> dict[str, Any]:
    if meter_point is None:
        return _empty_meter_reading_fields(None)

    mpan = meter_point.get("mpan")
    readings = meter_point.get("unbilledReadings")
    if readings is None:
        return _empty_meter_reading_fields(mpan)
    if not isinstance(readings, list):
        raise EonNextRatesUnsupportedError(
            "Electricity meter point payload missing expected list field: unbilledReadings"
        )

    sorted_readings = sorted(
        readings,
        key=lambda reading: _parse_datetime(reading.get("readAt"))
        or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )

    for reading in sorted_readings:
        read_at = _parse_datetime(reading.get("readAt"))
        if read_at is None:
            continue

        registers = reading.get("registers") or []
        if not isinstance(registers, list):
            continue

        for register in registers:
            value = _parse_meter_reading_value(register.get("value"))
            if value is None:
                continue

            return {
                "latest_meter_reading_kwh": value,
                "latest_meter_reading_at": read_at,
                "latest_meter_reading_source": reading.get("readingSource")
                or reading.get("source"),
                "latest_meter_reading_type": reading.get("readingType"),
                "latest_meter_reading_register_identifier": register.get("identifier"),
                "latest_meter_reading_register_name": register.get("name"),
                "latest_meter_reading_register_digits": register.get("digits"),
                "latest_meter_reading_register_is_quarantined": register.get("isQuarantined"),
                "meter_point_mpan": mpan,
            }

    return _empty_meter_reading_fields(mpan)


def build_account_snapshot(account: dict, agreement: dict, now: datetime) -> AccountSnapshot:
    account_number = account.get("number")
    if account_number is None:
        raise EonNextRatesUnsupportedError(
            "Account payload missing required field(s): number"
        )

    tariff = agreement["tariff"]
    tariff_type = tariff.get("__typename")
    if tariff_type != "HalfHourlyTariff":
        raise EonNextRatesUnsupportedError(
            f"Expected HalfHourlyTariff tariff, got {tariff_type!r}"
        )

    required_fields = ("unitRates", "displayName", "tariffCode", "standingCharge")
    missing_fields = [field for field in required_fields if field not in tariff]
    if missing_fields:
        missing = ", ".join(missing_fields)
        raise EonNextRatesUnsupportedError(
            f"HalfHourlyTariff payload missing required field(s): {missing}"
        )

    current_window = None
    next_window = None
    unit_rates = tariff["unitRates"]
    if not unit_rates:
        raise EonNextRatesUnsupportedError(
            "HalfHourlyTariff payload missing required field(s): unitRates"
        )

    for unit_rate in unit_rates:
        valid_from = _parse_datetime(unit_rate["validFrom"])
        valid_to = _parse_datetime(unit_rate.get("validTo"))

        if valid_from <= now and valid_to is None:
            raise EonNextRatesUnsupportedError(
                "Current HalfHourlyTariff window is missing validTo"
            )

        if valid_from <= now < valid_to:
            current_window = unit_rate
            next_window = min(
                (
                    candidate
                    for candidate in unit_rates
                    if _parse_datetime(candidate["validFrom"]) >= valid_to
                ),
                key=lambda candidate: _parse_datetime(candidate["validFrom"]),
                default=None,
            )
            break

    if current_window is None:
        raise EonNextRatesUnsupportedError(
            f"No current HalfHourlyTariff window found for {now.isoformat()}"
        )

    current_window_end = _parse_datetime(current_window["validTo"])
    if current_window_end is None:
        raise EonNextRatesUnsupportedError(
            "Current HalfHourlyTariff window is missing validTo"
        )

    next_window_start = None
    if next_window is not None:
        next_window_start = _parse_datetime(next_window["validFrom"])

    if next_window is not None and next_window_start != current_window_end:
        raise EonNextRatesUnsupportedError(
            "Expected contiguous HalfHourlyTariff windows, "
            f"got gap between {current_window['validTo']} and {next_window['validFrom']}"
        )

    agreement_valid_from = _parse_datetime(agreement.get("validFrom"))
    if agreement_valid_from is None:
        raise EonNextRatesUnsupportedError(
            "Active agreement payload missing required field(s): validFrom"
        )

    meter_reading_fields = _latest_meter_reading_fields(agreement.get("meterPoint"))

    return AccountSnapshot(
        current_rate_gbp_per_kwh=_pence_to_gbp(current_window["value"]),
        next_rate_gbp_per_kwh=(
            _pence_to_gbp(next_window["value"]) if next_window is not None else None
        ),
        next_rate_change_at=next_window_start,
        account_number=account_number,
        current_window_end=current_window_end,
        next_window_start=next_window_start,
        agreement_valid_from=agreement_valid_from,
        agreement_valid_to=_parse_datetime(agreement.get("validTo")),
        pre_vat_standing_charge_gbp_per_day=_optional_pence_to_gbp(
            tariff.get("preVatStandingCharge")
        ),
        tariff_name=tariff["displayName"],
        tariff_code=tariff["tariffCode"],
        standing_charge_gbp_per_day=_pence_to_gbp(tariff["standingCharge"]),
        latest_meter_reading_kwh=meter_reading_fields["latest_meter_reading_kwh"],
        latest_meter_reading_at=meter_reading_fields["latest_meter_reading_at"],
        latest_meter_reading_source=meter_reading_fields["latest_meter_reading_source"],
        latest_meter_reading_type=meter_reading_fields["latest_meter_reading_type"],
        latest_meter_reading_register_identifier=meter_reading_fields[
            "latest_meter_reading_register_identifier"
        ],
        latest_meter_reading_register_name=meter_reading_fields[
            "latest_meter_reading_register_name"
        ],
        latest_meter_reading_register_digits=meter_reading_fields[
            "latest_meter_reading_register_digits"
        ],
        latest_meter_reading_register_is_quarantined=meter_reading_fields[
            "latest_meter_reading_register_is_quarantined"
        ],
        meter_point_mpan=meter_reading_fields["meter_point_mpan"],
    )
```

Update the snapshot fixtures in `tests/components/eon_next/test_sensor.py` and `tests/components/eon_next/test_init.py` so they include meter-reading fields:

```python
return AccountSnapshot(
    current_rate_gbp_per_kwh=0.239022,
    next_rate_gbp_per_kwh=0.245,
    next_rate_change_at=datetime(2026, 5, 1, 12, 30, tzinfo=UTC),
    account_number="A-TEST0001",
    current_window_end=datetime(2026, 5, 1, 12, 30, tzinfo=UTC),
    next_window_start=datetime(2026, 5, 1, 12, 30, tzinfo=UTC),
    agreement_valid_from=datetime(2026, 4, 1, 0, 0, tzinfo=UTC),
    agreement_valid_to=None,
    pre_vat_standing_charge_gbp_per_day=0.57143,
    tariff_name="Next Drive Smart V5.2",
    tariff_code="E-TOU-NEXT_DRIVE_SMART_V5_2-N",
    standing_charge_gbp_per_day=0.6000015,
    latest_meter_reading_kwh=12346.0,
    latest_meter_reading_at=datetime(2026, 5, 2, 11, 0, tzinfo=UTC),
    latest_meter_reading_source="SMART",
    latest_meter_reading_type="actual",
    latest_meter_reading_register_identifier="00001",
    latest_meter_reading_register_name="IMP",
    latest_meter_reading_register_digits=5,
    latest_meter_reading_register_is_quarantined=False,
    meter_point_mpan="0012345678901",
)
```

- [ ] **Step 4: Run the Task 1 regression set**

Run:

```bash
python3 -m pytest \
  tests/components/eon_next/test_api.py::test_build_account_snapshot_selects_latest_usable_meter_reading \
  tests/components/eon_next/test_api.py::test_build_account_snapshot_returns_none_when_no_usable_meter_reading_exists \
  tests/components/eon_next/test_api.py::test_build_account_snapshot_raises_when_unbilled_readings_is_not_a_list \
  tests/components/eon_next/test_api.py::test_client_discovers_account_and_fetches_account_snapshot \
  tests/components/eon_next/test_sensor.py::test_current_rate_sensor_exposes_value_unit_and_attributes \
  tests/components/eon_next/test_init.py::test_async_setup_entry_creates_client_and_stores_runtime_objects \
  -q
```

Expected: PASS.

- [ ] **Step 5: Commit the widened snapshot model**

```bash
git add custom_components/eon_next/api.py tests/components/eon_next/test_api.py tests/components/eon_next/test_sensor.py tests/components/eon_next/test_init.py
git commit -m "feat: normalize latest meter reading data"
```

---

### Task 2: Expose meter-reading entities and attributes

**Files:**
- Modify: `custom_components/eon_next/const.py`
- Modify: `custom_components/eon_next/sensor.py`
- Modify: `tests/components/eon_next/test_sensor.py`

- [ ] **Step 1: Write the failing sensor tests first**

Update `tests/components/eon_next/test_sensor.py` with a helper and the new meter-reading assertions:

```python
def _entity_by_suffix(entities, suffix: str):
    return next(entity for entity in entities if entity.unique_id == f"entry-123_{suffix}")


@pytest.mark.asyncio
async def test_async_setup_entry_uses_stored_coordinator(sensor_module, snapshot) -> None:
    hass = sensor_module.HomeAssistant()
    coordinator = _DummyCoordinator(snapshot)
    hass.data = {DOMAIN: {"entry-123": {"coordinator": coordinator}}}
    entry = sensor_module.ConfigEntry(entry_id="entry-123")
    added_entities = []

    await sensor_module.async_setup_entry(
        hass,
        entry,
        lambda entities: added_entities.extend(entities),
    )

    assert len(added_entities) == 8
    assert added_entities[0].coordinator is coordinator


def test_latest_meter_reading_sensor_exposes_value_unit_and_attributes(
    sensor_module, snapshot
) -> None:
    entities = sensor_module._build_sensors("entry-123", _DummyCoordinator(snapshot))
    meter_sensor = _entity_by_suffix(entities, "latest_meter_reading")

    assert meter_sensor.name == "E.ON Latest Meter Reading"
    assert meter_sensor.native_value == 12346.0
    assert meter_sensor.native_unit_of_measurement == "kWh"
    assert meter_sensor.extra_state_attributes == {
        "meter_point_mpan": "0012345678901",
        "latest_meter_reading_source": "SMART",
        "latest_meter_reading_type": "actual",
        "latest_meter_reading_register_identifier": "00001",
        "latest_meter_reading_register_name": "IMP",
        "latest_meter_reading_register_digits": 5,
        "latest_meter_reading_register_is_quarantined": False,
    }


def test_latest_meter_reading_timestamp_sensor_exposes_expected_datetime(
    sensor_module, snapshot
) -> None:
    entities = sensor_module._build_sensors("entry-123", _DummyCoordinator(snapshot))
    timestamp_sensor = _entity_by_suffix(entities, "latest_meter_reading_at")

    assert timestamp_sensor.name == "E.ON Latest Meter Reading Time"
    assert timestamp_sensor.native_value == datetime(2026, 5, 2, 11, 0, tzinfo=UTC)
```

- [ ] **Step 2: Run the new sensor tests and confirm they fail**

Run:

```bash
python3 -m pytest \
  tests/components/eon_next/test_sensor.py::test_latest_meter_reading_sensor_exposes_value_unit_and_attributes \
  tests/components/eon_next/test_sensor.py::test_latest_meter_reading_timestamp_sensor_exposes_expected_datetime \
  -q
```

Expected: FAIL because `const.py` does not yet define the meter-reading attributes and `sensor.py` still exposes six sensors.

- [ ] **Step 3: Add the new constants and description-driven meter sensors**

Extend `custom_components/eon_next/const.py` with:

```python
ATTR_ACCOUNT_NUMBER = "account_number"
ATTR_TARIFF_NAME = "tariff_name"
ATTR_TARIFF_CODE = "tariff_code"
ATTR_STANDING_CHARGE_GBP_PER_DAY = "standing_charge_gbp_per_day"
ATTR_PRE_VAT_STANDING_CHARGE_GBP_PER_DAY = "pre_vat_standing_charge_gbp_per_day"
ATTR_CURRENT_WINDOW_END = "current_window_end"
ATTR_NEXT_WINDOW_START = "next_window_start"
ATTR_AGREEMENT_VALID_FROM = "agreement_valid_from"
ATTR_AGREEMENT_VALID_TO = "agreement_valid_to"
ATTR_METER_POINT_MPAN = "meter_point_mpan"
ATTR_LATEST_METER_READING_SOURCE = "latest_meter_reading_source"
ATTR_LATEST_METER_READING_TYPE = "latest_meter_reading_type"
ATTR_LATEST_METER_READING_REGISTER_IDENTIFIER = "latest_meter_reading_register_identifier"
ATTR_LATEST_METER_READING_REGISTER_NAME = "latest_meter_reading_register_name"
ATTR_LATEST_METER_READING_REGISTER_DIGITS = "latest_meter_reading_register_digits"
ATTR_LATEST_METER_READING_REGISTER_IS_QUARANTINED = "latest_meter_reading_register_is_quarantined"
```

Replace `custom_components/eon_next/sensor.py` with the description-driven attribute mapping below:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import AccountSnapshot
from .const import (
    ATTR_ACCOUNT_NUMBER,
    ATTR_AGREEMENT_VALID_FROM,
    ATTR_AGREEMENT_VALID_TO,
    ATTR_CURRENT_WINDOW_END,
    ATTR_LATEST_METER_READING_REGISTER_DIGITS,
    ATTR_LATEST_METER_READING_REGISTER_IDENTIFIER,
    ATTR_LATEST_METER_READING_REGISTER_IS_QUARANTINED,
    ATTR_LATEST_METER_READING_REGISTER_NAME,
    ATTR_LATEST_METER_READING_SOURCE,
    ATTR_LATEST_METER_READING_TYPE,
    ATTR_METER_POINT_MPAN,
    ATTR_NEXT_WINDOW_START,
    ATTR_PRE_VAT_STANDING_CHARGE_GBP_PER_DAY,
    ATTR_STANDING_CHARGE_GBP_PER_DAY,
    ATTR_TARIFF_CODE,
    ATTR_TARIFF_NAME,
    DOMAIN,
)
from .coordinator import EonNextRatesCoordinator

RATE_UNIT = "GBP/kWh"
CHARGE_UNIT = "GBP/day"
READING_UNIT = "kWh"


@dataclass(frozen=True, kw_only=True)
class EonRateSensorDescription(SensorEntityDescription):
    value_attr: str
    unique_id_suffix: str
    extra_attributes: dict[str, str] | None = None


SENSOR_DESCRIPTIONS = (
    EonRateSensorDescription(
        key="current_import_rate",
        name="E.ON Current Import Rate",
        native_unit_of_measurement=RATE_UNIT,
        value_attr="current_rate_gbp_per_kwh",
        unique_id_suffix="current_import_rate",
        extra_attributes={
            ATTR_ACCOUNT_NUMBER: "account_number",
            ATTR_TARIFF_NAME: "tariff_name",
            ATTR_TARIFF_CODE: "tariff_code",
            ATTR_STANDING_CHARGE_GBP_PER_DAY: "standing_charge_gbp_per_day",
            ATTR_PRE_VAT_STANDING_CHARGE_GBP_PER_DAY: "pre_vat_standing_charge_gbp_per_day",
            ATTR_CURRENT_WINDOW_END: "current_window_end",
            ATTR_NEXT_WINDOW_START: "next_window_start",
            ATTR_AGREEMENT_VALID_FROM: "agreement_valid_from",
            ATTR_AGREEMENT_VALID_TO: "agreement_valid_to",
        },
    ),
    EonRateSensorDescription(
        key="next_import_rate",
        name="E.ON Next Import Rate",
        native_unit_of_measurement=RATE_UNIT,
        value_attr="next_rate_gbp_per_kwh",
        unique_id_suffix="next_import_rate",
    ),
    EonRateSensorDescription(
        key="next_rate_change_at",
        name="E.ON Next Rate Change",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_attr="next_rate_change_at",
        unique_id_suffix="next_rate_change_at",
    ),
    EonRateSensorDescription(
        key="standing_charge",
        name="E.ON Standing Charge",
        native_unit_of_measurement=CHARGE_UNIT,
        value_attr="standing_charge_gbp_per_day",
        unique_id_suffix="standing_charge",
    ),
    EonRateSensorDescription(
        key="standing_charge_ex_vat",
        name="E.ON Standing Charge Ex VAT",
        native_unit_of_measurement=CHARGE_UNIT,
        value_attr="pre_vat_standing_charge_gbp_per_day",
        unique_id_suffix="standing_charge_ex_vat",
    ),
    EonRateSensorDescription(
        key="account_number",
        name="E.ON Account Number",
        value_attr="account_number",
        unique_id_suffix="account_number",
    ),
    EonRateSensorDescription(
        key="latest_meter_reading",
        name="E.ON Latest Meter Reading",
        native_unit_of_measurement=READING_UNIT,
        value_attr="latest_meter_reading_kwh",
        unique_id_suffix="latest_meter_reading",
        extra_attributes={
            ATTR_METER_POINT_MPAN: "meter_point_mpan",
            ATTR_LATEST_METER_READING_SOURCE: "latest_meter_reading_source",
            ATTR_LATEST_METER_READING_TYPE: "latest_meter_reading_type",
            ATTR_LATEST_METER_READING_REGISTER_IDENTIFIER: "latest_meter_reading_register_identifier",
            ATTR_LATEST_METER_READING_REGISTER_NAME: "latest_meter_reading_register_name",
            ATTR_LATEST_METER_READING_REGISTER_DIGITS: "latest_meter_reading_register_digits",
            ATTR_LATEST_METER_READING_REGISTER_IS_QUARANTINED: "latest_meter_reading_register_is_quarantined",
        },
    ),
    EonRateSensorDescription(
        key="latest_meter_reading_at",
        name="E.ON Latest Meter Reading Time",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_attr="latest_meter_reading_at",
        unique_id_suffix="latest_meter_reading_at",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: EonNextRatesCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(_build_sensors(entry.entry_id, coordinator))


def _build_sensors(
    entry_id: str, coordinator: EonNextRatesCoordinator
) -> list[EonNextRatesSensor]:
    return [
        EonNextRatesSensor(entry_id, coordinator, description)
        for description in SENSOR_DESCRIPTIONS
    ]


class EonNextRatesSensor(CoordinatorEntity, SensorEntity):
    entity_description: EonRateSensorDescription

    def __init__(
        self,
        entry_id: str,
        coordinator: EonNextRatesCoordinator,
        description: EonRateSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry_id}_{description.unique_id_suffix}"

    @property
    def native_value(self) -> float | str | datetime | None:
        snapshot = self.coordinator.data
        if snapshot is None:
            return None

        return getattr(snapshot, self.entity_description.value_attr)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        mapping = self.entity_description.extra_attributes
        if mapping is None:
            return None

        snapshot: AccountSnapshot | None = self.coordinator.data
        if snapshot is None:
            return None

        return {
            attr_name: getattr(snapshot, attr_field)
            for attr_name, attr_field in mapping.items()
        }
```

- [ ] **Step 4: Run the full sensor test file**

Run:

```bash
python3 -m pytest tests/components/eon_next/test_sensor.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit the meter-reading entities**

```bash
git add custom_components/eon_next/const.py custom_components/eon_next/sensor.py tests/components/eon_next/test_sensor.py
git commit -m "feat: add latest meter reading sensors"
```

---

### Task 3: Update the README and verify the whole slice

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Move meter readings into the shipped feature list**

Replace the feature lists in `README.md` with:

```markdown
## Current features

- Live VAT-inclusive import rate
- Next import rate when E.ON publishes a later tariff window
- Next rate change timestamp when available
- Standing charge sensors including pre-VAT standing charge
- Active tariff and account metadata, including account number and agreement window attributes
- Latest electricity meter reading and reading timestamp when available

## Planned features

- EV / charger / smart-tariff related entities
- Historical cost counters for Prometheus and Grafana
```

- [ ] **Step 2: Run the full repository verification command**

Run:

```bash
./scripts/check.sh
```

Expected: PASS with JSON checks, `compileall`, `pytest`, and `ruff` all green.

- [ ] **Step 3: Commit the README update**

```bash
git add README.md
git commit -m "docs: update README for meter readings"
```
