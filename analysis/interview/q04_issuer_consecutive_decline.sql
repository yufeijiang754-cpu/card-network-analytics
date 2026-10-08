-- Q4 Issuers whose approved volume fell month over month for 2+ consecutive months
with m as (
    select issuer_id,
           date_trunc('month', transaction_date) as month_start,
           sum(approved_amount_usd) as approved_usd
    from marts.fct_transactions
    group by 1, 2
),
g as (
    select *,
           approved_usd < lag(approved_usd) over (partition by issuer_id order by month_start) as is_down
    from m
),
streak as (
    select *,
           sum(case when is_down then 0 else 1 end)
               over (partition by issuer_id order by month_start rows unbounded preceding) as grp
    from g
)
select issuer_id,
       min(cast(month_start as date)) as streak_start,
       max(cast(month_start as date)) as streak_end,
       count(*) as months_down
from streak
where is_down
group by issuer_id, grp
having count(*) >= 2
order by months_down desc, issuer_id;
