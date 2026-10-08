# PySpark Notes: Scale Test, Reconciliation and When to Use Spark

All data is synthetic. Every number here comes from `spark/results/*.json`, produced by
`spark/reconcile.py` and `spark/experiments.py` on a single laptop:
macOS, 8 CPU cores, 8 GB RAM, Python 3.11, Spark 3.5.3 (`local[*]`, driver 4 GB), DuckDB 1.1.3, Java 17.

## 1. What was done

1. **Scaled the generator to 50M rows.** `python -m generator.generate --rows 50000000 --out data/raw_50m`
   generates 25 chunks of 2M rows, each with its own reproducible RNG stream. Result: 50.1M raw
   records, 1.2 GB of Parquet, 1.04M injected DQ defects, **274 s**.
2. **Built the 50M warehouse** with the same dbt project (`scripts/run_50m.sh`, separate DuckDB file):
   **477 s** for 112 nodes. The heaviest step is `int_transactions__dq_flagged` (369 s: four joins,
   window functions and an MD5 content hash over 50M rows). The result is 49.2M trusted fact rows.
3. **Rewrote the three heaviest Stage-4 analyses in PySpark** (`spark/jobs.py`). Each mirrors the
   SQL exactly (same filters, window frames and rounding):

   | Spark function | SQL source | Why it is "heavy" |
   |---|---|---|
   | `issuer_ranking` | `analysis/04_issuer_performance_ranking.sql` (A) | full-fact aggregation with 7 conditional measures, then 4 ranking windows |
   | `chargeback_anomaly` | `analysis/05_chargeback_anomaly_detection.sql` (A) | high-cardinality group-by (20k merchants) plus a per-MCC peer window (two shuffles) |
   | `card_testing` | `analysis/06_cnp_risk_analysis.sql` (A) | filtered aggregation plus a rolling 28-day exact median per acquirer |

4. **Reconciled** each Spark result against DuckDB row by row: identical keys and row counts,
   exact match for integers, strings and dates, and floats within one unit of the SQL's rounding
   precision. **All values matched exactly** (max absolute difference 0.0) at both 2M and 50M.
   `tests/test_spark_jobs.py` repeats the check on every run of the test suite.

## 2. Results

| Job | Scale | Rows out | DuckDB (warm) | Spark cold | Spark warm | Reconciled |
|---|---|---|---|---|---|---|
| issuer_ranking | 2.0M | 45 | 0.05 s | 3.57 s | 0.81 s | yes, exact |
| chargeback_anomaly | 2.0M | 47 | 0.10 s | 1.19 s | 0.67 s | yes, exact |
| card_testing | 2.0M | 3 | 0.04 s | 1.22 s | 0.63 s | yes, exact |
| issuer_ranking | 49.2M | 45 | 0.91 s | 5.99 s | 4.32 s | yes, exact |
| chargeback_anomaly | 49.2M | 348 | 1.59 s | 4.93 s | 3.75 s | yes, exact |
| card_testing | 49.2M | 3 | 0.41 s | 2.77 s | 1.53 s | yes, exact |

*Cold = first action in the session (JVM warm-up, file listing). DuckDB reads its native table;
Spark reads the month-partitioned Parquet export (12 files, 1.8 GB).*

**Reading the numbers honestly:** on one machine, DuckDB beats Spark local mode on every job.
That is expected, not a failure. DuckDB was **7-16x faster at 2M and 2-5x faster at 49M**:

- DuckDB is a single-process, vectorized engine with no task scheduling, serialization or JVM overhead.
- Spark pays a fixed cost per stage (task launch, shuffle files, Python-JVM round-trip for `toPandas`).
- Spark scaled **sub-linearly**: 25x more data took only 2.4-5.6x more time (warm), because fixed
  overhead dominates at 2M. DuckDB scaled 10-18x for the same 25x.
- Spark's advantage starts when data **no longer fits one machine** (TBs), when the work must
  scale *out* across a cluster, or when the job is not SQL-shaped at all.

## 3. Experiments: partitioning, shuffle, lazy evaluation

From `spark/experiments.py` on the 49.2M-row fact (`spark/results/experiments_50m.json`):

### Partition pruning: the biggest win

| Query: September approved volume | Time |
|---|---|
| `where txn_month = '2025-09'` (partition column) | **0.29 s** |
| `where date_format(transaction_date, 'yyyy-MM') = '2025-09'` | 3.87 s |

The export is written with `partition_by (txn_month)`, so the files are laid out as
`fct_transactions_by_month/txn_month=2025-09/...`. A filter on the **partition column** lets Spark
skip 11 of 12 directories before reading anything (the plan shows `PartitionFilters`). A filter on
an *expression* of another column reads every file. Lesson: **partition on the column people filter
by, and filter on that column as-is.** This is the same idea as Snowflake clustering on
`transaction_date` (DECISIONS.md D-22).

The physical plan for `card_testing` (`spark/results/plan_card_testing_50m.txt`) also shows:

- **Predicate pushdown**: `PushedFilters: [EqualTo(channel,card_not_present)]`. The filter is applied inside the Parquet reader using row-group statistics.
- **Column pruning**: `ReadSchema` contains only the 6 columns the job uses, out of 32. Columnar formats only pay for the columns you touch.
- **Broadcast join**: `BroadcastExchange` for the 15-row acquirer dimension, so the large side is never shuffled for the join.

### Lazy evaluation

| Step | Time |
|---|---|
| Build the `card_testing` DataFrame (filter -> groupBy -> join -> window -> filter) | 0.14 s |
| Execute it (`toPandas()`) | 2.66 s |

Transformations only build a logical plan. Nothing is read until an **action** (`count`, `collect`,
`toPandas`, `write`). Before running, the optimizer (Catalyst) rewrites the whole plan: pushing
filters into the scan, pruning columns, choosing broadcast vs. sort-merge joins. Practical
consequences:

- errors in transformation logic surface only at the action;
- calling an action twice recomputes everything unless you `cache()`;
- `explain()` is the way to see what will actually run.

### Shuffle tuning (median of 3 runs, `chargeback_anomaly`)

| `spark.sql.shuffle.partitions` | AQE | Median | Runs |
|---|---|---|---|
| 200 (default) | off | 5.28 s | 4.95 / 5.28 / 6.52 |
| 200 | on | 7.35 s | 6.24 / 7.35 / 7.54 |
| 16 | on | 6.52 s | 4.39 / 6.52 / 9.44 |
| 8 | off | 4.33 s | 4.23 / 4.33 / 5.56 |

**The differences are within run-to-run noise on a laptop**, and an earlier single-run attempt
ranked the configs differently. Why tuning barely matters here: a **shuffle** redistributes rows
across partitions by key. It happens at `groupBy("merchant_id")` and at the peer window
`partitionBy("mcc")`. Spark aggregates partially *before* the shuffle (map-side combine), so only
about 20k merchant rows per input partition cross the shuffle, not 49M. The job is dominated by
the Parquet scan. Shuffle partition count matters when **large** data is shuffled (joins of two big
tables, high-cardinality distinct counts): too few partitions cause spills and OOM, too many cause
thousands of tiny tasks. **AQE** (Adaptive Query Execution) addresses this at runtime by coalescing
small partitions and splitting skewed ones. The project defaults to 16 partitions with AQE on,
a sensible local setting, but the honest result is "no measurable difference at this shuffle size".

### Caching

| Two aggregations on the CNP subset | Run 1 | Run 2 |
|---|---|---|
| no cache | 7.07 s | 2.64 s |
| cached (after materialization) | 4.20 s | 3.73 s |

Inconclusive, and a useful lesson: the cached input is a **cheap columnar scan with a pushed-down
filter**, so recomputing it is nearly as fast as reading 20M cached rows from memory, and caching
competes for the 4 GB driver heap. Cache when the reused DataFrame is **expensive** to recompute
(after joins or shuffles) and is used several times.

## 4. Spark vs. the warehouse: when to use which

| Use a cloud warehouse (Snowflake / DuckDB / BigQuery) + dbt when... | Use Spark when... |
|---|---|
| The work is SQL-shaped: joins, aggregates, windows, star schemas | Data volume or compute exceeds one warehouse cost-effectively (multi-TB, heavy UDFs) |
| Analysts and BI tools consume the result | Logic is not SQL-friendly: complex Python/Scala, iterative algorithms, graph processing |
| You want governance, access control, time travel and zero ops | Streaming (Structured Streaming) or very low-latency micro-batches on a lakehouse |
| Concurrency of many small interactive queries | ML feature engineering and training at scale (MLlib, pandas UDFs, Spark + Delta/Iceberg) |
| Data fits a single node: DuckDB on a laptop handled 50M rows in seconds | You already own a data lake (Parquet / Delta / Iceberg on object storage) and want open formats with no load step |

For a card network, a typical split is:

- **Warehouse (Snowflake + dbt):** authorization star schema, KPI marts, DQ controls, BI.
  That is everything in this repo.
- **Spark (Databricks / EMR):** raw switch logs at full network scale (billions of messages per
  day), feature pipelines for real-time fraud models, backfills over years of history.
- **Snowpark** narrows the gap. It offers the DataFrame API inside Snowflake, so Spark-style code
  can run where the data already lives.

## 5. How to reproduce

```bash
make spark        # 2M: export marts, run the 3 jobs in both engines, reconcile
make spark-50m    # 50M: generate -> dbt build -> export -> reconcile (about 15-20 min on this laptop)
.venv/bin/python spark/experiments.py --exports data/exports_50m --label 50m
```

Timings vary between runs by roughly ±30% on a laptop (thermal throttling, background processes,
OS file cache). Treat the *ratios* and the *direction* of each effect as the result, not the exact seconds.
