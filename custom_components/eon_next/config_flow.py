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


def _reauth_data_schema(username: str) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_USERNAME, default=username): str,
            vol.Required(CONF_PASSWORD): str,
        }
    )


def _config_flow_error(
    err: EonNextRatesAuthError | EonNextRatesConnectionError | EonNextRatesUnsupportedError,
) -> str:
    if isinstance(err, EonNextRatesAuthError):
        return "invalid_auth"
    if isinstance(err, EonNextRatesConnectionError):
        return "cannot_connect"
    return "unsupported_tariff"


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


class EonNextRatesConfigFlow(  # pyright: ignore[reportGeneralTypeIssues]
    config_entries.ConfigFlow,
    domain=DOMAIN,  # pyright: ignore[reportCallIssue]
):
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
            except (
                EonNextRatesAuthError,
                EonNextRatesConnectionError,
                EonNextRatesUnsupportedError,
            ) as err:
                errors["base"] = _config_flow_error(err)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> dict[str, Any]:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, str] | None = None
    ) -> dict[str, Any]:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
                await self.async_set_unique_id(info["account_number"])
                self._abort_if_unique_id_mismatch()
            except (
                EonNextRatesAuthError,
                EonNextRatesConnectionError,
                EonNextRatesUnsupportedError,
            ) as err:
                errors["base"] = _config_flow_error(err)
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    title=info["title"],
                    data_updates={
                        CONF_USERNAME: info[CONF_USERNAME],
                        CONF_PASSWORD: info[CONF_PASSWORD],
                        "account_number": info["account_number"],
                    },
                )

        username = entry.data.get(CONF_USERNAME, "")
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=_reauth_data_schema(username),
            errors=errors,
        )
