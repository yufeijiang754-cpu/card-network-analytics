-- =============================================================================
-- 01_setup.sql - one-time Snowflake objects for the Card Network Analytics project
-- Run in a Snowsight worksheet or with SnowSQL / Snowflake CLI as an admin.
-- Replace <YOUR_USER> before running. All data loaded later is SYNTHETIC.
-- =============================================================================

-- ---- Compute & storage (SYSADMIN) --------------------------------------------
use role sysadmin;

create warehouse if not exists TRANSFORM_WH
    warehouse_size = 'XSMALL'
    auto_suspend = 60            -- seconds; keeps cost near zero when idle
    auto_resume = true
    initially_suspended = true
    comment = 'dbt transformations for card network analytics';

create database if not exists PAYMENTS_ANALYTICS comment = 'Card network analytics (synthetic data)';
create schema if not exists PAYMENTS_ANALYTICS.RAW comment = 'Landing zone: raw extracts loaded with COPY INTO';

-- ---- Roles (SECURITYADMIN) -----------------------------------------------------
use role securityadmin;

-- TRANSFORMER: used by dbt. Reads RAW, creates/owns staging, intermediate, marts, dq schemas.
create role if not exists TRANSFORMER;
-- REPORTER: used by BI tools (Power BI / Streamlit). Read-only on marts and dq.
create role if not exists REPORTER;

grant usage on warehouse TRANSFORM_WH to role TRANSFORMER;
grant usage on warehouse TRANSFORM_WH to role REPORTER;
grant usage, create schema on database PAYMENTS_ANALYTICS to role TRANSFORMER;
grant usage on database PAYMENTS_ANALYTICS to role REPORTER;
grant all on schema PAYMENTS_ANALYTICS.RAW to role TRANSFORMER;
grant select on future tables in schema PAYMENTS_ANALYTICS.RAW to role TRANSFORMER;

-- dbt creates the downstream schemas; future grants give REPORTER read access once they exist.
-- (Re-run these two lines after the first dbt run if the schemas did not exist yet.)
grant usage on future schemas in database PAYMENTS_ANALYTICS to role REPORTER;
grant select on future tables in database PAYMENTS_ANALYTICS to role REPORTER;
grant select on future views in database PAYMENTS_ANALYTICS to role REPORTER;

grant role TRANSFORMER to role sysadmin;
grant role REPORTER to role sysadmin;
grant role TRANSFORMER to user <YOUR_USER>;
grant role REPORTER to user <YOUR_USER>;
