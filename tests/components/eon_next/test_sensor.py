from __future__ import annotations

import importlib
import sys
import types
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.eon_next.api import AccountSnapshot
from custom_components.eon_next.const import DOMAIN


@pytest.fixture
def homeassistant_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(sys.modules):
        if name.startswith("homeassistant"):
            monkeypatch.delitem(sys.modules, name, raising=False)

    homeassistant = types.ModuleType("homeassistant")

    config_entries = types.ModuleType("homeassistant.config_entries")

    @dataclass
    class ConfigEntry:
        entry_id: str = "entry-123"
        runtime_data: object | None = None

    config_entries.ConfigEntry = ConfigEntry

    const = types.ModuleType("homeassistant.const")
    const.CURRENCY_GBP = "GBP"

    core = types.ModuleType("homeassistant.core")

    class HomeAssistant:
        def __init__(self) -> None:
            self.data: dict[str, object] = {}

    core.HomeAssistant = HomeAssistant

    entity_platform = types.ModuleType("homeassistant.helpers.entity_platform")
    entity_platform.AddEntitiesCallback = object

    sensor = types.ModuleType("homeassistant.components.sensor")

    @dataclass(frozen=True, kw_only=True)
    class SensorEntityDescription:
        key: str
        name: str
        native_unit_of_measurement: str | None = None
        device_class: str | None = None

    class SensorEntity:
        entity_description: SensorEntityDescription
        _attr_unique_id: str | None = None

        @property
        def native_value(self):
            return None

        @property
        def native_unit_of_measurement(self):
            return self.entity_description.native_unit_of_measurement

        @property
        def extra_state_attributes(self):
            return None

        @property
        def name(self):
            return self.entity_description.name

        @property
        def unique_id(self):
            return self._attr_unique_id

    class SensorDeviceClass:
        TIMESTAMP = "timestamp"

    sensor.SensorEntity = SensorEntity
    sensor.SensorEntityDescription = SensorEntityDescription
    sensor.SensorDeviceClass = SensorDeviceClass

    update_coordinator = types.ModuleType("homeassistant.helpers.update_coordinator")

    class UpdateFailed(Exception):
        pass

    class DataUpdateCoordinator:
        def __class_getitem__(cls, item):
            return cls

        def __init__(
            self,
            hass,
            logger,
            *,
            name: str,
            update_interval: timedelta,
        ) -> None:
            self.hass = hass
            self.logger = logger
            self.name = name
            self.update_interval = update_interval
            self.data = None

    class CoordinatorEntity:
        def __init__(self, coordinator) -> None:
            self.coordinator = coordinator

    update_coordinator.UpdateFailed = UpdateFailed
    update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator
    update_coordinator.CoordinatorEntity = CoordinatorEntity

    modules = {
        "homeassistant": homeassistant,
        "homeassistant.config_entries": config_entries,
        "homeassistant.const": const,
        "homeassistant.core": core,
        "homeassistant.components.sensor": sensor,
        "homeassistant.helpers.entity_platform": entity_platform,
        "homeassistant.helpers.update_coordinator": update_coordinator,
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)


@pytest.fixture
def sensor_module(homeassistant_stubs):
    sys.modules.pop("custom_components.eon_next.sensor", None)
    return importlib.import_module("custom_components.eon_next.sensor")


@pytest.fixture
def coordinator_module(homeassistant_stubs):
    sys.modules.pop("custom_components.eon_next.coordinator", None)
    return importlib.import_module("custom_components.eon_next.coordinator")


@pytest.fixture
def snapshot() -> AccountSnapshot:
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
        current_account_balance_gbp=123.45,
        latest_statement_issued_at=datetime(2026, 4, 20, 0, 0, tzinfo=UTC),
        latest_statement_period_start=datetime(2026, 3, 21, 0, 0, tzinfo=UTC),
        latest_statement_period_end=datetime(2026, 4, 19, 0, 0, tzinfo=UTC),
        latest_statement_payment_due_at=datetime(2026, 5, 5, 0, 0, tzinfo=UTC),
        latest_statement_opening_balance_gbp=370.23,
        latest_statement_closing_balance_gbp=98.76,
        latest_statement_charges_gbp=54.32,
        latest_statement_credits_gbp=0,
        latest_direct_debit_amount_gbp=400.05,
        latest_direct_debit_at=datetime(2026, 4, 1, 0, 0, tzinfo=UTC),
        latest_electricity_statement_total_gbp=290.51,
        latest_electricity_statement_quantity_kwh=1571.748,
        latest_electricity_statement_usage_cost_gbp=271.91,
        latest_electricity_statement_standing_charge_gbp=18.6,
        latest_gas_statement_total_gbp=169.16,
        latest_gas_statement_quantity_kwh=2721.06,
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
    )


class _DummyCoordinator:
    def __init__(self, data: AccountSnapshot) -> None:
        self.data = data


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

    assert len(added_entities) == 30
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


def test_standing_charge_and_account_number_sensors_expose_expected_values(
    sensor_module, snapshot
) -> None:
    entities = sensor_module._build_sensors("entry-123", _DummyCoordinator(snapshot))
    standing_charge_sensor = entities[3]
    pre_vat_standing_charge_sensor = entities[4]
    account_number_sensor = entities[5]

    assert standing_charge_sensor.native_value == 0.6000015
    assert standing_charge_sensor.native_unit_of_measurement == "GBP/day"
    assert pre_vat_standing_charge_sensor.native_value == 0.57143
    assert pre_vat_standing_charge_sensor.native_unit_of_measurement == "GBP/day"
    assert account_number_sensor.native_value == "A-TEST0001"
    assert account_number_sensor.native_unit_of_measurement is None


def test_next_rate_change_sensor_exposes_expected_datetime(sensor_module, snapshot) -> None:
    entities = sensor_module._build_sensors("entry-123", _DummyCoordinator(snapshot))
    next_change_sensor = _entity_by_suffix(entities, "electricity_next_rate_change_at")

    assert next_change_sensor.name == "E.ON Electricity Next Rate Change"
    assert next_change_sensor.unique_id == "entry-123_electricity_next_rate_change_at"
    assert next_change_sensor.native_value == datetime(2026, 5, 1, 12, 30, tzinfo=UTC)


def test_electricity_standing_charge_and_meter_sensors_use_explicit_names(
    sensor_module, snapshot
) -> None:
    entities = sensor_module._build_sensors("entry-123", _DummyCoordinator(snapshot))
    next_import_rate_sensor = _entity_by_suffix(entities, "electricity_next_import_rate")
    next_rate_change_sensor = _entity_by_suffix(entities, "electricity_next_rate_change_at")
    standing_charge_sensor = _entity_by_suffix(entities, "electricity_standing_charge")
    standing_charge_ex_vat_sensor = _entity_by_suffix(
        entities, "electricity_standing_charge_ex_vat"
    )
    latest_meter_reading_sensor = _entity_by_suffix(
        entities, "latest_electricity_meter_reading"
    )
    latest_meter_reading_at_sensor = _entity_by_suffix(
        entities, "latest_electricity_meter_reading_at"
    )

    assert next_import_rate_sensor.name == "E.ON Electricity Next Import Rate"
    assert next_rate_change_sensor.name == "E.ON Electricity Next Rate Change"
    assert standing_charge_sensor.name == "E.ON Electricity Standing Charge"
    assert standing_charge_ex_vat_sensor.name == "E.ON Electricity Standing Charge Ex VAT"
    assert latest_meter_reading_sensor.name == "E.ON Latest Electricity Meter Reading"
    assert latest_meter_reading_at_sensor.name == "E.ON Latest Electricity Meter Reading Time"

    assert standing_charge_sensor.native_value == 0.6000015
    assert standing_charge_sensor.native_unit_of_measurement == "GBP/day"
    assert standing_charge_ex_vat_sensor.native_value == 0.57143
    assert standing_charge_ex_vat_sensor.native_unit_of_measurement == "GBP/day"
    assert latest_meter_reading_sensor.native_value == 12346.0
    assert latest_meter_reading_sensor.native_unit_of_measurement == "kWh"
    assert latest_meter_reading_sensor.extra_state_attributes == {
        "electricity_meter_point_mpan": "0012345678901",
        "latest_electricity_meter_reading_source": "SMART",
        "latest_electricity_meter_reading_type": "actual",
        "latest_electricity_meter_reading_register_identifier": "00001",
        "latest_electricity_meter_reading_register_name": "IMP",
        "latest_electricity_meter_reading_register_digits": 5,
        "latest_electricity_meter_reading_register_is_quarantined": False,
    }
    assert latest_meter_reading_at_sensor.native_value == datetime(
        2026, 5, 2, 11, 0, tzinfo=UTC
    )


def test_gas_and_billing_sensor_names_remain_unchanged(sensor_module, snapshot) -> None:
    entities = sensor_module._build_sensors("entry-123", _DummyCoordinator(snapshot))

    assert _entity_by_suffix(entities, "current_account_balance").name == (
        "E.ON Current Account Balance"
    )
    assert _entity_by_suffix(entities, "latest_statement_closing_balance").name == (
        "E.ON Latest Statement Closing Balance"
    )
    assert _entity_by_suffix(entities, "latest_statement_charges").name == (
        "E.ON Latest Statement Charges"
    )
    assert _entity_by_suffix(entities, "gas_unit_rate").name == "E.ON Gas Unit Rate"
    assert _entity_by_suffix(entities, "gas_standing_charge").name == (
        "E.ON Gas Standing Charge"
    )
    assert _entity_by_suffix(entities, "gas_standing_charge_ex_vat").name == (
        "E.ON Gas Standing Charge Ex VAT"
    )
    assert _entity_by_suffix(entities, "latest_gas_meter_reading").name == (
        "E.ON Latest Gas Meter Reading"
    )
    assert _entity_by_suffix(entities, "latest_gas_meter_reading_at").name == (
        "E.ON Latest Gas Meter Reading Time"
    )


def test_billing_sensors_expose_expected_values(sensor_module, snapshot) -> None:
    entities = sensor_module._build_sensors("entry-123", _DummyCoordinator(snapshot))

    current_balance_sensor = _entity_by_suffix(entities, "current_account_balance")
    statement_closing_balance_sensor = _entity_by_suffix(
        entities, "latest_statement_closing_balance"
    )
    statement_charges_sensor = _entity_by_suffix(entities, "latest_statement_charges")

    assert current_balance_sensor.name == "E.ON Current Account Balance"
    assert current_balance_sensor.native_value == 123.45
    assert current_balance_sensor.native_unit_of_measurement == "GBP"
    assert statement_closing_balance_sensor.name == "E.ON Latest Statement Closing Balance"
    assert statement_closing_balance_sensor.native_value == 98.76
    assert statement_closing_balance_sensor.native_unit_of_measurement == "GBP"
    assert statement_charges_sensor.name == "E.ON Latest Statement Charges"
    assert statement_charges_sensor.native_value == 54.32
    assert statement_charges_sensor.native_unit_of_measurement == "GBP"


def test_statement_date_sensors_expose_expected_timestamps(sensor_module, snapshot) -> None:
    entities = sensor_module._build_sensors("entry-123", _DummyCoordinator(snapshot))

    assert _entity_by_suffix(entities, "latest_statement_issued_at").native_value == datetime(
        2026, 4, 20, 0, 0, tzinfo=UTC
    )
    assert _entity_by_suffix(entities, "latest_statement_period_start").native_value == datetime(
        2026, 3, 21, 0, 0, tzinfo=UTC
    )
    assert _entity_by_suffix(entities, "latest_statement_period_end").native_value == datetime(
        2026, 4, 19, 0, 0, tzinfo=UTC
    )
    assert _entity_by_suffix(entities, "latest_statement_payment_due_at").native_value == datetime(
        2026, 5, 5, 0, 0, tzinfo=UTC
    )
    assert _entity_by_suffix(entities, "latest_direct_debit_at").native_value == datetime(
        2026, 4, 1, 0, 0, tzinfo=UTC
    )


def test_statement_amount_sensors_expose_expected_values(sensor_module, snapshot) -> None:
    entities = sensor_module._build_sensors("entry-123", _DummyCoordinator(snapshot))

    assert _entity_by_suffix(entities, "latest_statement_opening_balance").native_value == 370.23
    assert _entity_by_suffix(entities, "latest_statement_closing_balance").native_value == 98.76
    assert _entity_by_suffix(entities, "latest_statement_charges").native_value == 54.32
    assert _entity_by_suffix(entities, "latest_statement_credits").native_value == 0
    assert _entity_by_suffix(entities, "latest_direct_debit_amount").native_value == 400.05


def test_statement_fuel_breakdown_sensors_expose_expected_values(
    sensor_module, snapshot
) -> None:
    entities = sensor_module._build_sensors("entry-123", _DummyCoordinator(snapshot))

    assert (
        _entity_by_suffix(entities, "latest_electricity_statement_total").native_value
        == 290.51
    )
    assert (
        _entity_by_suffix(entities, "latest_electricity_statement_quantity").native_value
        == 1571.748
    )
    assert (
        _entity_by_suffix(entities, "latest_electricity_statement_usage_cost").native_value
        == 271.91
    )
    assert _entity_by_suffix(
        entities, "latest_electricity_statement_standing_charge"
    ).native_value == 18.6
    assert _entity_by_suffix(entities, "latest_gas_statement_total").native_value == 169.16
    assert _entity_by_suffix(entities, "latest_gas_statement_quantity").native_value == 2721.06


def test_gas_rate_and_charge_sensors_expose_expected_values(
    sensor_module, snapshot
) -> None:
    entities = sensor_module._build_sensors("entry-123", _DummyCoordinator(snapshot))

    gas_rate_sensor = _entity_by_suffix(entities, "gas_unit_rate")
    gas_standing_charge_sensor = _entity_by_suffix(entities, "gas_standing_charge")
    gas_standing_charge_ex_vat_sensor = _entity_by_suffix(
        entities, "gas_standing_charge_ex_vat"
    )

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
    assert gas_standing_charge_sensor.name == "E.ON Gas Standing Charge"
    assert gas_standing_charge_sensor.native_value == 0.312
    assert gas_standing_charge_sensor.native_unit_of_measurement == "GBP/day"
    assert gas_standing_charge_ex_vat_sensor.name == "E.ON Gas Standing Charge Ex VAT"
    assert gas_standing_charge_ex_vat_sensor.native_value == 0.297
    assert gas_standing_charge_ex_vat_sensor.native_unit_of_measurement == "GBP/day"


def test_latest_gas_meter_reading_sensors_expose_expected_values(
    sensor_module, snapshot
) -> None:
    entities = sensor_module._build_sensors("entry-123", _DummyCoordinator(snapshot))

    gas_reading_sensor = _entity_by_suffix(entities, "latest_gas_meter_reading")
    gas_reading_timestamp_sensor = _entity_by_suffix(
        entities, "latest_gas_meter_reading_at"
    )

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
    assert gas_reading_timestamp_sensor.name == "E.ON Latest Gas Meter Reading Time"
    assert gas_reading_timestamp_sensor.native_value == datetime(
        2026, 5, 2, 13, 0, tzinfo=UTC
    )


def test_optional_billing_and_gas_sensors_return_none_when_data_is_absent(
    sensor_module, snapshot
) -> None:
    snapshot_without_optional_data = replace(
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
    entities = sensor_module._build_sensors(
        "entry-123", _DummyCoordinator(snapshot_without_optional_data)
    )

    assert _entity_by_suffix(entities, "current_account_balance").native_value is None
    assert (
        _entity_by_suffix(entities, "latest_statement_closing_balance").native_value
        is None
    )
    assert _entity_by_suffix(entities, "latest_statement_charges").native_value is None
    assert _entity_by_suffix(entities, "gas_unit_rate").native_value is None
    assert _entity_by_suffix(entities, "gas_unit_rate").extra_state_attributes == {
        "gas_tariff_name": None,
        "gas_tariff_code": None,
        "gas_pre_vat_rate_gbp_per_kwh": None,
        "gas_agreement_valid_from": None,
        "gas_agreement_valid_to": None,
        "gas_meter_point_mprn": None,
    }
    assert _entity_by_suffix(entities, "gas_standing_charge").native_value is None
    assert _entity_by_suffix(entities, "gas_standing_charge_ex_vat").native_value is None
    assert _entity_by_suffix(entities, "latest_gas_meter_reading").native_value is None
    assert _entity_by_suffix(entities, "latest_gas_meter_reading_at").native_value is None
    assert _entity_by_suffix(entities, "latest_gas_meter_reading").extra_state_attributes == {
        "gas_meter_point_mprn": None,
        "latest_gas_meter_reading_source": None,
        "latest_gas_meter_reading_type": None,
        "latest_gas_meter_reading_register_identifier": None,
        "latest_gas_meter_reading_register_name": None,
        "latest_gas_meter_reading_register_digits": None,
        "latest_gas_meter_reading_register_is_quarantined": None,
    }


def test_optional_statement_breakdown_sensors_return_none_when_data_is_absent(
    sensor_module, snapshot
) -> None:
    snapshot_without_statement_breakdown = replace(
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
    entities = sensor_module._build_sensors(
        "entry-123", _DummyCoordinator(snapshot_without_statement_breakdown)
    )

    assert _entity_by_suffix(entities, "latest_statement_issued_at").native_value is None
    assert _entity_by_suffix(entities, "latest_statement_period_start").native_value is None
    assert _entity_by_suffix(entities, "latest_statement_period_end").native_value is None
    assert _entity_by_suffix(entities, "latest_statement_payment_due_at").native_value is None
    assert _entity_by_suffix(entities, "latest_statement_opening_balance").native_value is None
    assert _entity_by_suffix(entities, "latest_statement_closing_balance").native_value is None
    assert _entity_by_suffix(entities, "latest_statement_charges").native_value is None
    assert _entity_by_suffix(entities, "latest_statement_credits").native_value is None
    assert _entity_by_suffix(entities, "latest_direct_debit_amount").native_value is None
    assert _entity_by_suffix(entities, "latest_direct_debit_at").native_value is None
    assert _entity_by_suffix(entities, "latest_electricity_statement_total").native_value is None
    assert (
        _entity_by_suffix(entities, "latest_electricity_statement_quantity").native_value
        is None
    )
    assert (
        _entity_by_suffix(entities, "latest_electricity_statement_usage_cost").native_value
        is None
    )
    assert (
        _entity_by_suffix(entities, "latest_electricity_statement_standing_charge").native_value
        is None
    )
    assert _entity_by_suffix(entities, "latest_gas_statement_total").native_value is None
    assert _entity_by_suffix(entities, "latest_gas_statement_quantity").native_value is None


@pytest.mark.asyncio
async def test_coordinator_fetches_snapshot_and_uses_default_interval(
    coordinator_module, snapshot
) -> None:
    class _Client:
        def __init__(self) -> None:
            self.calls = 0

        async def async_get_account_snapshot(self) -> AccountSnapshot:
            self.calls += 1
            return snapshot

    client = _Client()
    coordinator = coordinator_module.EonNextRatesCoordinator(hass=object(), client=client)

    result = await coordinator._async_update_data()

    assert result == snapshot
    assert client.calls == 1
    assert coordinator.update_interval == timedelta(minutes=1)


@pytest.mark.asyncio
async def test_coordinator_wraps_client_errors_in_update_failed(coordinator_module) -> None:
    class _Client:
        async def async_get_account_snapshot(self) -> AccountSnapshot:
            raise coordinator_module.EonNextRatesError("boom")

    coordinator = coordinator_module.EonNextRatesCoordinator(hass=object(), client=_Client())

    with pytest.raises(coordinator_module.UpdateFailed, match="boom"):
        await coordinator._async_update_data()
