-- Monthly performance by Merchant Category Code, with month-over-month growth.
with monthly as (

    select
        cast(date_trunc('month', transaction_date) as date)         as month_start_date,
        mcc,
        mcc_category,
        count(*)                                                    as transaction_count,
        sum({{ bool_to_int('is_approved') }})                       as approved_count,
        sum(approved_amount_usd)                                    as approved_amount_usd,
        sum({{ bool_to_int("channel = 'card_not_present'") }})    as cnp_transaction_count,
        sum({{ bool_to_int('is_cross_border') }})                   as cross_border_transaction_count,
        sum({{ bool_to_int('is_fraud') }})                          as fraud_attempt_count,
        sum(fraud_loss_amount_usd)                                  as fraud_loss_amount_usd,
        sum({{ bool_to_int('is_chargeback') }})                     as chargeback_count,
        sum(interchange_fee_usd)                                    as interchange_fee_usd
    from {{ ref('fct_transactions') }}
    group by 1, 2, 3

)

select
    month_start_date,
    mcc,
    mcc_category,
    transaction_count,
    approved_count,
    approved_amount_usd,
    cnp_transaction_count,
    cross_border_transaction_count,
    fraud_attempt_count,
    fraud_loss_amount_usd,
    chargeback_count,
    interchange_fee_usd,
    {{ safe_divide('approved_count', 'transaction_count') }}                    as approval_rate,
    {{ safe_divide('approved_amount_usd', 'approved_count') }}                  as avg_approved_ticket_usd,
    {{ safe_divide('fraud_loss_amount_usd * 10000', 'approved_amount_usd') }}   as fraud_loss_rate_bps,
    {{ safe_divide('chargeback_count', 'approved_count') }}                     as chargeback_rate,
    {{ safe_divide('interchange_fee_usd', 'approved_amount_usd') }}             as effective_interchange_rate,
    {{ safe_divide(
        'approved_amount_usd - lag(approved_amount_usd) over (partition by mcc order by month_start_date)',
        'lag(approved_amount_usd) over (partition by mcc order by month_start_date)') }} as approved_amount_mom_growth
from monthly
