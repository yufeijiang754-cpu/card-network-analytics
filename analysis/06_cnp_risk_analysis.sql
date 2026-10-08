-- =============================================================================
-- 06 Card-not-present (CNP) risk analysis
-- Business question: Where is CNP risk concentrated, and did any acquirer's
--   merchants experience a card-testing (BIN enumeration) attack, i.e. a burst of
--   small-ticket CNP attempts with abnormal "invalid card / expired card"
--   declines compared with their own trailing baseline?
-- Techniques: CTEs, rolling 28-day window baseline (MEDIAN / AVG OVER ROWS BETWEEN).
--   A trailing MEDIAN is used instead of mean/stddev because the attack days would
--   otherwise contaminate the baseline and mask day 2+ of a multi-day attack.
-- =============================================================================
with daily as (
    select
        f.acquirer_id,
        a.acquirer_name,
        a.acquirer_type,
        f.transaction_date,
        count(*)                                                                    as cnp_attempts,
        sum(case when f.amount_usd < 5 then 1 else 0 end)                           as small_ticket_attempts,
        sum(case when f.auth_response_code in ('14', '54') then 1 else 0 end)       as invalid_or_expired_declines,
        sum(case when f.is_fraud then 1 else 0 end)                                 as fraud_attempts
    from marts.fct_transactions f
    join marts.dim_acquirer a on f.acquirer_id = a.acquirer_id
    where f.channel = 'card_not_present'
    group by 1, 2, 3, 4
),
baseline as (
    select
        *,
        median(invalid_or_expired_declines) over w     as baseline_median,
        avg(small_ticket_attempts * 1.0 / cnp_attempts) over w as baseline_small_ticket_share
    from daily
    window w as (partition by acquirer_id order by transaction_date
                 rows between 28 preceding and 1 preceding)
)
select
    acquirer_id,
    acquirer_name,
    acquirer_type,
    transaction_date,
    cnp_attempts,
    small_ticket_attempts,
    invalid_or_expired_declines,
    baseline_median                                                                 as baseline_28d_median,
    round(invalid_or_expired_declines / greatest(baseline_median, 1), 1)            as multiple_of_baseline,
    round(small_ticket_attempts * 1.0 / cnp_attempts, 3)                            as small_ticket_share,
    round(baseline_small_ticket_share, 3)                                           as baseline_small_ticket_share,
    fraud_attempts
from baseline
where baseline_median is not null
  and invalid_or_expired_declines >= 5 * greatest(baseline_median, 1)
  and invalid_or_expired_declines >= 20
order by transaction_date;

-- Part B: CNP risk concentration by MCC category (where to focus 3-D Secure / tokenization)
select
    mcc_category,
    count(*)                                                                          as cnp_attempts,
    round(count(*) * 1.0 / sum(count(*)) over (), 4)                                  as share_of_cnp_attempts,
    round(sum(case when is_approved then 1 else 0 end) * 1.0 / count(*), 4)           as cnp_approval_rate,
    round(sum(fraud_loss_amount_usd) * 10000.0 / sum(approved_amount_usd), 1)         as cnp_fraud_loss_bps,
    round(sum(fraud_loss_amount_usd), 0)                                              as cnp_fraud_loss_usd,
    round(sum(fraud_loss_amount_usd) * 1.0 / sum(sum(fraud_loss_amount_usd)) over (), 4) as share_of_cnp_fraud_loss
from marts.fct_transactions
where channel = 'card_not_present'
group by 1
order by cnp_fraud_loss_usd desc;
