"""Export dbt seed CSVs from generator/reference_data.py (single source of truth)."""

from __future__ import annotations

import csv
from pathlib import Path

from generator import reference_data as ref

SEEDS = Path(__file__).resolve().parents[1] / "dbt" / "seeds"

# Soft declines are retryable (temporary condition); hard declines should not be retried.
DECLINE_META = {
    "00": ("Approved", ""),
    "51": ("Financial", "soft"), "61": ("Financial", "soft"),
    "05": ("Issuer Discretion", "soft"), "91": ("Technical", "soft"),
    "54": ("Card Status", "hard"), "14": ("Card Status", "hard"),
    "55": ("Cardholder Verification", "soft"), "57": ("Policy", "hard"),
    "59": ("Fraud / Risk", "hard"),
}


def write(name: str, header: list[str], rows: list[list]) -> None:
    SEEDS.mkdir(parents=True, exist_ok=True)
    with open(SEEDS / f"{name}.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def main() -> None:
    write("mcc_codes", ["mcc", "mcc_description", "mcc_category", "risk_tier"],
          [[m[0], m[1], m[2], m[9]] for m in ref.MCC_TABLE])
    write("currencies", ["currency_code", "numeric_code", "currency_symbol", "usd_rate", "minor_units"],
          [[c, ref.CURRENCY_NUMERIC[c], ref.CURRENCY_SYMBOL[c], r, ref.CURRENCY_DECIMALS.get(c, 2)]
           for c, r in ref.FX_TO_USD.items()])
    write("auth_response_codes", ["response_code", "response_description", "decline_reason", "is_approved",
                                  "decline_category", "decline_type"],
          [[k, v[0], v[1] or "", str(k == "00").lower(), *DECLINE_META[k]] for k, v in ref.AUTH_CODES.items()])
    write("countries", ["country_code", "country_name", "region", "currency_code"],
          [[k, v[0], v[1], v[2]] for k, v in ref.COUNTRIES.items()])
    write("us_holidays", ["holiday_date", "holiday_name"],
          [[d, v[0]] for d, v in ref.US_HOLIDAYS_2025.items()])
    print(f"seeds written to {SEEDS}")


if __name__ == "__main__":
    main()
