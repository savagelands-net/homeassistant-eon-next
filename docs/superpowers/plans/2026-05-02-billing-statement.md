# E.ON Next Billing Statement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an exact latest-statement billing snapshot that matches a verified recent E.ON statement shape, while keeping gas statement breakdown conservative where the API does not expose an exact standing-charge or usage-cost split.

**Architecture:** Keep the existing single config entry, single coordinator, and single sensor platform. Update `api.py` so billing uses `bills(first: 1, orderBy: ISSUED_DATE_DESC)` plus `StatementType.transactions(first: N)` to populate exact billing fields on `AccountSnapshot`, then project those fields into dedicated billing sensors in `sensor.py`.

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
  Change billing selection to the exact latest statement query shape and summarize statement transaction rows into exact electricity, gas, and direct-debit fields.
- `custom_components/eon_next/const.py`
  Define any new billing attribute labels needed for the statement sensors.
- `custom_components/eon_next/sensor.py`
  Add statement and payment sensors for the exact billing values.
- `tests/components/eon_next/test_api.py`
  Carry most of the confidence by proving statement selection and transaction summarization against raw payload shapes.
- `tests/components/eon_next/test_sensor.py`
  Prove the widened billing entity surface and `None` behavior.
- `tests/components/eon_next/test_init.py`
  Keep the shared `AccountSnapshot` fixture aligned with the new billing fields.
- `README.md`
  Move the statement breakdown wording into the current-features list after the implementation is verified.

---

### Task 1: Summarize the latest statement exactly in `AccountSnapshot`

**Files:**
- Modify: `custom_components/eon_next/api.py`
- Modify: `tests/components/eon_next/test_api.py`
- Modify: `tests/components/eon_next/test_sensor.py`
- Modify: `tests/components/eon_next/test_init.py`

- [ ] **Step 1: Write the failing API tests first**

Add these helpers near the top of `tests/components/eon_next/test_api.py`:

```python
def _statement_transaction_charge(
    *,
    title: str,
    posted_date: str,
    gross: int,
    net: int,
    tax: int,
    quantity: str,
    usage_cost: int,
    supply_charge: int,
) -> dict[str, Any]:
    return {
        "node": {
            "__typename": "Charge",
            "postedDate": posted_date,
            "createdAt": f"{posted_date}T00:00:00+00:00",
            "title": title,
            "note": "",
            "reasonCode": "",
        "billingDocumentIdentifier": "example-statement-id",
            "isReversed": False,
            "amounts": {"net": net, "tax": tax, "gross": gross},
            "isHeld": False,
            "isIssued": True,
            "isExport": False,
            "consumption": {
                "startDate": "2026-04-01",
                "endDate": "2026-04-18",
                "quantity": quantity,
                "unit": "kWh",
                "usageCost": usage_cost,
                "supplyCharge": supply_charge,
            },
        }
    }


def _statement_transaction_payment(*, posted_date: str, gross: int) -> dict[str, Any]:
    return {
        "node": {
            "__typename": "Payment",
            "postedDate": posted_date,
            "createdAt": f"{posted_date}T00:00:00+00:00",
            "title": "Direct debit",
            "note": None,
            "reasonCode": "",
        "billingDocumentIdentifier": "example-statement-id",
            "isReversed": False,
            "amounts": {"net": gross, "tax": 0, "gross": gross},
            "paymentTransactionType": "DD_REGULAR_COLLECTION",
        }
    }


def _statement_bill_node(*transactions: dict[str, Any]) -> dict[str, Any]:
    return {
        "__typename": "StatementType",
        "billType": "STATEMENT",
        "issuedDate": "2026-01-15",
        "fromDate": "2025-12-16",
        "toDate": "2026-01-14",
        "openingBalance": 12345,
        "closingBalance": 6789,
        "paymentDueDate": "2026-01-30",
        "status": "CLOSED",
        "totalCharges": {"netTotal": 32921, "taxTotal": 1646, "grossTotal": 34567},
        "totalCredits": {"netTotal": 0, "taxTotal": 0, "grossTotal": 0},
        "transactions": {"edges": list(transactions)},
    }
```

Add this primary billing test:

```python
def test_build_account_snapshot_includes_latest_statement_breakdown() -> None:
    account = _account_payload(
        balance=6789,
        bills=_bills_payload(
            _statement_bill_node(
                _statement_transaction_charge(
                    title="Gas",
                    posted_date="2026-01-14",
                    gross=7000,
                    net=6667,
                    tax=333,
                    quantity="1200.0000",
                    usage_cost=0,
                    supply_charge=0,
                ),
                _statement_transaction_charge(
                    title="Electricity",
                    posted_date="2026-01-14",
                    gross=10012,
                    net=9535,
                    tax=477,
                    quantity="500.1200",
                    usage_cost=9000,
                    supply_charge=1012,
                ),
                _statement_transaction_payment(
                    posted_date="2026-01-01",
                    gross=30000,
                ),
                _statement_transaction_charge(
                    title="Gas",
                    posted_date="2025-12-31",
                    gross=6555,
                    net=6243,
                    tax=312,
                    quantity="1145.6700",
                    usage_cost=0,
                    supply_charge=0,
                ),
                _statement_transaction_charge(
                    title="Electricity",
                    posted_date="2025-12-31",
                    gross=11000,
                    net=10476,
                    tax=524,
                    quantity="734.4400",
                    usage_cost=10800,
                    supply_charge=200,
                ),
            )
        ),
    )

    snapshot = build_account_snapshot(
        account,
        _agreement_payload_with_meter_readings(),
        datetime(2026, 5, 2, 12, 0, tzinfo=UTC),
    )

    assert snapshot.current_account_balance_gbp == 67.89
    assert snapshot.latest_statement_issued_at == datetime(2026, 1, 15, 0, 0, tzinfo=UTC)
    assert snapshot.latest_statement_period_start == datetime(2025, 12, 16, 0, 0, tzinfo=UTC)
    assert snapshot.latest_statement_period_end == datetime(2026, 1, 14, 0, 0, tzinfo=UTC)
    assert snapshot.latest_statement_payment_due_at == datetime(2026, 1, 30, 0, 0, tzinfo=UTC)
    assert snapshot.latest_statement_opening_balance_gbp == 123.45
    assert snapshot.latest_statement_closing_balance_gbp == 67.89
    assert snapshot.latest_statement_charges_gbp == 345.67
    assert snapshot.latest_statement_credits_gbp == 0
    assert snapshot.latest_direct_debit_amount_gbp == 300.00
    assert snapshot.latest_direct_debit_at == datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    assert snapshot.latest_electricity_statement_total_gbp == 210.12
    assert snapshot.latest_electricity_statement_quantity_kwh == 1234.56
    assert snapshot.latest_electricity_statement_usage_cost_gbp == 198.00
    assert snapshot.latest_electricity_statement_standing_charge_gbp == 12.12
    assert snapshot.latest_gas_statement_total_gbp == 135.55
    assert snapshot.latest_gas_statement_quantity_kwh == 2345.67
```

Add one fallback test:

```python
def test_build_account_snapshot_returns_none_for_missing_statement_breakdown_rows() -> None:
    account = _account_payload(
        balance=6789,
        bills=_bills_payload(
            _statement_bill_node()
        ),
    )

    snapshot = build_account_snapshot(
        account,
        _agreement_payload_with_meter_readings(),
        datetime(2026, 5, 2, 12, 0, tzinfo=UTC),
    )

    assert snapshot.current_account_balance_gbp == 67.89
    assert snapshot.latest_statement_charges_gbp == 345.67
    assert snapshot.latest_direct_debit_amount_gbp is None
    assert snapshot.latest_electricity_statement_total_gbp is None
    assert snapshot.latest_gas_statement_total_gbp is None
```

Extend the shared `AccountSnapshot(...)` fixtures in `tests/components/eon_next/test_sensor.py` and `tests/components/eon_next/test_init.py` with these new fields:

```python
latest_statement_issued_at=datetime(2026, 1, 15, 0, 0, tzinfo=UTC),
latest_statement_period_start=datetime(2025, 12, 16, 0, 0, tzinfo=UTC),
latest_statement_period_end=datetime(2026, 1, 14, 0, 0, tzinfo=UTC),
latest_statement_payment_due_at=datetime(2026, 1, 30, 0, 0, tzinfo=UTC),
latest_statement_opening_balance_gbp=123.45,
latest_statement_credits_gbp=0,
latest_direct_debit_amount_gbp=300.00,
latest_direct_debit_at=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
latest_electricity_statement_total_gbp=210.12,
latest_electricity_statement_quantity_kwh=1234.56,
latest_electricity_statement_usage_cost_gbp=198.00,
latest_electricity_statement_standing_charge_gbp=12.12,
latest_gas_statement_total_gbp=135.55,
latest_gas_statement_quantity_kwh=2345.67,
```

- [ ] **Step 2: Run the new API tests and confirm they fail**

Run:

```bash
./.venv/bin/python -m pytest \
  tests/components/eon_next/test_api.py::test_build_account_snapshot_includes_latest_statement_breakdown \
  tests/components/eon_next/test_api.py::test_build_account_snapshot_returns_none_for_missing_statement_breakdown_rows \
  -q
```

Expected: FAIL because the current billing query and `AccountSnapshot` do not yet include the latest-statement breakdown fields.

- [ ] **Step 3: Add the latest-statement query and summarizer**

Replace the billing portion of `AGREEMENTS_QUERY` in `custom_components/eon_next/api.py` with:

```python
    bills(first: 1, orderBy: ISSUED_DATE_DESC) {
      edges {
        node {
          __typename
          billType
          issuedDate
          fromDate
          toDate
          ... on StatementType {
            openingBalance
            closingBalance
            paymentDueDate
            status
            totalCharges {
              netTotal
              taxTotal
              grossTotal
            }
            totalCredits {
              netTotal
              taxTotal
              grossTotal
            }
            transactions(first: 50) {
              edges {
                node {
                  __typename
                  postedDate
                  createdAt
                  title
                  note
                  reasonCode
                  billingDocumentIdentifier
                  isReversed
                  amounts {
                    net
                    tax
                    gross
                  }
                  ... on Charge {
                    isHeld
                    isIssued
                    isExport
                    consumption {
                      startDate
                      endDate
                      quantity
                      unit
                      usageCost
                      supplyCharge
                    }
                  }
                  ... on Payment {
                    paymentTransactionType
                  }
                }
              }
            }
          }
        }
      }
    }
```

Add these new optional fields to `AccountSnapshot`:

```python
    latest_statement_issued_at: datetime | None = None
    latest_statement_period_start: datetime | None = None
    latest_statement_period_end: datetime | None = None
    latest_statement_payment_due_at: datetime | None = None
    latest_statement_opening_balance_gbp: float | None = None
    latest_statement_credits_gbp: float | None = None
    latest_direct_debit_amount_gbp: float | None = None
    latest_direct_debit_at: datetime | None = None
    latest_electricity_statement_total_gbp: float | None = None
    latest_electricity_statement_quantity_kwh: float | None = None
    latest_electricity_statement_usage_cost_gbp: float | None = None
    latest_electricity_statement_standing_charge_gbp: float | None = None
    latest_gas_statement_total_gbp: float | None = None
    latest_gas_statement_quantity_kwh: float | None = None
```

Add helpers below `_optional_minor_units_to_gbp`:

```python
def _parse_date_to_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None

    return datetime.fromisoformat(f"{value}T00:00:00+00:00")


def _parse_decimal_string(value: str | None) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _statement_transaction_fields(statement: dict | None) -> dict[str, Any]:
    empty = {
        "latest_direct_debit_amount_gbp": None,
        "latest_direct_debit_at": None,
        "latest_electricity_statement_total_gbp": None,
        "latest_electricity_statement_quantity_kwh": None,
        "latest_electricity_statement_usage_cost_gbp": None,
        "latest_electricity_statement_standing_charge_gbp": None,
        "latest_gas_statement_total_gbp": None,
        "latest_gas_statement_quantity_kwh": None,
    }

    if not isinstance(statement, dict):
        return empty

    transactions = statement.get("transactions")
    edges = transactions.get("edges") if isinstance(transactions, dict) else None
    if not isinstance(edges, list):
        return empty

    direct_debit_amount = None
    direct_debit_at = None
    electricity_total = 0.0
    electricity_quantity = 0.0
    electricity_usage_cost = 0.0
    electricity_standing_charge = 0.0
    gas_total = 0.0
    gas_quantity = 0.0
    seen_electricity = False
    seen_gas = False

    for edge in edges:
        if not isinstance(edge, dict):
            continue
        transaction = edge.get("node")
        if not isinstance(transaction, dict):
            continue

        typename = transaction.get("__typename")
        title = transaction.get("title")

        if typename == "Payment" and title == "Direct debit":
            gross = (transaction.get("amounts") or {}).get("gross")
            posted = _parse_date_to_datetime(transaction.get("postedDate"))
            if isinstance(gross, int) and posted is not None:
                amount = _optional_minor_units_to_gbp(gross)
                if direct_debit_at is None or posted > direct_debit_at:
                    direct_debit_amount = amount
                    direct_debit_at = posted
            continue

        if typename != "Charge":
            continue

        gross = (transaction.get("amounts") or {}).get("gross")
        consumption = transaction.get("consumption")
        quantity = None
        usage_cost = None
        supply_charge = None
        if isinstance(consumption, dict):
            quantity = _parse_decimal_string(consumption.get("quantity"))
            usage_cost = _optional_minor_units_to_gbp(consumption.get("usageCost"))
            supply_charge = _optional_minor_units_to_gbp(consumption.get("supplyCharge"))

        if title == "Electricity" and isinstance(gross, int):
            electricity_total += _optional_minor_units_to_gbp(gross) or 0
            if quantity is not None:
                electricity_quantity += quantity
            if usage_cost is not None:
                electricity_usage_cost += usage_cost
            if supply_charge is not None:
                electricity_standing_charge += supply_charge
            seen_electricity = True
            continue

        if title == "Gas" and isinstance(gross, int):
            gas_total += _optional_minor_units_to_gbp(gross) or 0
            if quantity is not None:
                gas_quantity += quantity
            seen_gas = True

    return {
        "latest_direct_debit_amount_gbp": direct_debit_amount,
        "latest_direct_debit_at": direct_debit_at,
        "latest_electricity_statement_total_gbp": electricity_total if seen_electricity else None,
        "latest_electricity_statement_quantity_kwh": electricity_quantity if seen_electricity else None,
        "latest_electricity_statement_usage_cost_gbp": electricity_usage_cost if seen_electricity else None,
        "latest_electricity_statement_standing_charge_gbp": electricity_standing_charge if seen_electricity else None,
        "latest_gas_statement_total_gbp": gas_total if seen_gas else None,
        "latest_gas_statement_quantity_kwh": gas_quantity if seen_gas else None,
    }


def _billing_fields(account: dict) -> dict[str, Any]:
    statement = None
    bills = account.get("bills")

    if isinstance(bills, dict):
        edges = bills.get("edges")
        if isinstance(edges, list):
            for edge in edges:
                if not isinstance(edge, dict):
                    continue
                node = edge.get("node")
                if not isinstance(node, dict):
                    continue
                if node.get("__typename") == "StatementType":
                    statement = node
                    break

    transaction_fields = _statement_transaction_fields(statement)
    total_charges = statement.get("totalCharges") if isinstance(statement, dict) else None
    total_credits = statement.get("totalCredits") if isinstance(statement, dict) else None

    return {
        "current_account_balance_gbp": _optional_minor_units_to_gbp(account.get("balance")),
        "latest_statement_issued_at": _parse_date_to_datetime(statement.get("issuedDate")) if isinstance(statement, dict) else None,
        "latest_statement_period_start": _parse_date_to_datetime(statement.get("fromDate")) if isinstance(statement, dict) else None,
        "latest_statement_period_end": _parse_date_to_datetime(statement.get("toDate")) if isinstance(statement, dict) else None,
        "latest_statement_payment_due_at": _parse_date_to_datetime(statement.get("paymentDueDate")) if isinstance(statement, dict) else None,
        "latest_statement_opening_balance_gbp": _optional_minor_units_to_gbp(statement.get("openingBalance")) if isinstance(statement, dict) else None,
        "latest_statement_closing_balance_gbp": _optional_minor_units_to_gbp(statement.get("closingBalance")) if isinstance(statement, dict) else None,
        "latest_statement_charges_gbp": _optional_minor_units_to_gbp(total_charges.get("grossTotal")) if isinstance(total_charges, dict) else None,
        "latest_statement_credits_gbp": _optional_minor_units_to_gbp(total_credits.get("grossTotal")) if isinstance(total_credits, dict) else None,
        **transaction_fields,
    }
```

Update the existing `test_client_discovers_account_and_fetches_account_snapshot()` fixture payload and assertions so the latest statement uses the new `first: 1` shape and exact breakdown assertions.

- [ ] **Step 4: Run the Task 1 regression set**

Run:

```bash
./.venv/bin/python -m pytest \
  tests/components/eon_next/test_api.py::test_build_account_snapshot_includes_latest_statement_breakdown \
  tests/components/eon_next/test_api.py::test_build_account_snapshot_returns_none_for_missing_statement_breakdown_rows \
  tests/components/eon_next/test_api.py::test_client_discovers_account_and_fetches_account_snapshot \
  tests/components/eon_next/test_sensor.py::test_billing_sensors_expose_expected_values \
  tests/components/eon_next/test_init.py::test_async_setup_entry_creates_client_and_stores_runtime_objects \
  -q
```

Expected: PASS.

---

### Task 2: Expose the rich billing sensor surface

**Files:**
- Modify: `custom_components/eon_next/const.py`
- Modify: `custom_components/eon_next/sensor.py`
- Modify: `tests/components/eon_next/test_sensor.py`

- [ ] **Step 1: Write the failing sensor tests first**

Extend `tests/components/eon_next/test_sensor.py` with these expectations:

```python
def test_statement_date_sensors_expose_expected_timestamps(sensor_module, snapshot) -> None:
    entities = sensor_module._build_sensors("entry-123", _DummyCoordinator(snapshot))

    assert _entity_by_suffix(entities, "latest_statement_issued_at").native_value == datetime(2026, 4, 20, 0, 0, tzinfo=UTC)
    assert _entity_by_suffix(entities, "latest_statement_period_start").native_value == datetime(2026, 3, 21, 0, 0, tzinfo=UTC)
    assert _entity_by_suffix(entities, "latest_statement_period_end").native_value == datetime(2026, 4, 19, 0, 0, tzinfo=UTC)
    assert _entity_by_suffix(entities, "latest_statement_payment_due_at").native_value == datetime(2026, 5, 5, 0, 0, tzinfo=UTC)


def test_statement_amount_sensors_expose_expected_values(sensor_module, snapshot) -> None:
    entities = sensor_module._build_sensors("entry-123", _DummyCoordinator(snapshot))

    assert _entity_by_suffix(entities, "latest_statement_opening_balance").native_value == 370.23
    assert _entity_by_suffix(entities, "latest_statement_closing_balance").native_value == 310.61
    assert _entity_by_suffix(entities, "latest_statement_charges").native_value == 459.67
    assert _entity_by_suffix(entities, "latest_statement_credits").native_value == 0
    assert _entity_by_suffix(entities, "latest_direct_debit_amount").native_value == 400.05


def test_statement_fuel_breakdown_sensors_expose_expected_values(sensor_module, snapshot) -> None:
    entities = sensor_module._build_sensors("entry-123", _DummyCoordinator(snapshot))

    assert _entity_by_suffix(entities, "latest_electricity_statement_total").native_value == 210.12
    assert _entity_by_suffix(entities, "latest_electricity_statement_quantity").native_value == 1234.56
    assert _entity_by_suffix(entities, "latest_electricity_statement_usage_cost").native_value == 198.00
    assert _entity_by_suffix(entities, "latest_electricity_statement_standing_charge").native_value == 12.12
    assert _entity_by_suffix(entities, "latest_gas_statement_total").native_value == 135.55
    assert _entity_by_suffix(entities, "latest_gas_statement_quantity").native_value == 2345.67


def test_optional_statement_breakdown_sensors_return_none_when_data_is_absent(sensor_module, snapshot) -> None:
    snapshot_without_statement = replace(
        snapshot,
        latest_statement_issued_at=None,
        latest_statement_period_start=None,
        latest_statement_period_end=None,
        latest_statement_payment_due_at=None,
        latest_statement_opening_balance_gbp=None,
        latest_statement_closing_balance_gbp=None,
        latest_statement_charges_gbp=None,
        latest_statement_credits_gbp=None,
        latest_direct_debit_amount_gbp=None,
        latest_direct_debit_at=None,
        latest_electricity_statement_total_gbp=None,
        latest_electricity_statement_quantity_kwh=None,
        latest_electricity_statement_usage_cost_gbp=None,
        latest_electricity_statement_standing_charge_gbp=None,
        latest_gas_statement_total_gbp=None,
        latest_gas_statement_quantity_kwh=None,
    )
    entities = sensor_module._build_sensors("entry-123", _DummyCoordinator(snapshot_without_statement))

    assert _entity_by_suffix(entities, "latest_statement_issued_at").native_value is None
    assert _entity_by_suffix(entities, "latest_direct_debit_amount").native_value is None
    assert _entity_by_suffix(entities, "latest_electricity_statement_total").native_value is None
    assert _entity_by_suffix(entities, "latest_gas_statement_total").native_value is None
```

- [ ] **Step 2: Run the new sensor tests and confirm they fail**

Run:

```bash
./.venv/bin/python -m pytest \
  tests/components/eon_next/test_sensor.py::test_statement_date_sensors_expose_expected_timestamps \
  tests/components/eon_next/test_sensor.py::test_statement_amount_sensors_expose_expected_values \
  tests/components/eon_next/test_sensor.py::test_statement_fuel_breakdown_sensors_expose_expected_values \
  tests/components/eon_next/test_sensor.py::test_optional_statement_breakdown_sensors_return_none_when_data_is_absent \
  -q
```

Expected: FAIL because the current sensor platform does not expose these latest-statement breakdown entities yet.

- [ ] **Step 3: Add the billing statement sensors**

Extend `custom_components/eon_next/sensor.py` with these additional descriptions, keeping amount sensors on `BALANCE_UNIT`, energy sensors on `READING_UNIT`, and date sensors on `SensorDeviceClass.TIMESTAMP`:

```python
    EonRateSensorDescription(
        key="latest_statement_issued_at",
        name="E.ON Latest Statement Issued Date",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_attr="latest_statement_issued_at",
        unique_id_suffix="latest_statement_issued_at",
    ),
    EonRateSensorDescription(
        key="latest_statement_period_start",
        name="E.ON Latest Statement Period Start",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_attr="latest_statement_period_start",
        unique_id_suffix="latest_statement_period_start",
    ),
    EonRateSensorDescription(
        key="latest_statement_period_end",
        name="E.ON Latest Statement Period End",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_attr="latest_statement_period_end",
        unique_id_suffix="latest_statement_period_end",
    ),
    EonRateSensorDescription(
        key="latest_statement_payment_due_at",
        name="E.ON Latest Statement Payment Due Date",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_attr="latest_statement_payment_due_at",
        unique_id_suffix="latest_statement_payment_due_at",
    ),
    EonRateSensorDescription(
        key="latest_statement_opening_balance",
        name="E.ON Latest Statement Opening Balance",
        native_unit_of_measurement=BALANCE_UNIT,
        value_attr="latest_statement_opening_balance_gbp",
        unique_id_suffix="latest_statement_opening_balance",
    ),
    EonRateSensorDescription(
        key="latest_statement_credits",
        name="E.ON Latest Statement Credits",
        native_unit_of_measurement=BALANCE_UNIT,
        value_attr="latest_statement_credits_gbp",
        unique_id_suffix="latest_statement_credits",
    ),
    EonRateSensorDescription(
        key="latest_direct_debit_amount",
        name="E.ON Latest Direct Debit Amount",
        native_unit_of_measurement=BALANCE_UNIT,
        value_attr="latest_direct_debit_amount_gbp",
        unique_id_suffix="latest_direct_debit_amount",
    ),
    EonRateSensorDescription(
        key="latest_direct_debit_at",
        name="E.ON Latest Direct Debit Date",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_attr="latest_direct_debit_at",
        unique_id_suffix="latest_direct_debit_at",
    ),
    EonRateSensorDescription(
        key="latest_electricity_statement_total",
        name="E.ON Latest Electricity Statement Total",
        native_unit_of_measurement=BALANCE_UNIT,
        value_attr="latest_electricity_statement_total_gbp",
        unique_id_suffix="latest_electricity_statement_total",
    ),
    EonRateSensorDescription(
        key="latest_electricity_statement_quantity",
        name="E.ON Latest Electricity Quantity",
        native_unit_of_measurement=READING_UNIT,
        value_attr="latest_electricity_statement_quantity_kwh",
        unique_id_suffix="latest_electricity_statement_quantity",
    ),
    EonRateSensorDescription(
        key="latest_electricity_statement_usage_cost",
        name="E.ON Latest Electricity Usage Cost",
        native_unit_of_measurement=BALANCE_UNIT,
        value_attr="latest_electricity_statement_usage_cost_gbp",
        unique_id_suffix="latest_electricity_statement_usage_cost",
    ),
    EonRateSensorDescription(
        key="latest_electricity_statement_standing_charge",
        name="E.ON Latest Electricity Standing Charge",
        native_unit_of_measurement=BALANCE_UNIT,
        value_attr="latest_electricity_statement_standing_charge_gbp",
        unique_id_suffix="latest_electricity_statement_standing_charge",
    ),
    EonRateSensorDescription(
        key="latest_gas_statement_total",
        name="E.ON Latest Gas Statement Total",
        native_unit_of_measurement=BALANCE_UNIT,
        value_attr="latest_gas_statement_total_gbp",
        unique_id_suffix="latest_gas_statement_total",
    ),
    EonRateSensorDescription(
        key="latest_gas_statement_quantity",
        name="E.ON Latest Gas Quantity",
        native_unit_of_measurement=READING_UNIT,
        value_attr="latest_gas_statement_quantity_kwh",
        unique_id_suffix="latest_gas_statement_quantity",
    ),
```

No new constants are required if these are all plain sensor values without extra attributes.

- [ ] **Step 4: Run the full sensor test file**

Run:

```bash
./.venv/bin/python -m pytest tests/components/eon_next/test_sensor.py -q
```

Expected: PASS.

---

### Task 3: Update the README and verify the whole billing slice

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update the current-features list for the latest-statement breakdown**

Change the billing bullet in `README.md` to:

```markdown
- Current account balance, latest statement totals, fuel breakdown, and latest direct debit when available
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
git commit -m "docs: update README for statement breakdown"
```
