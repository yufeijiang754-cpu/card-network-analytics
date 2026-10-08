"""Controlled Spark experiments on the fact table, used for docs/SPARK_NOTES.md.

1. Lazy evaluation  - time to *define* a plan vs. time to *execute* it
2. Shuffle tuning   - spark.sql.shuffle.partitions 200 vs 16 vs 8, with AQE on/off (median of 3 runs)
3. Partition pruning - filter on the partition column (txn_month) vs. a derived date filter
4. Caching          - reuse a filtered CNP subset across two aggregations

Usage: python spark/experiments.py --exports data/exports_50m --label 50m
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pyspark.sql import SparkSession  # noqa: E402
from pyspark.sql import functions as F  # noqa: E402

from spark.jobs import chargeback_anomaly, card_testing  # noqa: E402


def timed(fn):
    t0 = time.perf_counter()
    out = fn()
    return out, round(time.perf_counter() - t0, 3)


def session(shuffle: int, aqe: bool) -> SparkSession:
    s = (SparkSession.builder.master("local[*]").appName("experiments")
         .config("spark.driver.memory", "4g")
         .config("spark.sql.shuffle.partitions", shuffle)
         .config("spark.sql.adaptive.enabled", str(aqe).lower())
         .config("spark.ui.showConsoleProgress", "false")
         .getOrCreate())
    s.sparkContext.setLogLevel("ERROR")
    return s


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exports", default=str(ROOT / "data/exports_50m"))
    ap.add_argument("--label", default="50m")
    a = ap.parse_args()
    ex = Path(a.exports)
    res: dict = {"label": a.label}

    # 2. shuffle tuning (fresh session per config, a warm-up run, then a timed run)
    shuffle = []
    for parts, aqe in [(200, False), (200, True), (16, True), (8, False)]:
        s = session(parts, aqe)
        fct = s.read.parquet(str(ex / "fct_transactions_by_month"))
        dim = s.read.parquet(str(ex / "dim_merchant.parquet"))
        chargeback_anomaly(fct, dim).count()  # warm-up (JIT, file listing)
        runs = sorted(timed(lambda: chargeback_anomaly(fct, dim).toPandas())[1] for _ in range(3))
        shuffle.append({"shuffle_partitions": parts, "aqe": aqe, "median_seconds": runs[1], "runs": runs})
        print("shuffle", shuffle[-1])
        s.stop()
    res["shuffle_tuning_chargeback_anomaly"] = shuffle

    s = session(16, True)
    fct = s.read.parquet(str(ex / "fct_transactions_by_month"))

    # 1. lazy evaluation
    acq = s.read.parquet(str(ex / "dim_acquirer.parquet"))
    plan, t_define = timed(lambda: card_testing(fct, acq))
    _, t_execute = timed(lambda: plan.toPandas())
    res["lazy_evaluation"] = {"define_plan_seconds": t_define, "execute_action_seconds": t_execute}
    print("lazy", res["lazy_evaluation"])

    # 3. partition pruning: September only
    _, t_pruned = timed(lambda: fct.where(F.col("txn_month") == "2025-09").agg(F.sum("approved_amount_usd")).collect())
    _, t_unpruned = timed(lambda: fct.where(F.date_format("transaction_date", "yyyy-MM") == "2025-09")
                          .agg(F.sum("approved_amount_usd")).collect())
    pruned_plan = fct.where(F.col("txn_month") == "2025-09")._jdf.queryExecution().executedPlan().toString()
    res["partition_pruning"] = {
        "filter_on_partition_column_seconds": t_pruned,
        "filter_on_derived_expression_seconds": t_unpruned,
        "partition_filter_in_plan": "PartitionFilters: [isnotnull(txn_month" in pruned_plan,
        "total_partitions": fct.select("txn_month").distinct().count(),
    }
    print("pruning", res["partition_pruning"])

    # 4. caching a reused subset
    def two_aggs(df):
        df.groupBy("mcc_category").agg(F.sum("fraud_loss_amount_usd")).collect()
        df.groupBy("acquirer_id").agg(F.count("*")).collect()

    cnp = fct.where(F.col("channel") == "card_not_present").select("mcc_category", "acquirer_id", "fraud_loss_amount_usd")
    _, t_nocache = timed(lambda: two_aggs(cnp))
    cached = cnp.cache()
    cached.count()  # materialise
    _, t_cache = timed(lambda: two_aggs(cached))
    cached.unpersist()
    res["caching_two_aggregations_on_cnp_subset"] = {"without_cache_seconds": t_nocache,
                                                     "with_cache_seconds_after_materialise": t_cache}
    print("cache", res["caching_two_aggregations_on_cnp_subset"])
    s.stop()
    out = ROOT / "spark/results" / f"experiments_{a.label}.json"
    out.write_text(json.dumps(res, indent=2))
    print("->", out.relative_to(ROOT))


if __name__ == "__main__":
    main()
