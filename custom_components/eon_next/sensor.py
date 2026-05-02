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
from .coordinator import EonNextRatesCoordinator

RATE_UNIT = "GBP/kWh"
CHARGE_UNIT = "GBP/day"
BALANCE_UNIT = "GBP"
READING_UNIT = "kWh"


@dataclass(frozen=True, kw_only=True)
class EonRateSensorDescription(SensorEntityDescription):
    value_attr: str
    unique_id_suffix: str
    attribute_fields: dict[str, str] | None = None


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
