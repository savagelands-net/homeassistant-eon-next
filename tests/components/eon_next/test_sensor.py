from __future__ import annotations

import importlib
import sys
import types
from dataclasses import dataclass
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

    assert len(added_entities) == 8
    assert added_entities[0].coordinator is coordinator


def test_current_rate_sensor_exposes_value_unit_and_attributes(sensor_module, snapshot) -> None:
    entities = sensor_module._build_sensors("entry-123", _DummyCoordinator(snapshot))
    current_sensor = entities[0]

    assert current_sensor.name == "E.ON Current Import Rate"
    assert current_sensor.unique_id == "entry-123_current_import_rate"
    assert current_sensor.native_value == 0.239022
    assert current_sensor.native_unit_of_measurement == "GBP/kWh"
    assert current_sensor.extra_state_attributes == {
        "account_number": "A-TEST0001",
        "tariff_name": "Next Drive Smart V5.2",
        "tariff_code": "E-TOU-NEXT_DRIVE_SMART_V5_2-N",
        "standing_charge_gbp_per_day": 0.6000015,
        "pre_vat_standing_charge_gbp_per_day": 0.57143,
        "current_window_end": datetime(2026, 5, 1, 12, 30, tzinfo=UTC),
        "next_window_start": datetime(2026, 5, 1, 12, 30, tzinfo=UTC),
        "agreement_valid_from": datetime(2026, 4, 1, 0, 0, tzinfo=UTC),
        "agreement_valid_to": None,
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
    next_change_sensor = entities[2]

    assert next_change_sensor.name == "E.ON Next Rate Change"
    assert next_change_sensor.unique_id == "entry-123_next_rate_change_at"
    assert next_change_sensor.native_value == datetime(2026, 5, 1, 12, 30, tzinfo=UTC)


def test_latest_meter_reading_sensor_exposes_value_unit_and_attributes(
    sensor_module, snapshot
) -> None:
    entities = sensor_module._build_sensors("entry-123", _DummyCoordinator(snapshot))
    reading_sensor = _entity_by_suffix(entities, "latest_meter_reading")

    assert reading_sensor.name == "E.ON Latest Meter Reading"
    assert reading_sensor.native_value == 12346.0
    assert reading_sensor.native_unit_of_measurement == "kWh"
    assert reading_sensor.extra_state_attributes == {
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
