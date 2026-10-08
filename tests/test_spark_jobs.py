"""PySpark jobs must reproduce the DuckDB analysis SQL exactly (2M-row exports)."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[1]
EXPORTS = ROOT / "data/exports"
pytestmark = pytest.mark.skipif(not (EXPORTS / "fct_transactions_by_month").exists(),
                                reason="exports missing (run scripts/export_marts.py --partitioned-fact)")


@pytest.fixture(scope="module")
def spark():
    from spark.jobs import build_spark
    s = build_spark(app_name="pytest", shuffle_partitions=8, driver_memory="2g")
    s.sparkContext.setLogLevel("ERROR")
    yield s
    s.stop()


@pytest.mark.parametrize("job", ["issuer_ranking", "chargeback_anomaly", "card_testing"])
def test_spark_matches_duckdb(spark, job):
    from spark.jobs import JOBS
    from spark.reconcile import compare, sql_statement
    fn, dim, file, idx, keys = JOBS[job]
    con = duckdb.connect(str(ROOT / "warehouse/payments.duckdb"), read_only=True)
    duck = con.sql(sql_statement(file, idx)).df()
    fct = spark.read.parquet(str(EXPORTS / "fct_transactions_by_month"))
    out = fn(fct, spark.read.parquet(str(EXPORTS / f"{dim}.parquet"))).toPandas()
    result = compare(duck, out, keys)
    assert result["matched"], result
    assert result["rows_duckdb"] > 0
