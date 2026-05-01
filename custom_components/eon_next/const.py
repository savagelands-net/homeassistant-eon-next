from __future__ import annotations

from datetime import timedelta

DOMAIN = "eon_next"
PLATFORMS = ["sensor"]
GRAPHQL_URL = "https://api.eonnext-kraken.energy/v1/graphql/"
DEFAULT_SCAN_INTERVAL = timedelta(minutes=1)
ATTR_TARIFF_NAME = "tariff_name"
ATTR_TARIFF_CODE = "tariff_code"
ATTR_ACCOUNT_NUMBER = "account_number"
ATTR_STANDING_CHARGE_GBP_PER_DAY = "standing_charge_gbp_per_day"
ATTR_PRE_VAT_STANDING_CHARGE_GBP_PER_DAY = "pre_vat_standing_charge_gbp_per_day"
ATTR_CURRENT_WINDOW_END = "current_window_end"
ATTR_NEXT_WINDOW_START = "next_window_start"
ATTR_AGREEMENT_VALID_FROM = "agreement_valid_from"
ATTR_AGREEMENT_VALID_TO = "agreement_valid_to"
ATTR_METER_POINT_MPAN = "meter_point_mpan"
ATTR_LATEST_METER_READING_SOURCE = "latest_meter_reading_source"
ATTR_LATEST_METER_READING_TYPE = "latest_meter_reading_type"
ATTR_LATEST_METER_READING_REGISTER_IDENTIFIER = "latest_meter_reading_register_identifier"
ATTR_LATEST_METER_READING_REGISTER_NAME = "latest_meter_reading_register_name"
ATTR_LATEST_METER_READING_REGISTER_DIGITS = "latest_meter_reading_register_digits"
ATTR_LATEST_METER_READING_REGISTER_IS_QUARANTINED = (
    "latest_meter_reading_register_is_quarantined"
)
