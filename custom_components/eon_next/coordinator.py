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

from .api import EonNextRatesAuthError, EonNextRatesError, TariffSnapshot
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class _TariffSnapshotClient(Protocol):
    async def async_get_tariff_snapshot(self) -> TariffSnapshot: ...


class EonNextRatesCoordinator(DataUpdateCoordinator[TariffSnapshot]):
    def __init__(self, hass: HomeAssistant, client: _TariffSnapshotClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self._client = client

    async def _async_update_data(self) -> TariffSnapshot:
        try:
            return await self._client.async_get_tariff_snapshot()
        except EonNextRatesAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except EonNextRatesError as err:
            raise UpdateFailed(str(err)) from err
