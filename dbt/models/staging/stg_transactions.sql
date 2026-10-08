-- Staging: 1:1 with the raw authorization feed. Renames, casts and light
-- standardization only; no rows are filtered here (filtering is a DQ decision
-- made explicitly in the intermediate layer).
with source as (

    select * from {{ source('raw', 'transactions') }}

)

select
    cast(transaction_id as varchar)            as transaction_id,
    cast(timestamp as timestamp)               as transaction_ts,
    cast(timestamp as date)                    as transaction_date,
    cast(_loaded_at as timestamp)              as loaded_at,
    cast(card_id as varchar)                   as card_id,
    cast(merchant_id as varchar)               as merchant_id,
    cast(issuer_id as varchar)                 as issuer_id,
    cast(acquirer_id as varchar)               as acquirer_id,
    cast(amount as decimal(18, 2))             as amount_local,
    cast(currency as varchar)                  as currency_raw,
    upper(trim(cast(currency as varchar)))     as currency_normalized,
    cast(channel as varchar)                   as channel,
    cast(is_cross_border as boolean)           as is_cross_border,
    cast(auth_response_code as varchar)        as auth_response_code,
    cast(is_approved as boolean)               as is_approved,
    cast(decline_reason as varchar)            as decline_reason_raw,
    cast(interchange_fee as decimal(18, 4))    as interchange_fee_local,
    cast(is_fraud as boolean)                  as is_fraud,
    cast(is_chargeback as boolean)             as is_chargeback
from source
