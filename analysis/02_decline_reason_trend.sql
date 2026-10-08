-- =============================================================================
-- 02 Decline reason trend
-- Business question: How is the decline-reason mix evolving month over month,
--   and which reasons are growing fastest? Soft declines (e.g. insufficient
--   funds, issuer unavailable) are recoverable with retries; hard declines are not.
-- Techniques: CTE, window share-of-total (SUM OVER PARTITION), LAG for MoM change
-- =============================================================================
with monthly as (
    select
        date_trunc('month', transaction_date)        as month_start,
        decline_reason,
        decline_type,
        count(*)                                     as declines
    from marts.fct_transactions
    where not is_approved
    group by 1, 2, 3
),
with_share as (
    select
        *,
        declines * 1.0 / sum(declines) over (partition by month_start) as share_of_declines
    from monthly
)
select
    cast(month_start as date)                                            as month_start,
    decline_reason,
    decline_type,
    declines,
    round(share_of_declines, 4)                                          as share_of_declines,
    round((share_of_declines - lag(share_of_declines) over w) * 10000, 0) as share_change_bps_mom,
    round(declines * 1.0 / nullif(lag(declines) over w, 0) - 1, 4)      as volume_change_mom,
    rank() over (partition by month_start order by declines desc)        as rank_in_month
from with_share
window w as (partition by decline_reason order by month_start)
order by month_start, rank_in_month
