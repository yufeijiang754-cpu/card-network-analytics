# Power BI Build Guide

A step-by-step recipe for rebuilding the two Streamlit pages (**Network Performance** and
**Data Quality Monitor**) in Power BI Desktop on top of this project's star schema. Every DAX
measure is listed with its code and business meaning. All data is synthetic.

> Estimated time: 1.5-2 hours. Requires Power BI Desktop (free, Windows). On a Mac, use a
> Windows VM or Power BI Service with a Snowflake source.

---

## 1. Get the data

**Option A (local, recommended): Parquet exports**

```bash
./run_all.sh                         # or: make build
.venv/bin/python scripts/export_marts.py
```

This writes `data/exports/*.parquet`. In Power BI: **Get Data -> Parquet**, then load each of these:

| File | Role in model |
|---|---|
| `fct_transactions.parquet` | Fact (1.97M rows) |
| `dim_date.parquet` | Date dimension |
| `dim_merchant.parquet` | Merchant dimension (MCC, category, acquirer) |
| `dim_issuer.parquet` | Issuer dimension |
| `dim_card.parquet` | Card dimension |
| `dim_acquirer.parquet` | Acquirer dimension |
| `dq_results.parquet` | DQ test results per run (separate fact) |
| `dq_daily_partition_metrics.parquet` | DQ pass rate per ingestion day (separate fact) |
| `dq_transaction_quarantine.parquet` | Quarantine detail (drill-through) |

> To load several Parquet files at once, use **Get Data -> Folder** on `data/exports`, filter
> `Extension = .parquet`, and click **Combine**. Separate imports are simpler for a star schema, though.

**Option B: Snowflake (DirectQuery or Import)**

Get Data -> Snowflake -> Server `<account>.snowflakecomputing.com`, Warehouse `TRANSFORM_WH`.
Sign in with the `REPORTER` role, then select tables from `PAYMENTS_ANALYTICS.MARTS` and
`PAYMENTS_ANALYTICS.DQ`. Use **Import** for this data size. DirectQuery makes sense once the fact
table reaches hundreds of millions of rows.

### Power Query clean-up (Transform Data)

1. `fct_transactions`: set `transaction_date` to **Date**, `transaction_ts` to **Date/Time**, and the money columns to **Fixed decimal number**.
2. Remove columns the report doesn't need: `loaded_at`, `amount_local`, `interchange_fee_local`. Smaller model, faster refresh.
3. `dim_date`: set `date_day` to **Date**.
4. Rename the queries without prefixes if you like (`Transactions`, `Date`, ...). The DAX below uses the original names.

---

## 2. Star schema

```
                 dim_date (date_day)
                        │ 1
                        │
                        * transaction_date
 dim_merchant ──1───*  fct_transactions  *───1── dim_issuer
 (merchant_id)          * card_id         * acquirer_id
                        │                 │
                        1                 1
                    dim_card         dim_acquirer

 dq_results  (stand-alone fact, run grain)    dq_daily_partition_metrics (stand-alone, load_date)
```

**Model view -> Manage relationships**:

| From (many) | To (one) | Cardinality | Cross-filter |
|---|---|---|---|
| `fct_transactions[transaction_date]` | `dim_date[date_day]` | Many-to-one | Single |
| `fct_transactions[merchant_id]` | `dim_merchant[merchant_id]` | Many-to-one | Single |
| `fct_transactions[issuer_id]` | `dim_issuer[issuer_id]` | Many-to-one | Single |
| `fct_transactions[card_id]` | `dim_card[card_id]` | Many-to-one | Single |
| `fct_transactions[acquirer_id]` | `dim_acquirer[acquirer_id]` | Many-to-one | Single |

Then:

- Select `dim_date`, then **Table tools -> Mark as date table** using `date_day`. Time-intelligence DAX needs this.
- Leave `dim_card` -> `dim_issuer` **without** a relationship. A second path from the fact to the issuer would create ambiguity. The fact already carries `issuer_id`.
- Hide all foreign-key columns in the fact (right-click -> Hide in report view). Users should slice by the dimensions.
- Sort `dim_date[day_name]` by `iso_day_of_week` (Column tools -> Sort by column).
- Create an empty table **`_Measures`** (Home -> Enter data -> OK) to hold all measures, then delete its dummy column.

Why a star schema? Filters propagate one way, from dimension to fact. Measures stay simple and
fast, and every report slices consistently. It is the same shape as the dbt marts.

---

## 3. DAX measures

Create each one in `_Measures` (Home -> New measure). Format strings are in brackets.

### 3.1 Volume

```dax
Transactions = COUNTROWS ( fct_transactions )                                   -- [#,0]
```
Authorization attempts (approved + declined).

```dax
Approved Transactions =
CALCULATE ( [Transactions], fct_transactions[is_approved] = TRUE () )           -- [#,0]
```

```dax
Declined Transactions = [Transactions] - [Approved Transactions]                 -- [#,0]
```

```dax
Approved Volume USD = SUM ( fct_transactions[approved_amount_usd] )              -- [$#,0]
```
Approved payment volume. The headline "how much money moved" number.

```dax
Avg Approved Ticket USD = DIVIDE ( [Approved Volume USD], [Approved Transactions] )   -- [$#,0.00]
```

```dax
Transactions 7D Avg =
AVERAGEX (
    DATESINPERIOD ( dim_date[date_day], MAX ( dim_date[date_day] ), -7, DAY ),
    [Transactions]
)                                                                               -- [#,0]
```
Rolling 7-day average that smooths the weekly cycle. Use it on the daily line chart.

### 3.2 Authorization performance

```dax
Approval Rate = DIVIDE ( [Approved Transactions], [Transactions] )               -- [0.00%]
```
Network health KPI: approved / all attempts.

```dax
CNP Approval Rate =
CALCULATE ( [Approval Rate], fct_transactions[channel] = "card_not_present" )   -- [0.00%]
```
Card-not-present approval rate, where issuer false declines show up first (see INSIGHTS #3).

```dax
Network Approval Rate =
CALCULATE ( [Approval Rate], REMOVEFILTERS ( dim_issuer ), REMOVEFILTERS ( dim_merchant ) )  -- [0.00%]
```
Benchmark that ignores issuer and merchant slicers but respects date and channel.

```dax
Approval Gap vs Network bps = ( [Approval Rate] - [Network Approval Rate] ) * 10000          -- [#,0]
```
Negative = below the network benchmark. Use it as conditional formatting in the issuer table.

```dax
Excess Declines =
MAX ( 0, [Network Approval Rate] * [Transactions] - [Approved Transactions] )   -- [#,0]
```
Declines that would be recovered if this slice matched the network average.

```dax
Soft Decline Share =
DIVIDE (
    CALCULATE ( [Declined Transactions], fct_transactions[decline_type] = "soft" ),
    [Declined Transactions]
)                                                                               -- [0.0%]
```
Share of declines that are retryable (insufficient funds, issuer unavailable, ...).

```dax
Issuer Unavailable Declines =
CALCULATE ( [Transactions], fct_transactions[auth_response_code] = "91" )      -- [#,0]
```
Technical declines (code 91). Spikes mean an issuer outage, where stand-in processing would help.

```dax
Issuer Approval Rank =
IF (
    HASONEVALUE ( dim_issuer[issuer_id] ),
    RANKX ( ALLSELECTED ( dim_issuer[issuer_id] ), [Approval Rate], , DESC, DENSE )
)                                                                               -- [#,0]
```
Rank of the issuer within the current selection. Blank on total rows.

### 3.3 Fraud & disputes

```dax
Fraud Loss USD = SUM ( fct_transactions[fraud_loss_amount_usd] )                -- [$#,0]
```

```dax
Fraud Loss Rate bps = DIVIDE ( [Fraud Loss USD], [Approved Volume USD] ) * 10000  -- [#,0.0]
```
Approved fraud USD / approved USD x 10,000. The industry-standard loss metric.

```dax
Fraud Attempt Rate bps =
DIVIDE ( CALCULATE ( [Transactions], fct_transactions[is_fraud] = TRUE () ), [Transactions] ) * 10000  -- [#,0.0]
```
Exposure: all fraudulent attempts, including those declined.

```dax
Fraud Catch Rate =
DIVIDE (
    CALCULATE ( [Transactions], fct_transactions[is_fraud] = TRUE (), fct_transactions[is_approved] = FALSE () ),
    CALCULATE ( [Transactions], fct_transactions[is_fraud] = TRUE () )
)                                                                               -- [0.0%]
```
Share of fraud attempts stopped at authorization.

```dax
Chargeback Rate =
DIVIDE ( CALCULATE ( [Transactions], fct_transactions[is_chargeback] = TRUE () ), [Approved Transactions] )  -- [0.00%]
```
Disputes / approved transactions. Monitoring programs flag about 1% when there are also at least 5 disputes.

### 3.4 Mix

```dax
Cross-border Share =
DIVIDE ( CALCULATE ( [Transactions], fct_transactions[is_cross_border] = TRUE () ), [Transactions] )  -- [0.00%]
```

```dax
CNP Share =
DIVIDE ( CALCULATE ( [Transactions], fct_transactions[channel] = "card_not_present" ), [Transactions] )  -- [0.0%]
```

### 3.5 Interchange

```dax
Interchange USD = SUM ( fct_transactions[interchange_fee_usd] )                 -- [$#,0]
```

```dax
Effective Interchange Rate = DIVIDE ( [Interchange USD], [Approved Volume USD] )  -- [0.00%]
```

```dax
Interchange Share =
DIVIDE ( [Interchange USD], CALCULATE ( [Interchange USD], REMOVEFILTERS ( fct_transactions[card_product], fct_transactions[card_type] ) ) )  -- [0.0%]
```
Share of total interchange within the current date and channel context. Use it in the revenue-mix bar chart.

### 3.6 Time intelligence

```dax
Transactions PM = CALCULATE ( [Transactions], DATEADD ( dim_date[date_day], -1, MONTH ) )   -- [#,0]

Transactions MoM % = DIVIDE ( [Transactions] - [Transactions PM], [Transactions PM] )       -- [+0.0%;-0.0%]

Approval Rate PM = CALCULATE ( [Approval Rate], DATEADD ( dim_date[date_day], -1, MONTH ) )  -- [0.00%]

Approval Rate MoM pp = ( [Approval Rate] - [Approval Rate PM] ) * 100                         -- [+0.00;-0.00]
```
Month-over-month comparisons. DATEADD needs the marked date table, and a monthly axis taken from `dim_date`.

```dax
Approved Volume MTD = TOTALMTD ( [Approved Volume USD], dim_date[date_day] )   -- [$#,0]
```

### 3.7 Data quality (on `dq_results`)

```dax
Latest Run Time = MAX ( dq_results[run_started_at] )

DQ Tests (Latest Run) =
CALCULATE ( COUNTROWS ( dq_results ), dq_results[run_started_at] = [Latest Run Time] )        -- [#,0]
```
Measures referencing the latest run: `CALCULATE` with a filter on the max run timestamp.

```dax
DQ Breaches (Latest Run) =
CALCULATE (
    COUNTROWS ( dq_results ),
    dq_results[threshold_status] = "BREACH",
    dq_results[run_started_at] = [Latest Run Time]
)                                                                               -- [#,0]
```

```dax
DQ Pass Rate =
1 - DIVIDE ( SUM ( dq_results[failed_rows] ), SUM ( dq_results[total_rows] ) )  -- [0.000%]
```
Pooled pass rate across the checks in context. Put `dimension` on the axis for the per-dimension view.

```dax
DQ Partition Pass Rate =
1 - DIVIDE ( SUM ( dq_daily_partition_metrics[failed_rows] ), SUM ( dq_daily_partition_metrics[total_rows] ) )  -- [0.000%]
```
Row-level pass rate per ingestion day. Use it for the trend line by `dq_dimension`.

```dax
DQ Status Icon =
SWITCH (
    SELECTEDVALUE ( dq_results[threshold_status] ),
    "WITHIN_THRESHOLD", "✅ Within threshold",
    "BREACH", "🔴 Breach",
    "ERROR", "⛔ Error"
)
```
Text status, with an icon plus a label so it isn't colour-only.

---

## 4. Build the pages

Theme: View -> Themes -> Customize. Set the categorical colours in this order:
`#2a78d6, #eb6834, #1baf7a, #eda100, #e87ba4, #008300, #4a3aa7, #e34948` (same as the
Streamlit app), and background `#fcfcfb`. Use one colour per entity everywhere (for example,
card_present is always blue).

### Page 1: Network Performance

1. **Slicer row** (top, horizontal): `dim_date[date_day]` (Between), `dim_merchant[mcc_category]`, `dim_merchant[mcc]`, `fct_transactions[channel]`, `dim_issuer[issuer_name]`. In Format -> Slicer settings, enable *Multi-select with Ctrl*. Use View -> Sync slicers if you add more pages.
2. **KPI cards** (6): `Transactions`, `Approved Volume USD`, `Approval Rate`, `Fraud Loss Rate bps`, `Cross-border Share`, `Interchange USD`. For the card visual, add `Transactions MoM %` as the reference label.
3. **Line chart: Daily volume**. X = `dim_date[date_day]`, Y = `Transactions` and `Transactions 7D Avg`. Both use the same unit and axis. Never put the approval rate on a secondary axis here.
4. **Line chart: Weekly approval rate by channel**. X = `dim_date[date_day]` (Date hierarchy -> Week, or add a `week_start` column), Y = `Approval Rate`, Legend = `channel`.
5. **Clustered column: Fraud loss by segment**. X = `is_cross_border`, Legend = `channel`, Y = `Fraud Loss Rate bps`. Turn data labels on.
6. **Line chart: Cross-border share by month**. X = `dim_date[month_start_date]`, Y = `Cross-border Share`.
7. **Bar chart: Approval by MCC category**. Y = `dim_merchant[mcc_category]`, X = `Approval Rate`, sorted ascending. If you set the X-axis minimum to 0.85, label the chart "axis does not start at 0".
8. **Bar chart: Decline reasons**. Y = `fct_transactions[decline_reason]`, X = `Declined Transactions`, Legend = `decline_type`.
9. **Table: Issuer performance**. Columns: `issuer_id`, `issuer_name`, `Transactions`, `Approval Rate`, `CNP Approval Rate`, `Approval Gap vs Network bps`, `Fraud Loss Rate bps`, `Issuer Unavailable Declines`, `Issuer Approval Rank`. Conditional formatting: background colour on `Approval Gap vs Network bps`, diverging from red (negative) through grey (0) to blue (positive).
10. Add a **tooltip page** (Page information -> Allow use as tooltip) showing `Fraud Attempt Rate bps`, `Fraud Catch Rate` and `Avg Approved Ticket USD`. Assign it to the visuals in Format -> Tooltips.

### Page 2: Data Quality Monitor

1. **Slicers**: `dq_results[run_started_at]` (dropdown, defaults to the latest), and `dq_results[model]` with a text filter "starts with raw." vs. not, which recreates the *Raw / Trusted* toggle.
2. **Cards**: `DQ Tests (Latest Run)`, `DQ Breaches (Latest Run)`, `DQ Pass Rate`.
3. **Line chart**: X = `dq_daily_partition_metrics[load_date]` (Week level), Y = `DQ Partition Pass Rate`, Legend = `dq_dimension`. Add constant lines at 0.9995 and 0.999 (Analytics pane) for the completeness and validity thresholds.
4. **Table: Scorecard**. Columns `model`, `dimension`, `check_name`, `status`, `failed_rows`, `total_rows`, `pass_rate`, `threshold`, `DQ Status Icon`.
5. **Bar chart**: Y = `dq_results[dimension]`, X = Sum of `failed_rows`.
6. **Drill-through page "Quarantine detail"**: a table on `dq_transaction_quarantine` with `dq_issues` as the drill-through field. Right-click a check -> Drill through.

---

## 5. Publish & governance (optional)

- Publish to a workspace and set a scheduled refresh (needs a gateway for local Parquet; Snowflake doesn't).
- **Row-level security** example. Modeling -> Manage roles -> role `IssuerPartner` with the filter on `dim_issuer`:
  `[issuer_id] = LOOKUPVALUE ( issuer_users[issuer_id], issuer_users[email], USERPRINCIPALNAME () )`.
  Each partner bank then sees only its own portfolio, the typical pattern for a network sharing benchmarks with issuers.
- **Endorse** the dataset as *Certified* once measure definitions match the dbt doc blocks. One metric, one definition.

## 6. Validate against the warehouse

After building, check these against `analysis/results/*.csv` or the Streamlit app (full year, no filters):

| Measure | Expected (2M-row default dataset) |
|---|---|
| Transactions | 1,967,974 |
| Approval Rate | 93.21% |
| Fraud Loss Rate bps | 21.9 |
| Cross-border Share | 7.80% |
| Interchange USD | about $2.07M |

If a number doesn't match, the usual cause is a relationship pointing the wrong way, or a slicer still applied.
