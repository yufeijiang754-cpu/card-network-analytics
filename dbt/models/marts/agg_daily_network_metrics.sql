-- Daily network KPIs by channel and cross-border flag. Additive measures only, so the
-- table can be rolled up in BI; rates are provided for convenience at this grain.
select
    transaction_date,
    channel,
    is_cross_border,
    count(*)                                                         as transaction_count,
    sum({{ bool_to_int('is_approved') }})                            as approved_count,
    sum({{ bool_to_int('not is_approved') }})                        as declined_count,
    sum(amount_usd)                                                  as total_amount_usd,
    sum(approved_amount_usd)                                         as approved_amount_usd,
    sum({{ bool_to_int('is_fraud') }})                               as fraud_attempt_count,
    sum({{ bool_to_int('is_fraud and is_approved') }})               as fraud_approved_count,
    sum(fraud_loss_amount_usd)                                       as fraud_loss_amount_usd,
    sum({{ bool_to_int('is_chargeback') }})                          as chargeback_count,
    sum(chargeback_amount_usd)                                       as chargeback_amount_usd,
    sum(interchange_fee_usd)                                         as interchange_fee_usd,
    {{ safe_divide("sum(" ~ bool_to_int('is_approved') ~ ")", "count(*)") }}                as approval_rate,
    {{ safe_divide("sum(fraud_loss_amount_usd) * 10000", "sum(approved_amount_usd)") }}     as fraud_loss_rate_bps,
    {{ safe_divide("sum(approved_amount_usd)", "sum(" ~ bool_to_int('is_approved') ~ ")") }} as avg_approved_ticket_usd
from {{ ref('fct_transactions') }}
group by transaction_date, channel, is_cross_border
