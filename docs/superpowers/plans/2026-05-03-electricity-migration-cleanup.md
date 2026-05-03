# Electricity Migration Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the obsolete electricity entity migration hook and its dedicated test scaffolding now that the electricity rename rollout is complete.

**Architecture:** Use the existing setup test as the regression harness to prove `async_setup_entry()` no longer touches the entity registry. Then delete the migration helper from `custom_components/eon_next/__init__.py`, followed by the migration-only tests and registry-stub behavior from `tests/components/eon_next/test_init.py`. Keep the current electricity entity surface unchanged and finish with the repository's standard verification command.

**Tech Stack:** Home Assistant custom integration, Python 3.13, `pytest`, `ruff`

---

## File Structure

**Modify:**
- `custom_components/eon_next/__init__.py`
- `tests/components/eon_next/test_init.py`

### Responsibilities

- `custom_components/eon_next/__init__.py`
  Owns config-entry setup and unload. After cleanup, this file should contain no electricity entity migration logic.
- `tests/components/eon_next/test_init.py`
  Owns integration setup, unload, and config-flow tests. After cleanup, it should verify normal setup behavior without any migration-specific registry mutation coverage.

---

### Task 1: Remove the runtime migration hook

**Files:**
- Modify: `tests/components/eon_next/test_init.py`
- Modify: `custom_components/eon_next/__init__.py`

- [ ] **Step 1: Write the failing regression test**

Update `test_async_setup_entry_creates_client_and_stores_runtime_objects()` so it proves normal setup must not query the entity registry anymore.

```python
@pytest.mark.asyncio
async def test_async_setup_entry_creates_client_and_stores_runtime_objects(
    init_module,
    integration_stubs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hass = init_module.HomeAssistant()
    entry = init_module.ConfigEntry(
        entry_id="entry-123",
        data={
            "username": "placeholder_email",
            "password": "secret",
            "account_number": "A-TEST0001",
        },
    )
    created: dict[str, object] = {}

    class _Client:
        def __init__(
            self, session, *, email: str, password: str, account_number: str
        ) -> None:
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

    def _unexpected_registry_lookup(*_args, **_kwargs) -> str | None:
        raise AssertionError(
            "async_setup_entry should not touch the entity registry during setup"
        )

    integration_stubs.async_get_entity_id = _unexpected_registry_lookup

    monkeypatch.setattr(init_module, "EonNextRatesClient", _Client)
    monkeypatch.setattr(init_module, "EonNextRatesCoordinator", _Coordinator)

    result = await init_module.async_setup_entry(hass, entry)

    assert result is True
    assert created == {
        "session": hass.client_session,
        "email": "placeholder_email",
        "password": "secret",
        "account_number": "A-TEST0001",
    }
    stored = hass.data[DOMAIN]["entry-123"]
    assert isinstance(stored["coordinator"], _Coordinator)
    assert isinstance(stored["client"], _Client)
    assert stored["coordinator"].first_refreshes == 1
    assert hass.forward_calls == [(entry, PLATFORMS)]
```

- [ ] **Step 2: Run the setup test and confirm it fails**

Run:

```bash
./.venv/bin/python -m pytest tests/components/eon_next/test_init.py::test_async_setup_entry_creates_client_and_stores_runtime_objects -q
```

Expected: FAIL with `AssertionError: async_setup_entry should not touch the entity registry during setup`, proving the migration hook is still being invoked.

- [ ] **Step 3: Remove the migration hook from `__init__.py`**

Replace `custom_components/eon_next/__init__.py` with this minimal setup/unload version:

```python
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
```

- [ ] **Step 4: Run the setup test again**

Run:

```bash
./.venv/bin/python -m pytest tests/components/eon_next/test_init.py::test_async_setup_entry_creates_client_and_stores_runtime_objects -q
```

Expected: PASS.

- [ ] **Step 5: Commit the runtime cleanup**

```bash
git add custom_components/eon_next/__init__.py tests/components/eon_next/test_init.py
git commit -m "refactor: remove electricity migration hook"
```

---

### Task 2: Remove migration-only test scaffolding and verify the suite

**Files:**
- Modify: `tests/components/eon_next/test_init.py`

- [ ] **Step 1: Write the failing cleanup by simplifying the registry stub first**

Delete the unused `_RegistryEntry` stub and reduce `_EntityRegistry` to the only behavior the remaining tests should need. Replace the entity-registry section inside `integration_stubs()` with this exact code and leave the rest of the fixture unchanged.

```python
entity_registry = types.ModuleType("homeassistant.helpers.entity_registry")


class _EntityRegistry:
    def __init__(self) -> None:
        self.entries: dict[str, str] = {}

    def async_get_entity_id(
        self, platform: str, domain: str, unique_id: str
    ) -> str | None:
        return self.entries.get(unique_id)


registry = _EntityRegistry()
entity_registry.async_get = lambda hass: registry
helpers.entity_registry = entity_registry
```

- [ ] **Step 2: Run the init test file and confirm it fails**

Run:

```bash
./.venv/bin/python -m pytest tests/components/eon_next/test_init.py -q
```

Expected: FAIL in the migration-specific tests because they still reference removed stub-only behavior such as `update_calls` and migration side effects.

- [ ] **Step 3: Remove the migration-only tests**

Delete the entire block of migration tests so `test_async_setup_entry_creates_client_and_stores_runtime_objects()` is followed immediately by `test_async_unload_entry_unloads_platforms_and_clears_storage()`.

The remaining section should look like this:

```python
@pytest.mark.asyncio
async def test_async_setup_entry_creates_client_and_stores_runtime_objects(
    init_module,
    integration_stubs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hass = init_module.HomeAssistant()
    entry = init_module.ConfigEntry(
        entry_id="entry-123",
        data={
            "username": "placeholder_email",
            "password": "secret",
            "account_number": "A-TEST0001",
        },
    )
    created: dict[str, object] = {}

    class _Client:
        def __init__(
            self, session, *, email: str, password: str, account_number: str
        ) -> None:
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

    def _unexpected_registry_lookup(*_args, **_kwargs) -> str | None:
        raise AssertionError(
            "async_setup_entry should not touch the entity registry during setup"
        )

    integration_stubs.async_get_entity_id = _unexpected_registry_lookup

    monkeypatch.setattr(init_module, "EonNextRatesClient", _Client)
    monkeypatch.setattr(init_module, "EonNextRatesCoordinator", _Coordinator)

    result = await init_module.async_setup_entry(hass, entry)

    assert result is True
    assert created == {
        "session": hass.client_session,
        "email": "placeholder_email",
        "password": "secret",
        "account_number": "A-TEST0001",
    }
    stored = hass.data[DOMAIN]["entry-123"]
    assert isinstance(stored["coordinator"], _Coordinator)
    assert isinstance(stored["client"], _Client)
    assert stored["coordinator"].first_refreshes == 1
    assert hass.forward_calls == [(entry, PLATFORMS)]


@pytest.mark.asyncio
async def test_async_unload_entry_unloads_platforms_and_clears_storage(init_module) -> None:
    hass = init_module.HomeAssistant()
    entry = init_module.ConfigEntry(entry_id="entry-123")
    hass.data = {DOMAIN: {"entry-123": {"client": object(), "coordinator": object()}}}

    result = await init_module.async_unload_entry(hass, entry)

    assert result is True
    assert hass.unload_calls == [(entry, PLATFORMS)]
    assert hass.data[DOMAIN] == {}
```

- [ ] **Step 4: Run the init tests again**

Run:

```bash
./.venv/bin/python -m pytest tests/components/eon_next/test_init.py -q
```

Expected: PASS.

- [ ] **Step 5: Run the full repository checks**

Run:

```bash
./scripts/check.sh
```

Expected: PASS.

- [ ] **Step 6: Commit the test cleanup**

```bash
git add tests/components/eon_next/test_init.py
git commit -m "test: remove obsolete migration coverage"
```
