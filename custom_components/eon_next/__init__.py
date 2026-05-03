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


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

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
