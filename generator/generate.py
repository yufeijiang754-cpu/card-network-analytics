"""Synthetic card-network authorization data generator.

Produces five Parquet datasets (transactions, merchants, cardholders, issuers,
acquirers) that mimic the authorization flow of a card payment network, plus a
data-quality answer key describing every deliberately injected defect.

All data is SYNTHETIC. Business patterns (seasonality, fraud by channel,
decline-reason mix, interchange) are plausible approximations, not real
network statistics.

Usage:
    python -m generator.generate                       # 2M rows (default)
    python -m generator.generate --rows 50000000 --out data/raw_50m
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from generator import reference_data as ref
from generator.dq_injection import inject_merchant_issues, inject_transaction_issues

# Planted business scenarios (documented in DECISIONS.md, surfaced in docs/INSIGHTS.md)
CARD_TESTING_WINDOW = ("2025-09-18", "2025-09-21")  # [start, end)
CARD_TESTING_SHARE = 0.0012  # share of transactions that belong to the attack
CARD_TESTING_ACQUIRER = "ACQ009"  # a payment facilitator with weak onboarding controls
OUTAGE_ISSUER = "ISS012"
OUTAGE_WINDOW = ("2025-06-14 14:00:00", "2025-06-14 17:00:00")
AGGRESSIVE_CNP_ISSUER = "ISS007"  # over-tuned CNP fraud rules -> false declines
N_HIGH_CHARGEBACK_MERCHANTS = 25


@dataclass
class GeneratorConfig:
    n_transactions: int = 2_000_000
    n_cardholders: int = 150_000
    n_merchants: int = 20_000
    n_issuers: int = 45
    seed: int = 42
    start_date: str = "2025-01-01"
    end_date: str = "2025-12-31"  # inclusive
    chunk_size: int = 2_000_000
    inject_dq: bool = True
    out_dir: str = "data/raw"
    answer_key_path: str = "data/dq_answer_key.csv"
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Dimension builders
# ---------------------------------------------------------------------------
def _ids(prefix: str, numbers: np.ndarray, width: int) -> np.ndarray:
    return np.char.add(prefix, np.char.zfill(numbers.astype(str), width)).astype(object)


def build_issuers(rng: np.random.Generator, n: int) -> pd.DataFrame:
    # Country allocation: most issuers are US-based; at least one per country.
    per_country = {"CA": 2, "MX": 2, "GB": 2, "DE": 2, "FR": 1, "ES": 1, "JP": 1, "AU": 1}
    per_country["US"] = n - sum(per_country.values())
    countries = np.concatenate([[c] * k for c, k in per_country.items()])
    rng.shuffle(countries)
    issuer_type = rng.choice(["Bank", "Credit Union", "Fintech"], size=n, p=[0.65, 0.2, 0.15])
    first, _ = ref.ISSUER_NAME_PARTS
    suffix_by_type = {"Bank": ["Bank", "Bancorp", "Savings Bank", "Trust"],
                      "Credit Union": ["Credit Union"], "Fintech": ["Financial", "Pay", "Card Co."]}
    names, used = [], set()
    for t in issuer_type:
        while True:
            nm = f"{rng.choice(first)} {rng.choice(suffix_by_type[t])}"
            if nm not in used:
                used.add(nm)
                names.append(nm)
                break
    is_large = rng.random(n) < 0.45
    df = pd.DataFrame({
        "issuer_id": _ids("ISS", np.arange(1, n + 1), 3),
        "issuer_name": names,
        "country_code": countries,
        "issuer_type": issuer_type,
        "asset_size_tier": np.where(is_large, "Large (>$10B)", "Small (<$10B)"),
    })
    # Hidden behavioural parameters (not exported)
    df["_share"] = rng.lognormal(0, 0.9, n) * np.where(is_large, 3.0, 1.0)
    df["_decline_bias"] = rng.normal(0, 0.012, n)
    df["_cnp_decline_bias"] = np.abs(rng.normal(0, 0.01, n))
    df.loc[df.issuer_id == AGGRESSIVE_CNP_ISSUER, "_cnp_decline_bias"] = 0.11
    df.loc[df.issuer_id == AGGRESSIVE_CNP_ISSUER, "country_code"] = "US"
    df.loc[df.issuer_id == OUTAGE_ISSUER, "country_code"] = "US"
    # The outage issuer is a top-3 US issuer so a 3-hour outage is material (~30 auths/hour).
    df.loc[df.issuer_id == OUTAGE_ISSUER, "_share"] = df._share.max() * 0.8
    df.loc[df.issuer_id == OUTAGE_ISSUER, "asset_size_tier"] = "Large (>$10B)"
    df["is_regulated_debit"] = df["asset_size_tier"].str.startswith("Large")
    df["onboarded_date"] = pd.to_datetime("2005-01-01") + pd.to_timedelta(rng.integers(0, 6000, n), unit="D")
    return df


def build_acquirers(rng: np.random.Generator) -> pd.DataFrame:
    countries = ["US"] * 10 + ["CA", "MX", "GB", "DE", "JP"]
    types = ["Bank", "Bank", "Bank", "Processor", "Processor", "Bank", "Processor", "Bank",
             "Payment Facilitator", "Processor", "Bank", "Bank", "Bank", "Processor", "Bank"]
    return pd.DataFrame({
        "acquirer_id": _ids("ACQ", np.arange(1, 16), 3),
        "acquirer_name": ref.ACQUIRER_NAMES,
        "country_code": countries,
        "acquirer_type": types,
    })


ACQUIRER_REGION = {"US": "US", "CA": "CA", "MX": "MX", "GB": "GB", "DE": "DE", "FR": "DE",
                   "ES": "DE", "JP": "JP", "AU": "JP"}


def build_merchants(rng: np.random.Generator, n: int, acquirers: pd.DataFrame) -> pd.DataFrame:
    mcc = np.array([m[0] for m in ref.MCC_TABLE])
    mcc_share = np.array([m[3] for m in ref.MCC_TABLE])
    countries = list(ref.COUNTRIES)
    c_share = np.array([ref.COUNTRIES[c][4] for c in countries])
    # Guarantee >=3 merchants in every (mcc, country) pool, distribute the rest proportionally.
    base = [(m, c) for m in mcc for c in countries for _ in range(3)]
    rest = n - len(base)
    m_rest = rng.choice(mcc, size=rest, p=mcc_share / mcc_share.sum())
    c_rest = rng.choice(countries, size=rest, p=c_share / c_share.sum())
    m_all = np.concatenate([[b[0] for b in base], m_rest])
    c_all = np.concatenate([[b[1] for b in base], c_rest])
    perm = rng.permutation(n)
    m_all, c_all = m_all[perm], c_all[perm]

    # Acquirer: country/regional pool; US merchants spread across US acquirers.
    acq_by_region = {}
    for _, a in acquirers.iterrows():
        acq_by_region.setdefault(a.country_code, []).append(a.acquirer_id)
    us_acq = acq_by_region["US"]
    us_w = rng.dirichlet(np.ones(len(us_acq)) * 2)
    acq = np.empty(n, dtype=object)
    for c in countries:
        mask = c_all == c
        pool = acq_by_region[ACQUIRER_REGION[c]]
        acq[mask] = rng.choice(pool, size=mask.sum(), p=us_w if c == "US" else None)

    adjectives = ["Blue", "Golden", "Urban", "Corner", "Prime", "Metro", "Sunset", "Coastal", "Maple",
                  "Silver", "Rapid", "Happy", "Grand", "Little", "Royal", "Green", "Bright", "Elm"]
    noun_by_cat = {"Grocery": "Market", "Dining": "Kitchen", "Fuel": "Fuel Stop", "Travel": "Travel",
                   "Transportation": "Rides", "Retail": "Store", "E-commerce": "Online Shop",
                   "Digital Goods": "Digital", "Subscriptions": "Streaming", "Health": "Pharmacy",
                   "Utilities": "Energy", "Gambling": "Gaming Club"}
    cat_by_mcc = {m[0]: m[2] for m in ref.MCC_TABLE}
    names = [f"{a} {noun_by_cat[cat_by_mcc[m]]} #{i:05d}"
             for i, (a, m) in enumerate(zip(rng.choice(adjectives, n), m_all), start=1)]
    df = pd.DataFrame({
        "merchant_id": _ids("M", np.arange(1, n + 1), 6),
        "merchant_name": names,
        "mcc": m_all,
        "country_code": c_all,
        "acquirer_id": acq,
        "onboarding_date": pd.to_datetime("2012-01-01") + pd.to_timedelta(rng.integers(0, 4700, n), unit="D"),
    })
    df["_popularity"] = rng.lognormal(0, 1.1, n)
    # High-chargeback merchants (planted for anomaly detection): CNP-heavy categories, US.
    risky_mask = df.mcc.isin(["5964", "5816", "5815", "4511", "5732"]) & (df.country_code == "US")
    # pick from the busier merchants so the pattern is statistically visible
    risky = df.index[risky_mask & (df._popularity >= df.loc[risky_mask, "_popularity"].quantile(0.75))]
    df["_high_cb"] = False
    df.loc[rng.choice(risky, N_HIGH_CHARGEBACK_MERCHANTS, replace=False), "_high_cb"] = True
    # Card-testing targets: digital-goods merchants onboarded by the PayFac acquirer.
    ct = df.index[(df.acquirer_id == CARD_TESTING_ACQUIRER) & df.mcc.isin(["5815", "5816"])]
    df["_card_testing_target"] = False
    df.loc[ct[:6], "_card_testing_target"] = True
    return df


def build_cardholders(rng: np.random.Generator, n: int, issuers: pd.DataFrame) -> pd.DataFrame:
    countries = list(ref.COUNTRIES)
    share = np.array([ref.COUNTRIES[c][3] for c in countries])
    home = rng.choice(countries, size=n, p=share / share.sum())
    issuer = np.empty(n, dtype=object)
    for c in countries:
        mask = home == c
        pool = issuers[issuers.country_code == c]
        w = pool["_share"].to_numpy()
        issuer[mask] = rng.choice(pool.issuer_id.to_numpy(), size=mask.sum(), p=w / w.sum())
    card_type = np.where(rng.random(n) < 0.6, "Credit", "Debit")
    products = list(ref.CARD_PRODUCTS)
    p_share = np.array([ref.CARD_PRODUCTS[p][0] for p in products])
    product = np.where(card_type == "Credit", rng.choice(products, size=n, p=p_share), "Debit")
    medians = np.array([ref.CARD_PRODUCTS.get(p, (0, 0))[1] for p in product], dtype=float)
    limit = np.where(card_type == "Credit", np.round(medians * rng.lognormal(0, 0.4, n), -2), np.nan)
    df = pd.DataFrame({
        "card_id": _ids("C", np.arange(1, n + 1), 8),
        "issuer_id": issuer,
        "home_country": home,
        "card_type": card_type,
        "card_product": product,
        "credit_limit": limit,
        "card_open_date": pd.to_datetime("2015-01-01") + pd.to_timedelta(rng.integers(0, 3600, n), unit="D"),
    })
    df["_activity"] = rng.lognormal(0, 0.8, n) * np.where(product == "Premium", 1.6, 1.0)
    return df


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------
def build_calendar(cfg: GeneratorConfig) -> pd.DataFrame:
    days = pd.date_range(cfg.start_date, cfg.end_date, freq="D")
    cal = pd.DataFrame({"date": days})
    cal["dow"] = cal.date.dt.dayofweek
    cal["is_weekend"] = cal.dow >= 5
    hol = {pd.Timestamp(k): v for k, v in ref.US_HOLIDAYS_2025.items()}
    cal["holiday_mult"] = cal.date.map(lambda d: hol.get(d, (None, 1.0))[1])
    cal["is_holiday"] = cal.date.isin(hol.keys())
    cal["weight"] = (cal.dow.map(ref.DOW_MULTIPLIER) * cal.date.dt.month.map(ref.MONTH_MULTIPLIER)
                     * cal.holiday_mult)
    # Gentle growth trend through the year (+6% Jan -> Dec)
    cal["weight"] *= np.linspace(0.97, 1.03, len(cal))
    cal["p"] = cal.weight / cal.weight.sum()
    return cal


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------
class _Dims:
    """Pre-computed numpy views of dimensions for fast vectorised sampling."""

    def __init__(self, issuers, merchants, cardholders, cal):
        self.issuers, self.merchants, self.cardholders, self.cal = issuers, merchants, cardholders, cal
        self.mcc_codes = np.array([m[0] for m in ref.MCC_TABLE])
        t = ref.MCC_TABLE
        self.mcc_wkday = np.array([m[3] for m in t]) / sum(m[3] for m in t)
        self.mcc_wkend = np.array([m[4] for m in t]) / sum(m[4] for m in t)
        self.mcc_cat = np.array([m[2] for m in t])
        self.mcc_median = np.array([m[5] for m in t])
        self.mcc_sigma = np.array([m[6] for m in t])
        self.mcc_pcnp = np.array([m[7] for m in t])
        self.mcc_pxb = np.array([m[8] for m in t])
        risk_base = {"low": 0.00025, "medium": 0.0005, "high": 0.0011}
        self.mcc_fraud = np.array([risk_base[m[9]] for m in t])
        self.mcc_pcb = np.array([m[10] for m in t])
        # Card arrays
        ch = cardholders
        self.card_ids = ch.card_id.to_numpy()
        self.card_p = (ch._activity / ch._activity.sum()).to_numpy()
        self.card_issuer = ch.issuer_id.to_numpy()
        self.card_home = ch.home_country.to_numpy()
        self.card_type = ch.card_type.to_numpy()
        self.card_product = ch.card_product.to_numpy()
        iss = issuers.set_index("issuer_id")
        self.iss_bias = iss._decline_bias
        self.iss_cnp_bias = iss._cnp_decline_bias
        self.iss_regulated = iss.is_regulated_debit
        # Merchant pools by (mcc, country)
        m = merchants
        self.m_ids = m.merchant_id.to_numpy()
        self.m_acq = m.acquirer_id.to_numpy()
        self.m_country = m.country_code.to_numpy()
        self.m_high_cb = m._high_cb.to_numpy()
        self.pools = {}
        for (mcc, c), g in m.groupby(["mcc", "country_code"]):
            w = g._popularity.to_numpy()
            self.pools[(mcc, c)] = (g.index.to_numpy(), w / w.sum())
        self.ct_targets = m.index[m._card_testing_target].to_numpy()


def _sample_timestamps(rng, n, cal, start=None, end=None):
    if start is not None:
        lo, hi = pd.Timestamp(start).value, pd.Timestamp(end).value
        return pd.to_datetime(rng.integers(lo, hi, n)).floor("s")
    day_idx = rng.choice(len(cal), size=n, p=cal.p.to_numpy())
    hw = np.array(ref.HOURLY_WEIGHTS)
    hours = rng.choice(24, size=n, p=hw / hw.sum())
    secs = hours * 3600 + rng.integers(0, 3600, n)
    return pd.to_datetime(cal.date.to_numpy()[day_idx]) + pd.to_timedelta(secs, unit="s"), day_idx


def generate_chunk(rng: np.random.Generator, n: int, d: _Dims, id_offset: int) -> pd.DataFrame:
    cal = d.cal
    n_ct = int(round(n * CARD_TESTING_SHARE))
    n_main = n - n_ct

    # --- when -----------------------------------------------------------------
    ts, day_idx = _sample_timestamps(rng, n_main, cal)
    special_day = (cal.is_weekend | cal.is_holiday).to_numpy()[day_idx]

    # --- what (MCC mix shifts on weekends / holidays) ------------------------
    mcc_idx = np.where(special_day,
                       rng.choice(len(d.mcc_codes), n_main, p=d.mcc_wkend),
                       rng.choice(len(d.mcc_codes), n_main, p=d.mcc_wkday))

    # --- who -------------------------------------------------------------------
    card_idx = rng.choice(len(d.card_ids), size=n_main, p=d.card_p)
    home = d.card_home[card_idx]

    # --- where: cross-border decision then merchant country ---------------------
    p_xb = d.mcc_pxb[mcc_idx] + np.where(home == "US", 0.0, 0.15)
    is_xb = rng.random(n_main) < p_xb
    m_country = home.copy()
    countries = list(ref.COUNTRIES)
    us_dest = list(ref.US_TRAVEL_DESTINATIONS)
    us_dest_p = np.array(list(ref.US_TRAVEL_DESTINATIONS.values()))
    for c in countries:
        mask = is_xb & (home == c)
        k = int(mask.sum())
        if not k:
            continue
        if c == "US":
            m_country[mask] = rng.choice(us_dest, size=k, p=us_dest_p / us_dest_p.sum())
        else:
            others = [x for x in countries if x != c]
            w = np.array([0.7 if x == "US" else 0.3 / (len(others) - 1) for x in others])
            m_country[mask] = rng.choice(others, size=k, p=w)

    # --- merchant within (mcc, country) pool (integer pool keys for speed) -----------------
    c_index = {c: i for i, c in enumerate(countries)}
    c_idx = pd.Series(m_country).map(c_index).to_numpy()
    pool_key = mcc_idx * len(countries) + c_idx
    order = np.argsort(pool_key, kind="stable")
    bounds = np.flatnonzero(np.diff(pool_key[order])) + 1
    merch_idx = np.empty(n_main, dtype=np.int64)
    for grp in np.split(order, bounds):
        key = pool_key[grp[0]]
        idx, p = d.pools[(d.mcc_codes[key // len(countries)], countries[key % len(countries)])]
        merch_idx[grp] = rng.choice(idx, size=len(grp), p=p)

    # --- how -------------------------------------------------------------------------
    is_cnp = rng.random(n_main) < d.mcc_pcnp[mcc_idx]
    amount_usd = np.exp(np.log(d.mcc_median[mcc_idx]) + d.mcc_sigma[mcc_idx] * rng.standard_normal(n_main))
    # Holiday-season basket uplift for retail / e-commerce
    nov_dec = pd.DatetimeIndex(ts).month.isin([11, 12])
    amount_usd = np.where(nov_dec & np.isin(d.mcc_cat[mcc_idx], ["Retail", "E-commerce"]),
                          amount_usd * 1.12, amount_usd)

    # --- fraud --------------------------------------------------------------------------
    p_fraud = d.mcc_fraud[mcc_idx] * np.where(is_cnp, 4.0, 1.0) * np.where(is_xb, 2.5, 1.0)
    is_fraud = rng.random(n_main) < p_fraud
    amount_usd = np.where(is_fraud, amount_usd * 1.7, amount_usd)

    main = pd.DataFrame({
        "timestamp": ts,
        "card_idx": card_idx,
        "merch_idx": merch_idx,
        "mcc_idx": mcc_idx,
        "is_cnp": is_cnp,
        "is_xb": is_xb,
        "amount_usd": amount_usd,
        "is_fraud": is_fraud,
        "card_testing": False,
    })

    # --- planted scenario: card-testing (BIN enumeration) attack ---------------------------
    if n_ct:
        ct_ts = _sample_timestamps(rng, n_ct, cal, *CARD_TESTING_WINDOW)
        ct = pd.DataFrame({
            "timestamp": ct_ts,
            "card_idx": rng.integers(0, len(d.card_ids), n_ct),
            "merch_idx": rng.choice(d.ct_targets, n_ct),
            "is_cnp": True,
            "amount_usd": np.round(rng.uniform(0.5, 3.0, n_ct), 2),
            "is_fraud": True,
            "card_testing": True,
        })
        mcc_lookup = {m: i for i, m in enumerate(d.mcc_codes)}
        ct["mcc_idx"] = [mcc_lookup[d.merchants.mcc.iat[i]] for i in ct.merch_idx]
        ct["is_xb"] = d.card_home[ct.card_idx] != d.m_country[ct.merch_idx]
        main = pd.concat([main, ct], ignore_index=True)

    df = main
    n = len(df)
    ci, mi = df.card_idx.to_numpy(), df.merch_idx.to_numpy()
    df["card_id"] = d.card_ids[ci]
    df["issuer_id"] = d.card_issuer[ci]
    df["merchant_id"] = d.m_ids[mi]
    df["acquirer_id"] = d.m_acq[mi]
    m_country = d.m_country[mi]
    df["currency"] = pd.Series(m_country).map({c: v[2] for c, v in ref.COUNTRIES.items()}).to_numpy()
    card_type = d.card_type[ci]
    product = d.card_product[ci]
    cat = d.mcc_cat[df.mcc_idx.to_numpy()]
    is_cnp, is_xb, is_fraud = df.is_cnp.to_numpy(), df.is_xb.to_numpy(), df.is_fraud.to_numpy()

    # --- authorization decision ---------------------------------------------------------------
    rel_amount = df.amount_usd.to_numpy() / d.mcc_median[df.mcc_idx.to_numpy()]
    p_decline = (0.042 + 0.035 * is_cnp + 0.05 * is_xb + 0.02 * (card_type == "Debit")
                 + 0.03 * (rel_amount > 3) + d.iss_bias.reindex(df.issuer_id).to_numpy()
                 + d.iss_cnp_bias.reindex(df.issuer_id).to_numpy() * is_cnp)
    p_decline = np.clip(p_decline, 0.01, 0.6)
    p_decline = np.where(is_fraud, 0.45, p_decline)
    p_decline = np.where(df.card_testing, 0.82, p_decline)
    declined = rng.random(n) < p_decline

    codes = np.full(n, "00", dtype=object)
    # non-fraud declines by channel mix
    for channel_mask, mix in ((~is_cnp, ref.DECLINE_MIX_CP), (is_cnp, ref.DECLINE_MIX_CNP)):
        mask = declined & ~is_fraud & channel_mask
        k_codes, k_p = list(mix), np.array(list(mix.values()))
        codes[mask] = rng.choice(k_codes, size=int(mask.sum()), p=k_p / k_p.sum())
    # cross-border declines lean towards "not permitted" / "do not honor"
    xb_shift = declined & ~is_fraud & is_xb & (rng.random(n) < 0.25)
    codes[xb_shift] = rng.choice(["57", "05"], size=int(xb_shift.sum()))
    # the aggressive-CNP issuer's extra declines surface as generic "do not honor"
    agg = declined & ~is_fraud & is_cnp & (df.issuer_id.to_numpy() == AGGRESSIVE_CNP_ISSUER) & (rng.random(n) < 0.6)
    codes[agg] = "05"
    # fraud declines (issuer risk engine caught it)
    mask = declined & is_fraud
    codes[mask] = rng.choice(["59", "05", "14", "54"], size=int(mask.sum()), p=[0.5, 0.3, 0.12, 0.08])
    mask = declined & df.card_testing.to_numpy()
    codes[mask] = rng.choice(["14", "54", "05", "59"], size=int(mask.sum()), p=[0.4, 0.25, 0.2, 0.15])
    # planted issuer outage -> "issuer unavailable"
    t = df.timestamp
    outage = ((df.issuer_id == OUTAGE_ISSUER) & (t >= OUTAGE_WINDOW[0]) & (t < OUTAGE_WINDOW[1])).to_numpy()
    codes[outage & (rng.random(n) < 0.75)] = "91"
    df["auth_response_code"] = codes
    approved = codes == "00"
    df["is_approved"] = approved
    df["decline_reason"] = pd.Series(codes).map({k: v[1] for k, v in ref.AUTH_CODES.items()}).to_numpy()

    # --- chargebacks ------------------------------------------------------------------------------
    p_cb = d.mcc_pcb[df.mcc_idx.to_numpy()] * np.where(d.m_high_cb[mi], 12.0, 1.0)
    p_cb = np.where(is_fraud, 0.72, p_cb)
    df["is_chargeback"] = approved & (rng.random(n) < p_cb)

    # --- interchange (issuer revenue, approved only; computed in USD then converted) ---------
    rate = np.array([ref.CREDIT_INTERCHANGE[c][0] for c in cat])
    fixed = np.array([ref.CREDIT_INTERCHANGE[c][1] for c in cat])
    rate = rate + pd.Series(product).map(ref.PRODUCT_UPLIFT).fillna(0).to_numpy()
    rate = rate + ref.CNP_UPLIFT * is_cnp + ref.CROSS_BORDER_UPLIFT * is_xb
    regulated = d.iss_regulated.reindex(df.issuer_id).to_numpy().astype(bool)
    debit = card_type == "Debit"
    rate = np.where(debit & regulated & ~is_xb, ref.REGULATED_DEBIT[0], np.where(debit, ref.EXEMPT_DEBIT[0], rate))
    fixed = np.where(debit & regulated & ~is_xb, ref.REGULATED_DEBIT[1], np.where(debit, ref.EXEMPT_DEBIT[1], fixed))
    fee_usd = np.where(approved, df.amount_usd.to_numpy() * rate + fixed, 0.0)

    fx = df.currency.map(ref.FX_TO_USD).to_numpy()
    decimals = df.currency.map(ref.CURRENCY_DECIMALS).fillna(2).to_numpy()
    amount_local = df.amount_usd.to_numpy() / fx
    fee_local = fee_usd / fx
    jpy = decimals == 0
    df["amount"] = np.where(jpy, np.round(amount_local, 0), np.round(amount_local, 2))
    df["interchange_fee"] = np.where(jpy, np.round(fee_local, 0), np.round(fee_local, 4))

    df["channel"] = np.where(is_cnp, "card_not_present", "card_present")
    df["is_cross_border"] = is_xb
    df["is_fraud"] = is_fraud

    # --- ingestion metadata: network switch -> data platform latency ---------------------------
    latency = np.maximum(1, rng.exponential(90, n)).astype(np.int64)
    df["_loaded_at"] = df.timestamp + pd.to_timedelta(latency, unit="s")

    df = df.sort_values("timestamp", kind="stable").reset_index(drop=True)
    df["transaction_id"] = _ids("TX", np.arange(id_offset + 1, id_offset + n + 1), 10)
    cols = ["transaction_id", "timestamp", "card_id", "merchant_id", "issuer_id", "acquirer_id",
            "amount", "currency", "channel", "is_cross_border", "auth_response_code", "is_approved",
            "decline_reason", "interchange_fee", "is_fraud", "is_chargeback", "_loaded_at"]
    return df[cols]


# ---------------------------------------------------------------------------
# IO
# ---------------------------------------------------------------------------
def _public(df: pd.DataFrame) -> pd.DataFrame:
    return df[[c for c in df.columns if not c.startswith("_")]]


TXN_SCHEMA = pa.schema([
    ("transaction_id", pa.string()), ("timestamp", pa.timestamp("us")), ("card_id", pa.string()),
    ("merchant_id", pa.string()), ("issuer_id", pa.string()), ("acquirer_id", pa.string()),
    ("amount", pa.float64()), ("currency", pa.string()), ("channel", pa.string()),
    ("is_cross_border", pa.bool_()), ("auth_response_code", pa.string()), ("is_approved", pa.bool_()),
    ("decline_reason", pa.string()), ("interchange_fee", pa.float64()), ("is_fraud", pa.bool_()),
    ("is_chargeback", pa.bool_()), ("_loaded_at", pa.timestamp("us")),
])


def write_parquet(df: pd.DataFrame, path: Path, schema: pa.Schema | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df, schema=schema, preserve_index=False)
    pq.write_table(table, path, compression="zstd", coerce_timestamps="us", allow_truncated_timestamps=True)


def run(cfg: GeneratorConfig) -> dict:
    t0 = time.time()
    out = Path(cfg.out_dir)
    rng = np.random.default_rng(cfg.seed)
    issuers = build_issuers(rng, cfg.n_issuers)
    acquirers = build_acquirers(rng)
    merchants = build_merchants(rng, cfg.n_merchants, acquirers)
    cardholders = build_cardholders(rng, cfg.n_cardholders, issuers)
    cal = build_calendar(cfg)
    dims = _Dims(issuers, merchants, cardholders, cal)

    answer_key = []
    merchants_out = _public(merchants).copy()
    if cfg.inject_dq:
        merchants_out, keys = inject_merchant_issues(np.random.default_rng(cfg.seed + 1), merchants_out)
        answer_key.extend(keys)

    txn_dir = out / "transactions"
    if txn_dir.exists():
        for f in txn_dir.glob("*.parquet"):
            f.unlink()
    n_chunks = int(np.ceil(cfg.n_transactions / cfg.chunk_size))
    total_rows, offset = 0, 0
    for i in range(n_chunks):
        n = min(cfg.chunk_size, cfg.n_transactions - i * cfg.chunk_size)
        crng = np.random.default_rng([cfg.seed, i])  # independent, reproducible stream per chunk
        chunk = generate_chunk(crng, n, dims, offset)
        offset += n
        if cfg.inject_dq:
            chunk, keys = inject_transaction_issues(crng, chunk, dims)
            answer_key.extend(keys)
        write_parquet(chunk, txn_dir / f"part-{i:05d}.parquet", TXN_SCHEMA)
        total_rows += len(chunk)
        print(f"  chunk {i + 1}/{n_chunks}: {len(chunk):,} rows ({time.time() - t0:,.0f}s)", flush=True)

    write_parquet(merchants_out, out / "merchants.parquet")
    write_parquet(_public(cardholders), out / "cardholders.parquet")
    write_parquet(_public(issuers), out / "issuers.parquet")
    write_parquet(acquirers, out / "acquirers.parquet")
    ak = pd.DataFrame(answer_key, columns=["table_name", "record_key", "issue_type", "dq_dimension",
                                           "column_name", "original_value", "injected_value"])
    Path(cfg.answer_key_path).parent.mkdir(parents=True, exist_ok=True)
    ak.to_csv(cfg.answer_key_path, index=False)

    manifest = {
        "config": asdict(cfg),
        "row_counts": {"transactions": total_rows, "merchants": len(merchants_out),
                       "cardholders": len(cardholders), "issuers": len(issuers), "acquirers": len(acquirers)},
        "injected_issues": int(len(ak)),
        "injected_issues_by_type": ak.issue_type.value_counts().to_dict(),
        "elapsed_seconds": round(time.time() - t0, 1),
        "synthetic": True,
    }
    (out / "_manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    return manifest


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--rows", type=int, default=2_000_000, help="number of transactions (before duplicates)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--chunk-size", type=int, default=2_000_000)
    p.add_argument("--cardholders", type=int, default=150_000)
    p.add_argument("--merchants", type=int, default=20_000)
    p.add_argument("--out", default="data/raw")
    p.add_argument("--answer-key", default=None, help="default: data/dq_answer_key.csv (or <out>/dq_answer_key.csv)")
    p.add_argument("--no-dq", action="store_true", help="generate clean data without injected issues")
    a = p.parse_args()
    answer_key = a.answer_key or ("data/dq_answer_key.csv" if a.out == "data/raw" else f"{a.out}/dq_answer_key.csv")
    cfg = GeneratorConfig(n_transactions=a.rows, seed=a.seed, chunk_size=a.chunk_size,
                          n_cardholders=a.cardholders, n_merchants=a.merchants, out_dir=a.out,
                          answer_key_path=answer_key, inject_dq=not a.no_dq)
    print(f"Generating {cfg.n_transactions:,} synthetic transactions -> {cfg.out_dir}")
    m = run(cfg)
    print(json.dumps({k: m[k] for k in ("row_counts", "injected_issues", "injected_issues_by_type",
                                        "elapsed_seconds")}, indent=2))


if __name__ == "__main__":
    main()
