from __future__ import annotations

from typing import TYPE_CHECKING

from aiohttp import CookieJar

from .api import EonNextRatesClient
from .const import (
    CONF_API_KEY,
    CONF_REFRESH_TOKEN,
    CONF_REFRESH_TOKEN_EXPIRES_AT,
    DOMAIN,
    PLATFORMS,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from .coordinator import EonNextRatesCoordinator
else:
    try:
        from homeassistant.config_entries import ConfigEntry
        from homeassistant.core import HomeAssistant
    except ModuleNotFoundError:  # Allows importing submodules in isolated unit tests.
        ConfigEntry = object
        HomeAssistant = object

    try:
        from .coordinator import EonNextRatesCoordinator
    except ModuleNotFoundError:  # Allows importing submodules in isolated unit tests.
        EonNextRatesCoordinator = object


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    from homeassistant.exceptions import ConfigEntryAuthFailed
    from homeassistant.helpers.aiohttp_client import async_create_clientsession

    api_key = entry.data.get(CONF_API_KEY)
    if not isinstance(api_key, str) or not api_key.strip():
        raise ConfigEntryAuthFailed(
            "E.ON Next now requires an API key; reauthenticate this config entry"
        )

    stored_refresh_token = entry.data.get(CONF_REFRESH_TOKEN)
    if not isinstance(stored_refresh_token, str):
        stored_refresh_token = None

    stored_refresh_expiry = entry.data.get(CONF_REFRESH_TOKEN_EXPIRES_AT)
    if not isinstance(stored_refresh_expiry, int) or isinstance(stored_refresh_expiry, bool):
        stored_refresh_expiry = None

    def _store_refresh_token(refresh_token: str | None, expires_at: int | None) -> None:
        data = dict(entry.data)
        if refresh_token is None or expires_at is None:
            data.pop(CONF_REFRESH_TOKEN, None)
            data.pop(CONF_REFRESH_TOKEN_EXPIRES_AT, None)
        else:
            data[CONF_REFRESH_TOKEN] = refresh_token
            data[CONF_REFRESH_TOKEN_EXPIRES_AT] = expires_at

        if data != entry.data:
            hass.config_entries.async_update_entry(entry, data=data)

    # Keep E.ON's load-balancer cookies scoped to this entry and clear them on unload.
    client = EonNextRatesClient(
        async_create_clientsession(hass, cookie_jar=CookieJar()),
        api_key=api_key.strip(),
        account_number=entry.data["account_number"],
        refresh_token=stored_refresh_token,
        refresh_token_expires_at=stored_refresh_expiry,
        token_state_callback=_store_refresh_token,
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
