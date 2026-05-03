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
    ATTR_ELECTRICITY_AGREEMENT_VALID_FROM,
    ATTR_ELECTRICITY_AGREEMENT_VALID_TO,
    ATTR_ELECTRICITY_CURRENT_WINDOW_END,
    ATTR_ELECTRICITY_METER_POINT_MPAN,
    ATTR_ELECTRICITY_NEXT_WINDOW_START,
    ATTR_ELECTRICITY_PRE_VAT_STANDING_CHARGE_GBP_PER_DAY,
    ATTR_ELECTRICITY_STANDING_CHARGE_GBP_PER_DAY,
    ATTR_ELECTRICITY_TARIFF_CODE,
    ATTR_ELECTRICITY_TARIFF_NAME,
    ATTR_GAS_AGREEMENT_VALID_FROM,
    ATTR_GAS_AGREEMENT_VALID_TO,
    ATTR_GAS_METER_POINT_MPRN,
    ATTR_GAS_PRE_VAT_RATE_GBP_PER_KWH,
    ATTR_GAS_TARIFF_CODE,
    ATTR_GAS_TARIFF_NAME,
    ATTR_LATEST_ELECTRICITY_METER_READING_REGISTER_DIGITS,
    ATTR_LATEST_ELECTRICITY_METER_READING_REGISTER_IDENTIFIER,
    ATTR_LATEST_ELECTRICITY_METER_READING_REGISTER_IS_QUARANTINED,
    ATTR_LATEST_ELECTRICITY_METER_READING_REGISTER_NAME,
    ATTR_LATEST_ELECTRICITY_METER_READING_SOURCE,
    ATTR_LATEST_ELECTRICITY_METER_READING_TYPE,
    ATTR_LATEST_GAS_METER_READING_REGISTER_DIGITS,
    ATTR_LATEST_GAS_METER_READING_REGISTER_IDENTIFIER,
    ATTR_LATEST_GAS_METER_READING_REGISTER_IS_QUARANTINED,
    ATTR_LATEST_GAS_METER_READING_REGISTER_NAME,
    ATTR_LATEST_GAS_METER_READING_SOURCE,
    ATTR_LATEST_GAS_METER_READING_TYPE,
    ATTR_SMARTFLEX_COMPLETED_DISPATCH_LOCATION,
    ATTR_SMARTFLEX_COMPLETED_DISPATCH_SOURCE,
    ATTR_SMARTFLEX_DEVICE_ID,
    ATTR_SMARTFLEX_DEVICE_TYPE,
    ATTR_SMARTFLEX_INTEGRATION_DEVICE_ID,
    ATTR_SMARTFLEX_IS_SOC_LIMIT_VIOLATED,
    ATTR_SMARTFLEX_IS_SUSPENDED,
    ATTR_SMARTFLEX_LATEST_CHARGING_SESSION_END,
    ATTR_SMARTFLEX_LATEST_CHARGING_SESSION_SOC_DELTA,
    ATTR_SMARTFLEX_LATEST_CHARGING_SESSION_SOC_FINAL,
    ATTR_SMARTFLEX_LATEST_CHARGING_SESSION_START,
    ATTR_SMARTFLEX_LIFECYCLE_STATUS,
    ATTR_SMARTFLEX_MAKE,
    ATTR_SMARTFLEX_MODEL,
    ATTR_SMARTFLEX_NEXT_PLANNED_DISPATCH_END,
    ATTR_SMARTFLEX_NEXT_PLANNED_DISPATCH_START,
    ATTR_SMARTFLEX_NEXT_PLANNED_DISPATCH_TYPE,
    ATTR_SMARTFLEX_PROPERTY_ID,
    ATTR_SMARTFLEX_PROVIDER,
    ATTR_SMARTFLEX_READING_TIMESTAMP,
    ATTR_SMARTFLEX_SOC_LIMIT_TIMESTAMP,
    ATTR_SMARTFLEX_TEST_DISPATCH_FAILURE_REASON,
    ATTR_SMARTFLEX_UPPER_SOC_LIMIT,
    DOMAIN,
)
from .coordinator import EonNextRatesCoordinator

RATE_UNIT = "GBP/kWh"
CHARGE_UNIT = "GBP/day"
BALANCE_UNIT = "GBP"
READING_UNIT = "kWh"
POWER_UNIT = "kW"
PERCENT_UNIT = "%"

PathType = tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class EonRateSensorDescription(SensorEntityDescription):
    value_attr: str
    unique_id_suffix: str
    attribute_fields: dict[str, str] | None = None


@dataclass(frozen=True, kw_only=True)
class SmartFlexDeviceSensorDescription(SensorEntityDescription):
    value_path: PathType
    unique_id_suffix: str
    attribute_paths: dict[str, PathType] | None = None
    native_unit_path: PathType | None = None


@dataclass(frozen=True, kw_only=True)
class NestedAccountSensorDescription(SensorEntityDescription):
    value_path: PathType
    unique_id_suffix: str
    attribute_paths: dict[str, PathType] | None = None


SENSOR_DESCRIPTIONS = (
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
            ATTR_ELECTRICITY_PRE_VAT_STANDING_CHARGE_GBP_PER_DAY:
                "pre_vat_standing_charge_gbp_per_day",
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
        key="account_number",
        name="E.ON Account Number",
        value_attr="account_number",
        unique_id_suffix="account_number",
    ),
    EonRateSensorDescription(
        key="current_account_balance",
        name="E.ON Current Account Balance",
        native_unit_of_measurement=BALANCE_UNIT,
        value_attr="current_account_balance_gbp",
        unique_id_suffix="current_account_balance",
    ),
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

SMARTFLEX_DEVICE_SENSOR_DESCRIPTIONS = (
    SmartFlexDeviceSensorDescription(
        key="smartflex_current_state",
        name="Current State",
        value_path=("current_state",),
        unique_id_suffix="current_state",
        attribute_paths={
            ATTR_SMARTFLEX_DEVICE_ID: ("device_id",),
            ATTR_SMARTFLEX_DEVICE_TYPE: ("device_type",),
            ATTR_SMARTFLEX_PROVIDER: ("provider",),
            ATTR_SMARTFLEX_INTEGRATION_DEVICE_ID: ("integration_device_id",),
            ATTR_SMARTFLEX_PROPERTY_ID: ("property_id",),
            ATTR_SMARTFLEX_MAKE: ("make",),
            ATTR_SMARTFLEX_MODEL: ("model",),
            ATTR_SMARTFLEX_LIFECYCLE_STATUS: ("lifecycle_status",),
            ATTR_SMARTFLEX_IS_SUSPENDED: ("is_suspended",),
            ATTR_SMARTFLEX_TEST_DISPATCH_FAILURE_REASON: (
                "test_dispatch_failure_reason",
            ),
        },
    ),
    SmartFlexDeviceSensorDescription(
        key="smartflex_state_of_charge",
        name="State Of Charge",
        native_unit_of_measurement=PERCENT_UNIT,
        value_path=("state_of_charge", "value"),
        unique_id_suffix="state_of_charge",
        attribute_paths={
            ATTR_SMARTFLEX_READING_TIMESTAMP: ("state_of_charge", "timestamp"),
            ATTR_SMARTFLEX_UPPER_SOC_LIMIT: ("state_of_charge_limit", "upper_soc_limit"),
            ATTR_SMARTFLEX_SOC_LIMIT_TIMESTAMP: (
                "state_of_charge_limit",
                "timestamp",
            ),
            ATTR_SMARTFLEX_IS_SOC_LIMIT_VIOLATED: (
                "state_of_charge_limit",
                "is_limit_violated",
            ),
        },
    ),
    SmartFlexDeviceSensorDescription(
        key="smartflex_active_power",
        name="Active Power",
        native_unit_of_measurement=POWER_UNIT,
        value_path=("active_power", "value"),
        unique_id_suffix="active_power",
        attribute_paths={
            ATTR_SMARTFLEX_READING_TIMESTAMP: ("active_power", "timestamp"),
        },
    ),
    SmartFlexDeviceSensorDescription(
        key="smartflex_battery_size",
        name="Battery Size",
        native_unit_of_measurement=READING_UNIT,
        value_path=("vehicle_battery_size_kwh",),
        unique_id_suffix="battery_size",
    ),
    SmartFlexDeviceSensorDescription(
        key="smartflex_charge_point_power_output",
        name="Charge Point Power Output",
        native_unit_of_measurement=POWER_UNIT,
        value_path=("charge_point_power_output_kw",),
        unique_id_suffix="charge_point_power_output",
    ),
    SmartFlexDeviceSensorDescription(
        key="smartflex_latest_charging_session_start",
        name="Latest Charging Session Start",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_path=("latest_charging_session", "start"),
        unique_id_suffix="latest_charging_session_start",
    ),
    SmartFlexDeviceSensorDescription(
        key="smartflex_latest_charging_session_end",
        name="Latest Charging Session End",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_path=("latest_charging_session", "end"),
        unique_id_suffix="latest_charging_session_end",
    ),
    SmartFlexDeviceSensorDescription(
        key="smartflex_latest_charging_session_energy_added",
        name="Latest Charging Session Energy Added",
        value_path=("latest_charging_session", "energy_added_value"),
        unique_id_suffix="latest_charging_session_energy_added",
        native_unit_path=("latest_charging_session", "energy_added_unit"),
        attribute_paths={
            ATTR_SMARTFLEX_LATEST_CHARGING_SESSION_START: (
                "latest_charging_session",
                "start",
            ),
            ATTR_SMARTFLEX_LATEST_CHARGING_SESSION_END: (
                "latest_charging_session",
                "end",
            ),
            ATTR_SMARTFLEX_LATEST_CHARGING_SESSION_SOC_DELTA: (
                "latest_charging_session",
                "state_of_charge_change",
            ),
            ATTR_SMARTFLEX_LATEST_CHARGING_SESSION_SOC_FINAL: (
                "latest_charging_session",
                "state_of_charge_final",
            ),
        },
    ),
    SmartFlexDeviceSensorDescription(
        key="smartflex_latest_charging_session_cost",
        name="Latest Charging Session Cost",
        value_path=("latest_charging_session", "cost_amount"),
        unique_id_suffix="latest_charging_session_cost",
        native_unit_path=("latest_charging_session", "cost_currency"),
        attribute_paths={
            ATTR_SMARTFLEX_LATEST_CHARGING_SESSION_START: (
                "latest_charging_session",
                "start",
            ),
            ATTR_SMARTFLEX_LATEST_CHARGING_SESSION_END: (
                "latest_charging_session",
                "end",
            ),
            ATTR_SMARTFLEX_LATEST_CHARGING_SESSION_SOC_DELTA: (
                "latest_charging_session",
                "state_of_charge_change",
            ),
            ATTR_SMARTFLEX_LATEST_CHARGING_SESSION_SOC_FINAL: (
                "latest_charging_session",
                "state_of_charge_final",
            ),
        },
    ),
    SmartFlexDeviceSensorDescription(
        key="smartflex_next_planned_dispatch_start",
        name="Next Planned Dispatch Start",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_path=("next_planned_dispatch", "start"),
        unique_id_suffix="next_planned_dispatch_start",
        attribute_paths={
            ATTR_SMARTFLEX_NEXT_PLANNED_DISPATCH_END: (
                "next_planned_dispatch",
                "end",
            ),
            ATTR_SMARTFLEX_NEXT_PLANNED_DISPATCH_TYPE: (
                "next_planned_dispatch",
                "dispatch_type",
            ),
        },
    ),
    SmartFlexDeviceSensorDescription(
        key="smartflex_next_planned_dispatch_energy_added",
        name="Next Planned Dispatch Energy Added",
        native_unit_of_measurement=READING_UNIT,
        value_path=("next_planned_dispatch", "energy_added_kwh"),
        unique_id_suffix="next_planned_dispatch_energy_added",
        attribute_paths={
            ATTR_SMARTFLEX_NEXT_PLANNED_DISPATCH_START: (
                "next_planned_dispatch",
                "start",
            ),
            ATTR_SMARTFLEX_NEXT_PLANNED_DISPATCH_END: (
                "next_planned_dispatch",
                "end",
            ),
            ATTR_SMARTFLEX_NEXT_PLANNED_DISPATCH_TYPE: (
                "next_planned_dispatch",
                "dispatch_type",
            ),
        },
    ),
)

SMARTFLEX_ACCOUNT_SENSOR_DESCRIPTIONS = (
    NestedAccountSensorDescription(
        key="smartflex_latest_completed_dispatch_start",
        name="E.ON Latest SmartFlex Completed Dispatch Start",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_path=("latest_completed_dispatch", "start"),
        unique_id_suffix="smartflex_latest_completed_dispatch_start",
    ),
    NestedAccountSensorDescription(
        key="smartflex_latest_completed_dispatch_end",
        name="E.ON Latest SmartFlex Completed Dispatch End",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_path=("latest_completed_dispatch", "end"),
        unique_id_suffix="smartflex_latest_completed_dispatch_end",
    ),
    NestedAccountSensorDescription(
        key="smartflex_latest_completed_dispatch_delta",
        name="E.ON Latest SmartFlex Completed Dispatch Delta",
        native_unit_of_measurement=READING_UNIT,
        value_path=("latest_completed_dispatch", "delta"),
        unique_id_suffix="smartflex_latest_completed_dispatch_delta",
        attribute_paths={
            ATTR_SMARTFLEX_COMPLETED_DISPATCH_SOURCE: (
                "latest_completed_dispatch",
                "source",
            ),
            ATTR_SMARTFLEX_COMPLETED_DISPATCH_LOCATION: (
                "latest_completed_dispatch",
                "location",
            ),
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: EonNextRatesCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    initial_entities = _build_sensors(entry.entry_id, coordinator)
    async_add_entities(initial_entities)

    known_unique_ids = {entity.unique_id for entity in initial_entities}

    def _async_add_new_smartflex_entities() -> None:
        new_entities = _build_new_smartflex_sensors(
            entry.entry_id,
            coordinator,
            known_unique_ids,
        )
        if not new_entities:
            return

        known_unique_ids.update(entity.unique_id for entity in new_entities)
        async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(_async_add_new_smartflex_entities))


def _build_sensors(
    entry_id: str, coordinator: EonNextRatesCoordinator
) -> list[SensorEntity]:
    sensors: list[SensorEntity] = [
        EonNextRatesSensor(entry_id, coordinator, description)
        for description in SENSOR_DESCRIPTIONS
    ]

    sensors.extend(_build_smartflex_sensors(entry_id, coordinator))

    return sensors


def _build_new_smartflex_sensors(
    entry_id: str,
    coordinator: EonNextRatesCoordinator,
    existing_unique_ids: set[str | None],
) -> list[SensorEntity]:
    return [
        entity
        for entity in _build_smartflex_sensors(entry_id, coordinator)
        if entity.unique_id not in existing_unique_ids
    ]


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
        )

    if snapshot.latest_completed_dispatch is not None:
        sensors.extend(
            SmartFlexAccountSensor(entry_id, coordinator, description)
            for description in SMARTFLEX_ACCOUNT_SENSOR_DESCRIPTIONS
        )

    return sensors


def _resolve_path(value: Any, path: PathType) -> Any:
    current = value
    for segment in path:
        if current is None:
            return None
        if isinstance(current, dict):
            current = current.get(segment)
            continue
        current = getattr(current, segment, None)
    return current


def _device_unique_id_fragment(device_id: str) -> str:
    return device_id


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
        attribute_fields = self.entity_description.attribute_fields
        if attribute_fields is None:
            return None

        snapshot: AccountSnapshot | None = self.coordinator.data
        if snapshot is None:
            return None

        return {
            attribute_name: getattr(snapshot, snapshot_attr)
            for attribute_name, snapshot_attr in attribute_fields.items()
        }


class SmartFlexDeviceSensor(CoordinatorEntity, SensorEntity):
    entity_description: SmartFlexDeviceSensorDescription

    def __init__(
        self,
        entry_id: str,
        coordinator: EonNextRatesCoordinator,
        device_id: str,
        description: SmartFlexDeviceSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._device_id = device_id
        self._attr_unique_id = (
            f"{entry_id}_smartflex_{_device_unique_id_fragment(device_id)}_"
            f"{description.unique_id_suffix}"
        )

    @property
    def name(self) -> str:
        device_name = _resolve_path(self._device_snapshot, ("name",)) or self._device_id
        return f"E.ON {device_name} {self.entity_description.name}"

    @property
    def native_value(self) -> float | str | datetime | None:
        return _resolve_path(self._device_snapshot, self.entity_description.value_path)

    @property
    def native_unit_of_measurement(self) -> str | None:
        native_unit_path = self.entity_description.native_unit_path
        if native_unit_path is not None:
            return _resolve_path(self._device_snapshot, native_unit_path)
        return self.entity_description.native_unit_of_measurement

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        attribute_paths = self.entity_description.attribute_paths
        if attribute_paths is None:
            return None

        return {
            attribute_name: _resolve_path(self._device_snapshot, path)
            for attribute_name, path in attribute_paths.items()
        }

    @property
    def _device_snapshot(self) -> Any:
        snapshot: AccountSnapshot | None = self.coordinator.data
        if snapshot is None:
            return None

        for device in snapshot.smartflex_devices:
            if device.device_id == self._device_id:
                return device

        return None


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
    def native_value(self) -> float | str | datetime | None:
        return _resolve_path(self.coordinator.data, self.entity_description.value_path)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        attribute_paths = self.entity_description.attribute_paths
        if attribute_paths is None:
            return None

        return {
            attribute_name: _resolve_path(self.coordinator.data, path)
            for attribute_name, path in attribute_paths.items()
        }
