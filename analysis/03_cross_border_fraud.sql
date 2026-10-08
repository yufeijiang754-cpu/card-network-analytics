-- =============================================================================
-- 03 Cross-border vs domestic fraud
-- Business question: How much riskier are cross-border transactions than
--   domestic ones, and does the gap hold within each channel (CP vs CNP)?
--   Expressed both as fraud attempt rate (exposure) and fraud loss bps (what
--   got through), plus the issuer fraud "catch rate".
-- Techniques: CTE, conditional aggregation, window function for relative risk
--   against the domestic card-present baseline
-- =============================================================================
with seg as (
    select
        case when is_cross_border then 'cross_border' else 'domestic' end    as geography,
        channel,
        count(*)                                                             as attempts,
        sum(case when is_fraud then 1 else 0 end)                            as fraud_attempts,
        sum(case when is_fraud and not is_approved then 1 else 0 end)        as fraud_declined,
        sum(approved_amount_usd)                                             as approved_usd,
        sum(fraud_loss_amount_usd)                                           as fraud_loss_usd,
        sum(case when is_approved then 1 else 0 end) * 1.0 / count(*)        as approval_rate
    from marts.fct_transactions
    group by 1, 2
)
select
    geography,
    channel,
    attempts,
    round(approval_rate, 4)                                                  as approval_rate,
    round(fraud_attempts * 10000.0 / attempts, 1)                            as fraud_attempt_rate_bps,
    round(fraud_loss_usd * 10000.0 / approved_usd, 1)                        as fraud_loss_rate_bps,
    round(fraud_declined * 1.0 / nullif(fraud_attempts, 0), 3)               as fraud_catch_rate,
    round(fraud_loss_usd, 0)                                                 as fraud_loss_usd,
    round((fraud_attempts * 1.0 / attempts)
          / max(case when geography = 'domestic' and channel = 'card_present'
                     then fraud_attempts * 1.0 / attempts end) over (), 1)   as relative_risk_vs_domestic_cp
from seg
order by fraud_attempt_rate_bps desc
