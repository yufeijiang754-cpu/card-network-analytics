-- Trusted authorizations (dq_status valid or repaired) enriched with merchant, card,
-- issuer and reference data, with all monetary values converted to USD.
with txn as (

    select *
    from {{ ref('int_transactions__dq_flagged') }}
    where dq_status in ('valid', 'repaired')

)

select
    t.transaction_id,
    t.transaction_ts,
    t.transaction_date,
    extract(hour from t.transaction_ts)                         as transaction_hour,
    t.loaded_at,
    t.card_id,
    t.merchant_id,
    t.issuer_id,
    t.acquirer_id,
    m.mcc,
    m.mcc_category,
    m.country_code                                              as merchant_country,
    c.home_country                                              as card_country,
    c.card_type,
    c.card_product,
    t.channel,
    t.is_cross_border,
    t.currency_code,
    t.amount_local,
    cast(t.amount_local * fx.usd_rate as decimal(18, 2))        as amount_usd,
    t.interchange_fee_local,
    cast(t.interchange_fee_local * fx.usd_rate as decimal(18, 4)) as interchange_fee_usd,
    t.auth_response_code,
    t.is_approved,
    coalesce(t.decline_reason_raw, rc.decline_reason)           as decline_reason,
    rc.decline_category,
    rc.decline_type,
    t.is_fraud,
    t.is_chargeback,
    (c.card_type = 'Debit' and i.is_regulated_debit and not t.is_cross_border) as is_regulated_debit_txn,
    t.dq_status,
    t.dq_issues
from txn as t
inner join {{ ref('int_merchants__classified') }} as m  on t.merchant_id = m.merchant_id
inner join {{ ref('stg_cardholders') }}           as c  on t.card_id = c.card_id
inner join {{ ref('stg_issuers') }}               as i  on t.issuer_id = i.issuer_id
inner join {{ ref('currencies') }}                as fx on t.currency_code = fx.currency_code
left join  {{ ref('auth_response_codes') }}       as rc on t.auth_response_code = rc.response_code
