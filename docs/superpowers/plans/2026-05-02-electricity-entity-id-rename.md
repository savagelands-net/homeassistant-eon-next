# E.ON Next Electricity Entity ID Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename legacy electricity `entity_id`s to explicit electricity-prefixed forms during integration setup, while preserving the already-renamed electricity display names and `unique_id`s.

**Architecture:** Keep the current coordinator, snapshot, gas, and billing behavior unchanged. Extend the existing electricity migration hook in `custom_components/eon_next/__init__.py` so it updates `new_entity_id` as well as `new_unique_id` through Home Assistant’s entity registry, and verify the behavior in `tests/components/eon_next/test_init.py` with a more complete registry stub.

**Tech Stack:** Home Assistant custom integration, Python 3.13, `pytest`, `pytest-asyncio`, `ruff`

---

## Scope Note

This plan covers **phase 1 only**: repository-side entity registry migration.

The live Home Assistant helper remediation pass happens after the updated integration is installed and is intentionally not part of this repository implementation plan.

---

## File Structure

**Modify:**
- `custom_components/eon_next/__init__.py`
- `tests/components/eon_next/test_init.py`

### Responsibilities

- `custom_components/eon_next/__init__.py`
  Extend the existing electricity migration helper so it renames legacy electricity `entity_id`s alongside legacy electricity `unique_id`s.
- `tests/components/eon_next/test_init.py`
  Strengthen the entity-registry stub and prove migration success, no-op behavior for missing legacy entries, and no-op behavior when the new target already exists.

---

### Task 1: Migrate electricity `entity_id`s alongside `unique_id`s

**Files:**
- Modify: `custom_components/eon_next/__init__.py`
- Modify: `tests/components/eon_next/test_init.py`

- [ ] **Step 1: Write the failing migration test first**

Update the entity-registry stub in `tests/components/eon_next/test_init.py` so it can track both `new_unique_id` and `new_entity_id`:

```python
    class _EntityRegistry:
        def __init__(self) -> None:
            self.entries: dict[str, str] = {}
            self.update_calls: list[tuple[str, str, str]] = []

        def async_get_entity_id(
            self, platform: str, domain: str, unique_id: str
        ) -> str | None:
            return self.entries.get(unique_id)

        def async_is_registered(self, entity_id: str) -> bool:
            return entity_id in self.entries.values()

        def async_update_entity(
            self,
            entity_id: str,
            *,
            new_entity_id: str,
            new_unique_id: str,
        ) -> None:
            old_unique_id = next(
                unique_id
                for unique_id, existing_entity_id in self.entries.items()
                if existing_entity_id == entity_id
            )
            self.update_calls.append((entity_id, new_unique_id, new_entity_id))
            self.entries.pop(old_unique_id)
            self.entries[new_unique_id] = new_entity_id
```

Replace the current migration test with:

```python
@pytest.mark.asyncio
async def test_async_setup_entry_migrates_old_electricity_unique_ids_and_entity_ids(
    init_module, integration_stubs, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = integration_stubs
    registry.entries = {
        "entry-123_current_import_rate": "sensor.eon_current_import_rate",
        "entry-123_next_import_rate": "sensor.eon_next_import_rate",
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
            "username": "placeholder_email",
            "password": "secret",
            "account_number": "A-TEST0001",
        },
    )

    result = await init_module.async_setup_entry(hass, entry)

    assert result is True
    assert registry.update_calls == [
        (
            "sensor.eon_current_import_rate",
            "entry-123_electricity_current_import_rate",
            "sensor.eon_electricity_current_import_rate",
        ),
        (
            "sensor.eon_next_import_rate",
            "entry-123_electricity_next_import_rate",
            "sensor.eon_electricity_next_import_rate",
        ),
    ]
    assert registry.entries == {
        "entry-123_electricity_current_import_rate": "sensor.eon_electricity_current_import_rate",
        "entry-123_electricity_next_import_rate": "sensor.eon_electricity_next_import_rate",
    }
```

- [ ] **Step 2: Run the migration test and confirm it fails**

Run:

```bash
./.venv/bin/python -m pytest tests/components/eon_next/test_init.py::test_async_setup_entry_migrates_old_electricity_unique_ids_and_entity_ids -q
```

Expected: FAIL because `_async_migrate_electricity_unique_ids()` currently only passes `new_unique_id` to `registry.async_update_entity(...)`.

- [ ] **Step 3: Extend the migration map with target entity IDs**

Replace `ELECTRICITY_UNIQUE_ID_MIGRATIONS` in `custom_components/eon_next/__init__.py` with:

```python
ELECTRICITY_ENTITY_MIGRATIONS = {
    "current_import_rate": (
        "electricity_current_import_rate",
        "sensor.eon_electricity_current_import_rate",
    ),
    "next_import_rate": (
        "electricity_next_import_rate",
        "sensor.eon_electricity_next_import_rate",
    ),
    "next_rate_change_at": (
        "electricity_next_rate_change_at",
        "sensor.eon_electricity_next_rate_change",
    ),
    "standing_charge": (
        "electricity_standing_charge",
        "sensor.eon_electricity_standing_charge",
    ),
    "standing_charge_ex_vat": (
        "electricity_standing_charge_ex_vat",
        "sensor.eon_electricity_standing_charge_ex_vat",
    ),
    "latest_meter_reading": (
        "latest_electricity_meter_reading",
        "sensor.eon_latest_electricity_meter_reading",
    ),
    "latest_meter_reading_at": (
        "latest_electricity_meter_reading_at",
        "sensor.eon_latest_electricity_meter_reading_time",
    ),
}
```

Update `_async_migrate_electricity_unique_ids()` in the same file to:

```python
async def _async_migrate_electricity_unique_ids(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    import homeassistant.helpers.entity_registry as er

    registry = er.async_get(hass)
    for old_suffix, (new_suffix, new_entity_id) in ELECTRICITY_ENTITY_MIGRATIONS.items():
        old_unique_id = f"{entry.entry_id}_{old_suffix}"
        new_unique_id = f"{entry.entry_id}_{new_suffix}"
        old_entity_id = registry.async_get_entity_id("sensor", DOMAIN, old_unique_id)
        if old_entity_id is None:
            continue

        existing_new_entity_id = registry.async_get_entity_id("sensor", DOMAIN, new_unique_id)
        if existing_new_entity_id is not None:
            continue

        if registry.async_is_registered(new_entity_id):
            continue

        registry.async_update_entity(
            old_entity_id,
            new_entity_id=new_entity_id,
            new_unique_id=new_unique_id,
        )
```

- [ ] **Step 4: Run the migration test again**

Run:

```bash
./.venv/bin/python -m pytest tests/components/eon_next/test_init.py::test_async_setup_entry_migrates_old_electricity_unique_ids_and_entity_ids -q
```

Expected: PASS.

---

### Task 2: Guard the migration against missing and colliding entries

**Files:**
- Modify: `tests/components/eon_next/test_init.py`
- Modify: `custom_components/eon_next/__init__.py`

- [ ] **Step 1: Write the failing no-op tests first**

Add these tests to `tests/components/eon_next/test_init.py`:

```python
@pytest.mark.asyncio
async def test_async_setup_entry_skips_missing_legacy_electricity_entities(
    init_module, integration_stubs, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = integration_stubs
    registry.entries = {}

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
            "username": "placeholder_email",
            "password": "secret",
            "account_number": "A-TEST0001",
        },
    )

    result = await init_module.async_setup_entry(hass, entry)

    assert result is True
    assert registry.update_calls == []


@pytest.mark.asyncio
async def test_async_setup_entry_skips_when_new_electricity_unique_id_already_exists(
    init_module, integration_stubs, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = integration_stubs
    registry.entries = {
        "entry-123_current_import_rate": "sensor.eon_current_import_rate",
        "entry-123_electricity_current_import_rate": "sensor.eon_electricity_current_import_rate",
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
            "username": "placeholder_email",
            "password": "secret",
            "account_number": "A-TEST0001",
        },
    )

    result = await init_module.async_setup_entry(hass, entry)

    assert result is True
    assert registry.update_calls == []
    assert registry.entries["entry-123_current_import_rate"] == "sensor.eon_current_import_rate"
    assert (
        registry.entries["entry-123_electricity_current_import_rate"]
        == "sensor.eon_electricity_current_import_rate"
    )


@pytest.mark.asyncio
async def test_async_setup_entry_skips_when_new_electricity_entity_id_already_exists(
    init_module, integration_stubs, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = integration_stubs
    registry.entries = {
        "entry-123_current_import_rate": "sensor.eon_current_import_rate",
        "some_other_unique_id": "sensor.eon_electricity_current_import_rate",
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
            "username": "placeholder_email",
            "password": "secret",
            "account_number": "A-TEST0001",
        },
    )

    result = await init_module.async_setup_entry(hass, entry)

    assert result is True
    assert registry.update_calls == []
    assert registry.entries["entry-123_current_import_rate"] == "sensor.eon_current_import_rate"
    assert (
        registry.entries["some_other_unique_id"]
        == "sensor.eon_electricity_current_import_rate"
    )
```

- [ ] **Step 2: Run the new no-op tests and confirm they fail if needed**

Run:

```bash
./.venv/bin/python -m pytest \
  tests/components/eon_next/test_init.py::test_async_setup_entry_skips_missing_legacy_electricity_entities \
  tests/components/eon_next/test_init.py::test_async_setup_entry_skips_when_new_electricity_unique_id_already_exists \
  tests/components/eon_next/test_init.py::test_async_setup_entry_skips_when_new_electricity_entity_id_already_exists \
  -q
```

Expected: PASS if the migration helper already behaves this way after Task 1. If not, make the minimal production change required and rerun until green.

- [ ] **Step 3: Run the full init test file**

Run:

```bash
./.venv/bin/python -m pytest tests/components/eon_next/test_init.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit the entity-id migration support**

```bash
git add custom_components/eon_next/__init__.py tests/components/eon_next/test_init.py
git commit -m "feat: migrate electricity entity IDs"
```

---

### Task 3: Verify the full rename slice without widening scope

**Files:**
- Modify: none unless verification exposes a small correctness issue

- [ ] **Step 1: Run the full repository verification command**

Run:

```bash
./scripts/check.sh
```

Expected: PASS with JSON checks, `compileall`, `pytest`, and `ruff` all green.

- [ ] **Step 2: Record the live Home Assistant follow-up checklist in the work log only**

After code verification passes, note these operational next steps for the post-install remediation pass:

```text
1. Install updated integration in Home Assistant
2. Restart or reload the integration
3. Confirm new electricity entity_ids exist
4. Obtain long-lived access token from user
5. Query HA helpers/objects for old electricity entity_id references
6. Rewrite exact matches to new electricity entity_ids
7. Re-read the affected objects to verify updates
```

Do not change repository files for this step.
