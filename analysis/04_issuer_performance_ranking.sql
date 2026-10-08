-- =============================================================================
-- 04 Issuer performance ranking
-- Business question: Which issuers under-perform their peers on approval rate
--   (especially CNP, where over-tuned fraud rules cause false declines) and on
--   fraud losses, and did any issuer have availability incidents (code 91)?
-- Techniques: CTEs, DENSE_RANK, PERCENT_RANK, peer z-score (AVG/STDDEV OVER),
--   NTILE quartiles
-- =============================================================================
with issuer as (
    select
        f.issuer_id,
        i.issuer_name,
        i.issuer_country,
        i.issuer_type,
        count(*)                                                                    as attempts,
        sum(case when f.is_approved then 1 else 0 end) * 1.0 / count(*)             as approval_rate,
        sum(case when f.channel = 'card_not_present' and f.is_approved then 1 else 0 end) * 1.0
            / nullif(sum(case when f.channel = 'card_not_present' then 1 else 0 end), 0) as cnp_approval_rate,
        sum(case when f.auth_response_code = '05' then 1 else 0 end) * 1.0 / count(*) as do_not_honor_rate,
        sum(case when f.auth_response_code = '91' then 1 else 0 end)                as issuer_unavailable_declines,
        sum(f.fraud_loss_amount_usd) * 10000.0 / nullif(sum(f.approved_amount_usd), 0) as fraud_loss_bps
    from marts.fct_transactions f
    join marts.dim_issuer i on f.issuer_id = i.issuer_id
    group by 1, 2, 3, 4
    having count(*) >= 5000                       -- ignore issuers too small to rank reliably
)
select
    issuer_id,
    issuer_name,
    issuer_country,
    issuer_type,
    attempts,
    round(approval_rate, 4)                                                         as approval_rate,
    round(cnp_approval_rate, 4)                                                     as cnp_approval_rate,
    round(do_not_honor_rate, 4)                                                     as do_not_honor_rate,
    issuer_unavailable_declines,
    round(fraud_loss_bps, 1)                                                        as fraud_loss_bps,
    dense_rank() over (order by approval_rate desc)                                 as approval_rank,
    round(percent_rank() over (order by cnp_approval_rate), 3)                      as cnp_approval_percentile,
    round((cnp_approval_rate - avg(cnp_approval_rate) over ())
          / nullif(stddev_samp(cnp_approval_rate) over (), 0), 2)                   as cnp_approval_zscore,
    ntile(4) over (order by fraud_loss_bps, issuer_id)                              as fraud_loss_quartile
from issuer
order by cnp_approval_zscore;

-- Part B: issuer availability incidents - hours where an issuer's "issuer unavailable"
-- (91) rate exceeded 20% with meaningful volume. Candidates for network stand-in processing.
with hourly as (
    select
        issuer_id,
        date_trunc('hour', transaction_ts)                                          as hour_start,
        count(*)                                                                    as attempts,
        sum(case when auth_response_code = '91' then 1 else 0 end)                  as code_91
    from marts.fct_transactions
    group by 1, 2
)
select
    issuer_id,
    hour_start,
    attempts,
    code_91,
    round(code_91 * 1.0 / attempts, 3)                                              as code_91_rate
from hourly
where attempts >= 10 and code_91 * 1.0 / attempts > 0.2
order by hour_start;
