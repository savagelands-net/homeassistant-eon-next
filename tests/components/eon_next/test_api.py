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
    EonNextRatesAuthError,
    EonNextRatesClient,
    EonNextRatesUnsupportedError,
    TariffSnapshot,
    build_tariff_snapshot,
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


def _viewer_payload(account_number: str = "A-116BA522") -> dict[str, Any]:
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

    snapshot = build_tariff_snapshot(agreement, now)

    assert snapshot == TariffSnapshot(
        current_rate_gbp_per_kwh=0.239022,
        next_rate_gbp_per_kwh=0.029925,
        next_rate_change_at=datetime(2026, 4, 30, 23, 0, tzinfo=UTC),
        tariff_name="Next Drive Smart V5.2",
        tariff_code="E-TOU-NEXT_DRIVE_SMART_V5_2-N",
        standing_charge_gbp_per_day=0.6000015,
    )


def test_build_tariff_snapshot_allows_missing_next_window() -> None:
    agreement = {
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

    snapshot = build_tariff_snapshot(
        agreement,
        datetime(2026, 5, 1, 9, 50, tzinfo=UTC),
    )

    assert snapshot == TariffSnapshot(
        current_rate_gbp_per_kwh=0.239022,
        next_rate_gbp_per_kwh=None,
        next_rate_change_at=None,
        tariff_name="Next Drive Smart V5.2",
        tariff_code="E-TOU-NEXT_DRIVE_SMART_V5_2-N",
        standing_charge_gbp_per_day=0.6000015,
    )


def test_select_account_number_returns_first_account_number() -> None:
    viewer = {
        "accounts": [
            {"__typename": "AccountType", "number": "A-116BA522"},
            {"__typename": "AccountType", "number": "A-SECOND"},
        ]
    }

    assert select_account_number(viewer) == "A-116BA522"


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


def test_client_discovers_account_and_fetches_tariff_snapshot() -> None:
    agreement_payload = {
        "data": {
            "account": {
                "number": "A-116BA522",
                "electricityAgreements": [
                    {
                        "id": "agreement-current",
                        "validFrom": "2026-04-01T00:00:00+00:00",
                        "validTo": "2026-06-01T00:00:00+00:00",
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

    snapshot = asyncio.run(client.async_get_tariff_snapshot())

    assert snapshot == TariffSnapshot(
        current_rate_gbp_per_kwh=0.239022,
        next_rate_gbp_per_kwh=0.245,
        next_rate_change_at=datetime(2026, 5, 1, 12, 30, tzinfo=UTC),
        tariff_name="Next Drive Smart V5.2",
        tariff_code="E-TOU-NEXT_DRIVE_SMART_V5_2-N",
        standing_charge_gbp_per_day=0.6000015,
    )
    assert session.requests[0]["json"]["query"] == LOGIN_MUTATION
    assert session.requests[1]["json"]["query"] == VIEWER_QUERY
    assert session.requests[1]["headers"]["authorization"] == "JWT access-1"
    assert session.requests[2]["json"]["query"] == AGREEMENTS_QUERY
    assert session.requests[2]["json"]["variables"] == {"accountNumber": "A-116BA522"}
    assert session.requests[3]["json"]["query"] == AGREEMENTS_QUERY
    assert session.requests[3]["json"]["variables"] == {"accountNumber": "A-116BA522"}


def test_client_refreshes_stale_token_before_reuse() -> None:
    session = _FakeSession(
        [
            _token_payload("access-1", "refresh-1", 1),
            _viewer_payload(),
            {
                "data": {
                    "account": {
                        "number": "A-116BA522",
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

    assert first_account_number == "A-116BA522"
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
                        "number": "A-116BA522",
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

    assert account_number == "A-116BA522"
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
        "tariff": {
            "__typename": "DayNightTariff",
            "displayName": "Legacy Two Rate",
            "tariffCode": "legacy",
            "standingCharge": 50.0,
        }
    }

    with pytest.raises(EonNextRatesUnsupportedError, match="HalfHourlyTariff"):
        build_tariff_snapshot(agreement, datetime(2026, 4, 30, 20, 30, tzinfo=UTC))


def test_build_tariff_snapshot_raises_when_now_is_not_covered() -> None:
    agreement = {
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
        build_tariff_snapshot(agreement, datetime(2026, 4, 30, 20, 30, tzinfo=UTC))


def test_build_tariff_snapshot_returns_none_when_next_window_is_missing() -> None:
    agreement = {
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

    snapshot = build_tariff_snapshot(agreement, datetime(2026, 4, 30, 20, 30, tzinfo=UTC))

    assert snapshot == TariffSnapshot(
        current_rate_gbp_per_kwh=0.239022,
        next_rate_gbp_per_kwh=None,
        next_rate_change_at=None,
        tariff_name="Next Drive Smart V5.2",
        tariff_code="E-TOU-NEXT_DRIVE_SMART_V5_2-N",
        standing_charge_gbp_per_day=0.6000015,
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
        build_tariff_snapshot(
            {"tariff": tariff}, datetime(2026, 4, 30, 20, 30, tzinfo=UTC)
        )


def test_build_tariff_snapshot_raises_when_next_window_is_not_contiguous() -> None:
    agreement = {
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
        build_tariff_snapshot(agreement, datetime(2026, 4, 30, 20, 30, tzinfo=UTC))
