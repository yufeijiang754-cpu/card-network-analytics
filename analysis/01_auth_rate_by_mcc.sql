-- =============================================================================
-- 01 Authorization approval rate by MCC
-- Business question: Which merchant categories have the lowest approval rates,
--   how far below the network average are they, and is the gap driven by the
--   card-not-present channel? (Low approval = lost sales for merchants and lost
--   interchange for issuers; the network wants to know where to focus.)
-- Techniques: CTE, conditional aggregation, window functions (AVG OVER, RANK)
-- =============================================================================
with by_mcc as (
    select
        f.mcc,
        m.mcc_description,
        f.mcc_category,
        count(*)                                                        as attempts,
        sum(case when f.is_approved then 1 else 0 end)                  as approved,
        sum(case when f.channel = 'card_present' then 1 else 0 end)     as cp_attempts,
        sum(case when f.channel = 'card_present' and f.is_approved then 1 else 0 end) as cp_approved,
        sum(case when f.channel = 'card_not_present' then 1 else 0 end) as cnp_attempts,
        sum(case when f.channel = 'card_not_present' and f.is_approved then 1 else 0 end) as cnp_approved
    from marts.fct_transactions f
    join marts.dim_merchant m on f.merchant_id = m.merchant_id
    where m.is_valid_mcc
    group by 1, 2, 3
),
network as (
    select sum(approved) * 1.0 / sum(attempts) as network_approval_rate from by_mcc
)
select
    b.mcc,
    b.mcc_description,
    b.mcc_category,
    b.attempts,
    round(b.approved * 1.0 / b.attempts, 4)                              as approval_rate,
    round(b.cp_approved * 1.0 / nullif(b.cp_attempts, 0), 4)             as cp_approval_rate,
    round(b.cnp_approved * 1.0 / nullif(b.cnp_attempts, 0), 4)           as cnp_approval_rate,
    round(b.cnp_attempts * 1.0 / b.attempts, 3)                          as cnp_share,
    round((b.approved * 1.0 / b.attempts - n.network_approval_rate) * 10000, 0) as gap_vs_network_bps,
    -- declines that would be recovered if this MCC matched the network average
    round(greatest(n.network_approval_rate * b.attempts - b.approved, 0), 0) as excess_declines,
    rank() over (order by b.approved * 1.0 / b.attempts)                 as rank_lowest_approval
from by_mcc b
cross join network n
order by approval_rate
