from __future__ import annotations

from dataclasses import dataclass
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

from .api import TariffSnapshot
from .const import (
    ATTR_STANDING_CHARGE_GBP_PER_DAY,
    ATTR_TARIFF_CODE,
    ATTR_TARIFF_NAME,
    DOMAIN,
)
from .coordinator import EonNextRatesCoordinator

RATE_UNIT = "GBP/kWh"


@dataclass(frozen=True, kw_only=True)
class EonRateSensorDescription(SensorEntityDescription):
    value_attr: str
    unique_id_suffix: str
    include_extra_attributes: bool = False


SENSOR_DESCRIPTIONS = (
    EonRateSensorDescription(
        key="current_import_rate",
        name="E.ON Current Import Rate",
        native_unit_of_measurement=RATE_UNIT,
        value_attr="current_rate_gbp_per_kwh",
        unique_id_suffix="current_import_rate",
        include_extra_attributes=True,
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
    def native_value(self) -> float | str | None:
        snapshot = self.coordinator.data
        if snapshot is None:
            return None

        return getattr(snapshot, self.entity_description.value_attr)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self.entity_description.include_extra_attributes:
            return None

        snapshot: TariffSnapshot | None = self.coordinator.data
        if snapshot is None:
            return None

        return {
            ATTR_TARIFF_NAME: snapshot.tariff_name,
            ATTR_TARIFF_CODE: snapshot.tariff_code,
            ATTR_STANDING_CHARGE_GBP_PER_DAY: snapshot.standing_charge_gbp_per_day,
        }
