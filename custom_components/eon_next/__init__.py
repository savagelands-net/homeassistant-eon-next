from __future__ import annotations

try:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
except ModuleNotFoundError:  # Allows importing submodules in isolated unit tests.
    ConfigEntry = object
    HomeAssistant = object

from .api import EonNextRatesClient
from .const import DOMAIN, PLATFORMS

try:
    from .coordinator import EonNextRatesCoordinator
except ModuleNotFoundError:  # Allows importing submodules in isolated unit tests.
    EonNextRatesCoordinator = object


ELECTRICITY_ENTITY_MIGRATIONS = {
    "current_import_rate": (
        "sensor.eon_current_import_rate",
        "electricity_current_import_rate",
        "sensor.eon_electricity_current_import_rate",
    ),
    "next_import_rate": (
        "sensor.eon_next_import_rate",
        "electricity_next_import_rate",
        "sensor.eon_electricity_next_import_rate",
    ),
    "next_rate_change_at": (
        "sensor.eon_next_rate_change",
        "electricity_next_rate_change_at",
        "sensor.eon_electricity_next_rate_change",
    ),
    "standing_charge": (
        "sensor.eon_standing_charge",
        "electricity_standing_charge",
        "sensor.eon_electricity_standing_charge",
    ),
    "standing_charge_ex_vat": (
        "sensor.eon_standing_charge_ex_vat",
        "electricity_standing_charge_ex_vat",
        "sensor.eon_electricity_standing_charge_ex_vat",
    ),
    "latest_meter_reading": (
        "sensor.eon_latest_meter_reading",
        "latest_electricity_meter_reading",
        "sensor.eon_latest_electricity_meter_reading",
    ),
    "latest_meter_reading_at": (
        "sensor.eon_latest_meter_reading_time",
        "latest_electricity_meter_reading_at",
        "sensor.eon_latest_electricity_meter_reading_time",
    ),
}


async def _async_migrate_electricity_unique_ids(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    import homeassistant.helpers.entity_registry as er

    registry = er.async_get(hass)
    for old_suffix, (
        old_canonical_entity_id,
        new_suffix,
        new_canonical_entity_id,
    ) in ELECTRICITY_ENTITY_MIGRATIONS.items():
        old_unique_id = f"{entry.entry_id}_{old_suffix}"
        new_unique_id = f"{entry.entry_id}_{new_suffix}"
        old_entity_id = registry.async_get_entity_id("sensor", DOMAIN, old_unique_id)
        if old_entity_id is None:
            continue

        if registry.async_get_entity_id("sensor", DOMAIN, new_unique_id) is not None:
            continue

        target_entity_id = (
            new_canonical_entity_id
            if old_entity_id == old_canonical_entity_id
            else old_entity_id
        )

        if (
            target_entity_id != old_entity_id
            and registry.async_is_registered(target_entity_id)
        ):
            continue

        registry.async_update_entity(
            old_entity_id,
            new_entity_id=target_entity_id,
            new_unique_id=new_unique_id,
        )


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


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        domain_data = hass.data.get(DOMAIN)
        if domain_data is not None:
            domain_data.pop(entry.entry_id, None)

    return unloaded
