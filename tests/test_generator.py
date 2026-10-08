"""Tests for the synthetic data generator (run on a small sample for speed)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from generator.generate import GeneratorConfig, run

N = 200_000


def _gen(tmp: Path, seed: int = 7, **kw) -> Path:
    cfg = GeneratorConfig(n_transactions=N, n_cardholders=20_000, n_merchants=4_000, seed=seed,
                          out_dir=str(tmp / "raw"), answer_key_path=str(tmp / "ak.csv"), **kw)
    run(cfg)
    return tmp


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    tmp = _gen(tmp_path_factory.mktemp("gen"))
    con = duckdb.connect()
    con.sql(f"create view t as select * from read_parquet('{tmp}/raw/transactions/*.parquet')")
    con.sql(f"create view m as select * from read_parquet('{tmp}/raw/merchants.parquet')")
    con.sql(f"create view ak as select * from read_csv('{tmp}/ak.csv', all_varchar=true)")
    return tmp, con


def _digest(path: Path) -> str:
    df = pd.read_parquet(path)
    return hashlib.sha256(pd.util.hash_pandas_object(df, index=False).values.tobytes()).hexdigest()


def test_reproducible_with_same_seed(tmp_path, data):
    tmp, _ = data
    other = _gen(tmp_path)
    for f in ["transactions/part-00000.parquet", "merchants.parquet", "cardholders.parquet"]:
        assert _digest(tmp / "raw" / f) == _digest(other / "raw" / f), f
    assert (tmp / "ak.csv").read_bytes() == (other / "ak.csv").read_bytes()


def test_different_seed_changes_data(tmp_path, data):
    tmp, _ = data
    other = _gen(tmp_path, seed=8)
    assert _digest(tmp / "raw/transactions/part-00000.parquet") != _digest(other / "raw/transactions/part-00000.parquet")


def test_row_count_and_injection_rate(data):
    _, con = data
    n = con.sql("select count(*) from t").fetchone()[0]
    assert N <= n <= N * 1.003  # + exact-replay duplicates
    txn_issues = con.sql("select count(*) from ak where table_name='transactions'").fetchone()[0]
    assert 0.018 <= txn_issues / N <= 0.024


def test_all_seven_issue_types_present(data):
    _, con = data
    types = {r[0] for r in con.sql("select distinct issue_type from ak").fetchall()}
    assert types == {"null_value", "duplicate_transaction_id", "future_timestamp", "negative_amount",
                     "invalid_mcc", "orphan_foreign_key", "currency_format"}


def test_answer_key_matches_data(data):
    _, con = data
    # negative amounts really are negative
    bad = con.sql("""select count(*) from ak join t on ak.record_key = t.transaction_id
                     where issue_type='negative_amount' and t.amount >= 0""").fetchone()[0]
    assert bad == 0
    # duplicated ids really appear more than once
    bad = con.sql("""select count(*) from (select distinct record_key from ak where issue_type='duplicate_transaction_id') d
                     where (select count(*) from t where t.transaction_id = d.record_key) < 2""").fetchone()[0]
    assert bad == 0
    # injected nulls are null
    bad = con.sql("""select count(*) from ak join t on ak.record_key=t.transaction_id
                     where issue_type='null_value' and column_name='amount' and t.amount is not null""").fetchone()[0]
    assert bad == 0
    # orphan merchants do not exist in merchants
    bad = con.sql("""select count(*) from ak join t on ak.record_key=t.transaction_id
                     where issue_type='orphan_foreign_key' and column_name='merchant_id'
                     and t.merchant_id in (select merchant_id from m)""").fetchone()[0]
    assert bad == 0
    # defects are disjoint: no transaction carries two injected issues
    dupes = con.sql("""select count(*) from (select record_key from ak where table_name='transactions'
                       group by 1 having count(*) > 1)""").fetchone()[0]
    assert dupes == 0


def test_business_rules(data):
    _, con = data
    clean = "select * from t where amount > 0 and channel is not null and timestamp < '2026-01-01'"
    r = con.sql(f"""select avg(case when channel='card_not_present' then is_fraud::int end) cnp,
                           avg(case when channel='card_present' then is_fraud::int end) cp,
                           avg(case when is_cross_border then is_fraud::int end) xb,
                           avg(case when not is_cross_border then is_fraud::int end) dom
                    from ({clean})""").fetchone()
    assert r[0] > 3 * r[1], "CNP fraud rate should be well above card-present"
    assert r[2] > 1.5 * r[3], "cross-border fraud rate should be above domestic"
    top = con.sql(f"""select decline_reason from ({clean}) where not is_approved and decline_reason is not null
                      group by 1 order by count(*) desc limit 1""").fetchone()[0]
    assert top == "Insufficient Funds"
    wk = con.sql(f"""select avg(case when isodow(timestamp) >= 6 then c end) / avg(case when isodow(timestamp) < 6 then c end)
                     from (select timestamp::date as timestamp, count(*) c from ({clean}) group by 1)""").fetchone()[0]
    assert wk > 1.05, "weekend daily volume should exceed weekday"
    med = dict(con.sql(f"""select m.mcc, median(amount) from ({clean}) t join m using (merchant_id)
                          where currency='USD' group by 1""").fetchall())
    assert med["4511"] > 5 * med["5411"] > 5 * med["5815"] * 0.5  # airlines >> grocery >> digital media
    assert 0.85 < con.sql(f"select avg(is_approved::int) from ({clean})").fetchone()[0] < 0.97


def test_approval_flag_consistent_with_response_code(data):
    _, con = data
    bad = con.sql("""select count(*) from t where auth_response_code is not null
                     and is_approved <> (auth_response_code = '00')""").fetchone()[0]
    assert bad == 0
