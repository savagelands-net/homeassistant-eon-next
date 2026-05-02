from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest

from custom_components.eon_next.api import (
    AGREEMENTS_QUERY,
    LOGIN_MUTATION,
    REFRESH_MUTATION,
    VIEWER_QUERY,
    AccountSnapshot,
    EonNextRatesAuthError,
    EonNextRatesClient,
    EonNextRatesUnsupportedError,
    build_account_snapshot,
    select_account_number,
    select_active_half_hourly_agreement,
)


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


def _auth_error_payload() -> dict[str, Any]:
    return {
        "errors": [
            {
                "message": "Signature has expired",
                "extensions": {"code": "UNAUTHENTICATED"},
            }
        ]
    }


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
    assert "bills(last: 5, orderBy: ISSUED_DATE_DESC)" in session.requests[2]["json"]["query"]
    assert session.requests[2]["json"]["variables"] == {"accountNumber": "A-TEST0001"}
    assert session.requests[3]["json"]["query"] == AGREEMENTS_QUERY
    assert "bills(last: 5, orderBy: ISSUED_DATE_DESC)" in session.requests[3]["json"]["query"]
    assert session.requests[3]["json"]["variables"] == {"accountNumber": "A-TEST0001"}
    assert snapshot.current_account_balance_gbp == 123.45
    assert snapshot.latest_statement_closing_balance_gbp == 98.76
    assert snapshot.latest_statement_charges_gbp == 54.32
    assert snapshot.gas_rate_gbp_per_kwh == 0.06543
    assert snapshot.gas_meter_point_mprn == "1234567890"


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
