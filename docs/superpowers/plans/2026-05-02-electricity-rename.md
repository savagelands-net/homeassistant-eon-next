# E.ON Next Electricity Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every electricity entity and electricity-specific attribute label explicit, while preserving gas and billing names and migrating existing electricity entity IDs cleanly for installed users.

**Architecture:** Keep the current coordinator and snapshot behavior unchanged. Update the sensor naming surface in `sensor.py`, electricity-specific attribute labels in `const.py`, and add an entity-registry unique-id migration step in `__init__.py` so old electricity entities are renamed rather than duplicated.

**Tech Stack:** Home Assistant custom integration, Python 3.13, `pytest`, `pytest-asyncio`, `ruff`

---

## File Structure

**Modify:**
- `custom_components/eon_next/__init__.py`
- `custom_components/eon_next/const.py`
- `custom_components/eon_next/sensor.py`
- `tests/components/eon_next/test_init.py`
- `tests/components/eon_next/test_sensor.py`
- `README.md`

### Responsibilities

- `custom_components/eon_next/sensor.py`
  Rename electricity sensor display names, keys, unique-id suffixes, and electricity-specific attribute mappings.
- `custom_components/eon_next/const.py`
  Rename electricity-specific attribute constants to explicit electricity-prefixed names while keeping neutral account-wide and gas names unchanged.
- `custom_components/eon_next/__init__.py`
  Add an entity-registry migration step that renames old electricity unique IDs to their new electricity-prefixed versions during setup.
- `tests/components/eon_next/test_sensor.py`
  Prove the renamed electricity entity names, IDs, and attributes, and assert that gas/billing naming remains unchanged.
- `tests/components/eon_next/test_init.py`
  Prove entity-registry migration runs and updates the old electricity unique IDs before platform setup.
- `README.md`
  Update current-feature wording so electricity is explicitly named where needed.

---

### Task 1: Rename the electricity sensor surface

**Files:**
- Modify: `custom_components/eon_next/const.py`
- Modify: `custom_components/eon_next/sensor.py`
- Modify: `tests/components/eon_next/test_sensor.py`

- [ ] **Step 1: Write the failing sensor tests first**

Update `tests/components/eon_next/test_sensor.py` with the explicit electricity expectations:

```python
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


def test_electricity_current_rate_sensor_exposes_value_unit_and_attributes(
    sensor_module, snapshot
) -> None:
    entities = sensor_module._build_sensors("entry-123", _DummyCoordinator(snapshot))
    current_sensor = _entity_by_suffix(entities, "electricity_current_import_rate")

    assert current_sensor.name == "E.ON Electricity Current Import Rate"
    assert current_sensor.unique_id == "entry-123_electricity_current_import_rate"
    assert current_sensor.native_value == 0.239022
    assert current_sensor.native_unit_of_measurement == "GBP/kWh"
    assert current_sensor.extra_state_attributes == {
        "account_number": "A-TEST0001",
        "electricity_tariff_name": "Next Drive Smart V5.2",
        "electricity_tariff_code": "E-TOU-NEXT_DRIVE_SMART_V5_2-N",
        "electricity_standing_charge_gbp_per_day": 0.6000015,
        "electricity_pre_vat_standing_charge_gbp_per_day": 0.57143,
        "electricity_current_window_end": datetime(2026, 5, 1, 12, 30, tzinfo=UTC),
        "electricity_next_window_start": datetime(2026, 5, 1, 12, 30, tzinfo=UTC),
        "electricity_agreement_valid_from": datetime(2026, 4, 1, 0, 0, tzinfo=UTC),
        "electricity_agreement_valid_to": None,
    }


def test_electricity_standing_charge_and_meter_sensors_use_explicit_names(
    sensor_module, snapshot
) -> None:
    entities = sensor_module._build_sensors("entry-123", _DummyCoordinator(snapshot))

    electricity_next_rate_sensor = _entity_by_suffix(entities, "electricity_next_import_rate")
    electricity_next_change_sensor = _entity_by_suffix(entities, "electricity_next_rate_change_at")
    electricity_standing_charge_sensor = _entity_by_suffix(entities, "electricity_standing_charge")
    electricity_standing_charge_ex_vat_sensor = _entity_by_suffix(
        entities, "electricity_standing_charge_ex_vat"
    )
    electricity_meter_sensor = _entity_by_suffix(entities, "latest_electricity_meter_reading")
    electricity_meter_time_sensor = _entity_by_suffix(
        entities, "latest_electricity_meter_reading_at"
    )

    assert electricity_next_rate_sensor.name == "E.ON Electricity Next Import Rate"
    assert electricity_next_change_sensor.name == "E.ON Electricity Next Rate Change"
    assert electricity_standing_charge_sensor.name == "E.ON Electricity Standing Charge"
    assert electricity_standing_charge_ex_vat_sensor.name == "E.ON Electricity Standing Charge Ex VAT"
    assert electricity_meter_sensor.name == "E.ON Latest Electricity Meter Reading"
    assert electricity_meter_time_sensor.name == "E.ON Latest Electricity Meter Reading Time"


def test_gas_and_billing_sensor_names_remain_unchanged(sensor_module, snapshot) -> None:
    entities = sensor_module._build_sensors("entry-123", _DummyCoordinator(snapshot))

    assert _entity_by_suffix(entities, "current_account_balance").name == "E.ON Current Account Balance"
    assert _entity_by_suffix(entities, "latest_statement_closing_balance").name == "E.ON Latest Statement Closing Balance"
    assert _entity_by_suffix(entities, "latest_statement_charges").name == "E.ON Latest Statement Charges"
    assert _entity_by_suffix(entities, "gas_unit_rate").name == "E.ON Gas Unit Rate"
    assert _entity_by_suffix(entities, "gas_standing_charge").name == "E.ON Gas Standing Charge"
    assert _entity_by_suffix(entities, "latest_gas_meter_reading").name == "E.ON Latest Gas Meter Reading"
```

- [ ] **Step 2: Run the focused sensor tests and confirm they fail**

Run:

```bash
./.venv/bin/python -m pytest \
  tests/components/eon_next/test_sensor.py::test_electricity_current_rate_sensor_exposes_value_unit_and_attributes \
  tests/components/eon_next/test_sensor.py::test_electricity_standing_charge_and_meter_sensors_use_explicit_names \
  tests/components/eon_next/test_sensor.py::test_gas_and_billing_sensor_names_remain_unchanged \
  -q
```

Expected: FAIL because the current electricity names, unique-id suffixes, and attribute labels are still generic.

- [ ] **Step 3: Rename electricity-specific constants and sensor descriptions**

Replace the electricity-related constants in `custom_components/eon_next/const.py` with:

```python
ATTR_ELECTRICITY_TARIFF_NAME = "electricity_tariff_name"
ATTR_ELECTRICITY_TARIFF_CODE = "electricity_tariff_code"
ATTR_ELECTRICITY_STANDING_CHARGE_GBP_PER_DAY = "electricity_standing_charge_gbp_per_day"
ATTR_ELECTRICITY_PRE_VAT_STANDING_CHARGE_GBP_PER_DAY = (
    "electricity_pre_vat_standing_charge_gbp_per_day"
)
ATTR_ELECTRICITY_CURRENT_WINDOW_END = "electricity_current_window_end"
ATTR_ELECTRICITY_NEXT_WINDOW_START = "electricity_next_window_start"
ATTR_ELECTRICITY_AGREEMENT_VALID_FROM = "electricity_agreement_valid_from"
ATTR_ELECTRICITY_AGREEMENT_VALID_TO = "electricity_agreement_valid_to"
ATTR_ELECTRICITY_METER_POINT_MPAN = "electricity_meter_point_mpan"
ATTR_LATEST_ELECTRICITY_METER_READING_SOURCE = "latest_electricity_meter_reading_source"
ATTR_LATEST_ELECTRICITY_METER_READING_TYPE = "latest_electricity_meter_reading_type"
ATTR_LATEST_ELECTRICITY_METER_READING_REGISTER_IDENTIFIER = (
    "latest_electricity_meter_reading_register_identifier"
)
ATTR_LATEST_ELECTRICITY_METER_READING_REGISTER_NAME = "latest_electricity_meter_reading_register_name"
ATTR_LATEST_ELECTRICITY_METER_READING_REGISTER_DIGITS = (
    "latest_electricity_meter_reading_register_digits"
)
ATTR_LATEST_ELECTRICITY_METER_READING_REGISTER_IS_QUARANTINED = (
    "latest_electricity_meter_reading_register_is_quarantined"
)
```

Keep these existing constants unchanged:

```python
ATTR_ACCOUNT_NUMBER = "account_number"
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

In `custom_components/eon_next/sensor.py`, replace the electricity sensor descriptions and electricity attribute mappings with:

```python
EonRateSensorDescription(
    key="electricity_current_import_rate",
    name="E.ON Electricity Current Import Rate",
    native_unit_of_measurement=RATE_UNIT,
    value_attr="current_rate_gbp_per_kwh",
    unique_id_suffix="electricity_current_import_rate",
    attribute_fields={
        ATTR_ACCOUNT_NUMBER: "account_number",
        ATTR_ELECTRICITY_TARIFF_NAME: "tariff_name",
        ATTR_ELECTRICITY_TARIFF_CODE: "tariff_code",
        ATTR_ELECTRICITY_STANDING_CHARGE_GBP_PER_DAY: "standing_charge_gbp_per_day",
        ATTR_ELECTRICITY_PRE_VAT_STANDING_CHARGE_GBP_PER_DAY: "pre_vat_standing_charge_gbp_per_day",
        ATTR_ELECTRICITY_CURRENT_WINDOW_END: "current_window_end",
        ATTR_ELECTRICITY_NEXT_WINDOW_START: "next_window_start",
        ATTR_ELECTRICITY_AGREEMENT_VALID_FROM: "agreement_valid_from",
        ATTR_ELECTRICITY_AGREEMENT_VALID_TO: "agreement_valid_to",
    },
),
EonRateSensorDescription(
    key="electricity_next_import_rate",
    name="E.ON Electricity Next Import Rate",
    native_unit_of_measurement=RATE_UNIT,
    value_attr="next_rate_gbp_per_kwh",
    unique_id_suffix="electricity_next_import_rate",
),
EonRateSensorDescription(
    key="electricity_next_rate_change_at",
    name="E.ON Electricity Next Rate Change",
    device_class=SensorDeviceClass.TIMESTAMP,
    value_attr="next_rate_change_at",
    unique_id_suffix="electricity_next_rate_change_at",
),
EonRateSensorDescription(
    key="electricity_standing_charge",
    name="E.ON Electricity Standing Charge",
    native_unit_of_measurement=CHARGE_UNIT,
    value_attr="standing_charge_gbp_per_day",
    unique_id_suffix="electricity_standing_charge",
),
EonRateSensorDescription(
    key="electricity_standing_charge_ex_vat",
    name="E.ON Electricity Standing Charge Ex VAT",
    native_unit_of_measurement=CHARGE_UNIT,
    value_attr="pre_vat_standing_charge_gbp_per_day",
    unique_id_suffix="electricity_standing_charge_ex_vat",
),
EonRateSensorDescription(
    key="latest_electricity_meter_reading",
    name="E.ON Latest Electricity Meter Reading",
    native_unit_of_measurement=READING_UNIT,
    value_attr="latest_meter_reading_kwh",
    unique_id_suffix="latest_electricity_meter_reading",
    attribute_fields={
        ATTR_ELECTRICITY_METER_POINT_MPAN: "meter_point_mpan",
        ATTR_LATEST_ELECTRICITY_METER_READING_SOURCE: "latest_meter_reading_source",
        ATTR_LATEST_ELECTRICITY_METER_READING_TYPE: "latest_meter_reading_type",
        ATTR_LATEST_ELECTRICITY_METER_READING_REGISTER_IDENTIFIER:
            "latest_meter_reading_register_identifier",
        ATTR_LATEST_ELECTRICITY_METER_READING_REGISTER_NAME:
            "latest_meter_reading_register_name",
        ATTR_LATEST_ELECTRICITY_METER_READING_REGISTER_DIGITS:
            "latest_meter_reading_register_digits",
        ATTR_LATEST_ELECTRICITY_METER_READING_REGISTER_IS_QUARANTINED:
            "latest_meter_reading_register_is_quarantined",
    },
),
EonRateSensorDescription(
    key="latest_electricity_meter_reading_at",
    name="E.ON Latest Electricity Meter Reading Time",
    device_class=SensorDeviceClass.TIMESTAMP,
    value_attr="latest_meter_reading_at",
    unique_id_suffix="latest_electricity_meter_reading_at",
),
```

Update the import block in the same file so it imports the renamed electricity constants instead of the old generic electricity ones.

- [ ] **Step 4: Run the full sensor test file**

Run:

```bash
./.venv/bin/python -m pytest tests/components/eon_next/test_sensor.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit the electricity sensor rename**

```bash
git add custom_components/eon_next/const.py custom_components/eon_next/sensor.py tests/components/eon_next/test_sensor.py
git commit -m "refactor: rename electricity sensor surface"
```

---

### Task 2: Migrate old electricity entity IDs to the renamed ones

**Files:**
- Modify: `custom_components/eon_next/__init__.py`
- Modify: `tests/components/eon_next/test_init.py`

- [ ] **Step 1: Write the failing migration test first**

Extend the `integration_stubs` fixture in `tests/components/eon_next/test_init.py` with an entity-registry stub:

```python
entity_registry = types.ModuleType("homeassistant.helpers.entity_registry")


class _RegistryEntry:
    def __init__(self, unique_id: str) -> None:
        self.unique_id = unique_id


class _EntityRegistry:
    def __init__(self) -> None:
        self.entries: dict[tuple[str, str], _RegistryEntry] = {}
        self.update_calls: list[tuple[str, str]] = []

    def async_get_entity_id(self, domain: str, platform: str, unique_id: str) -> str | None:
        return unique_id if (domain, unique_id) in self.entries else None

    def async_update_entity(self, entity_id: str, *, new_unique_id: str) -> None:
        old_key = (DOMAIN, entity_id)
        entry = self.entries.pop(old_key)
        entry.unique_id = new_unique_id
        self.entries[(DOMAIN, new_unique_id)] = entry
        self.update_calls.append((entity_id, new_unique_id))


registry = _EntityRegistry()
entity_registry.RegistryEntry = _RegistryEntry
helpers.entity_registry = entity_registry
entity_registry.async_get = lambda hass: registry
```

Add this test to `tests/components/eon_next/test_init.py`:

```python
@pytest.mark.asyncio
async def test_async_setup_entry_migrates_old_electricity_unique_ids(init_module, monkeypatch) -> None:
    hass = init_module.HomeAssistant()
    entry = init_module.ConfigEntry(
        entry_id="entry-123",
        data={
            "username": "example@example.invalid",
            "password": "secret",
            "account_number": "A-TEST0001",
        },
    )
    registry = sys.modules["homeassistant.helpers.entity_registry"].async_get(hass)
    entry_type = sys.modules["homeassistant.helpers.entity_registry"].RegistryEntry
    registry.entries[(DOMAIN, "entry-123_current_import_rate")] = entry_type(
        "entry-123_current_import_rate"
    )
    registry.entries[(DOMAIN, "entry-123_next_import_rate")] = entry_type(
        "entry-123_next_import_rate"
    )

    class _Client:
        def __init__(self, session, *, email: str, password: str, account_number: str) -> None:
            pass

    class _Coordinator:
        def __init__(self, hass, client) -> None:
            self.first_refreshes = 0

        async def async_config_entry_first_refresh(self) -> None:
            self.first_refreshes += 1

    monkeypatch.setattr(init_module, "EonNextRatesClient", _Client)
    monkeypatch.setattr(init_module, "EonNextRatesCoordinator", _Coordinator)

    await init_module.async_setup_entry(hass, entry)

    assert registry.update_calls == [
        ("entry-123_current_import_rate", "entry-123_electricity_current_import_rate"),
        ("entry-123_next_import_rate", "entry-123_electricity_next_import_rate"),
    ]
```

- [ ] **Step 2: Run the migration test and confirm it fails**

Run:

```bash
./.venv/bin/python -m pytest tests/components/eon_next/test_init.py::test_async_setup_entry_migrates_old_electricity_unique_ids -q
```

Expected: FAIL because `async_setup_entry()` does not yet perform any entity-registry migration.

- [ ] **Step 3: Add the unique-id migration hook**

Add this helper to `custom_components/eon_next/__init__.py` above `async_setup_entry()`:

```python
ELECTRICITY_UNIQUE_ID_MIGRATIONS = {
    "current_import_rate": "electricity_current_import_rate",
    "next_import_rate": "electricity_next_import_rate",
    "next_rate_change_at": "electricity_next_rate_change_at",
    "standing_charge": "electricity_standing_charge",
    "standing_charge_ex_vat": "electricity_standing_charge_ex_vat",
    "latest_meter_reading": "latest_electricity_meter_reading",
    "latest_meter_reading_at": "latest_electricity_meter_reading_at",
}


async def _async_migrate_electricity_unique_ids(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)

    for old_suffix, new_suffix in ELECTRICITY_UNIQUE_ID_MIGRATIONS.items():
        old_unique_id = f"{entry.entry_id}_{old_suffix}"
        new_unique_id = f"{entry.entry_id}_{new_suffix}"

        old_entity_id = registry.async_get_entity_id("sensor", DOMAIN, old_unique_id)
        if old_entity_id is None:
            continue

        if registry.async_get_entity_id("sensor", DOMAIN, new_unique_id) is not None:
            continue

        registry.async_update_entity(old_entity_id, new_unique_id=new_unique_id)
```

Call the helper at the start of `async_setup_entry()`:

```python
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    await _async_migrate_electricity_unique_ids(hass, entry)

    client = EonNextRatesClient(
        async_get_clientsession(hass),
        email=entry.data["username"],
        password=entry.data["password"],
        account_number=entry.data["account_number"],
    )
    coordinator = EonNextRatesCoordinator(hass, client)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True
```

- [ ] **Step 4: Run the init test file**

Run:

```bash
./.venv/bin/python -m pytest tests/components/eon_next/test_init.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit the migration support**

```bash
git add custom_components/eon_next/__init__.py tests/components/eon_next/test_init.py
git commit -m "feat: migrate electricity entity IDs"
```

---

### Task 3: Update README wording and verify the full rename slice

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Make the README electricity wording explicit**

Update the current-features list in `README.md` to:

```markdown
## Current features

- Live VAT-inclusive electricity import rate
- Next electricity import rate when E.ON publishes a later tariff window
- Next electricity rate change timestamp when available
- Electricity standing charge sensors including pre-VAT standing charge
- Active electricity tariff metadata, including agreement window attributes
- Latest electricity meter reading and reading timestamp when available
- Current account balance and latest statement amounts when available
- Gas unit rate, standing charge, tariff metadata, and latest gas meter reading when available
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
git commit -m "docs: clarify electricity entity naming"
```
