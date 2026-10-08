-- Authorization fact: one row per trusted (deduplicated, DQ-passed) authorization.
-- Incremental on ingestion time; delete+insert on transaction_id is supported by both
-- DuckDB and Snowflake. On Snowflake the table is clustered by transaction_date.
{{
    config(
        materialized='incremental',
        unique_key='transaction_id',
        incremental_strategy='delete+insert',
        on_schema_change='append_new_columns',
        cluster_by=['transaction_date']
    )
}}

select
    transaction_id,
    transaction_ts,
    transaction_date,
    transaction_hour,
    loaded_at,
    card_id,
    merchant_id,
    issuer_id,
    acquirer_id,
    mcc,
    mcc_category,
    channel,
    is_cross_border,
    card_type,
    card_product,
    currency_code,
    amount_local,
    amount_usd,
    interchange_fee_local,
    interchange_fee_usd,
    auth_response_code,
    is_approved,
    decline_reason,
    decline_category,
    decline_type,
    is_fraud,
    is_chargeback,
    is_regulated_debit_txn,
    case when is_approved then amount_usd else 0 end                     as approved_amount_usd,
    case when is_approved and is_fraud then amount_usd else 0 end        as fraud_loss_amount_usd,
    case when is_chargeback then amount_usd else 0 end                   as chargeback_amount_usd,
    dq_status
from {{ ref('int_transactions__enriched') }}

{% if is_incremental() %}
where loaded_at > (select max(loaded_at) from {{ this }})
{% endif %}
