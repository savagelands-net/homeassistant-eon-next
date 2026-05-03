from __future__ import annotations

import importlib
import sys
import types
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.eon_next.api import (
    AccountSnapshot,
    SmartFlexChargingSessionSnapshot,
    SmartFlexCompletedDispatchSnapshot,
    SmartFlexDeviceSnapshot,
    SmartFlexPlannedDispatchSnapshot,
    SmartFlexReadingSnapshot,
    SmartFlexSocLimitSnapshot,
)
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
        unload_callbacks: list[object] | None = None

        def __post_init__(self) -> None:
            if self.unload_callbacks is None:
                self.unload_callbacks = []

        def async_on_unload(self, callback):
            self.unload_callbacks.append(callback)

        def async_unload(self) -> None:
            for callback in list(self.unload_callbacks):
                callback()

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

    def async_add_listener(self, update_callback):
        return lambda: None


class _ListenerCoordinator(_DummyCoordinator):
    def __init__(self, data: AccountSnapshot) -> None:
        super().__init__(data)
        self._listeners = []

    def async_add_listener(self, update_callback):
        self._listeners.append(update_callback)

        def _remove_listener() -> None:
            self._listeners.remove(update_callback)

        return _remove_listener

    def async_set_updated_data(self, data: AccountSnapshot) -> None:
        self.data = data
        for listener in list(self._listeners):
            listener()


_DEFAULT = object()


def _entity_by_suffix(entities, suffix: str):
    return next(entity for entity in entities if entity.unique_id == f"entry-123_{suffix}")


def _build_smartflex_device_snapshot(
    *,
    device_id: str = "charger-001",
    name: str = "Driveway Charger",
    device_type: str = "EV_CHARGER",
    provider: str = "EON_NEXT_DRIVE",
    integration_device_id: str = "integration-charger-001",
    property_id: str = "property-001",
    make: str = "Wallbox",
    model: str = "Pulsar Plus",
    vehicle_battery_size_kwh: float | None = None,
    charge_point_power_output_kw: float | None = 7.4,
    lifecycle_status: str | None = "LIVE",
    current_state: str | None = "CHARGING",
    is_suspended: bool | None = False,
    state_of_charge: SmartFlexReadingSnapshot | None | object = _DEFAULT,
    active_power: SmartFlexReadingSnapshot | None | object = _DEFAULT,
    state_of_charge_limit: SmartFlexSocLimitSnapshot | None | object = _DEFAULT,
    test_dispatch_failure_reason: str | None = None,
    latest_charging_session: SmartFlexChargingSessionSnapshot | None | object = _DEFAULT,
    next_planned_dispatch: SmartFlexPlannedDispatchSnapshot | None | object = _DEFAULT,
) -> SmartFlexDeviceSnapshot:
    if state_of_charge is _DEFAULT:
        state_of_charge = SmartFlexReadingSnapshot(
            timestamp=datetime(2026, 5, 1, 20, 10, tzinfo=UTC),
            value=55.0,
        )

    if active_power is _DEFAULT:
        active_power = SmartFlexReadingSnapshot(
            timestamp=datetime(2026, 5, 1, 20, 10, tzinfo=UTC),
            value=6.8,
        )

    if state_of_charge_limit is _DEFAULT:
        state_of_charge_limit = SmartFlexSocLimitSnapshot(
            upper_soc_limit=90.0,
            timestamp=datetime(2026, 5, 1, 20, 0, tzinfo=UTC),
            is_limit_violated=False,
        )

    if latest_charging_session is _DEFAULT:
        latest_charging_session = SmartFlexChargingSessionSnapshot(
            start=datetime(2026, 5, 1, 20, 0, tzinfo=UTC),
            end=datetime(2026, 5, 1, 21, 0, tzinfo=UTC),
            state_of_charge_change=23.0,
            state_of_charge_final=55.0,
            energy_added_value=5.6,
            energy_added_unit="kWh",
            cost_amount=1.12,
            cost_currency="GBP",
        )

    if next_planned_dispatch is _DEFAULT:
        next_planned_dispatch = SmartFlexPlannedDispatchSnapshot(
            start=datetime(2026, 5, 1, 21, 0, tzinfo=UTC),
            end=datetime(2026, 5, 1, 21, 30, tzinfo=UTC),
            dispatch_type="GRID_CHARGE",
            energy_added_kwh=2.5,
        )

    return SmartFlexDeviceSnapshot(
        device_id=device_id,
        name=name,
        device_type=device_type,
        provider=provider,
        integration_device_id=integration_device_id,
        property_id=property_id,
        make=make,
        model=model,
        vehicle_battery_size_kwh=vehicle_battery_size_kwh,
        charge_point_power_output_kw=charge_point_power_output_kw,
        lifecycle_status=lifecycle_status,
        current_state=current_state,
        is_suspended=is_suspended,
        state_of_charge=state_of_charge,
        active_power=active_power,
        state_of_charge_limit=state_of_charge_limit,
        test_dispatch_failure_reason=test_dispatch_failure_reason,
        latest_charging_session=latest_charging_session,
        next_planned_dispatch=next_planned_dispatch,
    )


def _build_completed_dispatch_snapshot() -> SmartFlexCompletedDispatchSnapshot:
    return SmartFlexCompletedDispatchSnapshot(
        start=datetime(2026, 5, 1, 18, 0, tzinfo=UTC),
        end=datetime(2026, 5, 1, 18, 30, tzinfo=UTC),
        delta=4.8,
        source="SMARTFLEX",
        location="HOME",
    )


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


@pytest.mark.asyncio
async def test_async_setup_entry_adds_smartflex_entities_when_data_arrives_later(
    sensor_module, snapshot
) -> None:
    hass = sensor_module.HomeAssistant()
    coordinator = _ListenerCoordinator(snapshot)
    hass.data = {DOMAIN: {"entry-123": {"coordinator": coordinator}}}
    entry = sensor_module.ConfigEntry(entry_id="entry-123")
    added_batches = []

    await sensor_module.async_setup_entry(
        hass,
        entry,
        lambda entities: added_batches.append(list(entities)),
    )

    coordinator.async_set_updated_data(
        replace(
            snapshot,
            smartflex_devices=(_build_smartflex_device_snapshot(),),
            latest_completed_dispatch=_build_completed_dispatch_snapshot(),
        )
    )

    assert len(added_batches) == 2
    assert len(added_batches[0]) == 30
    assert len(added_batches[1]) == 14
    assert {
        entity.unique_id for entity in added_batches[1]
    } == {
        "entry-123_smartflex_charger-001_current_state",
        "entry-123_smartflex_charger-001_state_of_charge",
        "entry-123_smartflex_charger-001_active_power",
        "entry-123_smartflex_charger-001_battery_size",
        "entry-123_smartflex_charger-001_charge_point_power_output",
        "entry-123_smartflex_charger-001_latest_charging_session_start",
        "entry-123_smartflex_charger-001_latest_charging_session_end",
        "entry-123_smartflex_charger-001_latest_charging_session_energy_added",
        "entry-123_smartflex_charger-001_latest_charging_session_cost",
        "entry-123_smartflex_charger-001_next_planned_dispatch_start",
        "entry-123_smartflex_charger-001_next_planned_dispatch_energy_added",
        "entry-123_smartflex_latest_completed_dispatch_start",
        "entry-123_smartflex_latest_completed_dispatch_end",
        "entry-123_smartflex_latest_completed_dispatch_delta",
    }


@pytest.mark.asyncio
async def test_async_setup_entry_registers_listener_unsubscribe_with_entry_unload(
    sensor_module, snapshot
) -> None:
    hass = sensor_module.HomeAssistant()
    coordinator = _ListenerCoordinator(snapshot)
    hass.data = {DOMAIN: {"entry-123": {"coordinator": coordinator}}}
    entry = sensor_module.ConfigEntry(entry_id="entry-123")

    await sensor_module.async_setup_entry(
        hass,
        entry,
        lambda entities: None,
    )

    assert len(entry.unload_callbacks) == 1
    assert len(coordinator._listeners) == 1

    entry.async_unload()

    assert coordinator._listeners == []


@pytest.mark.asyncio
async def test_async_setup_entry_does_not_add_duplicate_smartflex_entities_on_repeated_updates(
    sensor_module, snapshot
) -> None:
    hass = sensor_module.HomeAssistant()
    coordinator = _ListenerCoordinator(snapshot)
    hass.data = {DOMAIN: {"entry-123": {"coordinator": coordinator}}}
    entry = sensor_module.ConfigEntry(entry_id="entry-123")
    added_batches = []
    smartflex_snapshot = replace(
        snapshot,
        smartflex_devices=(_build_smartflex_device_snapshot(),),
        latest_completed_dispatch=_build_completed_dispatch_snapshot(),
    )

    await sensor_module.async_setup_entry(
        hass,
        entry,
        lambda entities: added_batches.append(list(entities)),
    )

    coordinator.async_set_updated_data(smartflex_snapshot)
    coordinator.async_set_updated_data(smartflex_snapshot)

    assert len(added_batches) == 2
    assert len(added_batches[0]) == 30
    assert len(added_batches[1]) == 14


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


def test_build_sensors_adds_smartflex_entities_for_each_device(
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
        latest_completed_dispatch=_build_completed_dispatch_snapshot(),
    )

    entities = sensor_module._build_sensors("entry-123", _DummyCoordinator(smartflex_snapshot))

    assert len(entities) == 55
    assert _entity_by_suffix(
        entities, "smartflex_charger-001_current_state"
    ).name == "E.ON Driveway Charger Current State"
    assert _entity_by_suffix(
        entities, "smartflex_vehicle-002_current_state"
    ).name == "E.ON Family EV Current State"
    assert _entity_by_suffix(
        entities, "smartflex_latest_completed_dispatch_delta"
    ).name == "E.ON Latest SmartFlex Completed Dispatch Delta"


def test_smartflex_device_sensors_expose_expected_values_and_attributes(
    sensor_module, snapshot
) -> None:
    smartflex_snapshot = replace(
        snapshot,
        smartflex_devices=(
            _build_smartflex_device_snapshot(test_dispatch_failure_reason="NONE"),
        ),
    )

    entities = sensor_module._build_sensors("entry-123", _DummyCoordinator(smartflex_snapshot))

    current_state_sensor = _entity_by_suffix(entities, "smartflex_charger-001_current_state")
    state_of_charge_sensor = _entity_by_suffix(entities, "smartflex_charger-001_state_of_charge")
    active_power_sensor = _entity_by_suffix(entities, "smartflex_charger-001_active_power")
    battery_size_sensor = _entity_by_suffix(entities, "smartflex_charger-001_battery_size")
    charge_point_power_output_sensor = _entity_by_suffix(
        entities, "smartflex_charger-001_charge_point_power_output"
    )
    latest_session_start_sensor = _entity_by_suffix(
        entities, "smartflex_charger-001_latest_charging_session_start"
    )
    latest_session_end_sensor = _entity_by_suffix(
        entities, "smartflex_charger-001_latest_charging_session_end"
    )
    latest_session_energy_sensor = _entity_by_suffix(
        entities, "smartflex_charger-001_latest_charging_session_energy_added"
    )
    latest_session_cost_sensor = _entity_by_suffix(
        entities, "smartflex_charger-001_latest_charging_session_cost"
    )
    next_dispatch_start_sensor = _entity_by_suffix(
        entities, "smartflex_charger-001_next_planned_dispatch_start"
    )
    next_dispatch_energy_sensor = _entity_by_suffix(
        entities, "smartflex_charger-001_next_planned_dispatch_energy_added"
    )

    assert current_state_sensor.name == "E.ON Driveway Charger Current State"
    assert current_state_sensor.native_value == "CHARGING"
    assert current_state_sensor.extra_state_attributes == {
        "smartflex_device_id": "charger-001",
        "smartflex_device_type": "EV_CHARGER",
        "smartflex_provider": "EON_NEXT_DRIVE",
        "smartflex_integration_device_id": "integration-charger-001",
        "smartflex_property_id": "property-001",
        "smartflex_make": "Wallbox",
        "smartflex_model": "Pulsar Plus",
        "smartflex_lifecycle_status": "LIVE",
        "smartflex_is_suspended": False,
        "smartflex_test_dispatch_failure_reason": "NONE",
    }

    assert state_of_charge_sensor.name == "E.ON Driveway Charger State Of Charge"
    assert state_of_charge_sensor.native_value == 55.0
    assert state_of_charge_sensor.native_unit_of_measurement == "%"
    assert state_of_charge_sensor.extra_state_attributes == {
        "smartflex_reading_timestamp": datetime(2026, 5, 1, 20, 10, tzinfo=UTC),
        "smartflex_upper_soc_limit": 90.0,
        "smartflex_soc_limit_timestamp": datetime(2026, 5, 1, 20, 0, tzinfo=UTC),
        "smartflex_is_soc_limit_violated": False,
    }

    assert active_power_sensor.name == "E.ON Driveway Charger Active Power"
    assert active_power_sensor.native_value == 6.8
    assert active_power_sensor.native_unit_of_measurement == "kW"
    assert active_power_sensor.extra_state_attributes == {
        "smartflex_reading_timestamp": datetime(2026, 5, 1, 20, 10, tzinfo=UTC)
    }

    assert battery_size_sensor.native_value is None
    assert battery_size_sensor.native_unit_of_measurement == "kWh"
    assert charge_point_power_output_sensor.native_value == 7.4
    assert charge_point_power_output_sensor.native_unit_of_measurement == "kW"

    assert latest_session_start_sensor.native_value == datetime(
        2026, 5, 1, 20, 0, tzinfo=UTC
    )
    assert latest_session_end_sensor.native_value == datetime(
        2026, 5, 1, 21, 0, tzinfo=UTC
    )
    assert latest_session_energy_sensor.native_value == 5.6
    assert latest_session_energy_sensor.native_unit_of_measurement == "kWh"
    assert latest_session_energy_sensor.extra_state_attributes == {
        "smartflex_latest_charging_session_start": datetime(
            2026, 5, 1, 20, 0, tzinfo=UTC
        ),
        "smartflex_latest_charging_session_end": datetime(
            2026, 5, 1, 21, 0, tzinfo=UTC
        ),
        "smartflex_latest_charging_session_soc_delta": 23.0,
        "smartflex_latest_charging_session_soc_final": 55.0,
    }
    assert latest_session_cost_sensor.native_value == 1.12
    assert latest_session_cost_sensor.native_unit_of_measurement == "GBP"
    assert latest_session_cost_sensor.extra_state_attributes == {
        "smartflex_latest_charging_session_start": datetime(
            2026, 5, 1, 20, 0, tzinfo=UTC
        ),
        "smartflex_latest_charging_session_end": datetime(
            2026, 5, 1, 21, 0, tzinfo=UTC
        ),
        "smartflex_latest_charging_session_soc_delta": 23.0,
        "smartflex_latest_charging_session_soc_final": 55.0,
    }

    assert next_dispatch_start_sensor.native_value == datetime(
        2026, 5, 1, 21, 0, tzinfo=UTC
    )
    assert next_dispatch_start_sensor.extra_state_attributes == {
        "smartflex_next_planned_dispatch_end": datetime(
            2026, 5, 1, 21, 30, tzinfo=UTC
        ),
        "smartflex_next_planned_dispatch_type": "GRID_CHARGE",
    }
    assert next_dispatch_energy_sensor.native_value == 2.5
    assert next_dispatch_energy_sensor.native_unit_of_measurement == "kWh"
    assert next_dispatch_energy_sensor.extra_state_attributes == {
        "smartflex_next_planned_dispatch_start": datetime(
            2026, 5, 1, 21, 0, tzinfo=UTC
        ),
        "smartflex_next_planned_dispatch_end": datetime(
            2026, 5, 1, 21, 30, tzinfo=UTC
        ),
        "smartflex_next_planned_dispatch_type": "GRID_CHARGE",
    }


def test_account_level_completed_dispatch_sensors_expose_expected_values(
    sensor_module, snapshot
) -> None:
    smartflex_snapshot = replace(
        snapshot,
        latest_completed_dispatch=_build_completed_dispatch_snapshot(),
    )

    entities = sensor_module._build_sensors("entry-123", _DummyCoordinator(smartflex_snapshot))

    start_sensor = _entity_by_suffix(
        entities, "smartflex_latest_completed_dispatch_start"
    )
    end_sensor = _entity_by_suffix(entities, "smartflex_latest_completed_dispatch_end")
    delta_sensor = _entity_by_suffix(
        entities, "smartflex_latest_completed_dispatch_delta"
    )

    assert start_sensor.native_value == datetime(2026, 5, 1, 18, 0, tzinfo=UTC)
    assert end_sensor.native_value == datetime(2026, 5, 1, 18, 30, tzinfo=UTC)
    assert delta_sensor.native_value == 4.8
    assert delta_sensor.native_unit_of_measurement == "kWh"
    assert delta_sensor.extra_state_attributes == {
        "smartflex_completed_dispatch_source": "SMARTFLEX",
        "smartflex_completed_dispatch_location": "HOME",
    }


def test_smartflex_sensors_return_none_for_missing_optional_surfaces(
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
        latest_completed_dispatch=SmartFlexCompletedDispatchSnapshot(
            start=datetime(2026, 5, 1, 18, 0, tzinfo=UTC),
            end=datetime(2026, 5, 1, 18, 30, tzinfo=UTC),
            delta=None,
            source=None,
            location=None,
        ),
    )

    entities = sensor_module._build_sensors("entry-123", _DummyCoordinator(smartflex_snapshot))

    state_of_charge_sensor = _entity_by_suffix(
        entities, "smartflex_charger-001_state_of_charge"
    )
    active_power_sensor = _entity_by_suffix(entities, "smartflex_charger-001_active_power")

    assert state_of_charge_sensor.native_value is None
    assert state_of_charge_sensor.extra_state_attributes == {
        "smartflex_reading_timestamp": None,
        "smartflex_upper_soc_limit": None,
        "smartflex_soc_limit_timestamp": None,
        "smartflex_is_soc_limit_violated": None,
    }
    assert active_power_sensor.native_value is None
    assert active_power_sensor.extra_state_attributes == {"smartflex_reading_timestamp": None}
    assert _entity_by_suffix(entities, "smartflex_charger-001_battery_size").native_value is None
    assert (
        _entity_by_suffix(
            entities, "smartflex_charger-001_charge_point_power_output"
        ).native_value
        is None
    )
    assert (
        _entity_by_suffix(
            entities, "smartflex_charger-001_latest_charging_session_start"
        ).native_value
        is None
    )
    assert (
        _entity_by_suffix(
            entities, "smartflex_charger-001_latest_charging_session_end"
        ).native_value
        is None
    )
    assert (
        _entity_by_suffix(
            entities, "smartflex_charger-001_latest_charging_session_energy_added"
        ).native_value
        is None
    )
    assert _entity_by_suffix(
        entities, "smartflex_charger-001_latest_charging_session_energy_added"
    ).extra_state_attributes == {
        "smartflex_latest_charging_session_start": None,
        "smartflex_latest_charging_session_end": None,
        "smartflex_latest_charging_session_soc_delta": None,
        "smartflex_latest_charging_session_soc_final": None,
    }
    assert (
        _entity_by_suffix(
            entities, "smartflex_charger-001_latest_charging_session_cost"
        ).native_value
        is None
    )
    assert _entity_by_suffix(
        entities, "smartflex_charger-001_latest_charging_session_cost"
    ).native_unit_of_measurement is None
    assert (
        _entity_by_suffix(
            entities, "smartflex_charger-001_next_planned_dispatch_start"
        ).native_value
        is None
    )
    assert _entity_by_suffix(
        entities, "smartflex_charger-001_next_planned_dispatch_start"
    ).extra_state_attributes == {
        "smartflex_next_planned_dispatch_end": None,
        "smartflex_next_planned_dispatch_type": None,
    }
    assert (
        _entity_by_suffix(
            entities, "smartflex_charger-001_next_planned_dispatch_energy_added"
        ).native_value
        is None
    )
    assert _entity_by_suffix(
        entities, "smartflex_charger-001_next_planned_dispatch_energy_added"
    ).extra_state_attributes == {
        "smartflex_next_planned_dispatch_start": None,
        "smartflex_next_planned_dispatch_end": None,
        "smartflex_next_planned_dispatch_type": None,
    }
    assert (
        _entity_by_suffix(entities, "smartflex_latest_completed_dispatch_delta").native_value
        is None
    )
    assert _entity_by_suffix(
        entities, "smartflex_latest_completed_dispatch_delta"
    ).extra_state_attributes == {
        "smartflex_completed_dispatch_source": None,
        "smartflex_completed_dispatch_location": None,
    }


def test_smartflex_unique_ids_preserve_distinct_raw_device_ids(
    sensor_module, snapshot
) -> None:
    smartflex_snapshot = replace(
        snapshot,
        smartflex_devices=(
            _build_smartflex_device_snapshot(device_id="charger-001", name="Hyphen Charger"),
            _build_smartflex_device_snapshot(device_id="charger_001", name="Underscore Charger"),
        ),
    )

    entities = sensor_module._build_sensors("entry-123", _DummyCoordinator(smartflex_snapshot))

    assert _entity_by_suffix(
        entities, "smartflex_charger-001_current_state"
    ).name == "E.ON Hyphen Charger Current State"
    assert _entity_by_suffix(
        entities, "smartflex_charger_001_current_state"
    ).name == "E.ON Underscore Charger Current State"


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
