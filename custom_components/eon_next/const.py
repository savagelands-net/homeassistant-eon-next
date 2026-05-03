from __future__ import annotations

from datetime import timedelta

DOMAIN = "eon_next"
PLATFORMS = ["sensor"]
GRAPHQL_URL = "https://api.eonnext-kraken.energy/v1/graphql/"
DEFAULT_SCAN_INTERVAL = timedelta(minutes=1)
ATTR_ACCOUNT_NUMBER = "account_number"
ATTR_ELECTRICITY_TARIFF_NAME = "electricity_tariff_name"
ATTR_ELECTRICITY_TARIFF_CODE = "electricity_tariff_code"
ATTR_ELECTRICITY_STANDING_CHARGE_GBP_PER_DAY = (
    "electricity_standing_charge_gbp_per_day"
)
ATTR_ELECTRICITY_PRE_VAT_STANDING_CHARGE_GBP_PER_DAY = (
    "electricity_pre_vat_standing_charge_gbp_per_day"
)
ATTR_ELECTRICITY_CURRENT_WINDOW_END = "electricity_current_window_end"
ATTR_ELECTRICITY_NEXT_WINDOW_START = "electricity_next_window_start"
ATTR_ELECTRICITY_AGREEMENT_VALID_FROM = "electricity_agreement_valid_from"
ATTR_ELECTRICITY_AGREEMENT_VALID_TO = "electricity_agreement_valid_to"
ATTR_GAS_TARIFF_NAME = "gas_tariff_name"
ATTR_GAS_TARIFF_CODE = "gas_tariff_code"
ATTR_GAS_PRE_VAT_RATE_GBP_PER_KWH = "gas_pre_vat_rate_gbp_per_kwh"
ATTR_GAS_AGREEMENT_VALID_FROM = "gas_agreement_valid_from"
ATTR_GAS_AGREEMENT_VALID_TO = "gas_agreement_valid_to"
ATTR_GAS_METER_POINT_MPRN = "gas_meter_point_mprn"
ATTR_ELECTRICITY_METER_POINT_MPAN = "electricity_meter_point_mpan"
ATTR_LATEST_ELECTRICITY_METER_READING_SOURCE = (
    "latest_electricity_meter_reading_source"
)
ATTR_LATEST_ELECTRICITY_METER_READING_TYPE = "latest_electricity_meter_reading_type"
ATTR_LATEST_ELECTRICITY_METER_READING_REGISTER_IDENTIFIER = (
    "latest_electricity_meter_reading_register_identifier"
)
ATTR_LATEST_ELECTRICITY_METER_READING_REGISTER_NAME = (
    "latest_electricity_meter_reading_register_name"
)
ATTR_LATEST_ELECTRICITY_METER_READING_REGISTER_DIGITS = (
    "latest_electricity_meter_reading_register_digits"
)
ATTR_LATEST_ELECTRICITY_METER_READING_REGISTER_IS_QUARANTINED = (
    "latest_electricity_meter_reading_register_is_quarantined"
)
ATTR_LATEST_GAS_METER_READING_SOURCE = "latest_gas_meter_reading_source"
ATTR_LATEST_GAS_METER_READING_TYPE = "latest_gas_meter_reading_type"
ATTR_LATEST_GAS_METER_READING_REGISTER_IDENTIFIER = (
    "latest_gas_meter_reading_register_identifier"
)
ATTR_LATEST_GAS_METER_READING_REGISTER_NAME = "latest_gas_meter_reading_register_name"
ATTR_LATEST_GAS_METER_READING_REGISTER_DIGITS = (
    "latest_gas_meter_reading_register_digits"
)
ATTR_LATEST_GAS_METER_READING_REGISTER_IS_QUARANTINED = (
    "latest_gas_meter_reading_register_is_quarantined"
)
ATTR_SMARTFLEX_DEVICE_ID = "smartflex_device_id"
ATTR_SMARTFLEX_DEVICE_TYPE = "smartflex_device_type"
ATTR_SMARTFLEX_PROVIDER = "smartflex_provider"
ATTR_SMARTFLEX_INTEGRATION_DEVICE_ID = "smartflex_integration_device_id"
ATTR_SMARTFLEX_PROPERTY_ID = "smartflex_property_id"
ATTR_SMARTFLEX_MAKE = "smartflex_make"
ATTR_SMARTFLEX_MODEL = "smartflex_model"
ATTR_SMARTFLEX_LIFECYCLE_STATUS = "smartflex_lifecycle_status"
ATTR_SMARTFLEX_IS_SUSPENDED = "smartflex_is_suspended"
ATTR_SMARTFLEX_TEST_DISPATCH_FAILURE_REASON = "smartflex_test_dispatch_failure_reason"
ATTR_SMARTFLEX_READING_TIMESTAMP = "smartflex_reading_timestamp"
ATTR_SMARTFLEX_UPPER_SOC_LIMIT = "smartflex_upper_soc_limit"
ATTR_SMARTFLEX_SOC_LIMIT_TIMESTAMP = "smartflex_soc_limit_timestamp"
ATTR_SMARTFLEX_IS_SOC_LIMIT_VIOLATED = "smartflex_is_soc_limit_violated"
ATTR_SMARTFLEX_LATEST_CHARGING_SESSION_START = "smartflex_latest_charging_session_start"
ATTR_SMARTFLEX_LATEST_CHARGING_SESSION_END = "smartflex_latest_charging_session_end"
ATTR_SMARTFLEX_LATEST_CHARGING_SESSION_SOC_DELTA = (
    "smartflex_latest_charging_session_soc_delta"
)
ATTR_SMARTFLEX_LATEST_CHARGING_SESSION_SOC_FINAL = (
    "smartflex_latest_charging_session_soc_final"
)
ATTR_SMARTFLEX_NEXT_PLANNED_DISPATCH_START = "smartflex_next_planned_dispatch_start"
ATTR_SMARTFLEX_NEXT_PLANNED_DISPATCH_END = "smartflex_next_planned_dispatch_end"
ATTR_SMARTFLEX_NEXT_PLANNED_DISPATCH_TYPE = "smartflex_next_planned_dispatch_type"
ATTR_SMARTFLEX_COMPLETED_DISPATCH_SOURCE = "smartflex_completed_dispatch_source"
ATTR_SMARTFLEX_COMPLETED_DISPATCH_LOCATION = "smartflex_completed_dispatch_location"
