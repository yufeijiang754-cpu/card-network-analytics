-- =============================================================================
-- 02_load_raw.sql - load the generated Parquet files into PAYMENTS_ANALYTICS.RAW
-- PUT commands must run from a client (SnowSQL or `snow sql`), not Snowsight.
-- Run from the repository root so the relative paths resolve, e.g.:
--   snowsql -a <account> -u <user> -r TRANSFORMER -w TRANSFORM_WH -f snowflake/02_load_raw.sql
-- =============================================================================
use role TRANSFORMER;
use warehouse TRANSFORM_WH;
use schema PAYMENTS_ANALYTICS.RAW;

-- ---- File format & internal stage ------------------------------------------------
create file format if not exists PARQUET_FMT
    type = parquet
    use_logical_type = true;      -- read Parquet TIMESTAMP logical types as timestamps

create stage if not exists RAW_STAGE
    file_format = PARQUET_FMT
    comment = 'Internal stage for synthetic card network extracts';

-- ---- Upload files (client-side) -------------------------------------------------
put file://data/raw/transactions/*.parquet @RAW_STAGE/transactions/ auto_compress = false overwrite = true parallel = 8;
put file://data/raw/merchants.parquet     @RAW_STAGE/merchants/    auto_compress = false overwrite = true;
put file://data/raw/cardholders.parquet   @RAW_STAGE/cardholders/  auto_compress = false overwrite = true;
put file://data/raw/issuers.parquet       @RAW_STAGE/issuers/      auto_compress = false overwrite = true;
put file://data/raw/acquirers.parquet     @RAW_STAGE/acquirers/    auto_compress = false overwrite = true;

-- ---- Raw tables (explicit DDL = the contract with the upstream feed) --------------
create or replace table TRANSACTIONS (
    TRANSACTION_ID      varchar,
    TIMESTAMP           timestamp_ntz,
    CARD_ID             varchar,
    MERCHANT_ID         varchar,
    ISSUER_ID           varchar,
    ACQUIRER_ID         varchar,
    AMOUNT              number(18, 2),
    CURRENCY            varchar,
    CHANNEL             varchar,
    IS_CROSS_BORDER     boolean,
    AUTH_RESPONSE_CODE  varchar,
    IS_APPROVED         boolean,
    DECLINE_REASON      varchar,
    INTERCHANGE_FEE     number(18, 4),
    IS_FRAUD            boolean,
    IS_CHARGEBACK       boolean,
    _LOADED_AT          timestamp_ntz
) comment = 'Raw authorization messages (synthetic). Untrusted: see dbt DQ tests.';

create or replace table MERCHANTS (
    MERCHANT_ID varchar, MERCHANT_NAME varchar, MCC varchar, COUNTRY_CODE varchar,
    ACQUIRER_ID varchar, ONBOARDING_DATE date
);
create or replace table CARDHOLDERS (
    CARD_ID varchar, ISSUER_ID varchar, HOME_COUNTRY varchar, CARD_TYPE varchar,
    CARD_PRODUCT varchar, CREDIT_LIMIT number(18, 2), CARD_OPEN_DATE date
);
create or replace table ISSUERS (
    ISSUER_ID varchar, ISSUER_NAME varchar, COUNTRY_CODE varchar, ISSUER_TYPE varchar,
    ASSET_SIZE_TIER varchar, IS_REGULATED_DEBIT boolean, ONBOARDED_DATE date
);
create or replace table ACQUIRERS (
    ACQUIRER_ID varchar, ACQUIRER_NAME varchar, COUNTRY_CODE varchar, ACQUIRER_TYPE varchar
);

-- ---- COPY INTO (column names matched case-insensitively from Parquet) --------------
copy into TRANSACTIONS from @RAW_STAGE/transactions/
    match_by_column_name = case_insensitive on_error = abort_statement;
copy into MERCHANTS   from @RAW_STAGE/merchants/   match_by_column_name = case_insensitive;
copy into CARDHOLDERS from @RAW_STAGE/cardholders/ match_by_column_name = case_insensitive;
copy into ISSUERS     from @RAW_STAGE/issuers/     match_by_column_name = case_insensitive;
copy into ACQUIRERS   from @RAW_STAGE/acquirers/   match_by_column_name = case_insensitive;

-- ---- Load verification (compare with data/raw/_manifest.json row_counts) -----------
select 'transactions' as table_name, count(*) as row_count from TRANSACTIONS
union all select 'merchants',   count(*) from MERCHANTS
union all select 'cardholders', count(*) from CARDHOLDERS
union all select 'issuers',     count(*) from ISSUERS
union all select 'acquirers',   count(*) from ACQUIRERS;

-- COPY history for audit: what was loaded, when, with which errors
select file_name, row_count, row_parsed, first_error_message, last_load_time
from information_schema.load_history
where schema_name = 'RAW'
order by last_load_time desc;
