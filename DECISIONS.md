# Design Decisions Log

Assumptions and judgment calls made while building this project, with the
reasoning behind each. All data in this repository is **synthetic**.

## Stage 1 - Synthetic data generation

| ID | Decision | Rationale |
|----|----------|-----------|
| D-01 | Simulate **calendar year 2025** (UTC timestamps, no time-zone modelling). | One full year is enough to show seasonality, holidays, and month-over-month trends. Time-zone handling would add complexity without adding analytical value. |
| D-02 | Dimension sizes are fixed (45 issuers, 15 acquirers, 20k merchants, 150k cards) and **do not scale** with `--rows`. | Scaling only the fact table keeps the 2M and 50M datasets comparable and makes the Spark benchmark measure fact-table volume only. |
| D-03 | Generation is **chunked** (default 2M rows per chunk). Each chunk uses its own RNG stream, `default_rng([seed, chunk_idx])`. | Memory stays bounded on an 8 GB laptop when generating 50M rows, and each chunk is still reproducible. |
| D-04 | `amount` and `interchange_fee` are in **transaction (merchant) currency**. USD conversion happens in dbt using a static FX seed. | This mirrors real authorization messages, which carry the transaction currency. It also gives the currency-format DQ issue a real downstream effect, because FX joins fail on badly formatted currency codes. |
| D-05 | Added a `_loaded_at` ingestion-metadata column (event time + about 90 s average latency). | Timeliness needs a reference point. "Future timestamp" means **event time later than ingestion time**, which is physically impossible. That is more meaningful than comparing against wall-clock time for a historical dataset. |
| D-06 | Each transaction gets **at most one** injected defect. | Each detection or miss traces back to exactly one cause, so recall and precision per issue type are clean. |
| D-07 | `transaction_id` is never nulled. | It is the record locator for the answer key. Primary-key completeness is still tested in dbt. |
| D-08 | Two duplicate flavours: **exact replay** (same message re-delivered later) and **ID collision** (a different authorization reuses an id). | They need different remediations. Replays are safe to dedupe; collisions mean upstream ID generation is broken and data is lost, so they must be escalated. |
| D-09 | About 10% of future-timestamp defects are a small **1-4 minute clock skew**. | This is realistic (terminal clocks drift) and deliberately sits inside the timeliness check's 5-minute grace window. It produces explainable misses in the detection report. |
| D-10 | Invalid MCCs are injected into **merchants** (1.5% of merchants), not into transactions. | MCC is a merchant attribute assigned by the acquirer. The defect lives in reference data and spreads to every transaction at that merchant. |
| D-11 | `is_fraud` marks **all fraudulent attempts**, including ones the issuer declined. Fraud loss metrics use approved fraud only. | This lets the analysis separate fraud *attempt* rate (risk exposure) from fraud *loss* rate (what got through). |
| D-12 | Christmas Day volume is set **below** normal (x0.85), while all other holidays are above. | Most physical stores close on Dec 25. Holidays on average are still higher volume, as required. |
| D-13 | Interchange uses **illustrative** rates: category base + product uplift + CNP and cross-border uplifts, with the US Reg II (Durbin) cap for regulated debit (0.05% + $0.22). | Close enough to real published schedules to support a realistic "interchange revenue mix" analysis, and clearly labelled as not any network's actual rates. |
| D-14 | Planted business scenarios: (1) a **card-testing attack** on 6 digital-goods merchants of payment facilitator ACQ009, 18-20 Sep; (2) an **issuer outage** at ISS012 on 14 Jun, 14:00-17:00; (3) issuer ISS007 with **over-tuned CNP fraud rules**; (4) 25 **high-chargeback merchants**. | These give the analysis layer real signals to find, so the insights read like monitoring findings rather than restated generator parameters. They are documented here for transparency. |

## Stage 2 - Warehouse modelling (dbt)

| ID | Decision | Rationale |
|----|----------|-----------|
| D-15 | **dbt-duckdb** is the default target; **Snowflake** is a second target in the same `profiles.yml`. | Zero cost and one command to run locally, with a credible path to a cloud warehouse. Snowflake SQL was verified by compiling every model against dbt-snowflake (no connection) and parsing the output with sqlglot's Snowflake dialect. |
| D-16 | Raw data is declared once as dbt **sources**. On DuckDB, `meta.external_location` reads Parquet in place; on Snowflake the same source names resolve to `RAW` tables. | One set of models, two warehouses. No copy step is needed locally. |
| D-17 | Cross-database differences are isolated in `macros/cross_db.sql` via `adapter.dispatch` (regex, ISO day-of-week, integer sequence). | Keeps model SQL portable. Avoided third-party packages (dbt_utils) so the project builds offline. |
| D-18 | Custom `generate_schema_name`: schemas are named `staging`, `intermediate`, `marts`, `dq`, `dq_audit`, `reference` instead of `<target>_<custom>`. | Stable, readable schema names for BI connections and documentation on both warehouses. |
| D-19 | DQ policy is applied in **one** model, `int_transactions__dq_flagged`: one boolean flag per rule plus a routing decision (`valid` / `repaired` / `quarantined` / `duplicate_dropped`). | Separates detection from routing. Analysts can see exactly why a row was excluded, and the quarantine model becomes a work queue with a named remediation owner. |
| D-20 | **Repair vs quarantine**: non-standard currency formats and missing decline reasons are *repaired* (deterministic fix from reference data). Nulls in critical fields, negative amounts, future timestamps, orphans and id collisions are *quarantined*. Exact replays are *dropped*. | Only fix what can be fixed without guessing. Orphans are quarantined rather than mapped to an "unknown" member because, on a payment network, a transaction that cannot be attributed to a merchant or card cannot be settled or reported correctly. |
| D-21 | Merchants with an **invalid MCC are kept** as `Unclassified`. | The sales are real. Excluding them would understate volume. The defect is in reference data and is fixed by the merchant data steward. |
| D-22 | `fct_transactions` is **incremental** (delete+insert on `transaction_id`, filtered by `loaded_at`). On Snowflake it is clustered by `transaction_date`. | Mirrors how a production authorization fact is maintained. delete+insert is supported by both adapters. Clustering on date matches the dominant filter in BI queries. |
| D-23 | Extra marts beyond those requested: `dim_card` and `dim_acquirer`. | Needed for a complete star schema (card product and acquirer slicing in Power BI). |
| D-24 | Amounts are in **USD** in marts, using a static 2025 FX seed. | Cross-currency aggregation requires one reporting currency. A daily FX table would be the production choice. |
| D-25 | Business definitions use reusable dbt **doc blocks** (`models/_docs.md`) for metrics like approval rate, fraud loss bps, and interchange. `scripts/check_doc_coverage.py` fails the build if any column lacks a description. | Treats metadata as a governed, tested asset. Every metric has one definition reused across models. |

## Stage 3 - Data quality monitoring

| ID | Decision | Rationale |
|----|----------|-----------|
| D-26 | Custom generic tests (`dbt/tests/generic/dq_*.sql`) instead of the built-ins. Each declares `meta.dq_dimension` and returns the **record key** of each failing row. | Built-in `relationships` and `accepted_values` return only the bad value, not the record. Record keys make every failure traceable and scorable against the answer key. |
| D-27 | Tests on **raw sources warn**; tests on intermediate, marts, DQ models and seeds **error** (path-based `+severity` in `dbt_project.yml`). | Raw data is expected to be dirty; measuring it must not stop the pipeline. Trusted layers must be clean, so a failure blocks the build before BI sees bad data. |
| D-28 | `dq_results` is written by an **on-run-end hook** (`macros/dq_results.sql`) from dbt's `results` object, with total rows counted per tested relation. Plain ANSI DDL/DML. | Works for `dbt test` and `dbt build`, on DuckDB and Snowflake, with no external orchestrator. History accumulates across runs for trend analysis. |
| D-29 | Two signals per check: dbt `status` (any failure) and `threshold_status` (pass rate vs. per-dimension tolerance). | Mirrors real DQ operations: not every defect is an incident. Thresholds are vars, overridable per check with `meta.dq_threshold`. |
| D-30 | `store_failures: true` for all tests (schema `dq_audit`). | Failing rows are kept for drill-down in the dashboard and for answer-key scoring. |
| D-31 | Timeliness uses ingestion time as the reference: future events (5-minute grace), late arrival (24 h), and recency against a fixed `dq_as_of_ts` var. | The dataset is historical, so wall-clock comparisons would be meaningless. Leaving `dq_as_of_ts` unset in production uses `current_timestamp`. |
| D-32 | Detection is scored at **(record, issue type, column)** level, with recall per issue and precision per test, and every miss is explained automatically. | A detection rate is only useful if it is precise about *what* was detected and *why* something was missed. |
| D-33 | The MCC check uses both a format test and a reference-list test. | Shows that format validity (`[0-9]{4}`) is not domain validity: 99 of 300 invalid MCCs are well-formed. |

## Stage 4 - Business analysis

| ID | Decision | Rationale |
|----|----------|-----------|
| D-34 | Analysis SQL lives in `analysis/` as plain SQL against `marts.*`, run by `scripts/run_analysis.py`, which writes CSVs to `analysis/results/`. A file may contain several statements (parts A/B/C). | Analysts can read and run each query directly in any SQL client. Avoided `filter (where ...)` and other DuckDB-only syntax where an ANSI form exists, so the queries port to Snowflake with minimal change. |
| D-35 | The card-testing detector uses a **trailing 28-day median** baseline, not mean/stddev. | Tested both. Mean/stddev flagged only day 1 because the attack contaminated its own baseline; the median flags all three days. |
| D-36 | Chargeback alerting requires **rate >= 1% AND >= 5 disputes**, with HIGH when also 3+ sd above MCC peers. | A rate-only rule produced 235 mostly-noise alerts on small merchants. The dual threshold mirrors how network monitoring programs combine ratio and count. |
| D-37 | Generator tweaks made while validating the analysis: the outage issuer is a top-volume issuer, issuer name suffixes match issuer type, and high-chargeback merchants are planted on top-quartile-volume merchants. | The first version planted signals on merchants and issuers too small to be statistically visible (e.g. about 4 auths/hour for the outage issuer). Re-generation needs `dbt build --full-refresh` because `fct_transactions` is incremental on `loaded_at` (see D-22). `run_all.sh` always full-refreshes. |
| D-38 | `docs/INSIGHTS.md` openly states which patterns were planted. | Honesty about synthetic data. The portfolio value is the detection and quantification method, not the "discovery". |
