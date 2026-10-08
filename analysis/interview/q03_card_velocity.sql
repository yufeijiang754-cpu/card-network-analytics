-- Q3 Velocity rule: merchants with 8+ declined authorizations inside any 60-minute window (card-testing signal)
with declines as (
    select merchant_id,
           transaction_ts,
           count(*) over (partition by merchant_id order by transaction_ts
                          range between interval 60 minutes preceding and current row) as declines_in_60m
    from marts.fct_transactions
    where not is_approved
)
select merchant_id,
       min(transaction_ts) as first_breach_ts,
       max(declines_in_60m) as max_declines_in_60m,
       count(*) as breaching_declines
from declines
where declines_in_60m >= 8
group by merchant_id
order by max_declines_in_60m desc;
