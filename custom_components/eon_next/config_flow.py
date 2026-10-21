from __future__ import annotations

from typing import Any, TypedDict

import voluptuous as vol
from aiohttp import CookieJar
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    EonNextRatesAuthError,
    EonNextRatesClient,
    EonNextRatesConnectionError,
    EonNextRatesUnsupportedError,
)
from .const import (
    CONF_API_KEY,
    CONF_REFRESH_TOKEN,
    CONF_REFRESH_TOKEN_EXPIRES_AT,
    DOMAIN,
)


class _ValidationResult(TypedDict):
    title: str
    api_key: str
    account_number: str
    refresh_token: str
    refresh_token_expires_at: int


API_KEY_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
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


def _entry_data(info: _ValidationResult) -> dict[str, str | int]:
    return {
        CONF_API_KEY: info[CONF_API_KEY],
        "account_number": info["account_number"],
        CONF_REFRESH_TOKEN: info[CONF_REFRESH_TOKEN],
        CONF_REFRESH_TOKEN_EXPIRES_AT: info[CONF_REFRESH_TOKEN_EXPIRES_AT],
    }


async def validate_input(hass: HomeAssistant, data: dict[str, str]) -> _ValidationResult:
    # Do not retain E.ON affinity cookies in Home Assistant's process-wide session.
    session = async_create_clientsession(
        hass,
        auto_cleanup=False,
        cookie_jar=CookieJar(),
    )
    try:
        api_key = data[CONF_API_KEY].strip()
        client = EonNextRatesClient(session, api_key=api_key)

        account_number = await client.async_discover_account_number()
        await client.async_get_account_snapshot()
        refresh_token = client.refresh_token
        refresh_token_expires_at = client.refresh_token_expires_at
        if refresh_token is None or refresh_token_expires_at is None:
            raise EonNextRatesConnectionError(
                "E.ON login did not return reusable refresh-token state"
            )

        return _ValidationResult(
            title=f"E.ON Next {account_number}",
            api_key=api_key,
            account_number=account_number,
            refresh_token=refresh_token,
            refresh_token_expires_at=refresh_token_expires_at,
        )
    finally:
        session.detach()


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
                    data=_entry_data(info),
                )
            except (
                EonNextRatesAuthError,
                EonNextRatesConnectionError,
                EonNextRatesUnsupportedError,
            ) as err:
                errors["base"] = _config_flow_error(err)

        return self.async_show_form(
            step_id="user",
            data_schema=API_KEY_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> dict[str, Any]:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, str] | None = None
    ) -> dict[str, Any]:
        return await self._async_update_api_key(
            "reauth_confirm",
            self._get_reauth_entry(),
            user_input,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, str] | None = None
    ) -> dict[str, Any]:
        return await self._async_update_api_key(
            "reconfigure",
            self._get_reconfigure_entry(),
            user_input,
        )

    async def _async_update_api_key(
        self,
        step_id: str,
        entry: config_entries.ConfigEntry,
        user_input: dict[str, str] | None,
    ) -> dict[str, Any]:
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
                    data=_entry_data(info),
                )

        return self.async_show_form(
            step_id=step_id,
            data_schema=API_KEY_DATA_SCHEMA,
            errors=errors,
        )
