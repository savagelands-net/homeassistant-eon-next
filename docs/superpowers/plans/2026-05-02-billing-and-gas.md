# E.ON Next Billing And Gas Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add account-level billing sensors plus bounded gas support while preserving the existing electricity entities and failure behavior.

**Architecture:** Keep the existing single config entry, single coordinator, and single sensor platform. Broaden `AccountSnapshot` in `api.py` into a whole-account model containing electricity, billing, and optional gas fields, then expose the new data through description-driven sensors in `sensor.py`. Billing and gas are best-effort data: they resolve to `None` instead of blocking the working electricity path.

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
  Widen the account query, normalize billing fields, select an active gas agreement, normalize gas tariff fields, and select the latest usable gas meter reading.
- `custom_components/eon_next/const.py`
  Define the new attribute names for gas tariff metadata and gas meter-reading metadata.
- `custom_components/eon_next/sensor.py`
  Extend the description-driven platform with billing and gas sensors while keeping the existing electricity entities unchanged.
- `tests/components/eon_next/test_api.py`
  Prove billing extraction, optional gas handling, gas meter-reading selection, and electricity non-regression.
- `tests/components/eon_next/test_sensor.py`
  Prove the widened entity set and `None` behavior for absent optional billing/gas data.
- `tests/components/eon_next/test_init.py`
  Keep the shared `AccountSnapshot` fixture aligned with the broader dataclass.
- `README.md`
  Move billing and gas into shipped features and narrow the remaining roadmap.

---

### Task 1: Broaden `AccountSnapshot` for billing and optional gas

**Files:**
- Modify: `custom_components/eon_next/api.py`
- Modify: `tests/components/eon_next/test_api.py`
- Modify: `tests/components/eon_next/test_sensor.py`
- Modify: `tests/components/eon_next/test_init.py`

- [ ] **Step 1: Write the failing API tests first**

Update `_account_payload()` and add helpers in `tests/components/eon_next/test_api.py`:

```python
def _account_payload(
    account_number: str = "A-TEST0001",
    *,
    balance: int | None = None,
    bills: dict[str, Any] | None = None,
    gas_agreements: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"number": account_number}
    if balance is not None:
        payload["balance"] = balance
    if bills is not None:
        payload["bills"] = bills
    if gas_agreements is not None:
        payload["gasAgreements"] = gas_agreements
    return payload


def _bills_payload(*nodes: dict[str, Any]) -> dict[str, Any]:
    return {
        "edges": [{"node": node} for node in nodes],
    }


def _statement_node(
    *,
    closing_balance: int = 9876,
    charges_gross_total: int = 5432,
) -> dict[str, Any]:
    return {
        "__typename": "StatementType",
        "billType": "STATEMENT",
        "issuedDate": "2026-05-02",
        "closingBalance": closing_balance,
        "totalCharges": {"grossTotal": charges_gross_total},
    }


def _gas_agreement_payload_with_meter_readings(*readings: dict[str, Any]) -> dict[str, Any]:
    return {
        "validFrom": "2026-04-01T00:00:00+00:00",
        "validTo": None,
        "meterPoint": {
            "mprn": "1234567890",
            "unbilledReadings": list(readings),
        },
        "tariff": {
            "displayName": "Next Flex Gas",
            "tariffCode": "G-1R-NEXT_FLEX_GAS",
            "standingCharge": 31.2,
            "preVatStandingCharge": 29.7,
            "unitRate": 6.543,
            "preVatUnitRate": 6.231,
        },
    }
```

Add these failing tests to the same file:

```python
def test_build_account_snapshot_includes_billing_and_gas_fields() -> None:
    account = _account_payload(
        balance=12345,
        bills=_bills_payload(_statement_node()),
        gas_agreements=[
            _gas_agreement_payload_with_meter_readings(
                {
                    "readAt": "2026-05-02T13:00:00+00:00",
                    "readingSource": "CUSTOMER",
                    "source": "self-service",
                    "readingType": "actual",
                    "registers": [
                        {
                            "identifier": "GAS-001",
                            "name": "GAS",
                            "value": "4567.0",
                            "digits": 4,
                            "isQuarantined": False,
                        }
                    ],
                }
            )
        ],
    )
    electricity_agreement = _agreement_payload_with_meter_readings()

    snapshot = build_account_snapshot(
        account,
        electricity_agreement,
        datetime(2026, 5, 2, 14, 0, tzinfo=UTC),
    )

    assert snapshot.current_account_balance_gbp == 123.45
    assert snapshot.latest_statement_closing_balance_gbp == 98.76
    assert snapshot.latest_statement_charges_gbp == 54.32
    assert snapshot.gas_rate_gbp_per_kwh == 0.06543
    assert snapshot.gas_pre_vat_rate_gbp_per_kwh == 0.06231
    assert snapshot.gas_tariff_name == "Next Flex Gas"
    assert snapshot.gas_tariff_code == "G-1R-NEXT_FLEX_GAS"
    assert snapshot.gas_standing_charge_gbp_per_day == 0.312
    assert snapshot.gas_pre_vat_standing_charge_gbp_per_day == 0.297
    assert snapshot.gas_agreement_valid_from == datetime(2026, 4, 1, 0, 0, tzinfo=UTC)
    assert snapshot.gas_agreement_valid_to is None
    assert snapshot.latest_gas_meter_reading_value == 4567.0
    assert snapshot.latest_gas_meter_reading_at == datetime(2026, 5, 2, 13, 0, tzinfo=UTC)
    assert snapshot.latest_gas_meter_reading_source == "CUSTOMER"
    assert snapshot.latest_gas_meter_reading_type == "actual"
    assert snapshot.latest_gas_meter_reading_register_identifier == "GAS-001"
    assert snapshot.latest_gas_meter_reading_register_name == "GAS"
    assert snapshot.latest_gas_meter_reading_register_digits == 4
    assert snapshot.latest_gas_meter_reading_register_is_quarantined is False
    assert snapshot.gas_meter_point_mprn == "1234567890"


def test_build_account_snapshot_returns_none_for_optional_billing_and_gas_fields_when_absent() -> None:
    snapshot = build_account_snapshot(
        _account_payload(),
        _agreement_payload_with_meter_readings(),
        datetime(2026, 5, 2, 14, 0, tzinfo=UTC),
    )

    assert snapshot.current_account_balance_gbp is None
    assert snapshot.latest_statement_closing_balance_gbp is None
    assert snapshot.latest_statement_charges_gbp is None
    assert snapshot.gas_rate_gbp_per_kwh is None
    assert snapshot.gas_pre_vat_rate_gbp_per_kwh is None
    assert snapshot.gas_tariff_name is None
    assert snapshot.gas_tariff_code is None
    assert snapshot.gas_standing_charge_gbp_per_day is None
    assert snapshot.gas_pre_vat_standing_charge_gbp_per_day is None
    assert snapshot.gas_agreement_valid_from is None
    assert snapshot.gas_agreement_valid_to is None
    assert snapshot.latest_gas_meter_reading_value is None
    assert snapshot.latest_gas_meter_reading_at is None
    assert snapshot.latest_gas_meter_reading_source is None
    assert snapshot.latest_gas_meter_reading_type is None
    assert snapshot.latest_gas_meter_reading_register_identifier is None
    assert snapshot.latest_gas_meter_reading_register_name is None
    assert snapshot.latest_gas_meter_reading_register_digits is None
    assert snapshot.latest_gas_meter_reading_register_is_quarantined is None
    assert snapshot.gas_meter_point_mprn is None


def test_build_account_snapshot_returns_none_for_latest_statement_fields_when_latest_bill_is_not_a_statement() -> None:
    account = _account_payload(
        balance=12345,
        bills=_bills_payload(
            {
                "__typename": "InvoiceType",
                "billType": "INVOICE",
                "issuedDate": "2026-05-02",
            }
        ),
    )

    snapshot = build_account_snapshot(
        account,
        _agreement_payload_with_meter_readings(),
        datetime(2026, 5, 2, 14, 0, tzinfo=UTC),
    )

    assert snapshot.current_account_balance_gbp == 123.45
    assert snapshot.latest_statement_closing_balance_gbp is None
    assert snapshot.latest_statement_charges_gbp is None


def test_build_account_snapshot_returns_none_for_malformed_optional_gas_meter_payload() -> None:
    account = _account_payload(
        gas_agreements=[
            {
                **_gas_agreement_payload_with_meter_readings(),
                "meterPoint": {"mprn": "1234567890", "unbilledReadings": {"bad": "shape"}},
            }
        ]
    )

    snapshot = build_account_snapshot(
        account,
        _agreement_payload_with_meter_readings(),
        datetime(2026, 5, 2, 14, 0, tzinfo=UTC),
    )

    assert snapshot.gas_rate_gbp_per_kwh == 0.06543
    assert snapshot.gas_standing_charge_gbp_per_day == 0.312
    assert snapshot.latest_gas_meter_reading_value is None
    assert snapshot.latest_gas_meter_reading_at is None
    assert snapshot.gas_meter_point_mprn == "1234567890"
```

Extend `test_client_discovers_account_and_fetches_account_snapshot()` so the account payload includes billing and gas data, then add these assertions after the existing electricity assertions:

```python
"balance": 12345,
"bills": _bills_payload(_statement_node()),
"gasAgreements": [
    _gas_agreement_payload_with_meter_readings(
        {
            "readAt": "2026-05-02T13:00:00+00:00",
            "readingSource": "CUSTOMER",
            "source": "self-service",
            "readingType": "actual",
            "registers": [
                {
                    "identifier": "GAS-001",
                    "name": "GAS",
                    "value": "4567.0",
                    "digits": 4,
                    "isQuarantined": False,
                }
            ],
        }
    )
],

assert snapshot.current_account_balance_gbp == 123.45
assert snapshot.latest_statement_closing_balance_gbp == 98.76
assert snapshot.latest_statement_charges_gbp == 54.32
assert snapshot.gas_rate_gbp_per_kwh == 0.06543
assert snapshot.gas_standing_charge_gbp_per_day == 0.312
assert snapshot.latest_gas_meter_reading_value == 4567.0
assert snapshot.latest_gas_meter_reading_at == datetime(2026, 5, 2, 13, 0, tzinfo=UTC)
assert snapshot.gas_meter_point_mprn == "1234567890"
```

Update the `AccountSnapshot(...)` fixtures in `tests/components/eon_next/test_sensor.py` and `tests/components/eon_next/test_init.py` to include these new fields:

```python
current_account_balance_gbp=123.45,
latest_statement_closing_balance_gbp=98.76,
latest_statement_charges_gbp=54.32,
gas_rate_gbp_per_kwh=0.06543,
gas_pre_vat_rate_gbp_per_kwh=0.06231,
gas_tariff_name="Next Flex Gas",
gas_tariff_code="G-1R-NEXT_FLEX_GAS",
gas_standing_charge_gbp_per_day=0.312,
gas_pre_vat_standing_charge_gbp_per_day=0.297,
gas_agreement_valid_from=datetime(2026, 4, 1, 0, 0, tzinfo=UTC),
gas_agreement_valid_to=None,
latest_gas_meter_reading_value=4567.0,
latest_gas_meter_reading_at=datetime(2026, 5, 2, 13, 0, tzinfo=UTC),
latest_gas_meter_reading_source="CUSTOMER",
latest_gas_meter_reading_type="actual",
latest_gas_meter_reading_register_identifier="GAS-001",
latest_gas_meter_reading_register_name="GAS",
latest_gas_meter_reading_register_digits=4,
latest_gas_meter_reading_register_is_quarantined=False,
gas_meter_point_mprn="1234567890",
```

- [ ] **Step 2: Run the new API tests and confirm they fail**

Run:

```bash
./.venv/bin/python -m pytest \
  tests/components/eon_next/test_api.py::test_build_account_snapshot_includes_billing_and_gas_fields \
  tests/components/eon_next/test_api.py::test_build_account_snapshot_returns_none_for_optional_billing_and_gas_fields_when_absent \
  tests/components/eon_next/test_api.py::test_build_account_snapshot_returns_none_for_latest_statement_fields_when_latest_bill_is_not_a_statement \
  tests/components/eon_next/test_api.py::test_build_account_snapshot_returns_none_for_malformed_optional_gas_meter_payload \
  -q
```

Expected: FAIL because `AGREEMENTS_QUERY`, `AccountSnapshot`, and `build_account_snapshot()` do not yet include billing and gas fields.

- [ ] **Step 3: Widen the account query, snapshot model, and billing/gas helpers**

Replace `AGREEMENTS_QUERY` in `custom_components/eon_next/api.py` with:

```python
AGREEMENTS_QUERY = """query GetHalfHourlyTariff($accountNumber: String!) {
  account(accountNumber: $accountNumber) {
    number
    balance
    bills(last: 1, orderBy: ISSUED_DATE_DESC) {
      edges {
        node {
          __typename
          billType
          issuedDate
          ... on StatementType {
            closingBalance
            totalCharges {
              grossTotal
            }
          }
        }
      }
    }
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
    gasAgreements {
      id
      validFrom
      validTo
      meterPoint {
        mprn
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
        displayName
        tariffCode
        standingCharge
        preVatStandingCharge
        unitRate
        preVatUnitRate
      }
    }
  }
}"""
```

Replace `AccountSnapshot` in the same file with:

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
    latest_meter_reading_kwh: float | None = None
    latest_meter_reading_at: datetime | None = None
    latest_meter_reading_source: str | None = None
    latest_meter_reading_type: str | None = None
    latest_meter_reading_register_identifier: str | None = None
    latest_meter_reading_register_name: str | None = None
    latest_meter_reading_register_digits: int | None = None
    latest_meter_reading_register_is_quarantined: bool | None = None
    meter_point_mpan: str | None = None
    current_account_balance_gbp: float | None = None
    latest_statement_closing_balance_gbp: float | None = None
    latest_statement_charges_gbp: float | None = None
    gas_rate_gbp_per_kwh: float | None = None
    gas_pre_vat_rate_gbp_per_kwh: float | None = None
    gas_tariff_name: str | None = None
    gas_tariff_code: str | None = None
    gas_standing_charge_gbp_per_day: float | None = None
    gas_pre_vat_standing_charge_gbp_per_day: float | None = None
    gas_agreement_valid_from: datetime | None = None
    gas_agreement_valid_to: datetime | None = None
    latest_gas_meter_reading_value: float | None = None
    latest_gas_meter_reading_at: datetime | None = None
    latest_gas_meter_reading_source: str | None = None
    latest_gas_meter_reading_type: str | None = None
    latest_gas_meter_reading_register_identifier: str | None = None
    latest_gas_meter_reading_register_name: str | None = None
    latest_gas_meter_reading_register_digits: int | None = None
    latest_gas_meter_reading_register_is_quarantined: bool | None = None
    gas_meter_point_mprn: str | None = None
```

Add these helpers below `_optional_pence_to_gbp`:

```python
def _optional_minor_units_to_gbp(value: int | None) -> float | None:
    if value is None:
        return None

    return value / 100


def _billing_fields(account: dict) -> dict[str, Any]:
    balance = account.get("balance")
    bills = account.get("bills")
    statement = None

    if isinstance(bills, dict):
        edges = bills.get("edges")
        if isinstance(edges, list) and edges:
            first_edge = edges[0]
            if isinstance(first_edge, dict):
                node = first_edge.get("node")
                if isinstance(node, dict) and node.get("__typename") == "StatementType":
                    statement = node

    total_charges = statement.get("totalCharges") if isinstance(statement, dict) else None
    gross_total = total_charges.get("grossTotal") if isinstance(total_charges, dict) else None

    return {
        "current_account_balance_gbp": _optional_minor_units_to_gbp(
            balance if isinstance(balance, int) else None
        ),
        "latest_statement_closing_balance_gbp": _optional_minor_units_to_gbp(
            statement.get("closingBalance") if isinstance(statement, dict) else None
        ),
        "latest_statement_charges_gbp": _optional_minor_units_to_gbp(
            gross_total if isinstance(gross_total, int) else None
        ),
    }


def _empty_gas_fields(mprn: str | None = None) -> dict[str, Any]:
    return {
        "gas_rate_gbp_per_kwh": None,
        "gas_pre_vat_rate_gbp_per_kwh": None,
        "gas_tariff_name": None,
        "gas_tariff_code": None,
        "gas_standing_charge_gbp_per_day": None,
        "gas_pre_vat_standing_charge_gbp_per_day": None,
        "gas_agreement_valid_from": None,
        "gas_agreement_valid_to": None,
        "latest_gas_meter_reading_value": None,
        "latest_gas_meter_reading_at": None,
        "latest_gas_meter_reading_source": None,
        "latest_gas_meter_reading_type": None,
        "latest_gas_meter_reading_register_identifier": None,
        "latest_gas_meter_reading_register_name": None,
        "latest_gas_meter_reading_register_digits": None,
        "latest_gas_meter_reading_register_is_quarantined": None,
        "gas_meter_point_mprn": mprn,
    }


def select_active_gas_agreement(account: dict, now: datetime) -> dict | None:
    gas_agreements = account.get("gasAgreements")
    if not isinstance(gas_agreements, list):
        return None

    for agreement in gas_agreements:
        if not isinstance(agreement, dict):
            continue

        valid_from = _parse_datetime(agreement.get("validFrom"))
        valid_to = _parse_datetime(agreement.get("validTo"))
        tariff = agreement.get("tariff")

        if valid_from is None or not isinstance(tariff, dict):
            continue

        if valid_from <= now and (valid_to is None or now < valid_to):
            return agreement

    return None


def _latest_gas_meter_reading_fields(meter_point: dict | None) -> dict[str, Any]:
    if not isinstance(meter_point, dict):
        return _empty_gas_fields()

    mprn = meter_point.get("mprn")
    readings = meter_point.get("unbilledReadings")
    if not isinstance(readings, list):
        return _empty_gas_fields(mprn)

    sorted_readings = sorted(
        readings,
        key=lambda reading: _parse_datetime(reading.get("readAt"))
        if isinstance(reading, dict)
        else datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )

    for reading in sorted_readings:
        if not isinstance(reading, dict):
            continue

        read_at = _parse_datetime(reading.get("readAt"))
        if read_at is None:
            continue

        registers = reading.get("registers")
        if not isinstance(registers, list):
            continue

        for register in registers:
            if not isinstance(register, dict):
                continue

            value = _parse_meter_reading_value(register.get("value"))
            if value is None:
                continue

            return {
                "latest_gas_meter_reading_value": value,
                "latest_gas_meter_reading_at": read_at,
                "latest_gas_meter_reading_source": reading.get("readingSource")
                or reading.get("source"),
                "latest_gas_meter_reading_type": reading.get("readingType"),
                "latest_gas_meter_reading_register_identifier": register.get("identifier"),
                "latest_gas_meter_reading_register_name": register.get("name"),
                "latest_gas_meter_reading_register_digits": register.get("digits"),
                "latest_gas_meter_reading_register_is_quarantined": register.get(
                    "isQuarantined"
                ),
                "gas_meter_point_mprn": mprn,
            }

    return _empty_gas_fields(mprn)


def _gas_fields(account: dict, now: datetime) -> dict[str, Any]:
    agreement = select_active_gas_agreement(account, now)
    if agreement is None:
        return _empty_gas_fields()

    tariff = agreement.get("tariff")
    if not isinstance(tariff, dict):
        return _empty_gas_fields()

    meter_fields = _latest_gas_meter_reading_fields(agreement.get("meterPoint"))

    return {
        "gas_rate_gbp_per_kwh": _optional_pence_to_gbp(tariff.get("unitRate")),
        "gas_pre_vat_rate_gbp_per_kwh": _optional_pence_to_gbp(
            tariff.get("preVatUnitRate")
        ),
        "gas_tariff_name": tariff.get("displayName"),
        "gas_tariff_code": tariff.get("tariffCode"),
        "gas_standing_charge_gbp_per_day": _optional_pence_to_gbp(
            tariff.get("standingCharge")
        ),
        "gas_pre_vat_standing_charge_gbp_per_day": _optional_pence_to_gbp(
            tariff.get("preVatStandingCharge")
        ),
        "gas_agreement_valid_from": _parse_datetime(agreement.get("validFrom")),
        "gas_agreement_valid_to": _parse_datetime(agreement.get("validTo")),
        **meter_fields,
    }
```

Update `build_account_snapshot(account, agreement, now)` so it collects billing and gas fields before returning the dataclass:

```python
    billing_fields = _billing_fields(account)
    gas_fields = _gas_fields(account, now)

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
        current_account_balance_gbp=billing_fields["current_account_balance_gbp"],
        latest_statement_closing_balance_gbp=billing_fields[
            "latest_statement_closing_balance_gbp"
        ],
        latest_statement_charges_gbp=billing_fields["latest_statement_charges_gbp"],
        gas_rate_gbp_per_kwh=gas_fields["gas_rate_gbp_per_kwh"],
        gas_pre_vat_rate_gbp_per_kwh=gas_fields["gas_pre_vat_rate_gbp_per_kwh"],
        gas_tariff_name=gas_fields["gas_tariff_name"],
        gas_tariff_code=gas_fields["gas_tariff_code"],
        gas_standing_charge_gbp_per_day=gas_fields["gas_standing_charge_gbp_per_day"],
        gas_pre_vat_standing_charge_gbp_per_day=gas_fields[
            "gas_pre_vat_standing_charge_gbp_per_day"
        ],
        gas_agreement_valid_from=gas_fields["gas_agreement_valid_from"],
        gas_agreement_valid_to=gas_fields["gas_agreement_valid_to"],
        latest_gas_meter_reading_value=gas_fields["latest_gas_meter_reading_value"],
        latest_gas_meter_reading_at=gas_fields["latest_gas_meter_reading_at"],
        latest_gas_meter_reading_source=gas_fields["latest_gas_meter_reading_source"],
        latest_gas_meter_reading_type=gas_fields["latest_gas_meter_reading_type"],
        latest_gas_meter_reading_register_identifier=gas_fields[
            "latest_gas_meter_reading_register_identifier"
        ],
        latest_gas_meter_reading_register_name=gas_fields[
            "latest_gas_meter_reading_register_name"
        ],
        latest_gas_meter_reading_register_digits=gas_fields[
            "latest_gas_meter_reading_register_digits"
        ],
        latest_gas_meter_reading_register_is_quarantined=gas_fields[
            "latest_gas_meter_reading_register_is_quarantined"
        ],
        gas_meter_point_mprn=gas_fields["gas_meter_point_mprn"],
    )
```

- [ ] **Step 4: Run the Task 1 regression set**

Run:

```bash
./.venv/bin/python -m pytest \
  tests/components/eon_next/test_api.py::test_build_account_snapshot_includes_billing_and_gas_fields \
  tests/components/eon_next/test_api.py::test_build_account_snapshot_returns_none_for_optional_billing_and_gas_fields_when_absent \
  tests/components/eon_next/test_api.py::test_build_account_snapshot_returns_none_for_latest_statement_fields_when_latest_bill_is_not_a_statement \
  tests/components/eon_next/test_api.py::test_build_account_snapshot_returns_none_for_malformed_optional_gas_meter_payload \
  tests/components/eon_next/test_api.py::test_client_discovers_account_and_fetches_account_snapshot \
  tests/components/eon_next/test_sensor.py::test_current_rate_sensor_exposes_value_unit_and_attributes \
  tests/components/eon_next/test_init.py::test_async_setup_entry_creates_client_and_stores_runtime_objects \
  -q
```

Expected: PASS.

- [ ] **Step 5: Commit the broadened snapshot model**

```bash
git add custom_components/eon_next/api.py tests/components/eon_next/test_api.py tests/components/eon_next/test_sensor.py tests/components/eon_next/test_init.py
git commit -m "feat: add billing and gas snapshot fields"
```

---

### Task 2: Expose billing and gas entities

**Files:**
- Modify: `custom_components/eon_next/const.py`
- Modify: `custom_components/eon_next/sensor.py`
- Modify: `tests/components/eon_next/test_sensor.py`

- [ ] **Step 1: Write the failing sensor tests first**

Update the snapshot fixture in `tests/components/eon_next/test_sensor.py` with the Task 1 billing and gas values, then add these tests:

```python
from dataclasses import dataclass, replace


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

    assert len(added_entities) == 16
    assert added_entities[0].coordinator is coordinator


def test_billing_sensors_expose_expected_values(sensor_module, snapshot) -> None:
    entities = sensor_module._build_sensors("entry-123", _DummyCoordinator(snapshot))
    balance_sensor = _entity_by_suffix(entities, "current_account_balance")
    statement_balance_sensor = _entity_by_suffix(entities, "latest_statement_closing_balance")
    statement_charges_sensor = _entity_by_suffix(entities, "latest_statement_charges")

    assert balance_sensor.name == "E.ON Current Account Balance"
    assert balance_sensor.native_value == 123.45
    assert balance_sensor.native_unit_of_measurement == "GBP"

    assert statement_balance_sensor.name == "E.ON Latest Statement Closing Balance"
    assert statement_balance_sensor.native_value == 98.76
    assert statement_balance_sensor.native_unit_of_measurement == "GBP"

    assert statement_charges_sensor.name == "E.ON Latest Statement Charges"
    assert statement_charges_sensor.native_value == 54.32
    assert statement_charges_sensor.native_unit_of_measurement == "GBP"


def test_gas_rate_and_charge_sensors_expose_expected_values(sensor_module, snapshot) -> None:
    entities = sensor_module._build_sensors("entry-123", _DummyCoordinator(snapshot))
    gas_rate_sensor = _entity_by_suffix(entities, "gas_unit_rate")
    gas_charge_sensor = _entity_by_suffix(entities, "gas_standing_charge")
    gas_charge_ex_vat_sensor = _entity_by_suffix(entities, "gas_standing_charge_ex_vat")

    assert gas_rate_sensor.name == "E.ON Gas Unit Rate"
    assert gas_rate_sensor.native_value == 0.06543
    assert gas_rate_sensor.native_unit_of_measurement == "GBP/kWh"
    assert gas_rate_sensor.extra_state_attributes == {
        "gas_tariff_name": "Next Flex Gas",
        "gas_tariff_code": "G-1R-NEXT_FLEX_GAS",
        "gas_pre_vat_rate_gbp_per_kwh": 0.06231,
        "gas_agreement_valid_from": datetime(2026, 4, 1, 0, 0, tzinfo=UTC),
        "gas_agreement_valid_to": None,
        "gas_meter_point_mprn": "1234567890",
    }

    assert gas_charge_sensor.native_value == 0.312
    assert gas_charge_sensor.native_unit_of_measurement == "GBP/day"
    assert gas_charge_ex_vat_sensor.native_value == 0.297
    assert gas_charge_ex_vat_sensor.native_unit_of_measurement == "GBP/day"


def test_latest_gas_meter_reading_sensors_expose_expected_values(sensor_module, snapshot) -> None:
    entities = sensor_module._build_sensors("entry-123", _DummyCoordinator(snapshot))
    gas_reading_sensor = _entity_by_suffix(entities, "latest_gas_meter_reading")
    gas_reading_time_sensor = _entity_by_suffix(entities, "latest_gas_meter_reading_at")

    assert gas_reading_sensor.name == "E.ON Latest Gas Meter Reading"
    assert gas_reading_sensor.native_value == 4567.0
    assert gas_reading_sensor.native_unit_of_measurement is None
    assert gas_reading_sensor.extra_state_attributes == {
        "gas_meter_point_mprn": "1234567890",
        "latest_gas_meter_reading_source": "CUSTOMER",
        "latest_gas_meter_reading_type": "actual",
        "latest_gas_meter_reading_register_identifier": "GAS-001",
        "latest_gas_meter_reading_register_name": "GAS",
        "latest_gas_meter_reading_register_digits": 4,
        "latest_gas_meter_reading_register_is_quarantined": False,
    }

    assert gas_reading_time_sensor.name == "E.ON Latest Gas Meter Reading Time"
    assert gas_reading_time_sensor.native_value == datetime(2026, 5, 2, 13, 0, tzinfo=UTC)


def test_optional_billing_and_gas_sensors_return_none_when_data_is_absent(
    sensor_module, snapshot
) -> None:
    empty_optional_snapshot = replace(
        snapshot,
        current_account_balance_gbp=None,
        latest_statement_closing_balance_gbp=None,
        latest_statement_charges_gbp=None,
        gas_rate_gbp_per_kwh=None,
        gas_pre_vat_rate_gbp_per_kwh=None,
        gas_tariff_name=None,
        gas_tariff_code=None,
        gas_standing_charge_gbp_per_day=None,
        gas_pre_vat_standing_charge_gbp_per_day=None,
        gas_agreement_valid_from=None,
        gas_agreement_valid_to=None,
        latest_gas_meter_reading_value=None,
        latest_gas_meter_reading_at=None,
        latest_gas_meter_reading_source=None,
        latest_gas_meter_reading_type=None,
        latest_gas_meter_reading_register_identifier=None,
        latest_gas_meter_reading_register_name=None,
        latest_gas_meter_reading_register_digits=None,
        latest_gas_meter_reading_register_is_quarantined=None,
        gas_meter_point_mprn=None,
    )
    entities = sensor_module._build_sensors("entry-123", _DummyCoordinator(empty_optional_snapshot))

    assert _entity_by_suffix(entities, "current_account_balance").native_value is None
    assert _entity_by_suffix(entities, "latest_statement_closing_balance").native_value is None
    assert _entity_by_suffix(entities, "latest_statement_charges").native_value is None
    assert _entity_by_suffix(entities, "gas_unit_rate").native_value is None
    assert _entity_by_suffix(entities, "latest_gas_meter_reading").native_value is None
    assert _entity_by_suffix(entities, "latest_gas_meter_reading_at").native_value is None
```

- [ ] **Step 2: Run the new sensor tests and confirm they fail**

Run:

```bash
./.venv/bin/python -m pytest \
  tests/components/eon_next/test_sensor.py::test_billing_sensors_expose_expected_values \
  tests/components/eon_next/test_sensor.py::test_gas_rate_and_charge_sensors_expose_expected_values \
  tests/components/eon_next/test_sensor.py::test_latest_gas_meter_reading_sensors_expose_expected_values \
  tests/components/eon_next/test_sensor.py::test_optional_billing_and_gas_sensors_return_none_when_data_is_absent \
  -q
```

Expected: FAIL because the current sensor platform only exposes electricity and electricity-meter entities.

- [ ] **Step 3: Add the new constants and sensor descriptions**

Extend `custom_components/eon_next/const.py` with:

```python
ATTR_GAS_TARIFF_NAME = "gas_tariff_name"
ATTR_GAS_TARIFF_CODE = "gas_tariff_code"
ATTR_GAS_PRE_VAT_RATE_GBP_PER_KWH = "gas_pre_vat_rate_gbp_per_kwh"
ATTR_GAS_AGREEMENT_VALID_FROM = "gas_agreement_valid_from"
ATTR_GAS_AGREEMENT_VALID_TO = "gas_agreement_valid_to"
ATTR_GAS_METER_POINT_MPRN = "gas_meter_point_mprn"
ATTR_LATEST_GAS_METER_READING_SOURCE = "latest_gas_meter_reading_source"
ATTR_LATEST_GAS_METER_READING_TYPE = "latest_gas_meter_reading_type"
ATTR_LATEST_GAS_METER_READING_REGISTER_IDENTIFIER = "latest_gas_meter_reading_register_identifier"
ATTR_LATEST_GAS_METER_READING_REGISTER_NAME = "latest_gas_meter_reading_register_name"
ATTR_LATEST_GAS_METER_READING_REGISTER_DIGITS = "latest_gas_meter_reading_register_digits"
ATTR_LATEST_GAS_METER_READING_REGISTER_IS_QUARANTINED = "latest_gas_meter_reading_register_is_quarantined"
```

Replace the `from .const import (...)` block in `custom_components/eon_next/sensor.py` with:

```python
from .const import (
    ATTR_ACCOUNT_NUMBER,
    ATTR_AGREEMENT_VALID_FROM,
    ATTR_AGREEMENT_VALID_TO,
    ATTR_CURRENT_WINDOW_END,
    ATTR_GAS_AGREEMENT_VALID_FROM,
    ATTR_GAS_AGREEMENT_VALID_TO,
    ATTR_GAS_METER_POINT_MPRN,
    ATTR_GAS_PRE_VAT_RATE_GBP_PER_KWH,
    ATTR_GAS_TARIFF_CODE,
    ATTR_GAS_TARIFF_NAME,
    ATTR_LATEST_GAS_METER_READING_REGISTER_DIGITS,
    ATTR_LATEST_GAS_METER_READING_REGISTER_IDENTIFIER,
    ATTR_LATEST_GAS_METER_READING_REGISTER_IS_QUARANTINED,
    ATTR_LATEST_GAS_METER_READING_REGISTER_NAME,
    ATTR_LATEST_GAS_METER_READING_SOURCE,
    ATTR_LATEST_GAS_METER_READING_TYPE,
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
```

Replace `SENSOR_DESCRIPTIONS` in the same file with this full tuple, and add `BALANCE_UNIT = "GBP"` above it:

```python
BALANCE_UNIT = "GBP"


SENSOR_DESCRIPTIONS = (
    EonRateSensorDescription(
        key="current_import_rate",
        name="E.ON Current Import Rate",
        native_unit_of_measurement=RATE_UNIT,
        value_attr="current_rate_gbp_per_kwh",
        unique_id_suffix="current_import_rate",
        attribute_fields={
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
        attribute_fields={
            ATTR_METER_POINT_MPAN: "meter_point_mpan",
            ATTR_LATEST_METER_READING_SOURCE: "latest_meter_reading_source",
            ATTR_LATEST_METER_READING_TYPE: "latest_meter_reading_type",
            ATTR_LATEST_METER_READING_REGISTER_IDENTIFIER:
                "latest_meter_reading_register_identifier",
            ATTR_LATEST_METER_READING_REGISTER_NAME: "latest_meter_reading_register_name",
            ATTR_LATEST_METER_READING_REGISTER_DIGITS: "latest_meter_reading_register_digits",
            ATTR_LATEST_METER_READING_REGISTER_IS_QUARANTINED:
                "latest_meter_reading_register_is_quarantined",
        },
    ),
    EonRateSensorDescription(
        key="latest_meter_reading_at",
        name="E.ON Latest Meter Reading Time",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_attr="latest_meter_reading_at",
        unique_id_suffix="latest_meter_reading_at",
    ),
    EonRateSensorDescription(
        key="current_account_balance",
        name="E.ON Current Account Balance",
        native_unit_of_measurement=BALANCE_UNIT,
        value_attr="current_account_balance_gbp",
        unique_id_suffix="current_account_balance",
    ),
    EonRateSensorDescription(
        key="latest_statement_closing_balance",
        name="E.ON Latest Statement Closing Balance",
        native_unit_of_measurement=BALANCE_UNIT,
        value_attr="latest_statement_closing_balance_gbp",
        unique_id_suffix="latest_statement_closing_balance",
    ),
    EonRateSensorDescription(
        key="latest_statement_charges",
        name="E.ON Latest Statement Charges",
        native_unit_of_measurement=BALANCE_UNIT,
        value_attr="latest_statement_charges_gbp",
        unique_id_suffix="latest_statement_charges",
    ),
    EonRateSensorDescription(
        key="gas_unit_rate",
        name="E.ON Gas Unit Rate",
        native_unit_of_measurement=RATE_UNIT,
        value_attr="gas_rate_gbp_per_kwh",
        unique_id_suffix="gas_unit_rate",
        attribute_fields={
            ATTR_GAS_TARIFF_NAME: "gas_tariff_name",
            ATTR_GAS_TARIFF_CODE: "gas_tariff_code",
            ATTR_GAS_PRE_VAT_RATE_GBP_PER_KWH: "gas_pre_vat_rate_gbp_per_kwh",
            ATTR_GAS_AGREEMENT_VALID_FROM: "gas_agreement_valid_from",
            ATTR_GAS_AGREEMENT_VALID_TO: "gas_agreement_valid_to",
            ATTR_GAS_METER_POINT_MPRN: "gas_meter_point_mprn",
        },
    ),
    EonRateSensorDescription(
        key="gas_standing_charge",
        name="E.ON Gas Standing Charge",
        native_unit_of_measurement=CHARGE_UNIT,
        value_attr="gas_standing_charge_gbp_per_day",
        unique_id_suffix="gas_standing_charge",
    ),
    EonRateSensorDescription(
        key="gas_standing_charge_ex_vat",
        name="E.ON Gas Standing Charge Ex VAT",
        native_unit_of_measurement=CHARGE_UNIT,
        value_attr="gas_pre_vat_standing_charge_gbp_per_day",
        unique_id_suffix="gas_standing_charge_ex_vat",
    ),
    EonRateSensorDescription(
        key="latest_gas_meter_reading",
        name="E.ON Latest Gas Meter Reading",
        value_attr="latest_gas_meter_reading_value",
        unique_id_suffix="latest_gas_meter_reading",
        attribute_fields={
            ATTR_GAS_METER_POINT_MPRN: "gas_meter_point_mprn",
            ATTR_LATEST_GAS_METER_READING_SOURCE: "latest_gas_meter_reading_source",
            ATTR_LATEST_GAS_METER_READING_TYPE: "latest_gas_meter_reading_type",
            ATTR_LATEST_GAS_METER_READING_REGISTER_IDENTIFIER:
                "latest_gas_meter_reading_register_identifier",
            ATTR_LATEST_GAS_METER_READING_REGISTER_NAME:
                "latest_gas_meter_reading_register_name",
            ATTR_LATEST_GAS_METER_READING_REGISTER_DIGITS:
                "latest_gas_meter_reading_register_digits",
            ATTR_LATEST_GAS_METER_READING_REGISTER_IS_QUARANTINED:
                "latest_gas_meter_reading_register_is_quarantined",
        },
    ),
    EonRateSensorDescription(
        key="latest_gas_meter_reading_at",
        name="E.ON Latest Gas Meter Reading Time",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_attr="latest_gas_meter_reading_at",
        unique_id_suffix="latest_gas_meter_reading_at",
    ),
)
```

- [ ] **Step 4: Run the full sensor test file**

Run:

```bash
./.venv/bin/python -m pytest tests/components/eon_next/test_sensor.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit the billing and gas sensors**

```bash
git add custom_components/eon_next/const.py custom_components/eon_next/sensor.py tests/components/eon_next/test_sensor.py
git commit -m "feat: add billing and gas sensors"
```

---

### Task 3: Update the README and verify the full slice

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update the feature lists for billing and gas support**

Replace the feature lists in `README.md` with:

```markdown
## Current features

- Live VAT-inclusive import rate
- Next import rate when E.ON publishes a later tariff window
- Next rate change timestamp when available
- Standing charge sensors including pre-VAT standing charge
- Active tariff and account metadata, including account number and agreement window attributes
- Latest electricity meter reading and reading timestamp when available
- Current account balance and latest statement amounts when available
- Gas unit rate, standing charge, tariff metadata, and latest gas meter reading when available

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
git commit -m "docs: update README for billing and gas support"
```
