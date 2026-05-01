from __future__ import annotations

import logging
from typing import Protocol

try:
    from homeassistant.exceptions import ConfigEntryAuthFailed
except ModuleNotFoundError:  # Allows importing in isolated stub tests.
    class ConfigEntryAuthFailed(Exception):
        pass

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import AccountSnapshot, EonNextRatesAuthError, EonNextRatesError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class _AccountSnapshotClient(Protocol):
    async def async_get_account_snapshot(self) -> AccountSnapshot: ...


class EonNextRatesCoordinator(DataUpdateCoordinator[AccountSnapshot]):
    def __init__(self, hass: HomeAssistant, client: _AccountSnapshotClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self._client = client

    async def _async_update_data(self) -> AccountSnapshot:
        try:
            return await self._client.async_get_account_snapshot()
        except EonNextRatesAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except EonNextRatesError as err:
            raise UpdateFailed(str(err)) from err
