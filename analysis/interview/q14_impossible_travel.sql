-- Q14 "Impossible travel": card-present transactions on the same card in two different countries within 2 hours
with cp as (
    select f.card_id, f.transaction_id, f.transaction_ts, m.merchant_country,
           lag(f.transaction_ts) over (partition by f.card_id order by f.transaction_ts) as prev_ts,
           lag(m.merchant_country) over (partition by f.card_id order by f.transaction_ts) as prev_country
    from marts.fct_transactions f
    join marts.dim_merchant m on f.merchant_id = m.merchant_id
    where f.channel = 'card_present'
)
select card_id, prev_country, merchant_country, prev_ts, transaction_ts,
       datediff('minute', prev_ts, transaction_ts) as minutes_apart
from cp
where merchant_country <> prev_country
  and transaction_ts <= prev_ts + interval 2 hours
order by minutes_apart
limit 20;
