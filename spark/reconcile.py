"""Run the three heavy aggregations in DuckDB and PySpark, time both, and reconcile row by row.

DuckDB executes the original analysis SQL against the warehouse; Spark executes spark/jobs.py
against the Parquet export of the same fact table (data/exports/fct_transactions_by_month).

Reconciliation rules
  * identical row sets (same keys, same row count)
  * integers / strings / dates: exact match
  * floats: |diff| <= one unit of the rounding precision used in the SQL (e.g. 1e-4 for round(x, 4)),
    because both engines round independently and sum floats in different orders

Writes spark/results/benchmark_<label>.json. Exit code 1 on any mismatch.

Usage:
  python spark/reconcile.py --label 2m
  python spark/reconcile.py --label 50m --db warehouse/payments_50m.duckdb --exports data/exports_50m
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import sys
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from spark.jobs import JOBS, build_spark  # noqa: E402


def sql_statement(file: str, idx: int) -> str:
    sql = re.sub(r"--[^\n]*", "", (ROOT / "analysis" / file).read_text())
    return [s.strip() for s in sql.split(";") if s.strip()][idx]


def decimals(series: pd.Series) -> int:
    vals = series.dropna().astype(float)
    if vals.empty:
        return 6
    for d in range(0, 7):
        if np.allclose(vals, vals.round(d), atol=1e-9, rtol=0):
            return d
    return 6


def normalise(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    df = df.copy()
    for c in df.columns:
        if "date" in c:
            df[c] = pd.to_datetime(df[c]).dt.strftime("%Y-%m-%d")
        elif df[c].dtype == object and df[c].map(lambda v: hasattr(v, "as_tuple")).any():  # Decimal
            df[c] = df[c].astype(float)
    return df.sort_values(keys).reset_index(drop=True)


def compare(duck: pd.DataFrame, spark: pd.DataFrame, keys: list[str]) -> dict:
    d, s = normalise(duck, keys), normalise(spark[duck.columns], keys)
    out = {"rows_duckdb": len(d), "rows_spark": len(s), "columns": {}, "matched": True}
    if len(d) != len(s) or not d[keys].astype(str).equals(s[keys].astype(str)):
        out["matched"] = False
        out["error"] = "row sets differ"
        return out
    for c in d.columns:
        if c in keys:
            continue
        a, b = d[c], s[c]
        if pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b):
            a, b = a.astype(float), b.astype(float)
            tol = 10.0 ** -decimals(a) * 1.0001
            diff = (a - b).abs()
            both_nan = a.isna() & b.isna()
            ok = bool(((diff <= tol) | both_nan).all())
            out["columns"][c] = {"max_abs_diff": float(diff.max(skipna=True) or 0.0), "tolerance": tol,
                                 "exact_matches": int(((diff == 0) | both_nan).sum()), "ok": ok}
        else:
            ok = bool((a.astype(str) == b.astype(str)).all())
            out["columns"][c] = {"ok": ok}
        out["matched"] &= ok
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", default="2m")
    ap.add_argument("--db", default=str(ROOT / "warehouse/payments.duckdb"))
    ap.add_argument("--exports", default=str(ROOT / "data/exports"))
    ap.add_argument("--runs", type=int, default=2, help="timed runs per engine (first Spark run is 'cold')")
    ap.add_argument("--shuffle-partitions", type=int, default=16)
    a = ap.parse_args()

    con = duckdb.connect(a.db, read_only=True)
    fact_rows = con.sql("select count(*) from marts.fct_transactions").fetchone()[0]
    spark = build_spark(shuffle_partitions=a.shuffle_partitions)
    spark.sparkContext.setLogLevel("ERROR")
    exports = Path(a.exports)
    fct = spark.read.parquet(str(exports / "fct_transactions_by_month"))
    input_files = len(fct.inputFiles())

    report = {"label": a.label, "fact_rows": fact_rows, "spark_input_files": input_files,
              "spark_version": spark.version, "duckdb_version": duckdb.__version__,
              "machine": {"platform": platform.platform(), "cpu_count": os.cpu_count(),
                          "python": platform.python_version()},
              "spark_conf": {"master": "local[*]", "shuffle_partitions": a.shuffle_partitions,
                             "adaptive_enabled": True, "driver_memory": "4g"},
              "jobs": {}}
    all_ok = True
    for name, (fn, dim, file, idx, keys) in JOBS.items():
        sql = sql_statement(file, idx)
        duck_times, spark_times = [], []
        for _ in range(a.runs):
            t0 = time.perf_counter()
            duck_df = con.sql(sql).df()
            duck_times.append(time.perf_counter() - t0)
        dim_df = spark.read.parquet(str(exports / f"{dim}.parquet"))
        for _ in range(a.runs):
            spark.sparkContext.setJobDescription(name)
            t0 = time.perf_counter()
            spark_df = fn(fct, dim_df).toPandas()
            spark_times.append(time.perf_counter() - t0)
        if name == "card_testing":
            plan = fn(fct, dim_df)._jdf.queryExecution().explainString(
                spark._jvm.org.apache.spark.sql.execution.ExplainMode.fromString("formatted"))
            (ROOT / "spark/results" / f"plan_{name}_{a.label}.txt").write_text(plan)
        rec = compare(duck_df, spark_df, keys)
        all_ok &= rec["matched"]
        report["jobs"][name] = {
            "analysis_sql": f"analysis/{file} (statement {idx + 1})",
            "duckdb_seconds": [round(t, 3) for t in duck_times],
            "spark_seconds": [round(t, 3) for t in spark_times],
            "reconciliation": rec,
        }
        print(f"{name:<20} rows duck={rec['rows_duckdb']:<5} spark={rec['rows_spark']:<5} "
              f"match={'YES' if rec['matched'] else 'NO '}  duckdb={min(duck_times):6.2f}s  "
              f"spark cold={spark_times[0]:6.2f}s warm={min(spark_times[1:] or spark_times):6.2f}s")
        if not rec["matched"]:
            print(json.dumps(rec, indent=2, default=str))
    out = ROOT / "spark/results" / f"benchmark_{a.label}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    report["all_matched"] = all_ok
    out.write_text(json.dumps(report, indent=2, default=str))
    print(f"\nfact rows: {fact_rows:,}   all reconciled: {all_ok}   -> {out.relative_to(ROOT)}")
    spark.stop()
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
