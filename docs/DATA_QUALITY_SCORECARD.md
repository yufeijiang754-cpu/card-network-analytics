# Data Quality Scorecard

How data quality is measured, thresholded and acted on in this project. All data is synthetic.
The live numbers come from `dq.dq_results` (one row per test per run) and
`dq.dq_daily_partition_metrics` (row-level rule results per ingestion day). Both appear on the
Streamlit **Data Quality Monitor** page.

## 1. Core metric

For every check, on every run:

```
failed_rows = rows returned by the test query (failing records)
total_rows  = rows in the tested table at run time
pass_rate   = 1 - failed_rows / total_rows
```

For uniqueness checks, `failed_rows` counts **duplicated key values**, not duplicate rows.
Table-level checks such as recency return 0 or 1 failing row.

Each check produces two independent signals:

| Signal | Meaning | Where |
|---|---|---|
| `status` (dbt) | `pass` = 0 failing rows; `warn` / `fail` = at least 1 failing row, depending on severity | dbt output, `dq_results.status` |
| `threshold_status` | `WITHIN_THRESHOLD` when pass_rate >= the dimension threshold, else `BREACH` | `dq_results.threshold_status` |

A check can WARN yet stay WITHIN_THRESHOLD: defects exist but are within tolerance. That
calls for a ticket, not a page. A BREACH calls for action within the SLA below.

## 2. Dimensions, checks and thresholds

Thresholds are set in `dbt_project.yml` (`vars.dq_thresholds`). A single check can override
its dimension's threshold with `meta.dq_threshold`.

| Dimension | Question it answers | Checks (generic test -> columns) | Threshold (pass rate) |
|---|---|---|---|
| **Completeness** | Is every required value present? | `dq_not_null` on all critical transaction fields; conditional `dq_not_null` on `decline_reason` when `not is_approved`; PKs of all entities | **99.95%** |
| **Uniqueness** | Does each record exist once? | `dq_unique` on every primary key; `dq_unique_combination` on aggregate grains | **99.99%** |
| **Validity** | Are values well-formed and in the allowed domain? | `dq_matches_pattern` (currency `[A-Z]{3}`, MCC `[0-9]{4}`); `dq_in_reference_list` (currency, MCC, response code, country); `dq_accepted_values` (channel, card type); `dq_value_in_range` (amount >= 0, interchange >= 0, rates in [0,1]) | **99.90%** |
| **Timeliness** | Did data arrive on time, and are timestamps physically possible? | `dq_not_in_future` (event time <= ingestion time + 5 min grace); `dq_max_latency` (ingested within 24 h of the event); `dq_recency` (newest record < 36 h old at the as-of time) | **99.95%** |
| **Referential integrity** | Does every foreign key point to a real entity? | `dq_referential_integrity`: transaction -> card, merchant, issuer, acquirer; card -> issuer; merchant -> acquirer; mart FK `relationships` tests | **99.95%** |
| Consistency (supplementary) | Do related fields agree? | `dq_expression_is_true`: `is_approved = (auth_response_code = '00')`; debit cards have no credit limit | **99.99%** |

### Why these thresholds?

- **Uniqueness is the strictest** (99.99%). A duplicated authorization double-counts volume and
  can trigger a duplicate settlement. ID collisions also mean a real transaction was lost.
- **Validity is the loosest** (99.90%). Many validity defects can be repaired deterministically,
  such as currency `usd` -> `USD`, so their business impact after the DQ layer is lower.
- Completeness, timeliness and referential integrity sit at **99.95%**: 1 bad record in 2,000.
  On roughly 5,500 authorizations a day, that tolerates about 3 bad records daily before a breach.

## 3. Severity by layer

| Layer | dbt severity | Rationale |
|---|---|---|
| Raw sources (`raw.*`) | **warn** | Raw data is *expected* to contain defects. Tests measure them; the pipeline continues, and `int_transactions__dq_flagged` routes each record. |
| Intermediate, marts, DQ models, seeds | **error** | Trusted layers must be clean. Any failure stops the build so bad data never reaches BI. |

## 4. Record routing (what happens to a failing row)

Implemented in `int_transactions__dq_flagged.dq_status`:

| Issue | Route | Reason |
|---|---|---|
| Non-standard currency format (`usd`, ` USD `, `840`, `US$`) | **repaired** | Unique deterministic mapping via `reference.currencies` |
| Declined without decline reason | **repaired** | Derived from response code via `reference.auth_response_codes` |
| Exact replay duplicate | **dropped** (later copy) | Same content; keep the first arrival |
| ID collision (same id, different content) | **quarantined** (all copies) | Can't tell which record is genuine; escalate to switch engineering |
| Null critical field, negative amount, future timestamp, unknown currency, orphan FK, issuer mismatch | **quarantined** | Can't be fixed without guessing |
| Merchant with invalid MCC | **kept**, category `Unclassified` | Sales are real; the defect is in reference data |

Quarantined rows are in `dq.dq_transaction_quarantine`, each with `remediation_owner`.

## 5. Ownership and response

| Breach in | Owner | Response SLA | Typical action |
|---|---|---|---|
| Completeness / validity in `raw.transactions` | Upstream feed owner (network switch team) | 1 business day | Fix the mapping in the extract, then replay |
| Uniqueness (ID collision) | Network switch engineering | 4 hours | Check ID sequence or partitioning; reconcile with settlement files |
| Timeliness (late or future) | Data platform on-call | 4 hours | Check ingestion lag and terminal clock drift by acquirer |
| Referential integrity | Reference data team / partner onboarding | 1 business day | Backfill missing merchant / card / issuer master records |
| Invalid MCC | Merchant data stewardship -> acquirer | 5 business days | Request MCC correction from the acquirer |
| Any trusted-layer test failure | Analytics engineering | Before next BI refresh | Build is blocked until fixed |

## 6. Validation against ground truth

Because the data is synthetic, every injected defect is known (`data/dq_answer_key.csv`).
`dq/compare_answer_key.py` scores the tests against it and writes
`dq/reports/detection_report.md`.

Latest run on 2M rows:

| Metric | Value |
|---|---|
| Injected defects | 41,900 (7 issue types) |
| Recall (caught by the test designed for that defect) | **99.11%** |
| Precision (raw-layer tests) | **100%**: 0 records flagged outside the answer key |
| Misses | 374, all future timestamps 1-4 minutes ahead of ingestion, inside the 5-minute grace window (by design) |
| Trusted-layer tests | 44 / 44 pass |

**Coverage lesson:** the MCC *format* check catches only 201 of 300 invalid MCCs, because
`0000` and `1234` are well-formed. The *reference-list* check catches all 300. Format checks
and domain checks complement each other; neither is enough alone.

**Grace-window trade-off:** with 0 minutes of grace, recall on future timestamps is 100% (99.98% at 1 minute, 90.7% at 5 minutes). In
production, though, a tight window also flags legitimate terminals with drifting clocks. The
grace window is a business decision about acceptable false positives, documented in DECISIONS.md D-09.

## 7. How to run

```bash
make dq          # dbt build (tests log to dq.dq_results) + answer-key scoring
make dashboard   # Data Quality Monitor page
```

Useful queries:

```sql
-- latest run, breaches only
select model, dimension, check_name, failed_rows, pass_rate, threshold
from dq.dq_results
where run_id = (select run_id from dq.dq_results order by run_started_at desc limit 1)
  and threshold_status = 'BREACH'
order by pass_rate;

-- pass-rate trend by dimension per ingestion day
select load_date, dq_dimension, 1 - sum(failed_rows) * 1.0 / sum(total_rows) as pass_rate
from dq.dq_daily_partition_metrics
group by 1, 2 order by 1, 2;
```
