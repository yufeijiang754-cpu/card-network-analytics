-- =============================================================================
-- 05 Chargeback anomaly detection
-- Business question: Which merchants have abnormal chargeback rates, both against
--   the network monitoring threshold (~1%) and against peers in the same MCC?
--   Merchants flagged here are candidates for an excessive-chargeback program
--   (rule: rate >= 1% AND >= 5 chargebacks; HIGH if also 3+ sd above MCC peers).
--   Part B is a cohort (vintage) view: do merchants onboarded more recently
--   generate more chargebacks?
-- Techniques: CTEs, peer statistics with AVG/STDDEV OVER (PARTITION BY mcc),
--   z-scores, ROW_NUMBER, cohort grouping
-- =============================================================================
with merchant as (
    select
        f.merchant_id,
        m.merchant_name,
        m.mcc,
        m.mcc_category,
        m.acquirer_name,
        sum(case when f.is_approved then 1 else 0 end)                   as approved,
        sum(case when f.is_chargeback then 1 else 0 end)                 as chargebacks,
        sum(case when f.is_chargeback and not f.is_fraud then 1 else 0 end) as non_fraud_chargebacks,
        sum(f.chargeback_amount_usd)                                     as chargeback_usd
    from marts.fct_transactions f
    join marts.dim_merchant m on f.merchant_id = m.merchant_id
    group by 1, 2, 3, 4, 5
    having sum(case when f.is_approved then 1 else 0 end) >= 100        -- minimum volume for a stable rate
),
scored as (
    select
        *,
        chargebacks * 1.0 / approved                                                        as cb_rate,
        avg(chargebacks * 1.0 / approved) over (partition by mcc)                           as peer_avg_cb_rate,
        stddev_samp(chargebacks * 1.0 / approved) over (partition by mcc)                   as peer_sd_cb_rate
    from merchant
)
select
    merchant_id,
    merchant_name,
    mcc,
    mcc_category,
    acquirer_name,
    approved,
    chargebacks,
    non_fraud_chargebacks,
    round(chargeback_usd, 2)                                              as chargeback_usd,
    round(cb_rate, 4)                                                     as chargeback_rate,
    round(peer_avg_cb_rate, 4)                                            as peer_avg_chargeback_rate,
    round((cb_rate - peer_avg_cb_rate) / nullif(peer_sd_cb_rate, 0), 1)  as peer_zscore,
    case
        when (cb_rate - peer_avg_cb_rate) / nullif(peer_sd_cb_rate, 0) >= 3
            then 'HIGH: above 1% / 5 disputes and 3+ sd above MCC peers'
        else 'MEDIUM: above 1% / 5 disputes'
    end                                                                   as alert_level,
    row_number() over (order by cb_rate desc)                             as risk_rank
from scored
-- Like real network monitoring programs, require BOTH a rate threshold and a minimum
-- dispute count: a 1% rate on 2 disputes is noise, not a pattern.
where cb_rate >= 0.01
  and chargebacks >= 5
order by risk_rank;

-- Part B: merchant onboarding-vintage cohorts
select
    extract(year from m.onboarding_date)                                  as onboarding_cohort_year,
    count(distinct f.merchant_id)                                         as merchants,
    sum(case when f.is_approved then 1 else 0 end)                        as approved,
    round(sum(case when f.is_chargeback then 1 else 0 end) * 1.0
          / sum(case when f.is_approved then 1 else 0 end), 5)            as chargeback_rate,
    round(sum(f.fraud_loss_amount_usd) * 10000.0 / sum(f.approved_amount_usd), 1) as fraud_loss_bps
from marts.fct_transactions f
join marts.dim_merchant m on f.merchant_id = m.merchant_id
group by 1
order by 1;
