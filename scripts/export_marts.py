"""Export marts and DQ tables from DuckDB to Parquet for Power BI and Spark.

Output: data/exports/<table>.parquet (fct_transactions is also written partitioned by month for Spark).
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
TABLES = ["marts.fct_transactions", "marts.dim_date", "marts.dim_merchant", "marts.dim_issuer", "marts.dim_card",
          "marts.dim_acquirer", "marts.agg_daily_network_metrics", "marts.agg_mcc_metrics",
          "dq.dq_results", "dq.dq_daily_partition_metrics", "dq.dq_transaction_quarantine"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / "warehouse/payments.duckdb"))
    ap.add_argument("--out", default=str(ROOT / "data/exports"))
    ap.add_argument("--partitioned-fact", action="store_true", help="also write fct_transactions partitioned by month")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(a.db, read_only=True)
    for t in TABLES:
        name = t.split(".")[1]
        con.sql(f"copy (select * from {t}) to '{out / name}.parquet' (format parquet, compression zstd)")
        print(f"exported {t:<38} -> {out / name}.parquet")
    if a.partitioned_fact:
        part = out / "fct_transactions_by_month"
        shutil.rmtree(part, ignore_errors=True)
        con.sql(f"""copy (select *, strftime(transaction_date, '%Y-%m') as txn_month from marts.fct_transactions)
                    to '{part}' (format parquet, partition_by (txn_month), compression zstd)""")
        print(f"exported marts.fct_transactions (partitioned by month) -> {part}")


if __name__ == "__main__":
    main()
