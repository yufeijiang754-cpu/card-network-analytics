"""Deliberate data-quality defect injection.

Each injected defect is recorded in an answer key so that the data-quality
checks built later (dbt tests) can be scored for recall/precision.

Design rules
- Every transaction row receives at most ONE defect (disjoint sampling), so a
  missed or extra detection can be attributed to exactly one cause.
- transaction_id itself is never nulled: it is the record locator used by the
  answer key. PK completeness is still *checked* by dbt tests, just not
  injected (see DECISIONS.md).
- Rates are fractions of the chunk's rows; together they total ~2.1%.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from generator import reference_data as ref

# issue_type -> (dq_dimension, {column: rate})
TXN_ISSUES = {
    "null_value": ("completeness", {
        "amount": 0.0015, "merchant_id": 0.0010, "card_id": 0.0010, "currency": 0.0006,
        "auth_response_code": 0.0006, "timestamp": 0.0005, "channel": 0.0004,
        "decline_reason": 0.0004,  # only on declined rows: conditionally required
    }),
    "duplicate_transaction_id": ("uniqueness", {"exact_replay": 0.0020, "id_collision": 0.0008}),
    "future_timestamp": ("timeliness", {"timestamp": 0.0020}),
    "negative_amount": ("validity", {"amount": 0.0020}),
    "currency_format": ("validity", {"currency": 0.0030}),
    "orphan_foreign_key": ("referential_integrity", {
        "merchant_id": 0.0025, "card_id": 0.0012, "issuer_id": 0.0008, "acquirer_id": 0.0005,
    }),
}
MERCHANT_INVALID_MCC_RATE = 0.015
# Share of future-timestamp defects that are only a few minutes ahead (terminal clock skew).
SMALL_SKEW_SHARE = 0.10


def _fmt(v) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)) or v is pd.NaT:
        return ""
    return str(v)


def inject_merchant_issues(rng: np.random.Generator, merchants: pd.DataFrame):
    m = merchants.copy()
    n_bad = int(round(len(m) * MERCHANT_INVALID_MCC_RATE))
    idx = rng.choice(m.index.to_numpy(), n_bad, replace=False)
    keys = []
    for i in idx:
        bad = rng.choice(ref.INVALID_MCC_VALUES)
        keys.append(("merchants", m.at[i, "merchant_id"], "invalid_mcc", "validity", "mcc", m.at[i, "mcc"], bad))
        m.at[i, "mcc"] = bad
    return m, keys


def inject_transaction_issues(rng: np.random.Generator, df: pd.DataFrame, dims):
    """Return (df_with_defects, answer_key_rows). df is sorted by timestamp, unique ids."""
    df = df.copy()
    n = len(df)
    keys: list[tuple] = []
    used = np.zeros(n, dtype=bool)

    def take(k: int, eligible: np.ndarray | None = None) -> np.ndarray:
        pool = np.flatnonzero(~used if eligible is None else (~used & eligible))
        chosen = rng.choice(pool, size=min(k, len(pool)), replace=False)
        used[chosen] = True
        return chosen

    def record(rows, issue, dim, col, orig, new):
        tids = df.transaction_id.to_numpy()[rows]
        keys.extend(("transactions", t, issue, dim, col, _fmt(o), _fmt(v)) for t, o, v in zip(tids, orig, new))

    # --- completeness: nulls ---------------------------------------------------------------
    dim, cols = TXN_ISSUES["null_value"]
    declined = ~df.is_approved.to_numpy()
    for col, rate in cols.items():
        rows = take(int(round(n * rate)), declined if col == "decline_reason" else None)
        orig = df[col].to_numpy()[rows]
        df.loc[rows, col] = None
        record(rows, "null_value", dim, col, orig, [None] * len(rows))

    # --- uniqueness: duplicated transaction_id ------------------------------------------------
    dim, cols = TXN_ISSUES["duplicate_transaction_id"]
    # (a) exact replay: same message ingested twice (e.g. file re-delivery), later _loaded_at
    rows = take(int(round(n * cols["exact_replay"])))
    replay = df.loc[rows].copy()
    replay["_loaded_at"] = replay["_loaded_at"] + pd.to_timedelta(rng.integers(300, 7200, len(rows)), unit="s")
    record(rows, "duplicate_transaction_id", dim, "transaction_id", df.transaction_id.to_numpy()[rows],
           ["exact_replay"] * len(rows))
    # (b) id collision: a *different* authorization re-uses an existing id (upstream sequence reset)
    k = int(round(n * cols["id_collision"]))
    src = take(k)
    victims = take(k)
    orig_victim_ids = df.transaction_id.to_numpy()[victims].copy()
    df.loc[victims, "transaction_id"] = df.transaction_id.to_numpy()[src]
    record(src, "duplicate_transaction_id", dim, "transaction_id", orig_victim_ids, ["id_collision"] * k)

    # --- timeliness: event timestamp later than ingestion time ----------------------------------
    dim, cols = TXN_ISSUES["future_timestamp"]
    rows = take(int(round(n * cols["timestamp"])))
    small = rng.random(len(rows)) < SMALL_SKEW_SHARE
    offset_s = np.where(small, rng.integers(60, 240, len(rows)),           # 1-4 min clock skew
                        rng.integers(3600, 500 * 86400, len(rows)))         # 1 hour .. 500 days
    orig = df.timestamp.to_numpy()[rows]
    new = df._loaded_at.to_numpy()[rows] + offset_s.astype("timedelta64[s]")
    df.loc[rows, "timestamp"] = new
    record(rows, "future_timestamp", dim, "timestamp", orig, pd.to_datetime(new))

    # --- validity: negative amounts -------------------------------------------------------------
    dim, cols = TXN_ISSUES["negative_amount"]
    rows = take(int(round(n * cols["amount"])), df.amount.notna().to_numpy())
    orig = df.amount.to_numpy()[rows]
    df.loc[rows, "amount"] = -np.abs(orig)
    record(rows, "negative_amount", dim, "amount", orig, -np.abs(orig))

    # --- validity: inconsistent currency formats --------------------------------------------------
    dim, cols = TXN_ISSUES["currency_format"]
    rows = take(int(round(n * cols["currency"])), df.currency.notna().to_numpy())
    orig = df.currency.to_numpy()[rows]
    styles = rng.choice(["lower", "padded", "mixed", "numeric", "symbol"], size=len(rows))
    new = []
    for c, s in zip(orig, styles):
        new.append({"lower": c.lower(), "padded": f" {c} ", "mixed": c.capitalize(),
                    "numeric": ref.CURRENCY_NUMERIC[c], "symbol": ref.CURRENCY_SYMBOL[c]}[s])
    df.loc[rows, "currency"] = new
    record(rows, "currency_format", dim, "currency", orig, new)

    # --- referential integrity: orphan foreign keys -------------------------------------------------
    dim, cols = TXN_ISSUES["orphan_foreign_key"]
    fake = {"merchant_id": ("M9", 5), "card_id": ("C9", 7), "issuer_id": ("ISS9", 2), "acquirer_id": ("ACQ9", 2)}
    for col, rate in cols.items():
        rows = take(int(round(n * rate)), df[col].notna().to_numpy())
        prefix, width = fake[col]
        new = np.char.add(prefix, np.char.zfill(rng.integers(0, 10 ** width, len(rows)).astype(str), width))
        orig = df[col].to_numpy()[rows]
        df.loc[rows, col] = new.astype(object)
        record(rows, "orphan_foreign_key", dim, col, orig, new)

    df = pd.concat([df, replay], ignore_index=True)
    return df, keys
