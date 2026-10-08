# Running the dbt Project on Snowflake

The project runs locally on **DuckDB** by default, at zero cost. The same dbt models also
run on **Snowflake**. Only the connection target and the way raw data is loaded change.

| | DuckDB (default `dev` target) | Snowflake (`snowflake` target) |
|---|---|---|
| Raw data | Parquet files read in place (`meta.external_location` in `_sources.yml`) | `PAYMENTS_ANALYTICS.RAW.*` tables loaded with `COPY INTO` |
| Warehouse-specific SQL | `regexp_full_match`, `isodow` | `regexp_like`, `dayofweekiso` (via `adapter.dispatch` macros in `macros/cross_db.sql`) |
| `fct_transactions` | incremental, delete+insert | incremental, delete+insert, **clustered by `transaction_date`** |
| Cost | free | XSMALL warehouse, auto-suspend 60 s |

## 1. Prerequisites

- A Snowflake account. A [30-day trial](https://signup.snowflake.com/) is enough: the full 2M-row build uses well under 1 credit.
- A client that can run `PUT`: [SnowSQL](https://docs.snowflake.com/en/user-guide/snowsql) or the [Snowflake CLI](https://docs.snowflake.com/en/developer-guide/snowflake-cli/index) (`snow sql`).
- Install the Snowflake adapter into the project venv:

```bash
.venv/bin/pip install dbt-snowflake==1.8.4
```

## 2. Create warehouse, database, schemas and roles

Open `snowflake/01_setup.sql`, replace `<YOUR_USER>`, and run it as an admin (Snowsight worksheet is fine).

It creates:
- `TRANSFORM_WH` (XSMALL, auto-suspend 60 s)
- `PAYMENTS_ANALYTICS` database with a `RAW` landing schema
- `TRANSFORMER` role for dbt and `REPORTER` role (read-only) for Power BI and Streamlit

## 3. Load the raw data

Generate the data locally first (`make data`), then from the repo root run:

```bash
snowsql -a <account_identifier> -u <user> -r TRANSFORMER -w TRANSFORM_WH -f snowflake/02_load_raw.sql
# or: snow sql -f snowflake/02_load_raw.sql --role TRANSFORMER --warehouse TRANSFORM_WH
```

The script:
1. Creates a Parquet file format (`use_logical_type = true` so timestamps load correctly) and an internal stage.
2. `PUT`s the Parquet files into the stage.
3. Creates RAW tables with **explicit DDL**. That DDL is the contract with the upstream feed.
4. Runs `COPY INTO ... match_by_column_name = case_insensitive`.
5. Prints row counts. Compare them with `data/raw/_manifest.json`.

> For production you would use an external stage on S3 with a storage integration, plus
> Snowpipe for continuous loading. The internal stage keeps this demo self-contained.

## 4. Configure credentials

`dbt/profiles.yml` reads everything from environment variables, so no secrets live in the repo.
Create a `.env` file (already git-ignored):

```bash
export SNOWFLAKE_ACCOUNT=xy12345.us-east-1     # account identifier
export SNOWFLAKE_USER=your_user
export SNOWFLAKE_PASSWORD='***'                 # or use key-pair auth (see profiles.yml)
export SNOWFLAKE_ROLE=TRANSFORMER
export SNOWFLAKE_WAREHOUSE=TRANSFORM_WH
export SNOWFLAKE_DATABASE=PAYMENTS_ANALYTICS
export SNOWFLAKE_SCHEMA=DBT                     # default schema (custom schemas override it)
```

## 5. Switch target and run

```bash
source .env
cd dbt
DBT_TARGET=snowflake ../.venv/bin/dbt debug --profiles-dir .     # connection check
DBT_TARGET=snowflake ../.venv/bin/dbt build --profiles-dir .     # seeds + models + tests
DBT_TARGET=snowflake ../.venv/bin/dbt docs generate --profiles-dir .
```

dbt creates the schemas `REFERENCE`, `STAGING`, `INTERMEDIATE`, `MARTS`, `DQ` and `DQ_AUDIT`
(stored test failures) inside `PAYMENTS_ANALYTICS`. The `on-run-end` hook appends test
results to `DQ.DQ_RESULTS` exactly as on DuckDB.

## 6. Post-run checks

```sql
use role REPORTER;
select count(*) from PAYMENTS_ANALYTICS.MARTS.FCT_TRANSACTIONS;            -- ~1.97M
select * from PAYMENTS_ANALYTICS.DQ.DQ_RESULTS order by run_started_at desc limit 20;
select system$clustering_information('PAYMENTS_ANALYTICS.MARTS.FCT_TRANSACTIONS', '(transaction_date)');
```

## 7. Pointing BI tools at Snowflake

- **Power BI**: Get Data -> Snowflake -> server `<account>.snowflakecomputing.com`, warehouse `TRANSFORM_WH`, role `REPORTER`. See `docs/POWERBI_GUIDE.md`.
- **Streamlit**: the dashboard reads DuckDB by default. Swapping the connection for `snowflake.connector` only requires changing `dashboard/db.py`.

## Cost notes

- XSMALL is 1 credit per hour, billed per second after the first minute. A full `dbt build` on 2M rows takes a few minutes.
- `auto_suspend = 60` stops billing a minute after the last query.
- Suspend manually with `alter warehouse TRANSFORM_WH suspend;` when you're done.
