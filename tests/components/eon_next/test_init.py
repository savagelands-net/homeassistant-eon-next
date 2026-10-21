from __future__ import annotations

import importlib
import sys
import types
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
from aiohttp import CookieJar

from custom_components.eon_next.api import AccountSnapshot
from custom_components.eon_next.const import CONF_API_KEY, DOMAIN, PLATFORMS


@pytest.fixture
def integration_stubs(monkeypatch: pytest.MonkeyPatch):
    for name in list(sys.modules):
        if name.startswith("homeassistant"):
            monkeypatch.delitem(sys.modules, name, raising=False)

    homeassistant: Any = types.ModuleType("homeassistant")
    homeassistant.__path__ = []

    helpers: Any = types.ModuleType("homeassistant.helpers")
    helpers.__path__ = []

    aiohttp_client: Any = types.ModuleType("homeassistant.helpers.aiohttp_client")

    class _ClientSession:
        def __init__(self, kwargs: dict[str, Any]) -> None:
            self.kwargs = kwargs
            self.detached = False

        def detach(self) -> None:
            self.detached = True

    def _async_create_clientsession(hass, **kwargs):
        session = _ClientSession(kwargs)
        hass.created_client_sessions.append(session)
        return session

    aiohttp_client.async_create_clientsession = _async_create_clientsession
    aiohttp_client.async_get_clientsession = lambda hass: hass.client_session
    helpers.aiohttp_client = aiohttp_client

    selector: Any = types.ModuleType("homeassistant.helpers.selector")

    class TextSelectorType:
        PASSWORD = "password"

    class TextSelectorConfig:
        def __init__(self, *, type: str) -> None:
            self.type = type

    class TextSelector:
        def __init__(self, config: TextSelectorConfig) -> None:
            self.config = config

        def __call__(self, value: str) -> str:
            return value

    selector.TextSelector = TextSelector
    selector.TextSelectorConfig = TextSelectorConfig
    selector.TextSelectorType = TextSelectorType
    helpers.selector = selector

    entity_registry: Any = types.ModuleType("homeassistant.helpers.entity_registry")

    class _EntityRegistry:
        def __init__(self) -> None:
            self.entries: dict[str, str] = {}

        def async_get_entity_id(self, platform: str, domain: str, unique_id: str) -> str | None:
            return self.entries.get(unique_id)

    registry = _EntityRegistry()
    entity_registry.async_get = lambda hass: registry
    helpers.entity_registry = entity_registry

    exceptions: Any = types.ModuleType("homeassistant.exceptions")

    class ConfigEntryAuthFailed(Exception):
        pass

    class ConfigEntryNotReady(Exception):
        pass

    exceptions.ConfigEntryAuthFailed = ConfigEntryAuthFailed
    exceptions.ConfigEntryNotReady = ConfigEntryNotReady

    core: Any = types.ModuleType("homeassistant.core")

    class HomeAssistant:
        def __init__(self) -> None:
            self.data: dict[str, object] = {}
            self.client_session = object()
            self.config_entries = types.SimpleNamespace(
                async_forward_entry_setups=self._async_forward_entry_setups,
                async_unload_platforms=self._async_unload_platforms,
                async_update_entry=self._async_update_entry,
            )
            self.created_client_sessions: list[_ClientSession] = []
            self.forward_calls: list[tuple[object, list[str]]] = []
            self.unload_calls: list[tuple[object, list[str]]] = []
            self.update_calls: list[tuple[object, dict[str, Any]]] = []
            self.forward_result = True
            self.unload_result = True

        async def _async_forward_entry_setups(self, entry, platforms):
            self.forward_calls.append((entry, list(platforms)))
            return self.forward_result

        async def _async_unload_platforms(self, entry, platforms):
            self.unload_calls.append((entry, list(platforms)))
            return self.unload_result

        def _async_update_entry(self, entry, *, data):
            entry.data = data
            self.update_calls.append((entry, data))

    core.HomeAssistant = HomeAssistant

    data_entry_flow: Any = types.ModuleType("homeassistant.data_entry_flow")

    class FlowResultType:
        FORM = "form"
        CREATE_ENTRY = "create_entry"
        ABORT = "abort"

    data_entry_flow.FlowResultType = FlowResultType

    const: Any = types.ModuleType("homeassistant.const")
    const.CONF_PASSWORD = "password"
    const.CONF_USERNAME = "username"

    update_coordinator: Any = types.ModuleType("homeassistant.helpers.update_coordinator")

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

    config_entries: Any = types.ModuleType("homeassistant.config_entries")

    class ConfigFlow:
        def __init_subclass__(cls, **kwargs):
            return None

        def __init__(self) -> None:
            self._unique_id = None
            self._configured_ids: set[str] = set()
            self._reauth_entry = None
            self._reconfigure_entry = None

        async def async_set_unique_id(self, unique_id: str) -> None:
            self._unique_id = unique_id

        def _abort_if_unique_id_configured(self) -> None:
            if self._unique_id in self._configured_ids:
                raise _AbortFlow("already_configured")

        def _get_reauth_entry(self):
            assert self._reauth_entry is not None
            return self._reauth_entry

        def _get_reconfigure_entry(self):
            assert self._reconfigure_entry is not None
            return self._reconfigure_entry

        def _abort_if_unique_id_mismatch(self) -> None:
            entry = self._reauth_entry or self._reconfigure_entry
            assert entry is not None
            if self._unique_id != entry.unique_id:
                raise _AbortFlow("unique_id_mismatch")

        def async_show_form(self, *, step_id: str, data_schema=None, errors=None):
            return {
                "type": FlowResultType.FORM,
                "step_id": step_id,
                "data_schema": data_schema,
                "errors": errors or {},
            }

        def async_create_entry(self, *, title: str, data: dict[str, Any]):
            assert self._unique_id is not None
            self._configured_ids.add(self._unique_id)
            return {
                "type": FlowResultType.CREATE_ENTRY,
                "title": title,
                "data": data,
            }

        def async_abort(self, *, reason: str):
            return {"type": FlowResultType.ABORT, "reason": reason}

        def async_update_reload_and_abort(
            self,
            entry,
            *,
            title: str,
            data: dict[str, Any] | None = None,
            data_updates: dict[str, Any] | None = None,
        ):
            entry.title = title
            if data is not None:
                entry.data = data
            elif data_updates is not None:
                entry.data.update(data_updates)
            reason = (
                "reconfigure_successful"
                if entry is self._reconfigure_entry
                else "reauth_successful"
            )
            return self.async_abort(reason=reason)

    @dataclass
    class ConfigEntry:
        entry_id: str = "entry-123"
        data: dict[str, Any] = field(default_factory=dict)
        title: str = "E.ON Next"
        unique_id: str | None = "A-TEST0001"

    config_entries.ConfigFlow = ConfigFlow
    config_entries.ConfigEntry = ConfigEntry
    homeassistant.config_entries = config_entries
    homeassistant.helpers = helpers

    modules = {
        "homeassistant": homeassistant,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.aiohttp_client": aiohttp_client,
        "homeassistant.helpers.entity_registry": entity_registry,
        "homeassistant.helpers.selector": selector,
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
        latest_statement_issued_at=datetime(2026, 4, 20, 0, 0, tzinfo=UTC),
        latest_statement_period_start=datetime(2026, 3, 21, 0, 0, tzinfo=UTC),
        latest_statement_period_end=datetime(2026, 4, 19, 0, 0, tzinfo=UTC),
        latest_statement_payment_due_at=datetime(2026, 5, 5, 0, 0, tzinfo=UTC),
        latest_statement_opening_balance_gbp=370.23,
        latest_statement_closing_balance_gbp=98.76,
        latest_statement_charges_gbp=54.32,
        latest_statement_credits_gbp=0,
        latest_direct_debit_amount_gbp=400.05,
        latest_direct_debit_at=datetime(2026, 4, 1, 0, 0, tzinfo=UTC),
        latest_electricity_statement_total_gbp=290.51,
        latest_electricity_statement_quantity_kwh=1571.748,
        latest_electricity_statement_usage_cost_gbp=271.91,
        latest_electricity_statement_standing_charge_gbp=18.6,
        latest_gas_statement_total_gbp=169.16,
        latest_gas_statement_quantity_kwh=2721.06,
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
    init_module, integration_stubs, monkeypatch: pytest.MonkeyPatch, snapshot
) -> None:
    hass = init_module.HomeAssistant()
    entry = init_module.ConfigEntry(
        entry_id="entry-123",
        data={
            CONF_API_KEY: "sk_live_test",
            "account_number": "A-TEST0001",
            "refresh_token": "refresh-1",
            "refresh_token_expires_at": 2_000_007_200,
        },
    )
    created: dict[str, object] = {}

    class _Client:
        def __init__(
            self,
            session,
            *,
            api_key: str,
            account_number: str,
            refresh_token: str | None,
            refresh_token_expires_at: int | None,
            token_state_callback,
        ) -> None:
            created["session"] = session
            created["api_key"] = api_key
            created["account_number"] = account_number
            created["refresh_token"] = refresh_token
            created["refresh_token_expires_at"] = refresh_token_expires_at
            self.token_state_callback = token_state_callback

    class _Coordinator:
        def __init__(self, hass, client) -> None:
            self.hass = hass
            self.client = client
            self.first_refreshes = 0

        async def async_config_entry_first_refresh(self) -> None:
            self.first_refreshes += 1
            self.client.token_state_callback("refresh-2", 2_000_010_800)

    monkeypatch.setattr(init_module, "EonNextRatesClient", _Client)
    monkeypatch.setattr(init_module, "EonNextRatesCoordinator", _Coordinator)

    def _unexpected_registry_lookup(*_args, **_kwargs):
        raise AssertionError("async_setup_entry should not touch the entity registry during setup")

    integration_stubs.async_get_entity_id = _unexpected_registry_lookup

    result = await init_module.async_setup_entry(hass, entry)

    assert result is True
    assert len(hass.created_client_sessions) == 1
    session = hass.created_client_sessions[0]
    assert created == {
        "session": session,
        "api_key": "sk_live_test",
        "account_number": "A-TEST0001",
        "refresh_token": "refresh-1",
        "refresh_token_expires_at": 2_000_007_200,
    }
    assert isinstance(session.kwargs["cookie_jar"], CookieJar)
    assert session.detached is False
    assert entry.data["refresh_token"] == "refresh-2"
    assert entry.data["refresh_token_expires_at"] == 2_000_010_800
    assert hass.update_calls == [(entry, entry.data)]
    stored = hass.data[DOMAIN]["entry-123"]
    assert isinstance(stored["coordinator"], _Coordinator)
    assert isinstance(stored["client"], _Client)
    assert stored["coordinator"].first_refreshes == 1
    assert hass.forward_calls == [(entry, PLATFORMS)]


@pytest.mark.asyncio
async def test_async_setup_entry_requests_reauth_for_legacy_password_entry(init_module) -> None:
    hass = init_module.HomeAssistant()
    entry = init_module.ConfigEntry(
        data={
            "username": "user@example.com",
            "password": "old-secret",
            "account_number": "A-TEST0001",
        }
    )
    auth_error = sys.modules["homeassistant.exceptions"].ConfigEntryAuthFailed

    with pytest.raises(auth_error, match="requires an API key"):
        await init_module.async_setup_entry(hass, entry)

    assert hass.created_client_sessions == []
    assert entry.data["account_number"] == "A-TEST0001"


def test_entity_registry_stub_only_exposes_lookup_api(integration_stubs) -> None:
    assert integration_stubs.entries == {}
    assert hasattr(integration_stubs, "async_get_entity_id")
    assert not hasattr(integration_stubs, "async_is_registered")
    assert not hasattr(integration_stubs, "async_update_entity")


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
async def test_validate_input_creates_client_and_discovers_account(
    config_flow_module, monkeypatch: pytest.MonkeyPatch, snapshot
) -> None:
    captured: dict[str, object] = {}

    class _Client:
        def __init__(self, session, *, api_key: str) -> None:
            captured["session"] = session
            captured["api_key"] = api_key
            self.refresh_token = "refresh-1"
            self.refresh_token_expires_at = 2_000_007_200

        async def async_discover_account_number(self) -> str:
            return "A-TEST0001"

        async def async_get_account_snapshot(self) -> AccountSnapshot:
            return snapshot

    monkeypatch.setattr(config_flow_module, "EonNextRatesClient", _Client)

    hass = config_flow_module.HomeAssistant()
    result = await config_flow_module.validate_input(
        hass=hass,
        data={CONF_API_KEY: "  sk_live_test  "},
    )

    assert result == {
        "title": "E.ON Next A-TEST0001",
        CONF_API_KEY: "sk_live_test",
        "account_number": "A-TEST0001",
        "refresh_token": "refresh-1",
        "refresh_token_expires_at": 2_000_007_200,
    }
    session = hass.created_client_sessions[0]
    assert captured == {
        "session": session,
        "api_key": "sk_live_test",
    }
    assert session.kwargs["auto_cleanup"] is False
    assert isinstance(session.kwargs["cookie_jar"], CookieJar)
    assert session.detached is True


@pytest.mark.asyncio
async def test_config_flow_user_step_sets_unique_id_and_creates_entry(
    config_flow_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _validate_input(hass, data):
        return {
            "title": "E.ON Next A-TEST0001",
            CONF_API_KEY: data[CONF_API_KEY],
            "account_number": "A-TEST0001",
            "refresh_token": "refresh-1",
            "refresh_token_expires_at": 2_000_007_200,
        }

    monkeypatch.setattr(config_flow_module, "validate_input", _validate_input)

    flow = config_flow_module.EonNextRatesConfigFlow()
    flow.hass = object()

    result = await flow.async_step_user({CONF_API_KEY: "sk_live_test"})

    assert result == {
        "type": "create_entry",
        "title": "E.ON Next A-TEST0001",
        "data": {
            CONF_API_KEY: "sk_live_test",
            "account_number": "A-TEST0001",
            "refresh_token": "refresh-1",
            "refresh_token_expires_at": 2_000_007_200,
        },
    }
    assert flow._unique_id == "A-TEST0001"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exception_name", "expected_error"),
    [
        ("EonNextRatesAuthError", "invalid_auth"),
        ("EonNextRatesConnectionError", "cannot_connect"),
        ("EonNextRatesUnsupportedError", "unsupported_tariff"),
    ],
)
async def test_config_flow_user_step_reports_validation_error(
    config_flow_module,
    monkeypatch: pytest.MonkeyPatch,
    exception_name: str,
    expected_error: str,
) -> None:
    async def _validate_input(hass, data):
        raise getattr(config_flow_module, exception_name)

    monkeypatch.setattr(config_flow_module, "validate_input", _validate_input)

    flow = config_flow_module.EonNextRatesConfigFlow()
    flow.hass = object()

    result = await flow.async_step_user({CONF_API_KEY: "sk_live_test"})

    assert result["type"] == "form"
    assert result["errors"] == {"base": expected_error}


@pytest.mark.asyncio
async def test_config_flow_user_step_aborts_when_account_is_already_configured(
    config_flow_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _validate_input(hass, data):
        return {
            "title": "E.ON Next A-TEST0001",
            CONF_API_KEY: data[CONF_API_KEY],
            "account_number": "A-TEST0001",
            "refresh_token": "refresh-1",
            "refresh_token_expires_at": 2_000_007_200,
        }

    monkeypatch.setattr(config_flow_module, "validate_input", _validate_input)

    flow = config_flow_module.EonNextRatesConfigFlow()
    flow.hass = object()
    flow._configured_ids.add("A-TEST0001")

    with pytest.raises(_AbortFlow, match="already_configured"):
        await flow.async_step_user({CONF_API_KEY: "sk_live_test"})


@pytest.mark.asyncio
async def test_config_flow_reauth_migrates_existing_entry_in_place(
    config_flow_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _validate_input(hass, data):
        return {
            "title": "E.ON Next A-TEST0001",
            CONF_API_KEY: data[CONF_API_KEY],
            "account_number": "A-TEST0001",
            "refresh_token": "refresh-2",
            "refresh_token_expires_at": 2_000_010_800,
        }

    monkeypatch.setattr(config_flow_module, "validate_input", _validate_input)

    entry = config_flow_module.config_entries.ConfigEntry(
        entry_id="entry-123",
        data={
            "username": "old@example.com",
            "password": "old-secret",
            "account_number": "A-TEST0001",
        },
        unique_id="A-TEST0001",
    )
    flow = config_flow_module.EonNextRatesConfigFlow()
    flow.hass = object()
    flow._reauth_entry = entry

    initial_result = await flow.async_step_reauth(entry.data)
    result = await flow.async_step_reauth_confirm({CONF_API_KEY: "sk_live_test"})

    assert initial_result["type"] == "form"
    assert initial_result["step_id"] == "reauth_confirm"
    assert result == {"type": "abort", "reason": "reauth_successful"}
    assert entry.entry_id == "entry-123"
    assert entry.unique_id == "A-TEST0001"
    assert entry.title == "E.ON Next A-TEST0001"
    assert entry.data == {
        CONF_API_KEY: "sk_live_test",
        "account_number": "A-TEST0001",
        "refresh_token": "refresh-2",
        "refresh_token_expires_at": 2_000_010_800,
    }


@pytest.mark.asyncio
async def test_config_flow_reauth_reports_invalid_auth_without_changing_entry(
    config_flow_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _validate_input(hass, data):
        raise config_flow_module.EonNextRatesAuthError

    monkeypatch.setattr(config_flow_module, "validate_input", _validate_input)

    original_data = {
        "username": "user@example.com",
        "password": "old-secret",
        "account_number": "A-TEST0001",
    }
    entry = config_flow_module.config_entries.ConfigEntry(
        data=dict(original_data),
        unique_id="A-TEST0001",
    )
    flow = config_flow_module.EonNextRatesConfigFlow()
    flow.hass = object()
    flow._reauth_entry = entry

    result = await flow.async_step_reauth_confirm({CONF_API_KEY: "sk_live_invalid"})

    assert result["type"] == "form"
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {"base": "invalid_auth"}
    assert entry.data == original_data


@pytest.mark.asyncio
async def test_config_flow_reconfigure_replaces_api_key(
    config_flow_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _validate_input(hass, data):
        return {
            "title": "E.ON Next A-TEST0001",
            CONF_API_KEY: data[CONF_API_KEY],
            "account_number": "A-TEST0001",
            "refresh_token": "refresh-2",
            "refresh_token_expires_at": 2_000_010_800,
        }

    monkeypatch.setattr(config_flow_module, "validate_input", _validate_input)

    entry = config_flow_module.config_entries.ConfigEntry(
        data={
            CONF_API_KEY: "sk_live_old",
            "account_number": "A-TEST0001",
        },
        unique_id="A-TEST0001",
    )
    flow = config_flow_module.EonNextRatesConfigFlow()
    flow.hass = object()
    flow._reconfigure_entry = entry

    initial_result = await flow.async_step_reconfigure()
    result = await flow.async_step_reconfigure({CONF_API_KEY: "sk_live_new"})

    assert initial_result["type"] == "form"
    assert initial_result["step_id"] == "reconfigure"
    assert result == {"type": "abort", "reason": "reconfigure_successful"}
    assert entry.data[CONF_API_KEY] == "sk_live_new"


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
