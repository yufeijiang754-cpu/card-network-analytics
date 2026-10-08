-- Q1 Daily approval rate and a 7-day rolling approval rate (volume-weighted, not an average of daily rates)
with daily as (
    select transaction_date,
           count(*) as attempts,
           sum(case when is_approved then 1 else 0 end) as approved
    from marts.fct_transactions
    group by transaction_date
)
select transaction_date,
       round(approved * 1.0 / attempts, 4) as approval_rate,
       round(sum(approved) over w * 1.0 / sum(attempts) over w, 4) as approval_rate_7d
from daily
window w as (order by transaction_date rows between 6 preceding and current row)
order by transaction_date;
