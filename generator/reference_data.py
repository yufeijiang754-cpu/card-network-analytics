"""Static reference data used by the synthetic data generator.

Everything here is synthetic or public-domain reference data:
- MCC codes and descriptions follow the ISO 18245 merchant category code list.
- Interchange rates are *illustrative* approximations of published US network
  rate schedules (not any specific network's actual rates).
- Issuer / acquirer names are fictional.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Merchant Category Codes (ISO 18245)
# mcc -> description, category, share of transactions (weekday, weekend/holiday),
#        amount distribution (lognormal median USD, sigma), probability of
#        card-not-present, base cross-border probability, fraud risk tier,
#        base (non-fraud) chargeback probability
# ---------------------------------------------------------------------------
MCC_TABLE = [
    # mcc,  description,                              category,        wkday, wkend, median, sigma, p_cnp, p_xb, risk,  p_cb
    ("5411", "Grocery Stores, Supermarkets",           "Grocery",        0.170, 0.165,  45.0, 0.75, 0.08, 0.02, "low",    0.0008),
    ("5812", "Eating Places, Restaurants",             "Dining",         0.110, 0.140,  38.0, 0.65, 0.06, 0.05, "low",    0.0010),
    ("5814", "Fast Food Restaurants",                  "Dining",         0.120, 0.120,  12.5, 0.55, 0.10, 0.03, "low",    0.0006),
    ("5541", "Service Stations",                       "Fuel",           0.060, 0.050,  42.0, 0.50, 0.00, 0.02, "medium", 0.0005),
    ("5542", "Automated Fuel Dispensers",              "Fuel",           0.060, 0.050,  48.0, 0.45, 0.00, 0.02, "medium", 0.0005),
    ("4511", "Airlines, Air Carriers",                 "Travel",         0.015, 0.016, 380.0, 0.70, 0.88, 0.35, "high",   0.0040),
    ("7011", "Hotels, Motels, Resorts",                "Travel",         0.020, 0.025, 240.0, 0.75, 0.45, 0.30, "medium", 0.0035),
    ("4121", "Taxicabs and Limousines",                "Transportation", 0.045, 0.050,  22.0, 0.60, 0.65, 0.10, "medium", 0.0015),
    ("5311", "Department Stores",                      "Retail",         0.050, 0.075,  72.0, 0.85, 0.25, 0.03, "medium", 0.0015),
    ("5732", "Electronics Stores",                     "Retail",         0.025, 0.035, 185.0, 0.95, 0.40, 0.04, "high",   0.0030),
    ("5999", "Miscellaneous and Specialty Retail",     "Retail",         0.060, 0.065,  40.0, 0.90, 0.30, 0.04, "medium", 0.0015),
    ("5964", "Direct Marketing - Catalog Merchant",    "E-commerce",     0.080, 0.075,  58.0, 0.85, 1.00, 0.12, "high",   0.0040),
    ("5815", "Digital Goods - Media, Books, Music",    "Digital Goods",  0.040, 0.035,  10.0, 0.70, 1.00, 0.15, "high",   0.0045),
    ("5816", "Digital Goods - Games",                  "Digital Goods",  0.025, 0.030,  15.0, 0.80, 1.00, 0.15, "high",   0.0050),
    ("4899", "Cable, Satellite and Streaming Services", "Subscriptions",  0.045, 0.020,  16.0, 0.40, 1.00, 0.05, "medium", 0.0025),
    ("5912", "Drug Stores and Pharmacies",             "Health",         0.050, 0.035,  26.0, 0.70, 0.10, 0.02, "low",    0.0008),
    ("4900", "Utilities - Electric, Gas, Water",       "Utilities",      0.020, 0.005, 125.0, 0.55, 0.95, 0.01, "low",    0.0010),
    ("7995", "Betting, Casino Gaming Chips",           "Gambling",       0.005, 0.009,  60.0, 1.00, 0.70, 0.20, "high",   0.0060),
]

# Values injected as "invalid MCC" data-quality issues (not in ISO 18245 list).
INVALID_MCC_VALUES = ["0000", "1234", "ABCD", "58120", "99999", "-1"]

# ---------------------------------------------------------------------------
# Interchange (illustrative). Credit: rate% + fixed USD by MCC category.
# ---------------------------------------------------------------------------
CREDIT_INTERCHANGE = {
    "Grocery":        (0.0135, 0.05),
    "Dining":         (0.0173, 0.10),
    "Fuel":           (0.0115, 0.10),
    "Travel":         (0.0210, 0.10),
    "Transportation": (0.0180, 0.10),
    "Retail":         (0.0165, 0.10),
    "E-commerce":     (0.0195, 0.10),
    "Digital Goods":  (0.0180, 0.05),
    "Subscriptions":  (0.0180, 0.10),
    "Health":         (0.0150, 0.10),
    "Utilities":      (0.0075, 0.50),
    "Gambling":       (0.0220, 0.10),
}
PRODUCT_UPLIFT = {"Classic": 0.0, "Rewards": 0.0030, "Premium": 0.0055, "Business": 0.0065}
CNP_UPLIFT = 0.0015
CROSS_BORDER_UPLIFT = 0.0060
# Regulated debit (US Reg II / "Durbin" cap for issuers with >$10B assets): 0.05% + $0.21 + $0.01 fraud adj.
REGULATED_DEBIT = (0.0005, 0.22)
EXEMPT_DEBIT = (0.0080, 0.15)

# ---------------------------------------------------------------------------
# Geography / currencies
# ---------------------------------------------------------------------------
COUNTRIES = {
    # code: (name, region, currency, cardholder share, merchant share)
    "US": ("United States", "North America", "USD", 0.880, 0.70),
    "CA": ("Canada", "North America", "CAD", 0.030, 0.05),
    "MX": ("Mexico", "Latin America", "MXN", 0.020, 0.05),
    "GB": ("United Kingdom", "Europe", "GBP", 0.025, 0.04),
    "DE": ("Germany", "Europe", "EUR", 0.015, 0.03),
    "FR": ("France", "Europe", "EUR", 0.010, 0.04),
    "ES": ("Spain", "Europe", "EUR", 0.005, 0.03),
    "JP": ("Japan", "Asia Pacific", "JPY", 0.010, 0.03),
    "AU": ("Australia", "Asia Pacific", "AUD", 0.005, 0.03),
}
# Where US cardholders go when a transaction is cross-border.
US_TRAVEL_DESTINATIONS = {"CA": 0.20, "MX": 0.22, "GB": 0.14, "FR": 0.11, "DE": 0.08,
                          "ES": 0.08, "JP": 0.10, "AU": 0.07}

# USD value of 1 unit of currency (static synthetic rates for 2025).
FX_TO_USD = {"USD": 1.0, "CAD": 0.73, "MXN": 0.055, "GBP": 1.27, "EUR": 1.08,
             "JPY": 0.0067, "AUD": 0.66}
CURRENCY_DECIMALS = {"JPY": 0}
# ISO 4217 numeric codes, used to inject "numeric code instead of alpha code" issues.
CURRENCY_NUMERIC = {"USD": "840", "CAD": "124", "MXN": "484", "GBP": "826", "EUR": "978",
                    "JPY": "392", "AUD": "036"}
CURRENCY_SYMBOL = {"USD": "US$", "CAD": "C$", "MXN": "MX$", "GBP": "£", "EUR": "€",
                   "JPY": "¥", "AUD": "A$"}

# ---------------------------------------------------------------------------
# Authorization response codes (ISO 8583 field 39 style)
# ---------------------------------------------------------------------------
AUTH_CODES = {
    "00": ("Approved", None),
    "51": ("Insufficient funds", "Insufficient Funds"),
    "05": ("Do not honor", "Do Not Honor"),
    "61": ("Exceeds withdrawal amount limit", "Exceeds Limit"),
    "54": ("Expired card", "Expired Card"),
    "55": ("Incorrect PIN", "Incorrect PIN"),
    "57": ("Transaction not permitted to cardholder", "Transaction Not Permitted"),
    "14": ("Invalid card number", "Invalid Card Number"),
    "91": ("Issuer or switch inoperative", "Issuer Unavailable"),
    "59": ("Suspected fraud", "Suspected Fraud"),
}
# Decline-reason mix for *non-fraud* declines, by channel.
DECLINE_MIX_CP = {"51": 0.42, "05": 0.17, "61": 0.10, "54": 0.06, "55": 0.09, "57": 0.06,
                  "14": 0.03, "91": 0.03, "59": 0.04}
DECLINE_MIX_CNP = {"51": 0.38, "05": 0.22, "61": 0.05, "54": 0.11, "55": 0.00, "57": 0.07,
                   "14": 0.07, "91": 0.03, "59": 0.07}

# ---------------------------------------------------------------------------
# Calendar effects (2025, US)
# ---------------------------------------------------------------------------
US_HOLIDAYS_2025 = {
    "2025-01-01": ("New Year's Day", 1.15),
    "2025-01-20": ("Martin Luther King Jr. Day", 1.15),
    "2025-02-14": ("Valentine's Day", 1.20),
    "2025-02-17": ("Presidents' Day", 1.25),
    "2025-05-26": ("Memorial Day", 1.30),
    "2025-07-04": ("Independence Day", 1.30),
    "2025-09-01": ("Labor Day", 1.25),
    "2025-11-11": ("Veterans Day", 1.15),
    "2025-11-27": ("Thanksgiving Day", 1.10),
    "2025-11-28": ("Black Friday", 1.90),
    "2025-12-01": ("Cyber Monday", 1.60),
    "2025-12-24": ("Christmas Eve", 1.45),
    "2025-12-25": ("Christmas Day", 0.85),  # most stores closed: deliberately lower
    "2025-12-31": ("New Year's Eve", 1.30),
}
DOW_MULTIPLIER = {0: 0.94, 1: 0.95, 2: 0.97, 3: 1.00, 4: 1.12, 5: 1.22, 6: 1.08}  # Mon=0
MONTH_MULTIPLIER = {1: 0.88, 2: 0.90, 3: 0.97, 4: 0.98, 5: 1.02, 6: 1.03, 7: 1.04,
                    8: 1.03, 9: 0.98, 10: 1.00, 11: 1.07, 12: 1.20}
# Share of daily volume per hour of day (local time, approximated in UTC for simplicity).
HOURLY_WEIGHTS = [0.6, 0.4, 0.3, 0.25, 0.3, 0.6, 1.4, 2.6, 3.6, 4.3, 4.9, 5.9,
                  6.8, 6.3, 5.5, 5.3, 5.6, 6.4, 7.0, 6.6, 5.5, 4.3, 2.8, 1.5]

CARD_PRODUCTS = {  # product -> (share of credit cards, credit limit lognormal median)
    "Classic": (0.40, 4000), "Rewards": (0.35, 9000), "Premium": (0.15, 20000), "Business": (0.10, 15000),
}
ISSUER_NAME_PARTS = (
    ["Summit", "Harbor", "Pioneer", "Lakeside", "Granite", "Redwood", "Beacon", "Prairie",
     "Keystone", "Meridian", "Cascade", "Liberty", "Northstar", "Bluewater", "Evergreen",
     "Frontier", "Silverline", "Canyon", "Riverbend", "Ironwood"],
    ["Bank", "Financial", "Credit Union", "Bancorp", "Savings Bank", "Trust"],
)
ACQUIRER_NAMES = [
    "Atlas Merchant Services", "Clearpath Payments", "Vantage Acquiring", "Orbit Pay",
    "Keel Commerce", "Halcyon Processing", "Brightgate Payments", "Sterling Merchant Solutions",
    "Nimbus PayFac", "Quarry Payments", "Tidewater Acquiring", "Copperleaf Commerce",
    "Lumen Merchant Services", "Paragon Pay", "Westward Processing",
]
