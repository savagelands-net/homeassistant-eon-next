from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from aiohttp import ClientError

from .const import GRAPHQL_URL

LOGIN_MUTATION = """mutation loginEmailAuthentication($input: ObtainJSONWebTokenInput!) {
  obtainKrakenToken(input: $input) {
    payload
    refreshExpiresIn
    refreshToken
    token
    __typename
  }
}"""

REFRESH_MUTATION = """mutation refreshToken($input: ObtainJSONWebTokenInput!) {
  obtainKrakenToken(input: $input) {
    payload
    refreshExpiresIn
    refreshToken
    token
    __typename
  }
}"""

VIEWER_QUERY = """query headerGetLoggedInUser {
  viewer {
    accounts {
      ... on AccountType {
        number
        __typename
      }
      __typename
    }
    __typename
  }
}"""

AGREEMENTS_QUERY = """query GetHalfHourlyTariff($accountNumber: String!) {
  account(accountNumber: $accountNumber) {
    number
    electricityAgreements {
      id
      validFrom
      validTo
      meterPoint {
        mpan
        unbilledReadings {
          readAt
          readingSource
          source
          readingType
          registers {
            identifier
            name
            value
            digits
            isQuarantined
          }
        }
      }
      tariff {
        __typename
        ... on HalfHourlyTariff {
          displayName
          tariffCode
          standingCharge
          preVatStandingCharge
          unitRates {
            value
            validFrom
            validTo
          }
        }
      }
    }
  }
}"""


@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    current_rate_gbp_per_kwh: float
    next_rate_gbp_per_kwh: float | None
    next_rate_change_at: datetime | None
    account_number: str
    current_window_end: datetime
    next_window_start: datetime | None
    agreement_valid_from: datetime
    agreement_valid_to: datetime | None
    pre_vat_standing_charge_gbp_per_day: float | None
    tariff_name: str
    tariff_code: str
    standing_charge_gbp_per_day: float
    latest_meter_reading_kwh: float | None = None
    latest_meter_reading_at: datetime | None = None
    latest_meter_reading_source: str | None = None
    latest_meter_reading_type: str | None = None
    latest_meter_reading_register_identifier: str | None = None
    latest_meter_reading_register_name: str | None = None
    latest_meter_reading_register_digits: int | None = None
    latest_meter_reading_register_is_quarantined: bool | None = None
    meter_point_mpan: str | None = None


class EonNextRatesError(Exception):
    pass


class EonNextRatesAuthError(EonNextRatesError):
    pass


class EonNextRatesConnectionError(EonNextRatesError):
    pass


class EonNextRatesUnsupportedError(EonNextRatesError):
    pass


def select_account_number(
    viewer: dict, supported_account_numbers: set[str] | None = None
) -> str:
    accounts = viewer.get("accounts", [])
    if not accounts:
        raise EonNextRatesUnsupportedError(
            "No accounts found for the authenticated E.ON viewer"
        )

    if supported_account_numbers is not None:
        for account in accounts:
            if account["number"] in supported_account_numbers:
                return account["number"]

        raise EonNextRatesUnsupportedError(
            "No supported active HalfHourlyTariff account found for the authenticated "
            "E.ON viewer"
        )

    return accounts[0]["number"]


def select_active_half_hourly_agreement(account: dict, now: datetime) -> dict:
    for agreement in account.get("electricityAgreements", []):
        valid_from = _parse_datetime(agreement["validFrom"])
        valid_to = _parse_datetime(agreement["validTo"])
        tariff_type = agreement["tariff"].get("__typename")

        if (
            valid_from <= now
            and (valid_to is None or now < valid_to)
            and tariff_type == "HalfHourlyTariff"
        ):
            return agreement

    raise EonNextRatesUnsupportedError(
        "No active HalfHourlyTariff electricity agreement found for "
        f"{now.isoformat()}"
    )


class EonNextRatesClient:
    def __init__(
        self,
        session,
        *,
        email: str,
        password: str,
        account_number: str | None = None,
        graphql_url: str = GRAPHQL_URL,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._graphql_url = graphql_url
        self._now = now or (lambda: datetime.now(UTC))
        self._token: str | None = None
        self._token_expires_at: datetime | None = None
        self._refresh_token: str | None = None
        self._refresh_token_expires_at: datetime | None = None
        self._account_number = account_number

    async def _graphql(
        self, query: str, variables: dict | None = None, token: str | None = None
    ) -> dict:
        headers = {"content-type": "application/json"}
        if token is not None:
            headers["authorization"] = f"JWT {token}"

        try:
            async with self._session.post(
                self._graphql_url,
                json={"query": query, "variables": variables or {}},
                headers=headers,
            ) as response:
                response.raise_for_status()
                payload = await response.json()
        except (ClientError, OSError, TimeoutError) as err:
            raise EonNextRatesConnectionError(str(err)) from err

        if payload.get("errors"):
            if _is_auth_error(payload["errors"]):
                raise EonNextRatesAuthError(
                    f"GraphQL authentication failed: {payload['errors']}"
                )
            raise EonNextRatesConnectionError(
                f"GraphQL request failed: {payload['errors']}"
            )

        data = payload.get("data")
        if data is None:
            raise EonNextRatesConnectionError("GraphQL response did not include data")

        return data

    async def _async_login(self) -> str:
        data = await self._graphql(
            LOGIN_MUTATION,
            {"input": {"email": self._email, "password": self._password}},
        )
        self._store_token_state(data["obtainKrakenToken"])
        return self._token

    async def _async_refresh(self) -> str:
        if self._refresh_token is None:
            return await self._async_login()

        if (
            self._refresh_token_expires_at is not None
            and self._refresh_token_expires_at <= self._now()
        ):
            self._refresh_token = None
            self._refresh_token_expires_at = None
            return await self._async_login()

        try:
            data = await self._graphql(
                REFRESH_MUTATION,
                {"input": {"refreshToken": self._refresh_token}},
            )
        except EonNextRatesAuthError:
            self._refresh_token = None
            self._refresh_token_expires_at = None
            return await self._async_login()

        self._store_token_state(data["obtainKrakenToken"])
        return self._token

    async def _async_access_token(self) -> str:
        if self._token is not None and not self._access_token_is_stale():
            return self._token

        if self._refresh_token is not None:
            return await self._async_refresh()

        return await self._async_login()

    async def _async_authenticated_graphql(
        self, query: str, variables: dict | None = None
    ) -> dict:
        token = await self._async_access_token()

        try:
            return await self._graphql(query, variables, token=token)
        except EonNextRatesAuthError:
            pass

        self._clear_access_token()
        token = await self._async_access_token()
        return await self._graphql(query, variables, token=token)

    async def async_discover_account_number(self) -> str:
        token = await self._async_access_token()

        async def _async_discovery_graphql(
            query: str, variables: dict | None = None
        ) -> dict:
            nonlocal token

            try:
                return await self._graphql(query, variables, token=token)
            except EonNextRatesAuthError:
                self._clear_access_token()
                token = await self._async_access_token()
                return await self._graphql(query, variables, token=token)

        data = await _async_discovery_graphql(VIEWER_QUERY)
        now = self._now()
        supported_account_numbers: set[str] = set()

        for account in data["viewer"].get("accounts", []):
            account_number = account["number"]
            account_data = await _async_discovery_graphql(
                AGREEMENTS_QUERY,
                {"accountNumber": account_number},
            )
            try:
                agreement = select_active_half_hourly_agreement(
                    account_data["account"], now
                )
                build_account_snapshot(account_data["account"], agreement, now)
            except EonNextRatesUnsupportedError:
                continue

            supported_account_numbers.add(account_number)

        self._account_number = select_account_number(
            data["viewer"], supported_account_numbers
        )
        return self._account_number

    async def async_get_account_snapshot(self) -> AccountSnapshot:
        if self._account_number is None:
            self._account_number = await self.async_discover_account_number()

        now = self._now()
        data = await self._async_authenticated_graphql(
            AGREEMENTS_QUERY,
            {"accountNumber": self._account_number},
        )
        account = data["account"]
        agreement = select_active_half_hourly_agreement(account, now)
        return build_account_snapshot(account, agreement, now)

    def _store_token_state(self, token_payload: dict[str, Any]) -> None:
        self._token = token_payload["token"]
        self._token_expires_at = _token_expiry_datetime(token_payload["payload"])
        self._refresh_token = token_payload["refreshToken"]
        self._refresh_token_expires_at = self._now() + timedelta(
            seconds=token_payload["refreshExpiresIn"]
        )

    def _access_token_is_stale(self) -> bool:
        if self._token is None:
            return True

        if self._token_expires_at is None:
            return False

        return self._token_expires_at <= self._now()

    def _clear_access_token(self) -> None:
        self._token = None
        self._token_expires_at = None


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None

    return datetime.fromisoformat(value)


def _pence_to_gbp(value: float) -> float:
    return value / 100


def _optional_pence_to_gbp(value: float | None) -> float | None:
    if value is None:
        return None

    return _pence_to_gbp(value)


def _parse_meter_reading_value(value: str | None) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _empty_meter_reading_fields(mpan: str | None) -> dict[str, Any]:
    return {
        "latest_meter_reading_kwh": None,
        "latest_meter_reading_at": None,
        "latest_meter_reading_source": None,
        "latest_meter_reading_type": None,
        "latest_meter_reading_register_identifier": None,
        "latest_meter_reading_register_name": None,
        "latest_meter_reading_register_digits": None,
        "latest_meter_reading_register_is_quarantined": None,
        "meter_point_mpan": mpan,
    }


def _latest_meter_reading_fields(meter_point: dict | None) -> dict[str, Any]:
    if not isinstance(meter_point, dict):
        return _empty_meter_reading_fields(None)

    mpan = meter_point.get("mpan")
    unbilled_readings = meter_point.get("unbilledReadings")
    if unbilled_readings is None:
        return _empty_meter_reading_fields(mpan)

    if not isinstance(unbilled_readings, list):
        return _empty_meter_reading_fields(mpan)

    def _parse_read_at(reading: dict[str, Any]) -> datetime | None:
        if not isinstance(reading, dict):
            return None

        try:
            return _parse_datetime(reading.get("readAt"))
        except ValueError:
            return None

    sorted_readings = sorted(
        ((_parse_read_at(reading), reading) for reading in unbilled_readings),
        key=lambda item: item[0] or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )

    for read_at, reading in sorted_readings:
        if read_at is None or not isinstance(reading, dict):
            continue

        registers = reading.get("registers")
        if not isinstance(registers, list):
            continue

        for register in registers:
            if not isinstance(register, dict):
                continue

            reading_value = _parse_meter_reading_value(register.get("value"))
            if reading_value is None:
                continue

            return {
                "latest_meter_reading_kwh": reading_value,
                "latest_meter_reading_at": read_at,
                "latest_meter_reading_source": reading.get("readingSource")
                or reading.get("source"),
                "latest_meter_reading_type": reading.get("readingType"),
                "latest_meter_reading_register_identifier": register.get("identifier"),
                "latest_meter_reading_register_name": register.get("name"),
                "latest_meter_reading_register_digits": register.get("digits"),
                "latest_meter_reading_register_is_quarantined": register.get(
                    "isQuarantined"
                ),
                "meter_point_mpan": mpan,
            }

    return _empty_meter_reading_fields(mpan)


def _token_expiry_datetime(payload: dict[str, Any] | None) -> datetime | None:
    if not isinstance(payload, dict):
        return None

    exp = payload.get("exp")
    if exp is None:
        return None

    return datetime.fromtimestamp(exp, UTC)


def _is_auth_error(errors: list[dict[str, Any]]) -> bool:
    for error in errors:
        extensions = error.get("extensions", {})
        if extensions.get("code") == "UNAUTHENTICATED":
            return True

        message = error.get("message", "").lower()
        if "auth" in message or "signature has expired" in message or "jwt" in message:
            return True

    return False


def build_account_snapshot(account: dict, agreement: dict, now: datetime) -> AccountSnapshot:
    account_number = account.get("number")
    if account_number is None:
        raise EonNextRatesUnsupportedError(
            "Account payload missing required field(s): number"
        )

    tariff = agreement["tariff"]
    tariff_type = tariff.get("__typename")
    if tariff_type != "HalfHourlyTariff":
        raise EonNextRatesUnsupportedError(
            f"Expected HalfHourlyTariff tariff, got {tariff_type!r}"
        )

    required_fields = ("unitRates", "displayName", "tariffCode", "standingCharge")
    missing_fields = [field for field in required_fields if field not in tariff]
    if missing_fields:
        missing = ", ".join(missing_fields)
        raise EonNextRatesUnsupportedError(
            f"HalfHourlyTariff payload missing required field(s): {missing}"
        )

    current_window = None
    next_window = None

    unit_rates = tariff["unitRates"]
    if not unit_rates:
        raise EonNextRatesUnsupportedError(
            "HalfHourlyTariff payload missing required field(s): unitRates"
        )

    for unit_rate in unit_rates:
        valid_from = _parse_datetime(unit_rate["validFrom"])
        valid_to = _parse_datetime(unit_rate.get("validTo"))

        if valid_from <= now and valid_to is None:
            raise EonNextRatesUnsupportedError(
                "Current HalfHourlyTariff window is missing validTo"
            )

        if valid_from <= now < valid_to:
            current_window = unit_rate
            next_window = min(
                (
                    candidate
                    for candidate in unit_rates
                    if _parse_datetime(candidate["validFrom"]) >= valid_to
                ),
                key=lambda candidate: _parse_datetime(candidate["validFrom"]),
                default=None,
            )
            break

    if current_window is None:
        raise EonNextRatesUnsupportedError(
            f"No current HalfHourlyTariff window found for {now.isoformat()}"
        )

    current_window_end = _parse_datetime(current_window["validTo"])
    if current_window_end is None:
        raise EonNextRatesUnsupportedError(
            "Current HalfHourlyTariff window is missing validTo"
        )

    next_window_start = None

    if next_window is not None:
        next_window_start = _parse_datetime(next_window["validFrom"])

    if next_window is not None and next_window_start != current_window_end:
        raise EonNextRatesUnsupportedError(
            "Expected contiguous HalfHourlyTariff windows, "
            f"got gap between {current_window['validTo']} and {next_window['validFrom']}"
        )

    agreement_valid_from = _parse_datetime(agreement.get("validFrom"))
    if agreement_valid_from is None:
        raise EonNextRatesUnsupportedError(
            "Active agreement payload missing required field(s): validFrom"
        )

    agreement_valid_to = _parse_datetime(agreement.get("validTo"))
    meter_reading_fields = _latest_meter_reading_fields(agreement.get("meterPoint"))

    return AccountSnapshot(
        current_rate_gbp_per_kwh=_pence_to_gbp(current_window["value"]),
        next_rate_gbp_per_kwh=(
            _pence_to_gbp(next_window["value"]) if next_window is not None else None
        ),
        next_rate_change_at=next_window_start,
        account_number=account_number,
        current_window_end=current_window_end,
        next_window_start=next_window_start,
        agreement_valid_from=agreement_valid_from,
        agreement_valid_to=agreement_valid_to,
        pre_vat_standing_charge_gbp_per_day=_optional_pence_to_gbp(
            tariff.get("preVatStandingCharge")
        ),
        tariff_name=tariff["displayName"],
        tariff_code=tariff["tariffCode"],
        standing_charge_gbp_per_day=_pence_to_gbp(tariff["standingCharge"]),
        **meter_reading_fields,
    )
