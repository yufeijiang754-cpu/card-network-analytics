-- Q2 Top 3 MCCs by approved USD volume in each month
with monthly as (
    select cast(date_trunc('month', transaction_date) as date) as month_start,
           mcc,
           sum(approved_amount_usd) as approved_usd
    from marts.fct_transactions
    group by 1, 2
)
select month_start, mcc, round(approved_usd, 0) as approved_usd,
       rank() over (partition by month_start order by approved_usd desc) as rnk
from monthly
qualify rnk <= 3
order by month_start, rnk;
