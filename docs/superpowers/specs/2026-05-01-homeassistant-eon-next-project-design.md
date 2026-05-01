# Home Assistant E.ON Next Project Design

## Goal

Turn this empty repository into a proper Home Assistant custom integration project for E.ON Next, with HACS-compatible packaging and enough local development/test tooling to support continued feature development.

The project should start from the already proven live-rate integration work, but be renamed and structured as a broader `E.ON Next` integration rather than a one-off `rates` component.

## Scope

This design covers project setup and repository structure.

It does not yet define every feature implementation detail for:

- tariff history and cost counters
- meter-reading sensors
- EV and charger related entities
- diagnostics, repairs, and advanced Home Assistant polish

Those will become follow-on implementation phases inside this new project.

## Requirements

- The repository should be installable as a normal Home Assistant custom integration.
- The repository should be HACS-friendly.
- The repository should include local testing/development structure from the start.
- The repository should support the current live-rate work as the first implemented feature.
- The repository structure should leave room to grow into a broader E.ON Next integration.

## Options Considered

### Option 1: Minimal custom integration only

Create only the `custom_components/<domain>/` tree and little or no project tooling.

Pros:

- fastest initial setup
- lowest amount of scaffolding

Cons:

- weak developer ergonomics
- harder to safely evolve as the integration grows
- poor foundation for a first integration project

### Option 2: HACS integration plus local dev/test harness

Create a normal HACS-compatible custom integration plus repository tooling for tests, linting, docs, and future iteration.

Pros:

- installable in Home Assistant immediately
- good balance of simplicity and maintainability
- supports incremental growth from rates to readings and EV data
- appropriate for a first Home Assistant integration project

Cons:

- more setup than the minimal option

### Option 3: Split project with separate API client library from day one

Create both a Home Assistant integration and a separate reusable Python library for E.ON API access.

Pros:

- strongest architectural separation long term

Cons:

- too much upfront complexity
- more moving parts before the integration behavior is stable

## Chosen Approach

Use Option 2.

The project should be a proper HACS custom integration with a local development/test harness, while keeping the API client inside the integration package for now.

If the E.ON API layer becomes large enough later, it can be extracted into a separate library as a future refactor.

## Domain and Naming

- Repository name: `homeassistant-eon-next`
- Integration domain: `eon_next`
- User-facing integration name: `E.ON Next`

The existing generated work used `eon_next_rates` as a temporary narrow domain. The new project should not keep that narrow name, because the integration is intended to cover more than rates.

## Repository Layout

The project should use this shape:

```text
homeassistant-eon-next/
├── custom_components/
│   └── eon_next/
│       ├── __init__.py
│       ├── manifest.json
│       ├── const.py
│       ├── config_flow.py
│       ├── coordinator.py
│       ├── sensor.py
│       ├── api.py
│       ├── strings.json
│       ├── translations/
│       │   └── en.json
│       └── brand/
│           ├── icon.png
│           └── logo.png
├── tests/
│   └── components/
│       └── eon_next/
├── README.md
├── hacs.json
├── pyproject.toml
├── requirements_dev.txt
├── .gitignore
└── scripts/
```

## Design Rationale

### `custom_components/eon_next/`

This is the standard Home Assistant custom integration layout and keeps the project directly installable by manual copy or HACS.

### `tests/components/eon_next/`

Keep tests in a standard Home Assistant-style test layout from the start so the project can grow without needing a later test-structure migration.

### `api.py`

Keep the E.ON GraphQL client inside the integration package for now. This is the smallest correct choice for an early integration project.

### `sensor.py`

Start with one sensor platform because the current proven feature work is sensor-based. If later growth justifies separate platforms or more entity types, that can be added incrementally.

### `brand/`

Home Assistant 2026.4 supports local custom-integration branding assets. Keeping them inside the integration makes the project self-contained.

### `hacs.json`

Add HACS metadata so the project is easy to install and update in Home Assistant.

### `pyproject.toml` and `requirements_dev.txt`

Include lightweight Python project tooling from the start for formatting, linting, and tests.

### `scripts/`

Reserve a place for convenience helpers such as local validation, copy/install helpers, or development commands. Do not overfill it initially.

## Initial Feature Boundaries

The first feature areas the project should support are:

1. Live tariff/rate sensors
2. Meter reading and account sensors
3. EV / smart tariff / charger related sensors

This ordering keeps the already proven rate work as the first implemented slice while leaving clear room for the broader integration vision.

## Migration Strategy From Generated Prototype

The previously generated `eon_next_rates` prototype should be treated as seed code, not as the final package layout.

Migration should:

1. rename the integration domain from `eon_next_rates` to `eon_next`
2. move generated code into the standard project layout under `custom_components/eon_next/`
3. move the generated tests into `tests/components/eon_next/`
4. keep the live-rate behavior working during the rename
5. avoid carrying over temporary prototype naming into the final project

## Validation Goals

Project setup is successful when:

1. the repository has the expected HACS/custom-component layout
2. the README describes the project rather than the default GitLab boilerplate
3. the custom integration can be copied into Home Assistant under `custom_components/eon_next`
4. the initial test and dev-tooling files are present
5. the project is ready to absorb the existing live-rate code as the first real feature
