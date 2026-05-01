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
