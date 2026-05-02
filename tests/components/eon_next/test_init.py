from __future__ import annotations

import importlib
import sys
import types
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from custom_components.eon_next.api import AccountSnapshot
from custom_components.eon_next.const import DOMAIN, PLATFORMS


@pytest.fixture
def integration_stubs(monkeypatch: pytest.MonkeyPatch):
    for name in list(sys.modules):
        if name.startswith("homeassistant"):
            monkeypatch.delitem(sys.modules, name, raising=False)

    homeassistant = types.ModuleType("homeassistant")
    homeassistant.__path__ = []

    helpers = types.ModuleType("homeassistant.helpers")
    helpers.__path__ = []

    aiohttp_client = types.ModuleType("homeassistant.helpers.aiohttp_client")
    aiohttp_client.async_get_clientsession = lambda hass: hass.client_session
    helpers.aiohttp_client = aiohttp_client

    entity_registry = types.ModuleType("homeassistant.helpers.entity_registry")

    @dataclass
    class _RegistryEntry:
        unique_id: str

    class _EntityRegistry:
        def __init__(self) -> None:
            self.entries: dict[str, str] = {}
            self.update_calls: list[tuple[str, str]] = []

        def async_get_entity_id(
            self, platform: str, domain: str, unique_id: str
        ) -> str | None:
            return self.entries.get(unique_id)

        def async_update_entity(self, entity_id: str, *, new_unique_id: str) -> None:
            old_unique_id = next(
                unique_id
                for unique_id, existing_entity_id in self.entries.items()
                if existing_entity_id == entity_id
            )
            self.update_calls.append((old_unique_id, new_unique_id))
            self.entries.pop(old_unique_id)
            self.entries[new_unique_id] = entity_id

    registry = _EntityRegistry()
    entity_registry.RegistryEntry = _RegistryEntry
    entity_registry.async_get = lambda hass: registry
    helpers.entity_registry = entity_registry

    exceptions = types.ModuleType("homeassistant.exceptions")

    class ConfigEntryAuthFailed(Exception):
        pass

    class ConfigEntryNotReady(Exception):
        pass

    exceptions.ConfigEntryAuthFailed = ConfigEntryAuthFailed
    exceptions.ConfigEntryNotReady = ConfigEntryNotReady

    core = types.ModuleType("homeassistant.core")

    class HomeAssistant:
        def __init__(self) -> None:
            self.data: dict[str, object] = {}
            self.client_session = object()
            self.config_entries = types.SimpleNamespace(
                async_forward_entry_setups=self._async_forward_entry_setups,
                async_unload_platforms=self._async_unload_platforms,
            )
            self.forward_calls: list[tuple[object, list[str]]] = []
            self.unload_calls: list[tuple[object, list[str]]] = []
            self.forward_result = True
            self.unload_result = True

        async def _async_forward_entry_setups(self, entry, platforms):
            self.forward_calls.append((entry, list(platforms)))
            return self.forward_result

        async def _async_unload_platforms(self, entry, platforms):
            self.unload_calls.append((entry, list(platforms)))
            return self.unload_result

    core.HomeAssistant = HomeAssistant

    data_entry_flow = types.ModuleType("homeassistant.data_entry_flow")

    class FlowResultType:
        FORM = "form"
        CREATE_ENTRY = "create_entry"
        ABORT = "abort"

    data_entry_flow.FlowResultType = FlowResultType

    const = types.ModuleType("homeassistant.const")
    const.CONF_PASSWORD = "password"
    const.CONF_USERNAME = "username"

    update_coordinator = types.ModuleType("homeassistant.helpers.update_coordinator")

    class UpdateFailed(Exception):
        pass

    class DataUpdateCoordinator:
        def __class_getitem__(cls, item):
            return cls

        def __init__(self, hass, logger, *, name: str, update_interval) -> None:
            self.hass = hass
            self.logger = logger
            self.name = name
            self.update_interval = update_interval

    update_coordinator.UpdateFailed = UpdateFailed
    update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator
    helpers.update_coordinator = update_coordinator

    config_entries = types.ModuleType("homeassistant.config_entries")

    class ConfigFlow:
        def __init_subclass__(cls, **kwargs):
            return None

        def __init__(self) -> None:
            self._unique_id = None
            self._configured_ids: set[str] = set()

        async def async_set_unique_id(self, unique_id: str) -> None:
            self._unique_id = unique_id

        def _abort_if_unique_id_configured(self) -> None:
            if self._unique_id in self._configured_ids:
                raise _AbortFlow("already_configured")

        def async_show_form(self, *, step_id: str, data_schema=None, errors=None):
            return {
                "type": FlowResultType.FORM,
                "step_id": step_id,
                "data_schema": data_schema,
                "errors": errors or {},
            }

        def async_create_entry(self, *, title: str, data: dict[str, str]):
            self._configured_ids.add(self._unique_id)
            return {
                "type": FlowResultType.CREATE_ENTRY,
                "title": title,
                "data": data,
            }

        def async_abort(self, *, reason: str):
            return {"type": FlowResultType.ABORT, "reason": reason}

    @dataclass
    class ConfigEntry:
        entry_id: str = "entry-123"
        data: dict[str, str] = field(default_factory=dict)

    config_entries.ConfigFlow = ConfigFlow
    config_entries.ConfigEntry = ConfigEntry
    homeassistant.config_entries = config_entries
    homeassistant.helpers = helpers

    modules = {
        "homeassistant": homeassistant,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.aiohttp_client": aiohttp_client,
        "homeassistant.helpers.entity_registry": entity_registry,
        "homeassistant.exceptions": exceptions,
        "homeassistant.core": core,
        "homeassistant.data_entry_flow": data_entry_flow,
        "homeassistant.const": const,
        "homeassistant.config_entries": config_entries,
        "homeassistant.helpers.update_coordinator": update_coordinator,
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    return registry


class _AbortFlow(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@pytest.fixture
def init_module(integration_stubs):
    sys.modules.pop("custom_components.eon_next.__init__", None)
    return importlib.import_module("custom_components.eon_next.__init__")


@pytest.fixture
def config_flow_module(integration_stubs):
    sys.modules.pop("custom_components.eon_next.config_flow", None)
    return importlib.import_module("custom_components.eon_next.config_flow")


@pytest.fixture
def coordinator_module(integration_stubs):
    sys.modules.pop("custom_components.eon_next.coordinator", None)
    return importlib.import_module("custom_components.eon_next.coordinator")


@pytest.fixture
def snapshot() -> AccountSnapshot:
    return AccountSnapshot(
        current_rate_gbp_per_kwh=0.239022,
        next_rate_gbp_per_kwh=0.245,
        next_rate_change_at=datetime(2026, 5, 1, 12, 30, tzinfo=UTC),
        account_number="A-TEST0001",
        current_window_end=datetime(2026, 5, 1, 12, 30, tzinfo=UTC),
        next_window_start=datetime(2026, 5, 1, 12, 30, tzinfo=UTC),
        agreement_valid_from=datetime(2026, 4, 1, 0, 0, tzinfo=UTC),
        agreement_valid_to=None,
        pre_vat_standing_charge_gbp_per_day=0.57143,
        tariff_name="Next Drive Smart V5.2",
        tariff_code="E-TOU-NEXT_DRIVE_SMART_V5_2-N",
        standing_charge_gbp_per_day=0.6000015,
        latest_meter_reading_kwh=12346.0,
        latest_meter_reading_at=datetime(2026, 5, 2, 11, 0, tzinfo=UTC),
        latest_meter_reading_source="SMART",
        latest_meter_reading_type="actual",
        latest_meter_reading_register_identifier="00001",
        latest_meter_reading_register_name="IMP",
        latest_meter_reading_register_digits=5,
        latest_meter_reading_register_is_quarantined=False,
        meter_point_mpan="0012345678901",
        current_account_balance_gbp=123.45,
        latest_statement_closing_balance_gbp=98.76,
        latest_statement_charges_gbp=54.32,
        gas_rate_gbp_per_kwh=0.06543,
        gas_pre_vat_rate_gbp_per_kwh=0.06231,
        gas_tariff_name="Next Flex Gas",
        gas_tariff_code="G-1R-NEXT_FLEX_GAS",
        gas_standing_charge_gbp_per_day=0.312,
        gas_pre_vat_standing_charge_gbp_per_day=0.297,
        gas_agreement_valid_from=datetime(2026, 4, 1, 0, 0, tzinfo=UTC),
        gas_agreement_valid_to=None,
        latest_gas_meter_reading_value=4567.0,
        latest_gas_meter_reading_at=datetime(2026, 5, 2, 13, 0, tzinfo=UTC),
        latest_gas_meter_reading_source="CUSTOMER",
        latest_gas_meter_reading_type="actual",
        latest_gas_meter_reading_register_identifier="GAS-001",
        latest_gas_meter_reading_register_name="GAS",
        latest_gas_meter_reading_register_digits=4,
        latest_gas_meter_reading_register_is_quarantined=False,
        gas_meter_point_mprn="1234567890",
    )


@pytest.mark.asyncio
async def test_async_setup_entry_creates_client_and_stores_runtime_objects(
    init_module, monkeypatch: pytest.MonkeyPatch, snapshot
) -> None:
    hass = init_module.HomeAssistant()
    entry = init_module.ConfigEntry(
        entry_id="entry-123",
        data={
            "username": "user@example.com",
            "password": "secret",
            "account_number": "A-TEST0001",
        },
    )
    created: dict[str, object] = {}

    class _Client:
        def __init__(self, session, *, email: str, password: str, account_number: str) -> None:
            created["session"] = session
            created["email"] = email
            created["password"] = password
            created["account_number"] = account_number

    class _Coordinator:
        def __init__(self, hass, client) -> None:
            self.hass = hass
            self.client = client
            self.first_refreshes = 0

        async def async_config_entry_first_refresh(self) -> None:
            self.first_refreshes += 1

    monkeypatch.setattr(init_module, "EonNextRatesClient", _Client)
    monkeypatch.setattr(init_module, "EonNextRatesCoordinator", _Coordinator)

    result = await init_module.async_setup_entry(hass, entry)

    assert result is True
    assert created == {
        "session": hass.client_session,
        "email": "user@example.com",
        "password": "secret",
        "account_number": "A-TEST0001",
    }
    stored = hass.data[DOMAIN]["entry-123"]
    assert isinstance(stored["coordinator"], _Coordinator)
    assert isinstance(stored["client"], _Client)
    assert stored["coordinator"].first_refreshes == 1
    assert hass.forward_calls == [(entry, PLATFORMS)]


@pytest.mark.asyncio
async def test_async_setup_entry_migrates_old_electricity_unique_ids(
    init_module, integration_stubs, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = integration_stubs
    registry.entries = {
        "entry-123_current_import_rate": "sensor.current_import_rate",
        "entry-123_next_import_rate": "sensor.next_import_rate",
    }

    class _Client:
        def __init__(
            self, session, *, email: str, password: str, account_number: str
        ) -> None:
            return None

    class _Coordinator:
        def __init__(self, hass, client) -> None:
            return None

        async def async_config_entry_first_refresh(self) -> None:
            return None

    monkeypatch.setattr(init_module, "EonNextRatesClient", _Client)
    monkeypatch.setattr(init_module, "EonNextRatesCoordinator", _Coordinator)

    hass = init_module.HomeAssistant()
    entry = init_module.ConfigEntry(
        entry_id="entry-123",
        data={
            "username": "user@example.com",
            "password": "secret",
            "account_number": "A-TEST0001",
        },
    )

    result = await init_module.async_setup_entry(hass, entry)

    assert result is True
    assert registry.update_calls == [
        (
            "entry-123_current_import_rate",
            "entry-123_electricity_current_import_rate",
        ),
        (
            "entry-123_next_import_rate",
            "entry-123_electricity_next_import_rate",
        ),
    ]


@pytest.mark.asyncio
async def test_async_unload_entry_unloads_platforms_and_clears_storage(init_module) -> None:
    hass = init_module.HomeAssistant()
    entry = init_module.ConfigEntry(entry_id="entry-123")
    hass.data = {DOMAIN: {"entry-123": {"client": object(), "coordinator": object()}}}

    result = await init_module.async_unload_entry(hass, entry)

    assert result is True
    assert hass.unload_calls == [(entry, PLATFORMS)]
    assert hass.data[DOMAIN] == {}


@pytest.mark.asyncio
async def test_async_step_user_creates_entry_after_validating_account(
    config_flow_module, monkeypatch: pytest.MonkeyPatch, snapshot
) -> None:
    captured: dict[str, str] = {}

    class _Client:
        def __init__(self, session, *, email: str, password: str) -> None:
            captured["session"] = session
            captured["email"] = email
            captured["password"] = password

        async def async_discover_account_number(self) -> str:
            return "A-TEST0001"

        async def async_get_account_snapshot(self) -> AccountSnapshot:
            return snapshot

    monkeypatch.setattr(config_flow_module, "EonNextRatesClient", _Client)

    result = await config_flow_module.validate_input(
        hass=types.SimpleNamespace(client_session="session"),
        data={"username": "user@example.com", "password": "secret"},
    )

    assert result == {
        "title": "E.ON Next A-TEST0001",
        "username": "user@example.com",
        "password": "secret",
        "account_number": "A-TEST0001",
    }
    assert captured == {
        "session": "session",
        "email": "user@example.com",
        "password": "secret",
    }


@pytest.mark.asyncio
async def test_config_flow_user_step_sets_unique_id_and_creates_entry(
    config_flow_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _validate_input(hass, data):
        return {
            "title": "E.ON Next A-TEST0001",
            "username": data["username"],
            "password": data["password"],
            "account_number": "A-TEST0001",
        }

    monkeypatch.setattr(config_flow_module, "validate_input", _validate_input)

    flow = config_flow_module.EonNextRatesConfigFlow()
    flow.hass = object()

    result = await flow.async_step_user(
        {"username": "user@example.com", "password": "secret"}
    )

    assert result == {
        "type": "create_entry",
        "title": "E.ON Next A-TEST0001",
        "data": {
            "username": "user@example.com",
            "password": "secret",
            "account_number": "A-TEST0001",
        },
    }
    assert flow._unique_id == "A-TEST0001"


@pytest.mark.asyncio
async def test_config_flow_user_step_reports_invalid_auth(
    config_flow_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _validate_input(hass, data):
        raise config_flow_module.EonNextRatesAuthError

    monkeypatch.setattr(config_flow_module, "validate_input", _validate_input)

    flow = config_flow_module.EonNextRatesConfigFlow()
    flow.hass = object()

    result = await flow.async_step_user(
        {"username": "user@example.com", "password": "secret"}
    )

    assert result["type"] == "form"
    assert result["errors"] == {"base": "invalid_auth"}


@pytest.mark.asyncio
async def test_config_flow_user_step_reports_cannot_connect(
    config_flow_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _validate_input(hass, data):
        raise config_flow_module.EonNextRatesConnectionError

    monkeypatch.setattr(config_flow_module, "validate_input", _validate_input)

    flow = config_flow_module.EonNextRatesConfigFlow()
    flow.hass = object()

    result = await flow.async_step_user(
        {"username": "user@example.com", "password": "secret"}
    )

    assert result["type"] == "form"
    assert result["errors"] == {"base": "cannot_connect"}


@pytest.mark.asyncio
async def test_config_flow_user_step_reports_unsupported_tariff(
    config_flow_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _validate_input(hass, data):
        raise config_flow_module.EonNextRatesUnsupportedError

    monkeypatch.setattr(config_flow_module, "validate_input", _validate_input)

    flow = config_flow_module.EonNextRatesConfigFlow()
    flow.hass = object()

    result = await flow.async_step_user(
        {"username": "user@example.com", "password": "secret"}
    )

    assert result["type"] == "form"
    assert result["errors"] == {"base": "unsupported_tariff"}


@pytest.mark.asyncio
async def test_config_flow_user_step_aborts_when_account_is_already_configured(
    config_flow_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _validate_input(hass, data):
        return {
            "title": "E.ON Next A-TEST0001",
            "username": data["username"],
            "password": data["password"],
            "account_number": "A-TEST0001",
        }

    monkeypatch.setattr(config_flow_module, "validate_input", _validate_input)

    flow = config_flow_module.EonNextRatesConfigFlow()
    flow.hass = object()
    flow._configured_ids.add("A-TEST0001")

    with pytest.raises(_AbortFlow, match="already_configured"):
        await flow.async_step_user({"username": "user@example.com", "password": "secret"})


@pytest.mark.asyncio
async def test_coordinator_raises_config_entry_auth_failed_for_auth_errors(
    coordinator_module,
) -> None:
    class _Client:
        async def async_get_account_snapshot(self) -> AccountSnapshot:
            raise coordinator_module.EonNextRatesAuthError

    coordinator = coordinator_module.EonNextRatesCoordinator(hass=object(), client=_Client())

    with pytest.raises(coordinator_module.ConfigEntryAuthFailed):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_coordinator_wraps_non_auth_errors_in_update_failed(
    coordinator_module,
) -> None:
    class _Client:
        async def async_get_account_snapshot(self) -> AccountSnapshot:
            raise coordinator_module.EonNextRatesError("offline")

    coordinator = coordinator_module.EonNextRatesCoordinator(hass=object(), client=_Client())

    with pytest.raises(coordinator_module.UpdateFailed, match="offline"):
        await coordinator._async_update_data()
