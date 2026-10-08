-- =============================================================================
-- 08 Interchange revenue structure
-- Business question: Where does interchange revenue come from (card type,
--   product, regulated vs exempt debit, MCC category, channel) and what is the
--   effective rate of each segment? Interchange is issuer revenue and a key lever
--   when a network competes for issuer portfolios.
-- Techniques: CTE, GROUPING-free segment union, share of total with SUM OVER,
--   cumulative share (Pareto) with running SUM OVER ORDER BY
-- =============================================================================
with seg as (
    select
        case
            when card_type = 'Credit' then 'Credit - ' || card_product
            when is_regulated_debit_txn then 'Debit - Regulated (Reg II cap)'
            else 'Debit - Exempt'
        end                                             as card_segment,
        mcc_category,
        channel,
        sum(approved_amount_usd)                        as approved_usd,
        sum(interchange_fee_usd)                        as interchange_usd,
        sum(case when is_approved then 1 else 0 end)    as approved_txns
    from marts.fct_transactions
    where is_approved
    group by 1, 2, 3
),
by_card as (
    select
        card_segment,
        sum(approved_txns)                              as approved_txns,
        sum(approved_usd)                               as approved_usd,
        sum(interchange_usd)                            as interchange_usd
    from seg
    group by 1
)
select
    card_segment,
    approved_txns,
    round(approved_usd, 0)                                                         as approved_usd,
    round(interchange_usd, 0)                                                      as interchange_usd,
    round(approved_usd / sum(approved_usd) over (), 4)                             as share_of_volume,
    round(interchange_usd / sum(interchange_usd) over (), 4)                       as share_of_interchange,
    round(interchange_usd / approved_usd, 4)                                       as effective_rate,
    round(interchange_usd / approved_txns, 3)                                      as interchange_per_txn,
    round(sum(interchange_usd) over (order by interchange_usd desc
          rows between unbounded preceding and current row)
          / sum(interchange_usd) over (), 4)                                       as cumulative_share
from by_card
order by interchange_usd desc;

-- Part B: by MCC category and channel
select
    mcc_category,
    channel,
    round(sum(approved_amount_usd), 0)                                             as approved_usd,
    round(sum(interchange_fee_usd), 0)                                             as interchange_usd,
    round(sum(interchange_fee_usd) / sum(approved_amount_usd), 4)                  as effective_rate,
    round(sum(interchange_fee_usd) / sum(sum(interchange_fee_usd)) over (), 4)     as share_of_interchange
from marts.fct_transactions
where is_approved
group by 1, 2
order by interchange_usd desc;
