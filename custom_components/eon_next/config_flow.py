from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    EonNextRatesAuthError,
    EonNextRatesClient,
    EonNextRatesConnectionError,
    EonNextRatesUnsupportedError,
)
from .const import DOMAIN

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, str]) -> dict[str, str]:
    client = EonNextRatesClient(
        async_get_clientsession(hass),
        email=data[CONF_USERNAME],
        password=data[CONF_PASSWORD],
    )

    account_number = await client.async_discover_account_number()
    await client.async_get_account_snapshot()

    return {
        "title": f"E.ON Next {account_number}",
        CONF_USERNAME: data[CONF_USERNAME],
        CONF_PASSWORD: data[CONF_PASSWORD],
        "account_number": account_number,
    }


class EonNextRatesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, str] | None = None) -> dict[str, Any]:
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
                await self.async_set_unique_id(info["account_number"])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=info["title"],
                    data={
                        CONF_USERNAME: info[CONF_USERNAME],
                        CONF_PASSWORD: info[CONF_PASSWORD],
                        "account_number": info["account_number"],
                    },
                )
            except EonNextRatesAuthError:
                errors["base"] = "invalid_auth"
            except EonNextRatesConnectionError:
                errors["base"] = "cannot_connect"
            except EonNextRatesUnsupportedError:
                errors["base"] = "unsupported_tariff"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
