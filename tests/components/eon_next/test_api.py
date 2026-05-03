from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from typing import Any

import pytest

from custom_components.eon_next.api import (
    AGREEMENTS_QUERY,
    LOGIN_MUTATION,
    REFRESH_MUTATION,
    SMARTFLEX_DEVICES_QUERY,
    VIEWER_QUERY,
    AccountSnapshot,
    EonNextRatesAuthError,
    EonNextRatesClient,
    EonNextRatesUnsupportedError,
    SmartFlexChargingSessionSnapshot,
    SmartFlexDeviceSnapshot,
    SmartFlexPlannedDispatchSnapshot,
    SmartFlexReadingSnapshot,
    SmartFlexSocLimitSnapshot,
    build_account_snapshot,
    build_smartflex_device_snapshot,
    select_account_number,
    select_active_half_hourly_agreement,
    select_next_planned_dispatch,
)

_UNSET = object()


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    async def __aenter__(self) -> _FakeResponse:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        return None


class _FakeSession:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = responses
        self.requests: list[dict[str, Any]] = []

    def post(self, url: str, *, json: dict[str, Any], headers: dict[str, str]):
        self.requests.append({"url": url, "json": json, "headers": headers})
        return _FakeResponse(self._responses.pop(0))


def _token_payload(token: str, refresh_token: str, exp: int) -> dict[str, Any]:
    return {
        "data": {
            "obtainKrakenToken": {
                "token": token,
                "refreshToken": refresh_token,
                "payload": {"exp": exp},
                "refreshExpiresIn": 3600,
                "__typename": "ObtainJSONWebToken",
            }
        }
    }


def _viewer_payload(account_number: str = "A-TEST0001") -> dict[str, Any]:
    return {
        "data": {
            "viewer": {
                "accounts": [{"number": account_number, "__typename": "AccountType"}],
                "__typename": "ViewerType",
            }
        }
    }


def _viewer_payload_for_accounts(*account_numbers: str) -> dict[str, Any]:
    return {
        "data": {
            "viewer": {
                "accounts": [
                    {"number": account_number, "__typename": "AccountType"}
                    for account_number in account_numbers
                ],
                "__typename": "ViewerType",
            }
        }
    }


def _account_payload(
    account_number: str = "A-TEST0001",
    *,
    balance: int | None = None,
    bills: dict[str, Any] | None = None,
    gas_agreements: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    account = {"number": account_number}
    if balance is not None:
        account["balance"] = balance
    if bills is not None:
        account["bills"] = bills
    if gas_agreements is not None:
        account["gasAgreements"] = gas_agreements
    return account


def _bills_payload(*nodes: dict[str, Any]) -> dict[str, Any]:
    return {"edges": [{"node": node} for node in nodes]}


def _statement_node(
    *,
    bill_type: str = "statement",
    issued_date: str = "2026-05-01",
    closing_balance: int = 9876,
    gross_total: int = 5432,
) -> dict[str, Any]:
    return {
        "__typename": "StatementType",
        "billType": bill_type,
        "issuedDate": issued_date,
        "closingBalance": closing_balance,
        "totalCharges": {"grossTotal": gross_total},
    }


def _statement_transaction_charge(
    *,
    title: str,
    posted_date: str,
    gross_total: int,
    quantity: str | None = None,
    usage_cost: int | None = None,
    supply_charge: int | None = None,
) -> dict[str, Any]:
    return {
        "__typename": "Charge",
        "title": title,
        "postedDate": posted_date,
        "amounts": {"grossTotal": gross_total},
        "consumption": {
            "quantity": quantity,
            "usageCost": usage_cost,
            "supplyCharge": supply_charge,
        }
        if quantity is not None
        else None,
    }


def _statement_transaction_payment(
    *, title: str,
    posted_date: str,
    gross_total: int,
) -> dict[str, Any]:
    return {
        "__typename": "Payment",
        "title": title,
        "postedDate": posted_date,
        "amounts": {"grossTotal": gross_total},
    }


def _statement_bill_node(*transactions: dict[str, Any]) -> dict[str, Any]:
    return {
        "__typename": "StatementType",
        "billType": "statement",
        "issuedDate": "2026-04-20",
        "fromDate": "2026-03-21",
        "toDate": "2026-04-19",
        "openingBalance": 37023,
        "closingBalance": 31061,
        "paymentDueDate": "2026-05-05",
        "status": "ISSUED",
        "totalCharges": {
            "netTotal": 43778,
            "taxTotal": 2189,
            "grossTotal": 45967,
        },
        "totalCredits": {
            "netTotal": 0,
            "taxTotal": 0,
            "grossTotal": 0,
        },
        "transactions": {"edges": [{"node": transaction} for transaction in transactions]},
    }


def _gas_agreement_payload_with_meter_readings(*readings: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "gas-agreement-current",
        "validFrom": "2026-04-01T00:00:00+00:00",
        "validTo": None,
        "meterPoint": {
            "mprn": "1234567890",
            "unbilledReadings": list(readings),
        },
        "tariff": {
            "displayName": "Next Flex Gas",
            "tariffCode": "G-1R-NEXT_FLEX_GAS",
            "standingCharge": 31.2,
            "preVatStandingCharge": 29.7,
            "unitRate": 6.543,
            "preVatUnitRate": 6.231,
        },
    }


def _agreement_payload_with_meter_readings(*readings: dict[str, Any]) -> dict[str, Any]:
    return {
        "validFrom": "2026-04-01T00:00:00+00:00",
        "validTo": None,
        "meterPoint": {
            "mpan": "0012345678901",
            "unbilledReadings": list(readings),
        },
        "tariff": {
            "__typename": "HalfHourlyTariff",
            "displayName": "Next Drive Smart V5.2",
            "tariffCode": "E-TOU-NEXT_DRIVE_SMART_V5_2-N",
            "standingCharge": 60.00015,
            "preVatStandingCharge": 57.143,
            "unitRates": [
                {
                    "value": 23.9022,
                    "validFrom": "2026-05-01T12:00:00+00:00",
                    "validTo": "2026-05-01T12:30:00+00:00",
                },
                {
                    "value": 24.5,
                    "validFrom": "2026-05-01T12:30:00+00:00",
                    "validTo": "2026-05-01T13:00:00+00:00",
                },
            ],
        },
    }


def _smartflex_reading_payload(
    *,
    timestamp: str,
    value: float,
) -> dict[str, Any]:
    return {
        "timestamp": timestamp,
        "value": value,
    }


def _smartflex_soc_limit_payload(
    *, timestamp: str, upper_soc_limit: float, is_limit_violated: bool
) -> dict[str, Any]:
    return {
        "timestamp": timestamp,
        "upperSocLimit": upper_soc_limit,
        "isLimitViolated": is_limit_violated,
    }


def _smartflex_planned_dispatch_payload(
    *,
    start: str,
    end: str,
    dispatch_type: str,
    energy_added_kwh: float,
) -> dict[str, Any]:
    return {
        "start": start,
        "end": end,
        "dispatchType": dispatch_type,
        "energyAddedKwh": energy_added_kwh,
    }


def _smartflex_charging_session_payload(
    *,
    start: str,
    end: str | None,
    state_of_charge_change: float,
    state_of_charge_final: float,
    energy_added_value: float,
    energy_added_unit: str,
    cost_amount: float,
    cost_currency: str,
    readings: list[dict[str, Any]] | None = None,
    soc_limits: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "start": start,
        "end": end,
        "stateOfChargeChange": state_of_charge_change,
        "stateOfChargeFinal": state_of_charge_final,
        "energyAddedValue": energy_added_value,
        "energyAddedUnit": energy_added_unit,
        "costAmount": cost_amount,
        "costCurrency": cost_currency,
        "readings": readings or [],
        "socLimits": soc_limits or [],
    }


def _smartflex_device_payload(
    *,
    device_id: str = "device-1",
    name: str = "Driveway Charger",
    device_type: str = "EV_CHARGER",
    provider: str = "EON_NEXT_DRIVE",
    integration_device_id: str = "integration-device-1",
    property_id: str = "property-1",
    make: str = "Wallbox",
    model: str = "Pulsar Plus",
    vehicle_battery_size_kwh: float = 64.0,
    charge_point_power_output_kw: float = 7.4,
    lifecycle_status: str = "LIVE",
    current_state: str = "CHARGING",
    is_suspended: bool = False,
    state_of_charge: dict[str, Any] | None | object = _UNSET,
    active_power: dict[str, Any] | None | object = _UNSET,
    state_of_charge_limit: dict[str, Any] | None | object = _UNSET,
    test_dispatch_failure_reason: str | None = None,
    sessions: list[dict[str, Any]] | None = None,
    completed_dispatches: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": device_id,
        "name": name,
        "deviceType": device_type,
        "provider": provider,
        "integrationDeviceId": integration_device_id,
        "propertyId": property_id,
        "make": make,
        "model": model,
        "vehicleBatterySizeKwh": vehicle_battery_size_kwh,
        "chargePointPowerOutputKw": charge_point_power_output_kw,
        "lifecycleStatus": lifecycle_status,
        "currentState": current_state,
        "isSuspended": is_suspended,
        "stateOfCharge": (
            {"timestamp": "2026-05-01T20:10:00+00:00", "value": 55.0}
            if state_of_charge is _UNSET
            else state_of_charge
        ),
        "activePower": (
            {"timestamp": "2026-05-01T20:10:00+00:00", "value": 6.8}
            if active_power is _UNSET
            else active_power
        ),
        "stateOfChargeLimit": (
            {
                "timestamp": "2026-05-01T20:00:00+00:00",
                "upperSocLimit": 90.0,
                "isLimitViolated": False,
            }
            if state_of_charge_limit is _UNSET
            else state_of_charge_limit
        ),
        "testDispatchFailureReason": test_dispatch_failure_reason,
        "chargingSessions": sessions or [],
        "completedDispatches": completed_dispatches or [],
    }


def _smartflex_devices_graphql_payload(*devices: dict[str, Any]) -> dict[str, Any]:
    return {"data": {"devices": list(devices)}}


def _smartflex_planned_dispatches_graphql_payload(
    *dispatches: dict[str, Any],
) -> dict[str, Any]:
    return {"data": {"flexPlannedDispatches": list(dispatches)}}


def _smartflex_graphql_charging_session_payload(
    *,
    start: str,
    end: str | None,
    state_of_charge_change: float,
    state_of_charge_final: float,
    energy_added_value: float,
    energy_added_unit: str,
    cost_amount: float,
    cost_currency: str,
) -> dict[str, Any]:
    return {
        "start": start,
        "end": end,
        "stateOfChargeChange": state_of_charge_change,
        "stateOfChargeFinal": state_of_charge_final,
        "energyAdded": {
            "value": energy_added_value,
            "unit": energy_added_unit,
        },
        "cost": {
            "amount": cost_amount,
            "currency": cost_currency,
        },
    }


def _smartflex_vehicle_graphql_payload(
    *,
    device_id: str = "vehicle-1",
    device_type: str = "EV",
    name: str = "Family EV",
    provider: str = "EON_NEXT_DRIVE",
    integration_device_id: str = "vehicle-integration-1",
    property_id: str = "property-1",
    make: str = "Kia",
    model: str = "EV6",
    vehicle_battery_size: float = 77.4,
    current_state: str = "READY",
    current: str = "LIVE",
    is_suspended: bool = False,
    charging_sessions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "__typename": "SmartFlexVehicle",
        "id": device_id,
        "deviceType": device_type,
        "name": name,
        "provider": provider,
        "integrationDeviceId": integration_device_id,
        "propertyId": property_id,
        "make": make,
        "model": model,
        "vehicleBatterySize": vehicle_battery_size,
        "status": {
            "current": current,
            "isSuspended": is_suspended,
            "currentState": current_state,
            "stateOfCharge": {
                "timestamp": "2026-05-01T20:10:00+00:00",
                "value": 55.0,
            },
            "activePower": {
                "timestamp": "2026-05-01T20:10:00+00:00",
                "value": 6.8,
            },
            "stateOfChargeLimit": {
                "upperSocLimit": 90.0,
                "timestamp": "2026-05-01T20:00:00+00:00",
                "isLimitViolated": False,
            },
            "testDispatchFailureReason": None,
        },
        "chargingSessions": {
            "edges": [
                {"node": session} for session in (charging_sessions or [])
            ]
        },
    }


def _smartflex_charge_point_graphql_payload(
    *,
    device_id: str = "charger-1",
    device_type: str = "EV_CHARGER",
    name: str = "Driveway Charger",
    provider: str = "EON_NEXT_DRIVE",
    integration_device_id: str = "charger-integration-1",
    property_id: str = "property-1",
    make: str = "Wallbox",
    model: str = "Pulsar Plus",
    charge_point_power_output: float = 7.4,
    current_state: str = "CHARGING",
    current: str = "LIVE",
    is_suspended: bool = False,
    charging_sessions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "__typename": "SmartFlexChargePoint",
        "id": device_id,
        "deviceType": device_type,
        "name": name,
        "provider": provider,
        "integrationDeviceId": integration_device_id,
        "propertyId": property_id,
        "make": make,
        "model": model,
        "chargePointPowerOutput": charge_point_power_output,
        "status": {
            "current": current,
            "isSuspended": is_suspended,
            "currentState": current_state,
            "stateOfCharge": {
                "timestamp": "2026-05-01T20:10:00+00:00",
                "value": 55.0,
            },
            "activePower": {
                "timestamp": "2026-05-01T20:10:00+00:00",
                "value": 6.8,
            },
            "stateOfChargeLimit": {
                "upperSocLimit": 90.0,
                "timestamp": "2026-05-01T20:00:00+00:00",
                "isLimitViolated": False,
            },
            "testDispatchFailureReason": None,
        },
        "chargingSessions": {
            "edges": [
                {"node": session} for session in (charging_sessions or [])
            ]
        },
    }


def _smartflex_non_ev_graphql_payload() -> dict[str, Any]:
    return {
        "__typename": "SmartFlexBattery",
        "id": "battery-1",
        "deviceType": "BATTERY",
        "name": "Home Battery",
        "provider": "EON_NEXT_DRIVE",
        "integrationDeviceId": "battery-integration-1",
        "propertyId": "property-1",
        "status": {
            "current": "LIVE",
            "isSuspended": False,
            "currentState": "IDLE",
            "stateOfCharge": None,
            "activePower": None,
            "stateOfChargeLimit": None,
            "testDispatchFailureReason": None,
        },
    }


def _graphql_error_payload(message: str = "Optional SmartFlex query failed") -> dict[str, Any]:
    return {"errors": [{"message": message}]}


def _auth_error_payload() -> dict[str, Any]:
    return {
        "errors": [
            {
                "message": "Signature has expired",
                "extensions": {"code": "UNAUTHENTICATED"},
            }
        ]
    }


def test_agreements_query_uses_charge_only_statement_fields_in_charge_fragment() -> None:
    node_block = AGREEMENTS_QUERY.split("transactions(first: 50) {", 1)[1].split(
        "electricityAgreements {", 1
    )[0]
    assert re.search(r"amounts\s*\{\s*(?:grossTotal:\s*)?gross\b", node_block)

    charge_fragment_start = node_block.index("... on Charge {")
    top_level_node_block = node_block[:charge_fragment_start]
    charge_fragment = node_block[charge_fragment_start:]

    assert "consumption {" not in top_level_node_block
    assert "usageCost" not in top_level_node_block
    assert "supplyCharge" not in top_level_node_block
    assert re.search(r"amounts\s*\{\s*grossTotal:\s*gross\s*\}", node_block)
    charge_fragment_pattern = (
        r"\.\.\. on Charge \{\s*consumption \{\s*quantity"
        r"\s*usageCost\s*\s*supplyCharge\s*\}\s*\}"
    )
    assert re.search(
        charge_fragment_pattern,
        charge_fragment,
        re.DOTALL,
    )
    assert re.search(r"\n\s*usageCost\s*:", top_level_node_block) is None
    assert re.search(r"\n\s*supplyCharge\s*:", top_level_node_block) is None


def test_smartflex_devices_query_uses_status_inline_fragments() -> None:
    device_block = SMARTFLEX_DEVICES_QUERY.split("devices(accountNumber: $accountNumber) {", 1)[1]
    status_block = device_block.split("status {", 1)[1].split("... on SmartFlexVehicle {", 1)[0]
    top_level_status_block = status_block.split("... on SmartFlexVehicleStatus {", 1)[0]

    assert "current" in top_level_status_block
    assert "isSuspended" in top_level_status_block
    assert "currentState" in top_level_status_block
    assert "stateOfCharge" not in top_level_status_block
    assert "activePower" not in top_level_status_block
    assert "stateOfChargeLimit" not in top_level_status_block
    assert "testDispatchFailureReason" not in top_level_status_block
    assert "... on SmartFlexVehicleStatus {" in status_block
    assert "... on SmartFlexChargePointStatus {" in status_block
    assert "completedDispatches(" not in SMARTFLEX_DEVICES_QUERY


def test_build_account_snapshot_parses_live_shaped_statement_transactions() -> None:
    agreement = _agreement_payload_with_meter_readings()
    account = _account_payload(
        balance=31061,
        bills=_bills_payload(
            _statement_bill_node(
                _statement_transaction_payment(
                    title="Direct debit",
                    posted_date="2026-04-01",
                    gross_total=40005,
                ),
                _statement_transaction_charge(
                    title="Electricity",
                    posted_date="2026-03-28",
                    gross_total=14920,
                    quantity="969.9660",
                    usage_cost=13840,
                    supply_charge=1080,
                ),
            )
        ),
    )

    snapshot = build_account_snapshot(
        account,
        agreement,
        datetime(2026, 5, 1, 12, 15, tzinfo=UTC),
    )

    assert snapshot.latest_direct_debit_amount_gbp == 400.05
    assert snapshot.latest_electricity_statement_total_gbp == 149.2
    assert snapshot.latest_electricity_statement_quantity_kwh == 969.966
    assert snapshot.latest_electricity_statement_usage_cost_gbp == 138.4
    assert snapshot.latest_electricity_statement_standing_charge_gbp == 10.8


def test_build_tariff_snapshot_selects_current_and_next_windows() -> None:
    agreement = {
        "validFrom": "2026-04-01T00:00:00+00:00",
        "validTo": None,
        "tariff": {
            "__typename": "HalfHourlyTariff",
            "displayName": "Next Drive Smart V5.2",
            "tariffCode": "E-TOU-NEXT_DRIVE_SMART_V5_2-N",
            "standingCharge": 60.00015,
            "unitRates": [
                {
                    "value": 2.9925,
                    "validFrom": "2026-04-29T23:00:00+00:00",
                    "validTo": "2026-04-30T05:00:00+00:00",
                },
                {
                    "value": 23.9022,
                    "validFrom": "2026-04-30T05:00:00+00:00",
                    "validTo": "2026-04-30T23:00:00+00:00",
                },
                {
                    "value": 2.9925,
                    "validFrom": "2026-04-30T23:00:00+00:00",
                    "validTo": "2026-05-01T05:00:00+00:00",
                },
            ],
        }
    }

    now = datetime(2026, 4, 30, 20, 30, tzinfo=UTC)

    snapshot = build_account_snapshot(_account_payload(), agreement, now)

    assert snapshot == AccountSnapshot(
        current_rate_gbp_per_kwh=0.239022,
        next_rate_gbp_per_kwh=0.029925,
        next_rate_change_at=datetime(2026, 4, 30, 23, 0, tzinfo=UTC),
        account_number="A-TEST0001",
        current_window_end=datetime(2026, 4, 30, 23, 0, tzinfo=UTC),
        next_window_start=datetime(2026, 4, 30, 23, 0, tzinfo=UTC),
        agreement_valid_from=datetime(2026, 4, 1, 0, 0, tzinfo=UTC),
        agreement_valid_to=None,
        pre_vat_standing_charge_gbp_per_day=None,
        tariff_name="Next Drive Smart V5.2",
        tariff_code="E-TOU-NEXT_DRIVE_SMART_V5_2-N",
        standing_charge_gbp_per_day=0.6000015,
    )


def test_build_account_snapshot_includes_account_and_agreement_metadata() -> None:
    agreement = _agreement_payload_with_meter_readings(
        {
            "readAt": "2026-05-02T11:00:00+00:00",
            "readingSource": "SMART",
            "source": "ESTIMATE",
            "readingType": "actual",
            "registers": [
                {
                    "identifier": "00001",
                    "name": "IMP",
                    "value": "12346.0",
                    "digits": 5,
                    "isQuarantined": False,
                }
            ],
        }
    )

    snapshot = build_account_snapshot(
        _account_payload(),
        agreement,
        datetime(2026, 5, 1, 12, 15, tzinfo=UTC),
    )

    assert snapshot.account_number == "A-TEST0001"
    assert snapshot.current_window_end == datetime(2026, 5, 1, 12, 30, tzinfo=UTC)
    assert snapshot.next_window_start == datetime(2026, 5, 1, 12, 30, tzinfo=UTC)
    assert snapshot.agreement_valid_from == datetime(2026, 4, 1, 0, 0, tzinfo=UTC)
    assert snapshot.agreement_valid_to is None
    assert snapshot.pre_vat_standing_charge_gbp_per_day == 0.57143
    assert snapshot.latest_meter_reading_kwh == 12346.0
    assert snapshot.latest_meter_reading_at == datetime(2026, 5, 2, 11, 0, tzinfo=UTC)
    assert snapshot.latest_meter_reading_source == "SMART"
    assert snapshot.latest_meter_reading_type == "actual"
    assert snapshot.latest_meter_reading_register_identifier == "00001"
    assert snapshot.latest_meter_reading_register_name == "IMP"
    assert snapshot.latest_meter_reading_register_digits == 5
    assert snapshot.latest_meter_reading_register_is_quarantined is False
    assert snapshot.meter_point_mpan == "0012345678901"


def test_build_account_snapshot_defaults_smartflex_surfaces_to_empty() -> None:
    snapshot = build_account_snapshot(
        _account_payload(),
        _agreement_payload_with_meter_readings(),
        datetime(2026, 5, 1, 12, 15, tzinfo=UTC),
    )

    assert snapshot.smartflex_devices == ()
    assert not hasattr(snapshot, "latest_completed_dispatch")


def test_build_smartflex_device_snapshot_selects_latest_session_and_planned_dispatch() -> None:
    device = _smartflex_device_payload(
        sessions=[
            _smartflex_charging_session_payload(
                start="2026-05-01T18:00:00+00:00",
                end="2026-05-01T19:00:00+00:00",
                state_of_charge_change=18,
                state_of_charge_final=42,
                energy_added_value=3.2,
                energy_added_unit="kWh",
                cost_amount=0.64,
                cost_currency="GBP",
            ),
            _smartflex_charging_session_payload(
                start="2026-05-01T20:00:00+00:00",
                end=None,
                state_of_charge_change=23,
                state_of_charge_final=55,
                energy_added_value=5.6,
                energy_added_unit="kWh",
                cost_amount=1.12,
                cost_currency="GBP",
            ),
        ],
    )

    next_planned_dispatch = SmartFlexPlannedDispatchSnapshot(
        start=datetime(2026, 5, 1, 21, 0, tzinfo=UTC),
        end=datetime(2026, 5, 1, 21, 30, tzinfo=UTC),
        dispatch_type="GRID_CHARGE",
        energy_added_kwh=2.5,
    )

    snapshot = build_smartflex_device_snapshot(device, next_planned_dispatch)

    assert snapshot == SmartFlexDeviceSnapshot(
        device_id="device-1",
        name="Driveway Charger",
        device_type="EV_CHARGER",
        provider="EON_NEXT_DRIVE",
        integration_device_id="integration-device-1",
        property_id="property-1",
        make="Wallbox",
        model="Pulsar Plus",
        vehicle_battery_size_kwh=64.0,
        charge_point_power_output_kw=7.4,
        lifecycle_status="LIVE",
        current_state="CHARGING",
        is_suspended=False,
        state_of_charge=SmartFlexReadingSnapshot(
            timestamp=datetime(2026, 5, 1, 20, 10, tzinfo=UTC),
            value=55.0,
        ),
        active_power=SmartFlexReadingSnapshot(
            timestamp=datetime(2026, 5, 1, 20, 10, tzinfo=UTC),
            value=6.8,
        ),
        state_of_charge_limit=SmartFlexSocLimitSnapshot(
            upper_soc_limit=90.0,
            timestamp=datetime(2026, 5, 1, 20, 0, tzinfo=UTC),
            is_limit_violated=False,
        ),
        test_dispatch_failure_reason=None,
        latest_charging_session=SmartFlexChargingSessionSnapshot(
            start=datetime(2026, 5, 1, 20, 0, tzinfo=UTC),
            end=None,
            state_of_charge_change=23,
            state_of_charge_final=55,
            energy_added_value=5.6,
            energy_added_unit="kWh",
            cost_amount=1.12,
            cost_currency="GBP",
        ),
        next_planned_dispatch=next_planned_dispatch,
    )


def test_build_smartflex_device_snapshot_ignores_null_or_non_dict_nested_subobjects() -> None:
    device = _smartflex_device_payload(
        state_of_charge=None,
        active_power="not-a-dict",
        state_of_charge_limit=42,
        sessions=[],
    )

    snapshot = build_smartflex_device_snapshot(device, None)

    assert snapshot.state_of_charge is None
    assert snapshot.active_power is None
    assert snapshot.state_of_charge_limit is None


def test_select_next_planned_dispatch_uses_earliest_valid_dispatch() -> None:
    planned_dispatches = [
        {"start": None, "end": "2026-05-01T20:30:00+00:00"},
        _smartflex_planned_dispatch_payload(
            start="2026-05-01T22:00:00+00:00",
            end="2026-05-01T22:30:00+00:00",
            dispatch_type="GRID_CHARGE",
            energy_added_kwh=4.4,
        ),
        _smartflex_planned_dispatch_payload(
            start="2026-05-01T21:00:00+00:00",
            end="2026-05-01T21:30:00+00:00",
            dispatch_type="GRID_CHARGE",
            energy_added_kwh=2.5,
        ),
        {"start": "not-a-datetime", "dispatchType": "GRID_CHARGE"},
    ]

    assert select_next_planned_dispatch(planned_dispatches) == SmartFlexPlannedDispatchSnapshot(
        start=datetime(2026, 5, 1, 21, 0, tzinfo=UTC),
        end=datetime(2026, 5, 1, 21, 30, tzinfo=UTC),
        dispatch_type="GRID_CHARGE",
        energy_added_kwh=2.5,
    )


def test_select_next_planned_dispatch_ignores_malformed_containers_and_members() -> None:
    assert select_next_planned_dispatch("not-a-list") is None

    assert select_next_planned_dispatch(
        [
            "not-a-dict",
            42,
            _smartflex_planned_dispatch_payload(
                start="2026-05-01T21:00:00+00:00",
                end="2026-05-01T21:30:00+00:00",
                dispatch_type="GRID_CHARGE",
                energy_added_kwh=2.5,
            ),
        ]
    ) == SmartFlexPlannedDispatchSnapshot(
        start=datetime(2026, 5, 1, 21, 0, tzinfo=UTC),
        end=datetime(2026, 5, 1, 21, 30, tzinfo=UTC),
        dispatch_type="GRID_CHARGE",
        energy_added_kwh=2.5,
    )


def test_select_active_half_hourly_agreement_preserves_fail_fast_invalid_datetime() -> None:
    with pytest.raises(ValueError, match="Invalid isoformat string"):
        select_active_half_hourly_agreement(
            {
                "electricityAgreements": [
                    {
                        "validFrom": "not-a-datetime",
                        "validTo": None,
                        "tariff": {"__typename": "HalfHourlyTariff"},
                    }
                ]
            },
            datetime(2026, 5, 1, 12, 15, tzinfo=UTC),
        )


def test_build_smartflex_device_snapshot_ignores_malformed_charging_sessions_collection() -> None:
    malformed_container_device = _smartflex_device_payload(sessions="not-a-list")
    snapshot = build_smartflex_device_snapshot(malformed_container_device, None)
    assert snapshot.latest_charging_session is None

    malformed_member_device = _smartflex_device_payload(
        sessions=[
            "not-a-dict",
            42,
            _smartflex_charging_session_payload(
                start="2026-05-01T20:00:00+00:00",
                end=None,
                state_of_charge_change=23,
                state_of_charge_final=55,
                energy_added_value=5.6,
                energy_added_unit="kWh",
                cost_amount=1.12,
                cost_currency="GBP",
            ),
        ]
    )
    snapshot = build_smartflex_device_snapshot(malformed_member_device, None)

    assert snapshot.latest_charging_session == SmartFlexChargingSessionSnapshot(
        start=datetime(2026, 5, 1, 20, 0, tzinfo=UTC),
        end=None,
        state_of_charge_change=23,
        state_of_charge_final=55,
        energy_added_value=5.6,
        energy_added_unit="kWh",
        cost_amount=1.12,
        cost_currency="GBP",
    )


def test_build_account_snapshot_includes_latest_statement_breakdown() -> None:
    agreement = _agreement_payload_with_meter_readings()
    account = _account_payload(
        balance=31061,
        bills=_bills_payload(
            _statement_bill_node(
                _statement_transaction_payment(
                    title="Direct debit",
                    posted_date="2026-04-01",
                    gross_total=40005,
                ),
                _statement_transaction_charge(
                    title="Electricity",
                    posted_date="2026-03-28",
                    gross_total=14920,
                    quantity="969.9660",
                    usage_cost=13840,
                    supply_charge=1080,
                ),
                _statement_transaction_charge(
                    title="Electricity",
                    posted_date="2026-04-19",
                    gross_total=14131,
                    quantity="601.7820",
                    usage_cost=13351,
                    supply_charge=780,
                ),
                _statement_transaction_charge(
                    title="Gas",
                    posted_date="2026-03-28",
                    gross_total=10432,
                    quantity="1720.0000",
                    usage_cost=999999,
                    supply_charge=999999,
                ),
                _statement_transaction_charge(
                    title="Gas",
                    posted_date="2026-04-19",
                    gross_total=6484,
                    quantity="1001.0600",
                    usage_cost=999999,
                    supply_charge=999999,
                ),
            )
        ),
    )

    snapshot = build_account_snapshot(
        account,
        agreement,
        datetime(2026, 5, 1, 12, 15, tzinfo=UTC),
    )

    assert snapshot.latest_statement_issued_at == datetime(2026, 4, 20, 0, 0, tzinfo=UTC)
    assert snapshot.latest_statement_period_start == datetime(
        2026, 3, 21, 0, 0, tzinfo=UTC
    )
    assert snapshot.latest_statement_period_end == datetime(2026, 4, 19, 0, 0, tzinfo=UTC)
    assert snapshot.latest_statement_payment_due_at == datetime(
        2026, 5, 5, 0, 0, tzinfo=UTC
    )
    assert snapshot.current_account_balance_gbp == 310.61
    assert snapshot.latest_statement_opening_balance_gbp == 370.23
    assert snapshot.latest_statement_closing_balance_gbp == 310.61
    assert snapshot.latest_statement_charges_gbp == 459.67
    assert snapshot.latest_statement_credits_gbp == 0
    assert snapshot.latest_direct_debit_amount_gbp == 400.05
    assert snapshot.latest_direct_debit_at == datetime(2026, 4, 1, 0, 0, tzinfo=UTC)
    assert snapshot.latest_electricity_statement_total_gbp == 290.51
    assert snapshot.latest_electricity_statement_quantity_kwh == 1571.748
    assert snapshot.latest_electricity_statement_usage_cost_gbp == 271.91
    assert snapshot.latest_electricity_statement_standing_charge_gbp == 18.6
    assert snapshot.latest_gas_statement_total_gbp == 169.16
    assert snapshot.latest_gas_statement_quantity_kwh == 2721.06


def test_build_account_snapshot_returns_none_for_missing_statement_breakdown_rows() -> None:
    agreement = _agreement_payload_with_meter_readings()
    account = _account_payload(
        balance=31061,
        bills=_bills_payload(
            _statement_bill_node(
                _statement_transaction_payment(
                    title="Card payment",
                    posted_date="2026-04-22",
                    gross_total=1234,
                ),
                _statement_transaction_charge(
                    title="Other",
                    posted_date="2026-04-19",
                    gross_total=555,
                    quantity="not-a-number",
                ),
            )
        ),
    )

    snapshot = build_account_snapshot(
        account,
        agreement,
        datetime(2026, 5, 1, 12, 15, tzinfo=UTC),
    )

    assert snapshot.current_account_balance_gbp == 310.61
    assert snapshot.latest_statement_charges_gbp == 459.67
    assert snapshot.latest_direct_debit_amount_gbp is None
    assert snapshot.latest_direct_debit_at is None
    assert snapshot.latest_electricity_statement_total_gbp is None
    assert snapshot.latest_electricity_statement_quantity_kwh is None
    assert snapshot.latest_electricity_statement_usage_cost_gbp is None
    assert snapshot.latest_electricity_statement_standing_charge_gbp is None
    assert snapshot.latest_gas_statement_total_gbp is None
    assert snapshot.latest_gas_statement_quantity_kwh is None


def test_build_account_snapshot_includes_billing_and_gas_fields() -> None:
    agreement = _agreement_payload_with_meter_readings()
    gas_agreement = _gas_agreement_payload_with_meter_readings(
        {
            "readAt": "2026-05-02T13:00:00+00:00",
            "readingSource": "CUSTOMER",
            "source": "SMART",
            "readingType": "actual",
            "registers": [
                {
                    "identifier": "GAS-001",
                    "name": "GAS",
                    "value": "4567.0",
                    "digits": 4,
                    "isQuarantined": False,
                }
            ],
        }
    )

    snapshot = build_account_snapshot(
        _account_payload(
            balance=12345,
            bills=_bills_payload(_statement_node()),
            gas_agreements=[gas_agreement],
        ),
        agreement,
        datetime(2026, 5, 1, 12, 15, tzinfo=UTC),
    )

    assert snapshot.current_account_balance_gbp == 123.45
    assert snapshot.latest_statement_closing_balance_gbp == 98.76
    assert snapshot.latest_statement_charges_gbp == 54.32
    assert snapshot.gas_rate_gbp_per_kwh == 0.06543
    assert snapshot.gas_pre_vat_rate_gbp_per_kwh == 0.06231
    assert snapshot.gas_tariff_name == "Next Flex Gas"
    assert snapshot.gas_tariff_code == "G-1R-NEXT_FLEX_GAS"
    assert snapshot.gas_standing_charge_gbp_per_day == 0.312
    assert snapshot.gas_pre_vat_standing_charge_gbp_per_day == 0.297
    assert snapshot.gas_agreement_valid_from == datetime(2026, 4, 1, 0, 0, tzinfo=UTC)
    assert snapshot.gas_agreement_valid_to is None
    assert snapshot.latest_gas_meter_reading_value == 4567.0
    assert snapshot.latest_gas_meter_reading_at == datetime(
        2026, 5, 2, 13, 0, tzinfo=UTC
    )
    assert snapshot.latest_gas_meter_reading_source == "CUSTOMER"
    assert snapshot.latest_gas_meter_reading_type == "actual"
    assert snapshot.latest_gas_meter_reading_register_identifier == "GAS-001"
    assert snapshot.latest_gas_meter_reading_register_name == "GAS"
    assert snapshot.latest_gas_meter_reading_register_digits == 4
    assert snapshot.latest_gas_meter_reading_register_is_quarantined is False
    assert snapshot.gas_meter_point_mprn == "1234567890"


def test_build_account_snapshot_returns_none_for_optional_billing_and_gas_fields_when_absent(
) -> None:
    snapshot = build_account_snapshot(
        _account_payload(),
        _agreement_payload_with_meter_readings(),
        datetime(2026, 5, 1, 12, 15, tzinfo=UTC),
    )

    assert snapshot.current_account_balance_gbp is None
    assert snapshot.latest_statement_closing_balance_gbp is None
    assert snapshot.latest_statement_charges_gbp is None
    assert snapshot.gas_rate_gbp_per_kwh is None
    assert snapshot.gas_pre_vat_rate_gbp_per_kwh is None
    assert snapshot.gas_tariff_name is None
    assert snapshot.gas_tariff_code is None
    assert snapshot.gas_standing_charge_gbp_per_day is None
    assert snapshot.gas_pre_vat_standing_charge_gbp_per_day is None
    assert snapshot.gas_agreement_valid_from is None
    assert snapshot.gas_agreement_valid_to is None
    assert snapshot.latest_gas_meter_reading_value is None
    assert snapshot.latest_gas_meter_reading_at is None
    assert snapshot.latest_gas_meter_reading_source is None
    assert snapshot.latest_gas_meter_reading_type is None
    assert snapshot.latest_gas_meter_reading_register_identifier is None
    assert snapshot.latest_gas_meter_reading_register_name is None
    assert snapshot.latest_gas_meter_reading_register_digits is None
    assert snapshot.latest_gas_meter_reading_register_is_quarantined is None
    assert snapshot.gas_meter_point_mprn is None


def test_build_account_snapshot_ignores_non_statement_latest_bill(
) -> None:
    snapshot = build_account_snapshot(
        _account_payload(
            balance=12345,
            bills=_bills_payload(
                {
                    "__typename": "PaymentType",
                    "billType": "payment",
                    "issuedDate": "2026-05-01",
                }
            ),
        ),
        _agreement_payload_with_meter_readings(),
        datetime(2026, 5, 1, 12, 15, tzinfo=UTC),
    )

    assert snapshot.current_account_balance_gbp == 123.45
    assert snapshot.latest_statement_closing_balance_gbp is None
    assert snapshot.latest_statement_charges_gbp is None


def test_build_account_snapshot_uses_first_usable_statement_from_bill_edges() -> None:
    snapshot = build_account_snapshot(
        _account_payload(
            balance=12345,
            bills=_bills_payload(
                {
                    "__typename": "PaymentType",
                    "billType": "payment",
                    "issuedDate": "2026-05-02",
                },
                _statement_node(
                    issued_date="2026-05-01",
                    closing_balance=9876,
                    gross_total=5432,
                ),
            ),
        ),
        _agreement_payload_with_meter_readings(),
        datetime(2026, 5, 1, 12, 15, tzinfo=UTC),
    )

    assert snapshot.current_account_balance_gbp == 123.45
    assert snapshot.latest_statement_closing_balance_gbp == 98.76
    assert snapshot.latest_statement_charges_gbp == 54.32


def test_build_account_snapshot_returns_none_for_malformed_optional_gas_meter_payload() -> None:
    snapshot = build_account_snapshot(
        _account_payload(
            gas_agreements=[
                _gas_agreement_payload_with_meter_readings(
                    {
                        "readAt": "2026-05-02T13:00:00+00:00",
                        "readingSource": "CUSTOMER",
                        "source": "SMART",
                        "readingType": "actual",
                        "registers": {"identifier": "GAS-001"},
                    }
                )
            ]
        ),
        _agreement_payload_with_meter_readings(),
        datetime(2026, 5, 1, 12, 15, tzinfo=UTC),
    )

    assert snapshot.gas_rate_gbp_per_kwh == 0.06543
    assert snapshot.gas_pre_vat_rate_gbp_per_kwh == 0.06231
    assert snapshot.gas_tariff_name == "Next Flex Gas"
    assert snapshot.gas_tariff_code == "G-1R-NEXT_FLEX_GAS"
    assert snapshot.gas_standing_charge_gbp_per_day == 0.312
    assert snapshot.gas_pre_vat_standing_charge_gbp_per_day == 0.297
    assert snapshot.gas_agreement_valid_from == datetime(2026, 4, 1, 0, 0, tzinfo=UTC)
    assert snapshot.gas_agreement_valid_to is None
    assert snapshot.latest_gas_meter_reading_value is None
    assert snapshot.latest_gas_meter_reading_at is None
    assert snapshot.latest_gas_meter_reading_source is None
    assert snapshot.latest_gas_meter_reading_type is None
    assert snapshot.latest_gas_meter_reading_register_identifier is None
    assert snapshot.latest_gas_meter_reading_register_name is None
    assert snapshot.latest_gas_meter_reading_register_digits is None
    assert snapshot.latest_gas_meter_reading_register_is_quarantined is None
    assert snapshot.gas_meter_point_mprn == "1234567890"


def test_build_account_snapshot_selects_latest_usable_meter_reading() -> None:
    agreement = _agreement_payload_with_meter_readings(
        {
            "readAt": "2026-05-02T11:00:00+00:00",
            "readingSource": "SMART",
            "source": "MANUAL",
            "readingType": "actual",
            "registers": [
                {
                    "identifier": "00001",
                    "name": "IMP",
                    "value": "12346.0",
                    "digits": 5,
                    "isQuarantined": False,
                }
            ],
        },
        {
            "readAt": "2026-05-02T12:00:00+00:00",
            "readingSource": None,
            "source": "SMART",
            "readingType": "estimated",
            "registers": [
                {
                    "identifier": "00002",
                    "name": "EXP",
                    "value": None,
                    "digits": 5,
                    "isQuarantined": True,
                },
                {
                    "identifier": "00003",
                    "name": "IMP",
                    "value": "12347.5",
                    "digits": 6,
                    "isQuarantined": False,
                },
            ],
        },
        {
            "readAt": None,
            "readingSource": "SMART",
            "source": "SMART",
            "readingType": "actual",
            "registers": [
                {
                    "identifier": "00004",
                    "name": "IMP",
                    "value": "99999",
                    "digits": 5,
                    "isQuarantined": False,
                }
            ],
        },
    )

    snapshot = build_account_snapshot(
        _account_payload(),
        agreement,
        datetime(2026, 5, 1, 12, 15, tzinfo=UTC),
    )

    assert snapshot.latest_meter_reading_kwh == 12347.5
    assert snapshot.latest_meter_reading_at == datetime(2026, 5, 2, 12, 0, tzinfo=UTC)
    assert snapshot.latest_meter_reading_source == "SMART"
    assert snapshot.latest_meter_reading_type == "estimated"
    assert snapshot.latest_meter_reading_register_identifier == "00003"
    assert snapshot.latest_meter_reading_register_name == "IMP"
    assert snapshot.latest_meter_reading_register_digits == 6
    assert snapshot.latest_meter_reading_register_is_quarantined is False
    assert snapshot.meter_point_mpan == "0012345678901"


def test_build_account_snapshot_returns_none_when_no_usable_meter_reading_exists() -> None:
    agreement = _agreement_payload_with_meter_readings(
        {
            "readAt": "2026-05-02T11:00:00+00:00",
            "readingSource": "SMART",
            "source": "SMART",
            "readingType": "actual",
            "registers": {"identifier": "00001"},
        },
        {
            "readAt": "not-a-datetime",
            "readingSource": "SMART",
            "source": "SMART",
            "readingType": "actual",
            "registers": [
                {
                    "identifier": "00002",
                    "name": "IMP",
                    "value": "12346.0",
                    "digits": 5,
                    "isQuarantined": False,
                }
            ],
        },
        {
            "readAt": "2026-05-02T10:00:00+00:00",
            "readingSource": "SMART",
            "source": "SMART",
            "readingType": "actual",
            "registers": [
                {
                    "identifier": "00003",
                    "name": "IMP",
                    "value": None,
                    "digits": 5,
                    "isQuarantined": False,
                }
            ],
        },
    )

    snapshot = build_account_snapshot(
        _account_payload(),
        agreement,
        datetime(2026, 5, 1, 12, 15, tzinfo=UTC),
    )

    assert snapshot.latest_meter_reading_kwh is None
    assert snapshot.latest_meter_reading_at is None
    assert snapshot.latest_meter_reading_source is None
    assert snapshot.latest_meter_reading_type is None
    assert snapshot.latest_meter_reading_register_identifier is None
    assert snapshot.latest_meter_reading_register_name is None
    assert snapshot.latest_meter_reading_register_digits is None
    assert snapshot.latest_meter_reading_register_is_quarantined is None
    assert snapshot.meter_point_mpan == "0012345678901"


def test_build_account_snapshot_returns_none_when_unbilled_readings_is_not_a_list() -> None:
    agreement = _agreement_payload_with_meter_readings()
    agreement["meterPoint"]["unbilledReadings"] = {"readAt": "2026-05-02T11:00:00+00:00"}

    snapshot = build_account_snapshot(
        _account_payload(),
        agreement,
        datetime(2026, 5, 1, 12, 15, tzinfo=UTC),
    )

    assert snapshot.current_rate_gbp_per_kwh == 0.239022
    assert snapshot.next_rate_gbp_per_kwh == 0.245
    assert snapshot.latest_meter_reading_kwh is None
    assert snapshot.latest_meter_reading_at is None
    assert snapshot.latest_meter_reading_source is None
    assert snapshot.latest_meter_reading_type is None
    assert snapshot.latest_meter_reading_register_identifier is None
    assert snapshot.latest_meter_reading_register_name is None
    assert snapshot.latest_meter_reading_register_digits is None
    assert snapshot.latest_meter_reading_register_is_quarantined is None
    assert snapshot.meter_point_mpan == "0012345678901"


def test_build_tariff_snapshot_allows_missing_next_window() -> None:
    agreement = {
        "validFrom": "2026-04-01T00:00:00+00:00",
        "validTo": None,
        "tariff": {
            "__typename": "HalfHourlyTariff",
            "displayName": "Next Drive Smart V5.2",
            "tariffCode": "E-TOU-NEXT_DRIVE_SMART_V5_2-N",
            "standingCharge": 60.00015,
            "unitRates": [
                {
                    "value": 2.9925,
                    "validFrom": "2026-04-30T23:00:00+00:00",
                    "validTo": "2026-05-01T05:00:00+00:00",
                },
                {
                    "value": 23.9022,
                    "validFrom": "2026-05-01T05:00:00+00:00",
                    "validTo": "2026-05-01T23:00:00+00:00",
                },
            ],
        }
    }

    snapshot = build_account_snapshot(
        _account_payload(),
        agreement,
        datetime(2026, 5, 1, 9, 50, tzinfo=UTC),
    )

    assert snapshot == AccountSnapshot(
        current_rate_gbp_per_kwh=0.239022,
        next_rate_gbp_per_kwh=None,
        next_rate_change_at=None,
        account_number="A-TEST0001",
        current_window_end=datetime(2026, 5, 1, 23, 0, tzinfo=UTC),
        next_window_start=None,
        agreement_valid_from=datetime(2026, 4, 1, 0, 0, tzinfo=UTC),
        agreement_valid_to=None,
        pre_vat_standing_charge_gbp_per_day=None,
        tariff_name="Next Drive Smart V5.2",
        tariff_code="E-TOU-NEXT_DRIVE_SMART_V5_2-N",
        standing_charge_gbp_per_day=0.6000015,
    )


def test_select_account_number_returns_first_account_number() -> None:
    viewer = {
        "accounts": [
            {"__typename": "AccountType", "number": "A-TEST0001"},
            {"__typename": "AccountType", "number": "A-SECOND"},
        ]
    }

    assert select_account_number(viewer) == "A-TEST0001"


def test_select_account_number_raises_when_accounts_are_missing() -> None:
    with pytest.raises(EonNextRatesUnsupportedError, match="No accounts"):
        select_account_number({"accounts": []})


def test_select_active_half_hourly_agreement_returns_current_agreement() -> None:
    account = {
        "electricityAgreements": [
            {
                "id": "agreement-old",
                "validFrom": "2026-04-01T00:00:00+00:00",
                "validTo": "2026-04-30T00:00:00+00:00",
                "tariff": {"__typename": "HalfHourlyTariff"},
            },
            {
                "id": "agreement-current",
                "validFrom": "2026-04-30T00:00:00+00:00",
                "validTo": "2026-05-31T00:00:00+00:00",
                "tariff": {"__typename": "HalfHourlyTariff"},
            },
        ]
    }

    agreement = select_active_half_hourly_agreement(
        account, datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    )

    assert agreement["id"] == "agreement-current"


def test_select_active_half_hourly_agreement_returns_open_ended_current_agreement() -> None:
    account = {
        "electricityAgreements": [
            {
                "id": "agreement-current",
                "validFrom": "2026-04-30T00:00:00+00:00",
                "validTo": None,
                "tariff": {"__typename": "HalfHourlyTariff"},
            }
        ]
    }

    agreement = select_active_half_hourly_agreement(
        account, datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    )

    assert agreement["id"] == "agreement-current"


def test_select_active_half_hourly_agreement_raises_when_no_match_exists() -> None:
    account = {
        "electricityAgreements": [
            {
                "id": "agreement-fixed",
                "validFrom": "2026-04-01T00:00:00+00:00",
                "validTo": "2026-05-31T00:00:00+00:00",
                "tariff": {"__typename": "DayNightTariff"},
            }
        ]
    }

    with pytest.raises(
        EonNextRatesUnsupportedError,
        match="active HalfHourlyTariff electricity agreement",
    ):
        select_active_half_hourly_agreement(
            account, datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
        )


def test_client_discovers_first_account_with_usable_snapshot() -> None:
    session = _FakeSession(
        [
            _token_payload("access-1", "refresh-1", 2000000000),
            _viewer_payload_for_accounts("A-UNUSABLE", "A-SUPPORTED"),
            {
                "data": {
                    "account": {
                        "number": "A-UNUSABLE",
                        "electricityAgreements": [
                            {
                                "id": "agreement-current",
                                "validFrom": "2026-04-01T00:00:00+00:00",
                                "validTo": None,
                                "tariff": {
                                    "__typename": "HalfHourlyTariff",
                                    "displayName": "Next Drive Smart V5.2",
                                    "tariffCode": "E-TOU-NEXT_DRIVE_SMART_V5_2-N",
                                    "standingCharge": 60.00015,
                                    "preVatStandingCharge": 57.143,
                                    "unitRates": [],
                                },
                            }
                        ],
                    }
                }
            },
            {
                "data": {
                    "account": {
                        "number": "A-SUPPORTED",
                        "electricityAgreements": [
                            {
                                "id": "agreement-current",
                                "validFrom": "2026-04-01T00:00:00+00:00",
                                "validTo": None,
                                "tariff": {
                                    "__typename": "HalfHourlyTariff",
                                    "displayName": "Next Drive Smart V5.2",
                                    "tariffCode": "E-TOU-NEXT_DRIVE_SMART_V5_2-N",
                                    "standingCharge": 60.00015,
                                    "preVatStandingCharge": 57.143,
                                    "unitRates": [
                                        {
                                            "value": 23.9022,
                                            "validFrom": "2026-05-01T12:00:00+00:00",
                                            "validTo": "2026-05-01T12:30:00+00:00",
                                        },
                                        {
                                            "value": 24.5,
                                            "validFrom": "2026-05-01T12:30:00+00:00",
                                            "validTo": "2026-05-01T13:00:00+00:00",
                                        },
                                    ],
                                },
                            }
                        ],
                    }
                }
            },
        ]
    )
    client = EonNextRatesClient(
        session,
        email="user@example.com",
        password="secret",
        now=lambda: datetime(2026, 5, 1, 12, 15, tzinfo=UTC),
    )

    account_number = asyncio.run(client.async_discover_account_number())

    assert account_number == "A-SUPPORTED"
    assert session.requests[2]["json"]["variables"] == {"accountNumber": "A-UNUSABLE"}
    assert session.requests[3]["json"]["variables"] == {"accountNumber": "A-SUPPORTED"}


def test_client_discovers_account_and_fetches_account_snapshot() -> None:
    agreement_payload = {
        "data": {
            "account": {
                "number": "A-TEST0001",
                "balance": 12345,
                "bills": _bills_payload(
                    {
                        "__typename": "PaymentType",
                        "billType": "payment",
                        "issuedDate": "2026-05-02",
                    },
                    _statement_node(),
                ),
                "gasAgreements": [
                    _gas_agreement_payload_with_meter_readings(
                        {
                            "readAt": "2026-05-02T13:00:00+00:00",
                            "readingSource": "CUSTOMER",
                            "source": "SMART",
                            "readingType": "actual",
                            "registers": [
                                {
                                    "identifier": "GAS-001",
                                    "name": "GAS",
                                    "value": "4567.0",
                                    "digits": 4,
                                    "isQuarantined": False,
                                }
                            ],
                        }
                    )
                ],
                "electricityAgreements": [
                    {
                        "id": "agreement-current",
                        "validFrom": "2026-04-01T00:00:00+00:00",
                        "validTo": "2026-06-01T00:00:00+00:00",
                        "meterPoint": {
                            "mpan": "0012345678901",
                            "unbilledReadings": {"readAt": "2026-05-02T11:00:00+00:00"},
                        },
                        "tariff": {
                            "__typename": "HalfHourlyTariff",
                            "displayName": "Next Drive Smart V5.2",
                            "tariffCode": "E-TOU-NEXT_DRIVE_SMART_V5_2-N",
                            "standingCharge": 60.00015,
                            "preVatStandingCharge": 57.143,
                            "unitRates": [
                                {
                                    "value": 23.9022,
                                    "validFrom": "2026-05-01T12:00:00+00:00",
                                    "validTo": "2026-05-01T12:30:00+00:00",
                                },
                                {
                                    "value": 24.5,
                                    "validFrom": "2026-05-01T12:30:00+00:00",
                                    "validTo": "2026-05-01T13:00:00+00:00",
                                },
                            ],
                        },
                    }
                ],
            }
        }
    }
    session = _FakeSession(
        [
            _token_payload("access-1", "refresh-1", 2000000000),
            _viewer_payload(),
            agreement_payload,
            agreement_payload,
            _smartflex_devices_graphql_payload(),
        ]
    )
    client = EonNextRatesClient(
        session,
        email="user@example.com",
        password="secret",
        now=lambda: datetime(2026, 5, 1, 12, 15, tzinfo=UTC),
    )

    snapshot = asyncio.run(client.async_get_account_snapshot())

    assert snapshot == AccountSnapshot(
        current_rate_gbp_per_kwh=0.239022,
        next_rate_gbp_per_kwh=0.245,
        next_rate_change_at=datetime(2026, 5, 1, 12, 30, tzinfo=UTC),
        account_number="A-TEST0001",
        current_window_end=datetime(2026, 5, 1, 12, 30, tzinfo=UTC),
        next_window_start=datetime(2026, 5, 1, 12, 30, tzinfo=UTC),
        agreement_valid_from=datetime(2026, 4, 1, 0, 0, tzinfo=UTC),
        agreement_valid_to=datetime(2026, 6, 1, 0, 0, tzinfo=UTC),
        pre_vat_standing_charge_gbp_per_day=0.57143,
        tariff_name="Next Drive Smart V5.2",
        tariff_code="E-TOU-NEXT_DRIVE_SMART_V5_2-N",
        standing_charge_gbp_per_day=0.6000015,
        latest_meter_reading_kwh=None,
        latest_meter_reading_at=None,
        latest_meter_reading_source=None,
        latest_meter_reading_type=None,
        latest_meter_reading_register_identifier=None,
        latest_meter_reading_register_name=None,
        latest_meter_reading_register_digits=None,
        latest_meter_reading_register_is_quarantined=None,
        meter_point_mpan="0012345678901",
        current_account_balance_gbp=123.45,
        latest_statement_issued_at=datetime(2026, 5, 1, 0, 0, tzinfo=UTC),
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
    assert session.requests[0]["json"]["query"] == LOGIN_MUTATION
    assert session.requests[1]["json"]["query"] == VIEWER_QUERY
    assert session.requests[1]["headers"]["authorization"] == "JWT access-1"
    assert session.requests[2]["json"]["query"] == AGREEMENTS_QUERY
    assert "bills(first: 1, orderBy: ISSUED_DATE_DESC)" in session.requests[2]["json"]["query"]
    assert session.requests[2]["json"]["variables"] == {"accountNumber": "A-TEST0001"}
    assert session.requests[3]["json"]["query"] == AGREEMENTS_QUERY
    assert "bills(first: 1, orderBy: ISSUED_DATE_DESC)" in session.requests[3]["json"]["query"]
    assert session.requests[3]["json"]["variables"] == {"accountNumber": "A-TEST0001"}
    assert session.requests[4]["json"]["variables"] == {"accountNumber": "A-TEST0001"}
    assert len(session.requests) == 5
    assert snapshot.current_account_balance_gbp == 123.45
    assert snapshot.latest_statement_closing_balance_gbp == 98.76
    assert snapshot.latest_statement_charges_gbp == 54.32
    assert snapshot.gas_rate_gbp_per_kwh == 0.06543
    assert snapshot.gas_meter_point_mprn == "1234567890"


def test_async_get_account_snapshot_includes_smartflex_devices_and_planned_dispatches(
) -> None:
    agreement_payload = {
        "data": {
            "account": {
                "number": "A-TEST0001",
                "electricityAgreements": [
                    {
                        "id": "agreement-current",
                        "validFrom": "2026-04-01T00:00:00+00:00",
                        "validTo": None,
                        "meterPoint": {
                            "mpan": "0012345678901",
                            "unbilledReadings": [],
                        },
                        "tariff": {
                            "__typename": "HalfHourlyTariff",
                            "displayName": "Next Drive Smart V5.2",
                            "tariffCode": "E-TOU-NEXT_DRIVE_SMART_V5_2-N",
                            "standingCharge": 60.00015,
                            "preVatStandingCharge": 57.143,
                            "unitRates": [
                                {
                                    "value": 23.9022,
                                    "validFrom": "2026-05-01T12:00:00+00:00",
                                    "validTo": "2026-05-01T12:30:00+00:00",
                                },
                                {
                                    "value": 24.5,
                                    "validFrom": "2026-05-01T12:30:00+00:00",
                                    "validTo": "2026-05-01T13:00:00+00:00",
                                },
                            ],
                        },
                    }
                ],
            }
        }
    }
    session = _FakeSession(
        [
            _token_payload("access-1", "refresh-1", 2000000000),
            _viewer_payload(),
            agreement_payload,
            agreement_payload,
            _smartflex_devices_graphql_payload(
                _smartflex_vehicle_graphql_payload(
                    charging_sessions=[
                        _smartflex_graphql_charging_session_payload(
                            start="2026-05-01T18:00:00+00:00",
                            end="2026-05-01T19:00:00+00:00",
                            state_of_charge_change=18,
                            state_of_charge_final=42,
                            energy_added_value=3.2,
                            energy_added_unit="kWh",
                            cost_amount=0.64,
                            cost_currency="GBP",
                        )
                    ]
                ),
                _smartflex_charge_point_graphql_payload(
                    charging_sessions=[
                        _smartflex_graphql_charging_session_payload(
                            start="2026-05-01T20:00:00+00:00",
                            end=None,
                            state_of_charge_change=23,
                            state_of_charge_final=55,
                            energy_added_value=5.6,
                            energy_added_unit="kWh",
                            cost_amount=1.12,
                            cost_currency="GBP",
                        )
                    ]
                ),
                _smartflex_non_ev_graphql_payload(),
            ),
            _smartflex_planned_dispatches_graphql_payload(
                {
                    "start": "2026-05-01T22:00:00+00:00",
                    "end": "2026-05-01T22:30:00+00:00",
                    "type": "GRID_CHARGE",
                    "energyAddedKwh": 4.4,
                },
                {
                    "start": "2026-05-01T21:00:00+00:00",
                    "end": "2026-05-01T21:30:00+00:00",
                    "type": "GRID_CHARGE",
                    "energyAddedKwh": 2.5,
                },
            ),
            _smartflex_planned_dispatches_graphql_payload(
                {
                    "start": "2026-05-01T23:00:00+00:00",
                    "end": "2026-05-01T23:30:00+00:00",
                    "type": "GRID_CHARGE",
                    "energyAddedKwh": 3.3,
                }
            ),
        ]
    )
    client = EonNextRatesClient(
        session,
        email="user@example.com",
        password="secret",
        now=lambda: datetime(2026, 5, 1, 12, 15, tzinfo=UTC),
    )

    snapshot = asyncio.run(client.async_get_account_snapshot())

    assert len(snapshot.smartflex_devices) == 2
    assert snapshot.smartflex_devices[0] == SmartFlexDeviceSnapshot(
        device_id="vehicle-1",
        name="Family EV",
        device_type="EV",
        provider="EON_NEXT_DRIVE",
        integration_device_id="vehicle-integration-1",
        property_id="property-1",
        make="Kia",
        model="EV6",
        vehicle_battery_size_kwh=77.4,
        charge_point_power_output_kw=None,
        lifecycle_status="LIVE",
        current_state="READY",
        is_suspended=False,
        state_of_charge=SmartFlexReadingSnapshot(
            timestamp=datetime(2026, 5, 1, 20, 10, tzinfo=UTC),
            value=55.0,
        ),
        active_power=SmartFlexReadingSnapshot(
            timestamp=datetime(2026, 5, 1, 20, 10, tzinfo=UTC),
            value=6.8,
        ),
        state_of_charge_limit=SmartFlexSocLimitSnapshot(
            upper_soc_limit=90.0,
            timestamp=datetime(2026, 5, 1, 20, 0, tzinfo=UTC),
            is_limit_violated=False,
        ),
        test_dispatch_failure_reason=None,
        latest_charging_session=SmartFlexChargingSessionSnapshot(
            start=datetime(2026, 5, 1, 18, 0, tzinfo=UTC),
            end=datetime(2026, 5, 1, 19, 0, tzinfo=UTC),
            state_of_charge_change=18,
            state_of_charge_final=42,
            energy_added_value=3.2,
            energy_added_unit="kWh",
            cost_amount=0.64,
            cost_currency="GBP",
        ),
        next_planned_dispatch=SmartFlexPlannedDispatchSnapshot(
            start=datetime(2026, 5, 1, 21, 0, tzinfo=UTC),
            end=datetime(2026, 5, 1, 21, 30, tzinfo=UTC),
            dispatch_type="GRID_CHARGE",
            energy_added_kwh=2.5,
        ),
    )
    assert snapshot.smartflex_devices[1] == SmartFlexDeviceSnapshot(
        device_id="charger-1",
        name="Driveway Charger",
        device_type="EV_CHARGER",
        provider="EON_NEXT_DRIVE",
        integration_device_id="charger-integration-1",
        property_id="property-1",
        make="Wallbox",
        model="Pulsar Plus",
        vehicle_battery_size_kwh=None,
        charge_point_power_output_kw=7.4,
        lifecycle_status="LIVE",
        current_state="CHARGING",
        is_suspended=False,
        state_of_charge=SmartFlexReadingSnapshot(
            timestamp=datetime(2026, 5, 1, 20, 10, tzinfo=UTC),
            value=55.0,
        ),
        active_power=SmartFlexReadingSnapshot(
            timestamp=datetime(2026, 5, 1, 20, 10, tzinfo=UTC),
            value=6.8,
        ),
        state_of_charge_limit=SmartFlexSocLimitSnapshot(
            upper_soc_limit=90.0,
            timestamp=datetime(2026, 5, 1, 20, 0, tzinfo=UTC),
            is_limit_violated=False,
        ),
        test_dispatch_failure_reason=None,
        latest_charging_session=SmartFlexChargingSessionSnapshot(
            start=datetime(2026, 5, 1, 20, 0, tzinfo=UTC),
            end=None,
            state_of_charge_change=23,
            state_of_charge_final=55,
            energy_added_value=5.6,
            energy_added_unit="kWh",
            cost_amount=1.12,
            cost_currency="GBP",
        ),
        next_planned_dispatch=SmartFlexPlannedDispatchSnapshot(
            start=datetime(2026, 5, 1, 23, 0, tzinfo=UTC),
            end=datetime(2026, 5, 1, 23, 30, tzinfo=UTC),
            dispatch_type="GRID_CHARGE",
            energy_added_kwh=3.3,
        ),
    )
    assert not hasattr(snapshot, "latest_completed_dispatch")
    assert session.requests[4]["json"]["variables"] == {"accountNumber": "A-TEST0001"}
    assert "devices(accountNumber: $accountNumber)" in session.requests[4]["json"]["query"]
    assert "deviceType" in session.requests[4]["json"]["query"]
    assert session.requests[5]["json"]["variables"] == {"deviceId": "vehicle-1"}
    assert "flexPlannedDispatches(deviceId: $deviceId)" in session.requests[5]["json"]["query"]
    assert session.requests[6]["json"]["variables"] == {"deviceId": "charger-1"}
    assert len(session.requests) == 7


def test_async_get_account_snapshot_ignores_optional_planned_dispatch_query_failures() -> None:
    agreement_payload = {
        "data": {
            "account": {
                "number": "A-TEST0001",
                "electricityAgreements": [
                    {
                        "id": "agreement-current",
                        "validFrom": "2026-04-01T00:00:00+00:00",
                        "validTo": None,
                        "meterPoint": {
                            "mpan": "0012345678901",
                            "unbilledReadings": [],
                        },
                        "tariff": {
                            "__typename": "HalfHourlyTariff",
                            "displayName": "Next Drive Smart V5.2",
                            "tariffCode": "E-TOU-NEXT_DRIVE_SMART_V5_2-N",
                            "standingCharge": 60.00015,
                            "preVatStandingCharge": 57.143,
                            "unitRates": [
                                {
                                    "value": 23.9022,
                                    "validFrom": "2026-05-01T12:00:00+00:00",
                                    "validTo": "2026-05-01T12:30:00+00:00",
                                },
                                {
                                    "value": 24.5,
                                    "validFrom": "2026-05-01T12:30:00+00:00",
                                    "validTo": "2026-05-01T13:00:00+00:00",
                                },
                            ],
                        },
                    }
                ],
            }
        }
    }
    session = _FakeSession(
        [
            _token_payload("access-1", "refresh-1", 2000000000),
            _viewer_payload(),
            agreement_payload,
            agreement_payload,
            _smartflex_devices_graphql_payload(
                _smartflex_vehicle_graphql_payload(
                    device_id="vehicle-1",
                    charging_sessions=[
                        _smartflex_graphql_charging_session_payload(
                            start="2026-05-01T18:00:00+00:00",
                            end="2026-05-01T19:00:00+00:00",
                            state_of_charge_change=18,
                            state_of_charge_final=42,
                            energy_added_value=3.2,
                            energy_added_unit="kWh",
                            cost_amount=0.64,
                            cost_currency="GBP",
                        )
                    ],
                )
            ),
            _graphql_error_payload("Planned dispatch query failed"),
        ]
    )
    client = EonNextRatesClient(
        session,
        email="user@example.com",
        password="secret",
        now=lambda: datetime(2026, 5, 1, 12, 15, tzinfo=UTC),
    )

    snapshot = asyncio.run(client.async_get_account_snapshot())

    assert snapshot.account_number == "A-TEST0001"
    assert snapshot.current_rate_gbp_per_kwh == 0.239022
    assert snapshot.smartflex_devices == (
        SmartFlexDeviceSnapshot(
            device_id="vehicle-1",
            name="Family EV",
            device_type="EV",
            provider="EON_NEXT_DRIVE",
            integration_device_id="vehicle-integration-1",
            property_id="property-1",
            make="Kia",
            model="EV6",
            vehicle_battery_size_kwh=77.4,
            charge_point_power_output_kw=None,
            lifecycle_status="LIVE",
            current_state="READY",
            is_suspended=False,
            state_of_charge=SmartFlexReadingSnapshot(
                timestamp=datetime(2026, 5, 1, 20, 10, tzinfo=UTC),
                value=55.0,
            ),
            active_power=SmartFlexReadingSnapshot(
                timestamp=datetime(2026, 5, 1, 20, 10, tzinfo=UTC),
                value=6.8,
            ),
            state_of_charge_limit=SmartFlexSocLimitSnapshot(
                upper_soc_limit=90.0,
                timestamp=datetime(2026, 5, 1, 20, 0, tzinfo=UTC),
                is_limit_violated=False,
            ),
            test_dispatch_failure_reason=None,
            latest_charging_session=SmartFlexChargingSessionSnapshot(
                start=datetime(2026, 5, 1, 18, 0, tzinfo=UTC),
                end=datetime(2026, 5, 1, 19, 0, tzinfo=UTC),
                state_of_charge_change=18,
                state_of_charge_final=42,
                energy_added_value=3.2,
                energy_added_unit="kWh",
                cost_amount=0.64,
                cost_currency="GBP",
            ),
            next_planned_dispatch=None,
        ),
    )
    assert not hasattr(snapshot, "latest_completed_dispatch")


def test_async_get_account_snapshot_returns_no_smartflex_devices_when_devices_query_fails() -> None:
    agreement_payload = {
        "data": {
            "account": {
                "number": "A-TEST0001",
                "electricityAgreements": [
                    {
                        "id": "agreement-current",
                        "validFrom": "2026-04-01T00:00:00+00:00",
                        "validTo": None,
                        "meterPoint": {
                            "mpan": "0012345678901",
                            "unbilledReadings": [],
                        },
                        "tariff": {
                            "__typename": "HalfHourlyTariff",
                            "displayName": "Next Drive Smart V5.2",
                            "tariffCode": "E-TOU-NEXT_DRIVE_SMART_V5_2-N",
                            "standingCharge": 60.00015,
                            "preVatStandingCharge": 57.143,
                            "unitRates": [
                                {
                                    "value": 23.9022,
                                    "validFrom": "2026-05-01T12:00:00+00:00",
                                    "validTo": "2026-05-01T12:30:00+00:00",
                                },
                                {
                                    "value": 24.5,
                                    "validFrom": "2026-05-01T12:30:00+00:00",
                                    "validTo": "2026-05-01T13:00:00+00:00",
                                },
                            ],
                        },
                    }
                ],
            }
        }
    }
    session = _FakeSession(
        [
            _token_payload("access-1", "refresh-1", 2000000000),
            _viewer_payload(),
            agreement_payload,
            agreement_payload,
            _graphql_error_payload("Devices query failed"),
        ]
    )
    client = EonNextRatesClient(
        session,
        email="user@example.com",
        password="secret",
        now=lambda: datetime(2026, 5, 1, 12, 15, tzinfo=UTC),
    )

    snapshot = asyncio.run(client.async_get_account_snapshot())

    assert snapshot.account_number == "A-TEST0001"
    assert snapshot.current_rate_gbp_per_kwh == 0.239022
    assert snapshot.smartflex_devices == ()
    assert not hasattr(snapshot, "latest_completed_dispatch")


def test_async_get_account_snapshot_ignores_past_planned_dispatches() -> None:
    agreement_payload = {
        "data": {
            "account": {
                "number": "A-TEST0001",
                "electricityAgreements": [
                    {
                        "id": "agreement-current",
                        "validFrom": "2026-04-01T00:00:00+00:00",
                        "validTo": None,
                        "meterPoint": {
                            "mpan": "0012345678901",
                            "unbilledReadings": [],
                        },
                        "tariff": {
                            "__typename": "HalfHourlyTariff",
                            "displayName": "Next Drive Smart V5.2",
                            "tariffCode": "E-TOU-NEXT_DRIVE_SMART_V5_2-N",
                            "standingCharge": 60.00015,
                            "preVatStandingCharge": 57.143,
                            "unitRates": [
                                {
                                    "value": 23.9022,
                                    "validFrom": "2026-05-01T12:00:00+00:00",
                                    "validTo": "2026-05-01T12:30:00+00:00",
                                },
                                {
                                    "value": 24.5,
                                    "validFrom": "2026-05-01T12:30:00+00:00",
                                    "validTo": "2026-05-01T13:00:00+00:00",
                                },
                            ],
                        },
                    }
                ],
            }
        }
    }
    session = _FakeSession(
        [
            _token_payload("access-1", "refresh-1", 2000000000),
            _viewer_payload(),
            agreement_payload,
            agreement_payload,
            _smartflex_devices_graphql_payload(_smartflex_vehicle_graphql_payload()),
            _smartflex_planned_dispatches_graphql_payload(
                {
                    "start": "2026-05-01T11:30:00+00:00",
                    "end": "2026-05-01T12:00:00+00:00",
                    "type": "GRID_CHARGE",
                    "energyAddedKwh": 1.1,
                },
                {
                    "start": "2026-05-01T12:45:00+00:00",
                    "end": "2026-05-01T13:15:00+00:00",
                    "type": "GRID_CHARGE",
                    "energyAddedKwh": 2.2,
                },
            ),
        ]
    )
    client = EonNextRatesClient(
        session,
        email="user@example.com",
        password="secret",
        now=lambda: datetime(2026, 5, 1, 12, 15, tzinfo=UTC),
    )

    snapshot = asyncio.run(client.async_get_account_snapshot())

    assert snapshot.smartflex_devices[0].next_planned_dispatch == SmartFlexPlannedDispatchSnapshot(
        start=datetime(2026, 5, 1, 12, 45, tzinfo=UTC),
        end=datetime(2026, 5, 1, 13, 15, tzinfo=UTC),
        dispatch_type="GRID_CHARGE",
        energy_added_kwh=2.2,
    )


def test_client_refreshes_stale_token_before_reuse() -> None:
    session = _FakeSession(
        [
            _token_payload("access-1", "refresh-1", 1),
            _viewer_payload(),
            {
                "data": {
                    "account": {
                        "number": "A-TEST0001",
                        "electricityAgreements": [
                            {
                                "id": "agreement-current",
                                "validFrom": "2026-04-01T00:00:00+00:00",
                                "validTo": None,
                                "tariff": {
                                    "__typename": "HalfHourlyTariff",
                                    "displayName": "Next Drive Smart V5.2",
                                    "tariffCode": "E-TOU-NEXT_DRIVE_SMART_V5_2-N",
                                    "standingCharge": 60.00015,
                                    "unitRates": [
                                        {
                                            "value": 23.9022,
                                            "validFrom": "2026-04-01T00:00:00+00:00",
                                            "validTo": "2026-06-01T00:00:00+00:00",
                                        }
                                    ],
                                },
                            }
                        ],
                    }
                }
            },
            _token_payload("access-2", "refresh-2", 2000003600),
            _viewer_payload("A-SECOND"),
            {
                "data": {
                    "account": {
                        "number": "A-SECOND",
                        "electricityAgreements": [
                            {
                                "id": "agreement-current",
                                "validFrom": "2026-04-01T00:00:00+00:00",
                                "validTo": None,
                                "tariff": {
                                    "__typename": "HalfHourlyTariff",
                                    "displayName": "Next Drive Smart V5.2",
                                    "tariffCode": "E-TOU-NEXT_DRIVE_SMART_V5_2-N",
                                    "standingCharge": 60.00015,
                                    "unitRates": [
                                        {
                                            "value": 23.9022,
                                            "validFrom": "2026-04-01T00:00:00+00:00",
                                            "validTo": "2026-06-01T00:00:00+00:00",
                                        }
                                    ],
                                },
                            }
                        ],
                    }
                }
            },
        ]
    )
    client = EonNextRatesClient(
        session,
        email="user@example.com",
        password="secret",
        now=lambda: datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
    )

    first_account_number = asyncio.run(client.async_discover_account_number())
    second_account_number = asyncio.run(client.async_discover_account_number())

    assert first_account_number == "A-TEST0001"
    assert second_account_number == "A-SECOND"
    assert session.requests[0]["json"]["query"] == LOGIN_MUTATION
    assert session.requests[3]["json"]["query"] == REFRESH_MUTATION
    assert session.requests[4]["headers"]["authorization"] == "JWT access-2"


def test_client_retries_once_with_new_token_after_auth_failure() -> None:
    session = _FakeSession(
        [
            _token_payload("access-1", "refresh-1", 2000000000),
            _auth_error_payload(),
            _token_payload("access-2", "refresh-2", 2000003600),
            _viewer_payload(),
            {
                "data": {
                    "account": {
                        "number": "A-TEST0001",
                        "electricityAgreements": [
                            {
                                "id": "agreement-current",
                                "validFrom": "2026-04-01T00:00:00+00:00",
                                "validTo": None,
                                "tariff": {
                                    "__typename": "HalfHourlyTariff",
                                    "displayName": "Next Drive Smart V5.2",
                                    "tariffCode": "E-TOU-NEXT_DRIVE_SMART_V5_2-N",
                                    "standingCharge": 60.00015,
                                    "unitRates": [
                                        {
                                            "value": 23.9022,
                                            "validFrom": "2026-04-01T00:00:00+00:00",
                                            "validTo": "2026-06-01T00:00:00+00:00",
                                        }
                                    ],
                                },
                            }
                        ],
                    }
                }
            },
        ]
    )
    client = EonNextRatesClient(session, email="user@example.com", password="secret")

    account_number = asyncio.run(client.async_discover_account_number())

    assert account_number == "A-TEST0001"
    assert session.requests[1]["headers"]["authorization"] == "JWT access-1"
    assert session.requests[2]["json"]["query"] == REFRESH_MUTATION
    assert session.requests[3]["headers"]["authorization"] == "JWT access-2"


def test_client_raises_after_single_auth_retry_fails() -> None:
    session = _FakeSession(
        [
            _token_payload("access-1", "refresh-1", 2000000000),
            _auth_error_payload(),
            _token_payload("access-2", "refresh-2", 2000003600),
            _auth_error_payload(),
        ]
    )
    client = EonNextRatesClient(session, email="user@example.com", password="secret")

    with pytest.raises(EonNextRatesAuthError, match="UNAUTHENTICATED"):
        asyncio.run(client.async_discover_account_number())


def test_build_tariff_snapshot_rejects_non_half_hourly_tariffs() -> None:
    agreement = {
        "validFrom": "2026-04-01T00:00:00+00:00",
        "validTo": None,
        "tariff": {
            "__typename": "DayNightTariff",
            "displayName": "Legacy Two Rate",
            "tariffCode": "legacy",
            "standingCharge": 50.0,
        }
    }

    with pytest.raises(EonNextRatesUnsupportedError, match="HalfHourlyTariff"):
        build_account_snapshot(
            _account_payload(),
            agreement,
            datetime(2026, 4, 30, 20, 30, tzinfo=UTC),
        )


def test_build_tariff_snapshot_raises_when_now_is_not_covered() -> None:
    agreement = {
        "validFrom": "2026-04-01T00:00:00+00:00",
        "validTo": None,
        "tariff": {
            "__typename": "HalfHourlyTariff",
            "displayName": "Next Drive Smart V5.2",
            "tariffCode": "E-TOU-NEXT_DRIVE_SMART_V5_2-N",
            "standingCharge": 60.00015,
            "unitRates": [
                {
                    "value": 2.9925,
                    "validFrom": "2026-04-30T18:00:00+00:00",
                    "validTo": "2026-04-30T20:00:00+00:00",
                },
                {
                    "value": 23.9022,
                    "validFrom": "2026-04-30T23:00:00+00:00",
                    "validTo": "2026-05-01T05:00:00+00:00",
                },
            ],
        }
    }

    with pytest.raises(EonNextRatesUnsupportedError, match="No current HalfHourlyTariff window"):
        build_account_snapshot(
            _account_payload(),
            agreement,
            datetime(2026, 4, 30, 20, 30, tzinfo=UTC),
        )


def test_build_tariff_snapshot_returns_none_when_next_window_is_missing() -> None:
    agreement = {
        "validFrom": "2026-04-01T00:00:00+00:00",
        "validTo": None,
        "tariff": {
            "__typename": "HalfHourlyTariff",
            "displayName": "Next Drive Smart V5.2",
            "tariffCode": "E-TOU-NEXT_DRIVE_SMART_V5_2-N",
            "standingCharge": 60.00015,
            "unitRates": [
                {
                    "value": 23.9022,
                    "validFrom": "2026-04-30T05:00:00+00:00",
                    "validTo": "2026-04-30T23:00:00+00:00",
                }
            ],
        }
    }

    snapshot = build_account_snapshot(
        _account_payload(),
        agreement,
        datetime(2026, 4, 30, 20, 30, tzinfo=UTC),
    )

    assert snapshot == AccountSnapshot(
        current_rate_gbp_per_kwh=0.239022,
        next_rate_gbp_per_kwh=None,
        next_rate_change_at=None,
        account_number="A-TEST0001",
        current_window_end=datetime(2026, 4, 30, 23, 0, tzinfo=UTC),
        next_window_start=None,
        agreement_valid_from=datetime(2026, 4, 1, 0, 0, tzinfo=UTC),
        agreement_valid_to=None,
        pre_vat_standing_charge_gbp_per_day=None,
        tariff_name="Next Drive Smart V5.2",
        tariff_code="E-TOU-NEXT_DRIVE_SMART_V5_2-N",
        standing_charge_gbp_per_day=0.6000015,
    )


@pytest.mark.parametrize(
    ("valid_to_value", "include_valid_to"),
    [
        (None, True),
        (None, False),
    ],
)
def test_build_tariff_snapshot_raises_when_current_window_is_missing_valid_to(
    valid_to_value: str | None, include_valid_to: bool
) -> None:
    current_window: dict[str, Any] = {
        "value": 23.9022,
        "validFrom": "2026-04-30T05:00:00+00:00",
    }
    if include_valid_to:
        current_window["validTo"] = valid_to_value

    agreement = {
        "validFrom": "2026-04-01T00:00:00+00:00",
        "validTo": None,
        "tariff": {
            "__typename": "HalfHourlyTariff",
            "displayName": "Next Drive Smart V5.2",
            "tariffCode": "E-TOU-NEXT_DRIVE_SMART_V5_2-N",
            "standingCharge": 60.00015,
            "unitRates": [current_window],
        },
    }

    with pytest.raises(
        EonNextRatesUnsupportedError,
        match="Current HalfHourlyTariff window is missing validTo",
    ):
        build_account_snapshot(
            _account_payload(),
            agreement,
            datetime(2026, 4, 30, 20, 30, tzinfo=UTC),
        )


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("unitRates", []),
        ("displayName", None),
        ("tariffCode", None),
        ("standingCharge", None),
    ],
)
def test_build_tariff_snapshot_rejects_incomplete_tariff_payloads(
    field_name: str, field_value: object
) -> None:
    tariff = {
        "__typename": "HalfHourlyTariff",
        "displayName": "Next Drive Smart V5.2",
        "tariffCode": "E-TOU-NEXT_DRIVE_SMART_V5_2-N",
        "standingCharge": 60.00015,
        "unitRates": [
            {
                "value": 23.9022,
                "validFrom": "2026-04-30T05:00:00+00:00",
                "validTo": "2026-04-30T23:00:00+00:00",
            }
        ],
    }
    tariff.pop(field_name)
    if field_value is not None:
        tariff[field_name] = field_value

    with pytest.raises(EonNextRatesUnsupportedError, match=field_name):
        build_account_snapshot(
            _account_payload(),
            {"validFrom": "2026-04-01T00:00:00+00:00", "validTo": None, "tariff": tariff},
            datetime(2026, 4, 30, 20, 30, tzinfo=UTC),
        )


def test_build_tariff_snapshot_raises_when_next_window_is_not_contiguous() -> None:
    agreement = {
        "validFrom": "2026-04-01T00:00:00+00:00",
        "validTo": None,
        "tariff": {
            "__typename": "HalfHourlyTariff",
            "displayName": "Next Drive Smart V5.2",
            "tariffCode": "E-TOU-NEXT_DRIVE_SMART_V5_2-N",
            "standingCharge": 60.00015,
            "unitRates": [
                {
                    "value": 23.9022,
                    "validFrom": "2026-04-30T05:00:00+00:00",
                    "validTo": "2026-04-30T23:00:00+00:00",
                },
                {
                    "value": 2.9925,
                    "validFrom": "2026-04-30T23:30:00+00:00",
                    "validTo": "2026-05-01T05:00:00+00:00",
                },
            ],
        }
    }

    with pytest.raises(EonNextRatesUnsupportedError, match="contiguous"):
        build_account_snapshot(
            _account_payload(),
            agreement,
            datetime(2026, 4, 30, 20, 30, tzinfo=UTC),
        )
