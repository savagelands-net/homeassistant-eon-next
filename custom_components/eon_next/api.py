from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from aiohttp import (  # pyright: ignore[reportMissingImports]
    ClientError,
    ClientResponseError,
)

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
    balance
    bills(first: 6, orderBy: ISSUED_DATE_DESC) {
      edges {
        node {
          __typename
          billType
          issuedDate
          ... on StatementType {
            fromDate
            toDate
            openingBalance
            closingBalance
            paymentDueDate
            status
            totalCharges {
              netTotal
              taxTotal
              grossTotal
            }
            totalCredits {
              netTotal
              taxTotal
              grossTotal
            }
            transactions(first: 50) {
              edges {
                node {
                  __typename
                  title
                  postedDate
                  amounts {
                    grossTotal: gross
                  }
                  ... on Charge {
                    consumption {
                      quantity
                      usageCost
                      supplyCharge
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
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
    gasAgreements {
      id
      validFrom
      validTo
      meterPoint {
        mprn
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
        displayName
        tariffCode
        standingCharge
        preVatStandingCharge
        unitRate
        preVatUnitRate
      }
    }
  }
}"""

SMARTFLEX_DEVICES_QUERY = """query SmartFlexDevices($accountNumber: String!) {
  devices(accountNumber: $accountNumber) {
    __typename
    deviceType
    id
    name
    provider
    integrationDeviceId
    propertyId
    status {
      current
      isSuspended
      currentState
      ... on SmartFlexVehicleStatus {
        stateOfCharge {
          timestamp
          value
        }
        activePower {
          timestamp
          value
        }
        stateOfChargeLimit {
          upperSocLimit
          timestamp
          isLimitViolated
        }
        testDispatchFailureReason
      }
      ... on SmartFlexChargePointStatus {
        stateOfCharge {
          timestamp
          value
        }
        activePower {
          timestamp
          value
        }
        stateOfChargeLimit {
          upperSocLimit
          timestamp
          isLimitViolated
        }
        testDispatchFailureReason
      }
    }
    ... on SmartFlexVehicle {
      make
      model
      vehicleBatterySize
      chargingSessions(last: 1) {
        edges {
          node {
            start
            end
            stateOfChargeChange
            stateOfChargeFinal
            energyAdded {
              value
              unit
            }
            cost {
              amount
              currency
            }
          }
        }
      }
    }
    ... on SmartFlexChargePoint {
      make
      model
      chargePointPowerOutput
      chargingSessions(last: 1) {
        edges {
          node {
            start
            end
            stateOfChargeChange
            stateOfChargeFinal
            energyAdded {
              value
              unit
            }
            cost {
              amount
              currency
            }
          }
        }
      }
    }
  }
}"""

SMARTFLEX_PLANNED_DISPATCHES_QUERY = """query SmartFlexPlannedDispatches($deviceId: String!) {
  flexPlannedDispatches(deviceId: $deviceId) {
    start
    end
    type
    energyAddedKwh
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
    current_account_balance_gbp: float | None = None
    latest_statement_issued_at: datetime | None = None
    latest_statement_period_start: datetime | None = None
    latest_statement_period_end: datetime | None = None
    latest_statement_payment_due_at: datetime | None = None
    latest_statement_opening_balance_gbp: float | None = None
    latest_statement_closing_balance_gbp: float | None = None
    latest_statement_charges_gbp: float | None = None
    latest_statement_credits_gbp: float | None = None
    latest_direct_debit_amount_gbp: float | None = None
    latest_direct_debit_at: datetime | None = None
    latest_electricity_statement_total_gbp: float | None = None
    latest_electricity_statement_quantity_kwh: float | None = None
    latest_electricity_statement_usage_cost_gbp: float | None = None
    latest_electricity_statement_standing_charge_gbp: float | None = None
    latest_gas_statement_total_gbp: float | None = None
    latest_gas_statement_quantity_kwh: float | None = None
    gas_rate_gbp_per_kwh: float | None = None
    gas_pre_vat_rate_gbp_per_kwh: float | None = None
    gas_tariff_name: str | None = None
    gas_tariff_code: str | None = None
    gas_standing_charge_gbp_per_day: float | None = None
    gas_pre_vat_standing_charge_gbp_per_day: float | None = None
    gas_agreement_valid_from: datetime | None = None
    gas_agreement_valid_to: datetime | None = None
    latest_gas_meter_reading_value: float | None = None
    latest_gas_meter_reading_at: datetime | None = None
    latest_gas_meter_reading_source: str | None = None
    latest_gas_meter_reading_type: str | None = None
    latest_gas_meter_reading_register_identifier: str | None = None
    latest_gas_meter_reading_register_name: str | None = None
    latest_gas_meter_reading_register_digits: int | None = None
    latest_gas_meter_reading_register_is_quarantined: bool | None = None
    gas_meter_point_mprn: str | None = None
    smartflex_devices: tuple[SmartFlexDeviceSnapshot, ...] = ()


@dataclass(frozen=True, slots=True)
class SmartFlexReadingSnapshot:
    timestamp: datetime
    value: float


@dataclass(frozen=True, slots=True)
class SmartFlexSocLimitSnapshot:
    upper_soc_limit: float
    timestamp: datetime
    is_limit_violated: bool


@dataclass(frozen=True, slots=True)
class SmartFlexPlannedDispatchSnapshot:
    start: datetime
    end: datetime | None
    dispatch_type: str | None
    energy_added_kwh: float | None


@dataclass(frozen=True, slots=True)
class SmartFlexChargingSessionSnapshot:
    start: datetime
    end: datetime | None
    state_of_charge_change: float | None
    state_of_charge_final: float | None
    energy_added_value: float | None
    energy_added_unit: str | None
    cost_amount: float | None
    cost_currency: str | None


@dataclass(frozen=True, slots=True)
class SmartFlexDeviceSnapshot:
    device_id: str
    name: str | None
    device_type: str | None
    provider: str | None
    integration_device_id: str | None
    property_id: str | None
    make: str | None
    model: str | None
    vehicle_battery_size_kwh: float | None
    charge_point_power_output_kw: float | None
    lifecycle_status: str | None
    current_state: str | None
    is_suspended: bool | None
    state_of_charge: SmartFlexReadingSnapshot | None
    active_power: SmartFlexReadingSnapshot | None
    state_of_charge_limit: SmartFlexSocLimitSnapshot | None
    test_dispatch_failure_reason: str | None
    latest_charging_session: SmartFlexChargingSessionSnapshot | None
    next_planned_dispatch: SmartFlexPlannedDispatchSnapshot | None


class EonNextRatesError(Exception):
    pass


class EonNextRatesAuthError(EonNextRatesError):
    pass


class EonNextRatesConnectionError(EonNextRatesError):
    pass


class EonNextRatesUnsupportedError(EonNextRatesError):
    pass


def select_account_number(viewer: dict, supported_account_numbers: set[str] | None = None) -> str:
    accounts = viewer.get("accounts", [])
    if not accounts:
        raise EonNextRatesUnsupportedError("No accounts found for the authenticated E.ON viewer")

    if supported_account_numbers is not None:
        for account in accounts:
            if account["number"] in supported_account_numbers:
                return account["number"]

        raise EonNextRatesUnsupportedError(
            "No supported active HalfHourlyTariff account found for the authenticated E.ON viewer"
        )

    return accounts[0]["number"]


def select_active_half_hourly_agreement(account: dict, now: datetime) -> dict:
    for agreement in account.get("electricityAgreements", []):
        valid_from = _parse_datetime(agreement["validFrom"])
        valid_to = _parse_datetime(agreement["validTo"])
        tariff_type = agreement["tariff"].get("__typename")

        if valid_from is None:
            continue

        if (
            valid_from <= now
            and (valid_to is None or now < valid_to)
            and tariff_type == "HalfHourlyTariff"
        ):
            return agreement

    raise EonNextRatesUnsupportedError(
        f"No active HalfHourlyTariff electricity agreement found for {now.isoformat()}"
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
        except ClientResponseError as err:
            if err.status == 403:
                if query == LOGIN_MUTATION:
                    raise EonNextRatesConnectionError(
                        "E.ON temporarily rejected the login request with HTTP 403"
                    ) from err
            if err.status in (401, 403):
                raise EonNextRatesAuthError(
                    f"E.ON authentication failed with HTTP {err.status}"
                ) from err
            raise EonNextRatesConnectionError(str(err)) from err
        except (ClientError, OSError, TimeoutError) as err:
            raise EonNextRatesConnectionError(str(err)) from err

        if payload.get("errors"):
            if _is_auth_error(payload["errors"]):
                raise EonNextRatesAuthError(f"GraphQL authentication failed: {payload['errors']}")
            raise EonNextRatesConnectionError(f"GraphQL request failed: {payload['errors']}")

        data = payload.get("data")
        if data is None:
            raise EonNextRatesConnectionError("GraphQL response did not include data")

        return data

    async def _async_login(self) -> str:
        data = await self._graphql(
            LOGIN_MUTATION,
            {"input": {"email": self._email, "password": self._password}},
        )
        return self._store_token_state(data["obtainKrakenToken"])

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

        return self._store_token_state(data["obtainKrakenToken"])

    async def _async_access_token(self) -> str:
        if self._token is not None and not self._access_token_is_stale():
            return self._token

        if self._refresh_token is not None:
            return await self._async_refresh()

        return await self._async_login()

    async def _async_authenticated_graphql(self, query: str, variables: dict | None = None) -> dict:
        token = await self._async_access_token()

        try:
            return await self._graphql(query, variables, token=token)
        except EonNextRatesAuthError:
            self._clear_access_token()

        token = await self._async_access_token()
        return await self._graphql(query, variables, token=token)

    async def _async_optional_authenticated_graphql(
        self, query: str, variables: dict | None = None
    ) -> dict | None:
        try:
            return await self._async_authenticated_graphql(query, variables)
        except EonNextRatesError:
            return None

    async def async_discover_account_number(self) -> str:
        token = await self._async_access_token()

        async def _async_discovery_graphql(query: str, variables: dict | None = None) -> dict:
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
                agreement = select_active_half_hourly_agreement(account_data["account"], now)
                build_account_snapshot(account_data["account"], agreement, now)
            except EonNextRatesUnsupportedError:
                continue

            supported_account_numbers.add(account_number)

        self._account_number = select_account_number(data["viewer"], supported_account_numbers)
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
        snapshot = build_account_snapshot(account, agreement, now)
        smartflex_devices = await self._async_get_smartflex_devices(self._account_number)
        return replace(
            snapshot,
            smartflex_devices=smartflex_devices,
        )

    async def _async_get_smartflex_devices(
        self, account_number: str
    ) -> tuple[SmartFlexDeviceSnapshot, ...]:
        data = await self._async_optional_authenticated_graphql(
            SMARTFLEX_DEVICES_QUERY,
            {"accountNumber": account_number},
        )
        devices = data.get("devices") if isinstance(data, dict) else None
        if not isinstance(devices, list):
            return ()

        snapshots: list[SmartFlexDeviceSnapshot] = []
        for raw_device in devices:
            normalized_device = _normalize_smartflex_device(raw_device)
            if normalized_device is None:
                continue

            planned_data = await self._async_optional_authenticated_graphql(
                SMARTFLEX_PLANNED_DISPATCHES_QUERY,
                {"deviceId": normalized_device["id"]},
            )
            planned_dispatches = (
                _normalize_smartflex_planned_dispatches(planned_data.get("flexPlannedDispatches"))
                if isinstance(planned_data, dict)
                else []
            )
            planned_dispatches = [
                dispatch
                for dispatch in planned_dispatches
                if (start := _parse_smartflex_datetime(dispatch.get("start"))) is not None
                and start >= self._now()
            ]
            snapshots.append(
                build_smartflex_device_snapshot(
                    normalized_device,
                    select_next_planned_dispatch(planned_dispatches),
                )
            )

        return tuple(snapshots)

    def _store_token_state(self, token_payload: dict[str, Any]) -> str:
        token = token_payload.get("token")
        if not isinstance(token, str):
            raise EonNextRatesConnectionError(
                "GraphQL token response did not include an access token"
            )

        self._token = token
        self._token_expires_at = _token_expiry_datetime(token_payload["payload"])
        self._refresh_token = token_payload["refreshToken"]
        # Despite its name, E.ON returns refreshExpiresIn as a Unix timestamp.
        self._refresh_token_expires_at = datetime.fromtimestamp(
            token_payload["refreshExpiresIn"], UTC
        )
        return token

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


def _optional_minor_units_to_gbp(value: int | None) -> float | None:
    if value is None:
        return None

    return value / 100


def _parse_date_to_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None

    try:
        return datetime.fromisoformat(value).replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def _parse_decimal_string(value: str | None) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_float(value: Any) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_smartflex_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None

    try:
        return _parse_datetime(value)
    except (TypeError, ValueError):
        return None


def _normalize_smartflex_charging_sessions(charging_sessions: Any) -> list[dict[str, Any]]:
    if not isinstance(charging_sessions, dict):
        return []

    edges = charging_sessions.get("edges")
    if not isinstance(edges, list):
        return []

    normalized_sessions = []
    for edge in edges:
        if not isinstance(edge, dict):
            continue

        session = edge.get("node")
        if not isinstance(session, dict):
            continue

        energy_added = session.get("energyAdded")
        cost = session.get("cost")
        normalized_sessions.append(
            {
                "start": session.get("start"),
                "end": session.get("end"),
                "stateOfChargeChange": session.get("stateOfChargeChange"),
                "stateOfChargeFinal": session.get("stateOfChargeFinal"),
                "energyAddedValue": (
                    energy_added.get("value") if isinstance(energy_added, dict) else None
                ),
                "energyAddedUnit": (
                    energy_added.get("unit") if isinstance(energy_added, dict) else None
                ),
                "costAmount": cost.get("amount") if isinstance(cost, dict) else None,
                "costCurrency": cost.get("currency") if isinstance(cost, dict) else None,
            }
        )

    return normalized_sessions


def _normalize_smartflex_device(device: Any) -> dict[str, Any] | None:
    if not isinstance(device, dict):
        return None

    graphql_type = device.get("__typename")
    if graphql_type not in {"SmartFlexVehicle", "SmartFlexChargePoint"}:
        return None

    status = device.get("status")
    if not isinstance(status, dict):
        status = {}

    return {
        "id": device.get("id"),
        "name": device.get("name"),
        "deviceType": device.get("deviceType"),
        "provider": device.get("provider"),
        "integrationDeviceId": device.get("integrationDeviceId"),
        "propertyId": device.get("propertyId"),
        "make": device.get("make"),
        "model": device.get("model"),
        "vehicleBatterySizeKwh": device.get("vehicleBatterySize"),
        "chargePointPowerOutputKw": device.get("chargePointPowerOutput"),
        "lifecycleStatus": status.get("current"),
        "currentState": status.get("currentState"),
        "isSuspended": status.get("isSuspended"),
        "stateOfCharge": status.get("stateOfCharge"),
        "activePower": status.get("activePower"),
        "stateOfChargeLimit": status.get("stateOfChargeLimit"),
        "testDispatchFailureReason": status.get("testDispatchFailureReason"),
        "chargingSessions": _normalize_smartflex_charging_sessions(device.get("chargingSessions")),
    }


def _normalize_smartflex_planned_dispatches(planned_dispatches: Any) -> list[dict[str, Any]]:
    if not isinstance(planned_dispatches, list):
        return []

    return [
        {
            "start": dispatch.get("start"),
            "end": dispatch.get("end"),
            "dispatchType": dispatch.get("type"),
            "energyAddedKwh": dispatch.get("energyAddedKwh"),
        }
        for dispatch in planned_dispatches
        if isinstance(dispatch, dict)
    ]


def _build_smartflex_reading_snapshot(reading: Any) -> SmartFlexReadingSnapshot | None:
    if not isinstance(reading, dict):
        return None

    timestamp = _parse_smartflex_datetime(reading.get("timestamp"))
    value = _parse_float(reading.get("value"))
    if timestamp is None or value is None:
        return None

    return SmartFlexReadingSnapshot(
        timestamp=timestamp,
        value=value,
    )


def _build_smartflex_soc_limit_snapshot(
    soc_limit: Any,
) -> SmartFlexSocLimitSnapshot | None:
    if not isinstance(soc_limit, dict):
        return None

    timestamp = _parse_smartflex_datetime(soc_limit.get("timestamp"))
    upper_soc_limit = _parse_float(soc_limit.get("upperSocLimit"))
    is_limit_violated = soc_limit.get("isLimitViolated")
    if timestamp is None or upper_soc_limit is None or not isinstance(is_limit_violated, bool):
        return None

    return SmartFlexSocLimitSnapshot(
        upper_soc_limit=upper_soc_limit,
        timestamp=timestamp,
        is_limit_violated=is_limit_violated,
    )


def select_next_planned_dispatch(
    planned_dispatches: Any,
) -> SmartFlexPlannedDispatchSnapshot | None:
    if not isinstance(planned_dispatches, list):
        return None

    snapshots = []
    for dispatch in planned_dispatches:
        if not isinstance(dispatch, dict):
            continue

        start = _parse_smartflex_datetime(dispatch.get("start"))
        if start is None:
            continue

        snapshots.append(
            SmartFlexPlannedDispatchSnapshot(
                start=start,
                end=_parse_smartflex_datetime(dispatch.get("end")),
                dispatch_type=dispatch.get("dispatchType"),
                energy_added_kwh=_parse_float(dispatch.get("energyAddedKwh")),
            )
        )

    if not snapshots:
        return None

    return min(snapshots, key=lambda snapshot: snapshot.start)


def build_smartflex_device_snapshot(
    device: dict[str, Any],
    next_planned_dispatch: SmartFlexPlannedDispatchSnapshot | None,
) -> SmartFlexDeviceSnapshot:
    latest_charging_session = None
    latest_start = None
    charging_sessions = device.get("chargingSessions", [])

    if not isinstance(charging_sessions, list):
        charging_sessions = []

    for session in charging_sessions:
        if not isinstance(session, dict):
            continue

        start = _parse_smartflex_datetime(session.get("start"))
        if start is None:
            continue

        if latest_start is not None and start <= latest_start:
            continue

        latest_charging_session = SmartFlexChargingSessionSnapshot(
            start=start,
            end=_parse_smartflex_datetime(session.get("end")),
            state_of_charge_change=_parse_float(session.get("stateOfChargeChange")),
            state_of_charge_final=_parse_float(session.get("stateOfChargeFinal")),
            energy_added_value=_parse_float(session.get("energyAddedValue")),
            energy_added_unit=session.get("energyAddedUnit"),
            cost_amount=_parse_float(session.get("costAmount")),
            cost_currency=session.get("costCurrency"),
        )
        latest_start = start

    return SmartFlexDeviceSnapshot(
        device_id=device["id"],
        name=device.get("name"),
        device_type=device.get("deviceType"),
        provider=device.get("provider"),
        integration_device_id=device.get("integrationDeviceId"),
        property_id=device.get("propertyId"),
        make=device.get("make"),
        model=device.get("model"),
        vehicle_battery_size_kwh=_parse_float(device.get("vehicleBatterySizeKwh")),
        charge_point_power_output_kw=_parse_float(device.get("chargePointPowerOutputKw")),
        lifecycle_status=device.get("lifecycleStatus"),
        current_state=device.get("currentState"),
        is_suspended=device.get("isSuspended"),
        state_of_charge=_build_smartflex_reading_snapshot(device.get("stateOfCharge", {})),
        active_power=_build_smartflex_reading_snapshot(device.get("activePower", {})),
        state_of_charge_limit=_build_smartflex_soc_limit_snapshot(
            device.get("stateOfChargeLimit", {})
        ),
        test_dispatch_failure_reason=device.get("testDispatchFailureReason"),
        latest_charging_session=latest_charging_session,
        next_planned_dispatch=next_planned_dispatch,
    )


def _statement_transaction_fields(statement: dict | None) -> dict[str, Any]:
    empty_fields = {
        "latest_direct_debit_amount_gbp": None,
        "latest_direct_debit_at": None,
        "latest_electricity_statement_total_gbp": None,
        "latest_electricity_statement_quantity_kwh": None,
        "latest_electricity_statement_usage_cost_gbp": None,
        "latest_electricity_statement_standing_charge_gbp": None,
        "latest_gas_statement_total_gbp": None,
        "latest_gas_statement_quantity_kwh": None,
    }
    if not isinstance(statement, dict):
        return empty_fields

    transactions = statement.get("transactions")
    if not isinstance(transactions, dict):
        return empty_fields

    edges = transactions.get("edges")
    if not isinstance(edges, list):
        return empty_fields

    electricity_total = 0
    electricity_quantity = 0.0
    electricity_usage_cost = 0
    electricity_standing_charge = 0
    has_electricity = False
    has_electricity_quantity = False
    has_electricity_usage_cost = False
    has_electricity_standing_charge = False
    gas_total = 0
    gas_quantity = 0.0
    has_gas = False
    has_gas_quantity = False
    latest_direct_debit_amount = None
    latest_direct_debit_at = None

    for edge in edges:
        if not isinstance(edge, dict):
            continue

        node = edge.get("node")
        if not isinstance(node, dict):
            continue

        title = node.get("title")
        posted_date = _parse_date_to_datetime(node.get("postedDate"))
        amounts = node.get("amounts")
        gross_total = amounts.get("grossTotal") if isinstance(amounts, dict) else None
        if not isinstance(gross_total, int):
            gross_total = None

        if node.get("__typename") == "Payment" and title == "Direct debit":
            if posted_date is None or gross_total is None:
                continue
            if latest_direct_debit_at is None or posted_date > latest_direct_debit_at:
                latest_direct_debit_at = posted_date
                latest_direct_debit_amount = _optional_minor_units_to_gbp(gross_total)
            continue

        if node.get("__typename") != "Charge" or gross_total is None:
            continue

        consumption = node.get("consumption")
        quantity = None
        if isinstance(consumption, dict):
            quantity = _parse_decimal_string(consumption.get("quantity"))

        if title == "Electricity":
            electricity_total += gross_total
            has_electricity = True
            if quantity is not None:
                electricity_quantity += quantity
                has_electricity_quantity = True

            usage_cost = consumption.get("usageCost") if isinstance(consumption, dict) else None
            if isinstance(usage_cost, int):
                electricity_usage_cost += usage_cost
                has_electricity_usage_cost = True

            supply_charge = (
                consumption.get("supplyCharge") if isinstance(consumption, dict) else None
            )
            if isinstance(supply_charge, int):
                electricity_standing_charge += supply_charge
                has_electricity_standing_charge = True
            continue

        if title == "Gas":
            gas_total += gross_total
            has_gas = True
            if quantity is not None:
                gas_quantity += quantity
                has_gas_quantity = True

    return {
        "latest_direct_debit_amount_gbp": latest_direct_debit_amount,
        "latest_direct_debit_at": latest_direct_debit_at,
        "latest_electricity_statement_total_gbp": (
            _optional_minor_units_to_gbp(electricity_total) if has_electricity else None
        ),
        "latest_electricity_statement_quantity_kwh": (
            electricity_quantity if has_electricity_quantity else None
        ),
        "latest_electricity_statement_usage_cost_gbp": (
            _optional_minor_units_to_gbp(electricity_usage_cost)
            if has_electricity_usage_cost
            else None
        ),
        "latest_electricity_statement_standing_charge_gbp": (
            _optional_minor_units_to_gbp(electricity_standing_charge)
            if has_electricity_standing_charge
            else None
        ),
        "latest_gas_statement_total_gbp": (
            _optional_minor_units_to_gbp(gas_total) if has_gas else None
        ),
        "latest_gas_statement_quantity_kwh": gas_quantity if has_gas_quantity else None,
    }


_ELECTRICITY_STATEMENT_FIELDS = (
    "latest_electricity_statement_total_gbp",
    "latest_electricity_statement_quantity_kwh",
    "latest_electricity_statement_usage_cost_gbp",
    "latest_electricity_statement_standing_charge_gbp",
)
_GAS_STATEMENT_FIELDS = (
    "latest_gas_statement_total_gbp",
    "latest_gas_statement_quantity_kwh",
)


def _latest_statement_transaction_fields(
    statements: list[dict[str, Any]],
) -> dict[str, Any]:
    latest_fields = _statement_transaction_fields(None)
    has_electricity_statement = False
    has_gas_statement = False

    for statement in statements:
        fields = _statement_transaction_fields(statement)

        direct_debit_at = fields["latest_direct_debit_at"]
        if isinstance(direct_debit_at, datetime) and (
            latest_fields["latest_direct_debit_at"] is None
            or direct_debit_at > latest_fields["latest_direct_debit_at"]
        ):
            latest_fields["latest_direct_debit_at"] = direct_debit_at
            latest_fields["latest_direct_debit_amount_gbp"] = fields[
                "latest_direct_debit_amount_gbp"
            ]

        if (
            not has_electricity_statement
            and fields["latest_electricity_statement_total_gbp"] is not None
        ):
            latest_fields.update({field: fields[field] for field in _ELECTRICITY_STATEMENT_FIELDS})
            has_electricity_statement = True

        if not has_gas_statement and fields["latest_gas_statement_total_gbp"] is not None:
            latest_fields.update({field: fields[field] for field in _GAS_STATEMENT_FIELDS})
            has_gas_statement = True

    return latest_fields


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


def _billing_fields(account: dict) -> dict[str, Any]:
    statements: list[dict[str, Any]] = []
    bills = account.get("bills")

    if isinstance(bills, dict):
        edges = bills.get("edges")
        if isinstance(edges, list):
            for edge in edges:
                if not isinstance(edge, dict):
                    continue

                bill = edge.get("node")
                if not isinstance(bill, dict):
                    continue

                if bill.get("__typename") == "StatementType":
                    statements.append(bill)

    statement = statements[0] if statements else None
    total_charges = statement.get("totalCharges") if isinstance(statement, dict) else None
    total_credits = statement.get("totalCredits") if isinstance(statement, dict) else None

    return {
        "current_account_balance_gbp": _optional_minor_units_to_gbp(account.get("balance")),
        "latest_statement_issued_at": _parse_date_to_datetime(
            statement.get("issuedDate") if isinstance(statement, dict) else None
        ),
        "latest_statement_period_start": _parse_date_to_datetime(
            statement.get("fromDate") if isinstance(statement, dict) else None
        ),
        "latest_statement_period_end": _parse_date_to_datetime(
            statement.get("toDate") if isinstance(statement, dict) else None
        ),
        "latest_statement_payment_due_at": _parse_date_to_datetime(
            statement.get("paymentDueDate") if isinstance(statement, dict) else None
        ),
        "latest_statement_opening_balance_gbp": _optional_minor_units_to_gbp(
            statement.get("openingBalance") if isinstance(statement, dict) else None
        ),
        "latest_statement_closing_balance_gbp": _optional_minor_units_to_gbp(
            statement.get("closingBalance") if isinstance(statement, dict) else None
        ),
        "latest_statement_charges_gbp": _optional_minor_units_to_gbp(
            total_charges.get("grossTotal") if isinstance(total_charges, dict) else None
        ),
        "latest_statement_credits_gbp": _optional_minor_units_to_gbp(
            total_credits.get("grossTotal") if isinstance(total_credits, dict) else None
        ),
        **_latest_statement_transaction_fields(statements),
    }


def _empty_gas_fields(mprn: str | None = None) -> dict[str, Any]:
    return {
        "gas_rate_gbp_per_kwh": None,
        "gas_pre_vat_rate_gbp_per_kwh": None,
        "gas_tariff_name": None,
        "gas_tariff_code": None,
        "gas_standing_charge_gbp_per_day": None,
        "gas_pre_vat_standing_charge_gbp_per_day": None,
        "gas_agreement_valid_from": None,
        "gas_agreement_valid_to": None,
        "latest_gas_meter_reading_value": None,
        "latest_gas_meter_reading_at": None,
        "latest_gas_meter_reading_source": None,
        "latest_gas_meter_reading_type": None,
        "latest_gas_meter_reading_register_identifier": None,
        "latest_gas_meter_reading_register_name": None,
        "latest_gas_meter_reading_register_digits": None,
        "latest_gas_meter_reading_register_is_quarantined": None,
        "gas_meter_point_mprn": mprn,
    }


def _empty_gas_meter_reading_fields(mprn: str | None = None) -> dict[str, Any]:
    return {
        "latest_gas_meter_reading_value": None,
        "latest_gas_meter_reading_at": None,
        "latest_gas_meter_reading_source": None,
        "latest_gas_meter_reading_type": None,
        "latest_gas_meter_reading_register_identifier": None,
        "latest_gas_meter_reading_register_name": None,
        "latest_gas_meter_reading_register_digits": None,
        "latest_gas_meter_reading_register_is_quarantined": None,
        "gas_meter_point_mprn": mprn,
    }


def select_active_gas_agreement(account: dict, now: datetime) -> dict | None:
    gas_agreements = account.get("gasAgreements")
    if not isinstance(gas_agreements, list):
        return None

    for agreement in gas_agreements:
        if not isinstance(agreement, dict):
            continue

        tariff = agreement.get("tariff")
        if not isinstance(tariff, dict):
            continue

        try:
            valid_from = _parse_datetime(agreement.get("validFrom"))
            valid_to = _parse_datetime(agreement.get("validTo"))
        except ValueError:
            continue

        if valid_from is None:
            continue

        if valid_from <= now and (valid_to is None or now < valid_to):
            return agreement

    return None


def _latest_meter_reading_data(meter_point: dict | None) -> dict[str, Any] | None:
    if not isinstance(meter_point, dict):
        return None

    unbilled_readings = meter_point.get("unbilledReadings")
    if not isinstance(unbilled_readings, list):
        return None

    def _parse_read_at(reading: Any) -> datetime | None:
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
                "value": reading_value,
                "at": read_at,
                "source": reading.get("readingSource") or reading.get("source"),
                "type": reading.get("readingType"),
                "register_identifier": register.get("identifier"),
                "register_name": register.get("name"),
                "register_digits": register.get("digits"),
                "register_is_quarantined": register.get("isQuarantined"),
            }

    return None


def _latest_gas_meter_reading_fields(meter_point: dict | None) -> dict[str, Any]:
    mprn = meter_point.get("mprn") if isinstance(meter_point, dict) else None
    reading = _latest_meter_reading_data(meter_point)
    if reading is None:
        return _empty_gas_meter_reading_fields(mprn)

    return {
        "latest_gas_meter_reading_value": reading["value"],
        "latest_gas_meter_reading_at": reading["at"],
        "latest_gas_meter_reading_source": reading["source"],
        "latest_gas_meter_reading_type": reading["type"],
        "latest_gas_meter_reading_register_identifier": reading["register_identifier"],
        "latest_gas_meter_reading_register_name": reading["register_name"],
        "latest_gas_meter_reading_register_digits": reading["register_digits"],
        "latest_gas_meter_reading_register_is_quarantined": reading["register_is_quarantined"],
        "gas_meter_point_mprn": mprn,
    }


def _gas_fields(account: dict, now: datetime) -> dict[str, Any]:
    agreement = select_active_gas_agreement(account, now)
    if agreement is None:
        return _empty_gas_fields()

    tariff = agreement["tariff"]
    meter_reading_fields = _latest_gas_meter_reading_fields(agreement.get("meterPoint"))

    return {
        "gas_rate_gbp_per_kwh": _optional_pence_to_gbp(tariff.get("unitRate")),
        "gas_pre_vat_rate_gbp_per_kwh": _optional_pence_to_gbp(tariff.get("preVatUnitRate")),
        "gas_tariff_name": tariff.get("displayName"),
        "gas_tariff_code": tariff.get("tariffCode"),
        "gas_standing_charge_gbp_per_day": _optional_pence_to_gbp(tariff.get("standingCharge")),
        "gas_pre_vat_standing_charge_gbp_per_day": _optional_pence_to_gbp(
            tariff.get("preVatStandingCharge")
        ),
        "gas_agreement_valid_from": _parse_datetime(agreement.get("validFrom")),
        "gas_agreement_valid_to": _parse_datetime(agreement.get("validTo")),
        **meter_reading_fields,
    }


def _latest_meter_reading_fields(meter_point: dict | None) -> dict[str, Any]:
    mpan = meter_point.get("mpan") if isinstance(meter_point, dict) else None
    reading = _latest_meter_reading_data(meter_point)
    if reading is None:
        return _empty_meter_reading_fields(mpan)

    return {
        "latest_meter_reading_kwh": reading["value"],
        "latest_meter_reading_at": reading["at"],
        "latest_meter_reading_source": reading["source"],
        "latest_meter_reading_type": reading["type"],
        "latest_meter_reading_register_identifier": reading["register_identifier"],
        "latest_meter_reading_register_name": reading["register_name"],
        "latest_meter_reading_register_digits": reading["register_digits"],
        "latest_meter_reading_register_is_quarantined": reading["register_is_quarantined"],
        "meter_point_mpan": mpan,
    }


def _token_expiry_datetime(payload: dict[str, Any] | None) -> datetime | None:
    if not isinstance(payload, dict):
        return None

    exp = payload.get("exp")
    if exp is None:
        return None

    return datetime.fromtimestamp(exp, UTC)


def _is_auth_error(errors: list[dict[str, Any]]) -> bool:
    for error in errors:
        extensions = error.get("extensions")
        if not isinstance(extensions, dict):
            extensions = {}

        if extensions.get("code") == "UNAUTHENTICATED":
            return True

        error_code = extensions.get("errorCode")
        # E.ON returns these validation errors for expired or rejected refresh tokens.
        if error_code in {"KT-CT-1134", "KT-CT-1135"}:
            return True
        # Invalid email/password responses use HTTP 200 with this GraphQL error code.
        if error_code == "KT-CT-1138":
            return True

        message_parts = [error.get("message"), extensions.get("errorDescription")]
        validation_errors = extensions.get("validationErrors")
        if isinstance(validation_errors, list):
            message_parts.extend(
                validation_error.get("message")
                for validation_error in validation_errors
                if isinstance(validation_error, dict)
            )

        message = " ".join(part for part in message_parts if isinstance(part, str)).lower()
        if (
            "auth" in message
            or "signature has expired" in message
            or "jwt" in message
            or "refresh token" in message
        ):
            return True

    return False


def build_account_snapshot(account: dict, agreement: dict, now: datetime) -> AccountSnapshot:
    account_number = account.get("number")
    if account_number is None:
        raise EonNextRatesUnsupportedError("Account payload missing required field(s): number")

    tariff = agreement["tariff"]
    tariff_type = tariff.get("__typename")
    if tariff_type != "HalfHourlyTariff":
        raise EonNextRatesUnsupportedError(f"Expected HalfHourlyTariff tariff, got {tariff_type!r}")

    required_fields = ("unitRates", "displayName", "tariffCode", "standingCharge")
    missing_fields = [field for field in required_fields if field not in tariff]
    if missing_fields:
        missing = ", ".join(missing_fields)
        raise EonNextRatesUnsupportedError(
            f"HalfHourlyTariff payload missing required field(s): {missing}"
        )

    current_window: dict[str, Any] | None = None
    next_window: dict[str, Any] | None = None

    unit_rates = tariff["unitRates"]
    if not isinstance(unit_rates, list) or not unit_rates:
        raise EonNextRatesUnsupportedError(
            "HalfHourlyTariff payload missing required field(s): unitRates"
        )

    parsed_windows: list[tuple[dict[str, Any], datetime, datetime | None]] = []
    for unit_rate in unit_rates:
        if not isinstance(unit_rate, dict):
            raise EonNextRatesUnsupportedError(
                "HalfHourlyTariff payload contains an invalid unitRates entry"
            )

        valid_from = _parse_datetime(unit_rate.get("validFrom"))
        if valid_from is None:
            raise EonNextRatesUnsupportedError("HalfHourlyTariff window is missing validFrom")

        parsed_windows.append((unit_rate, valid_from, _parse_datetime(unit_rate.get("validTo"))))

    for unit_rate, valid_from, valid_to in parsed_windows:
        if valid_to is None:
            if valid_from <= now:
                raise EonNextRatesUnsupportedError(
                    "Current HalfHourlyTariff window is missing validTo"
                )
            continue

        if valid_from <= now < valid_to:
            current_window = unit_rate
            future_windows = [
                (candidate_from, candidate)
                for candidate, candidate_from, _candidate_to in parsed_windows
                if candidate_from >= valid_to
            ]
            if future_windows:
                _, next_window = min(future_windows, key=lambda item: item[0])
            break

    if current_window is None:
        raise EonNextRatesUnsupportedError(
            f"No current HalfHourlyTariff window found for {now.isoformat()}"
        )

    current_window_end = _parse_datetime(current_window["validTo"])
    if current_window_end is None:
        raise EonNextRatesUnsupportedError("Current HalfHourlyTariff window is missing validTo")

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
    billing_fields = _billing_fields(account)
    gas_fields = _gas_fields(account, now)

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
        **billing_fields,
        **gas_fields,
        **meter_reading_fields,
    )
