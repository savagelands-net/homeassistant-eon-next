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
