-- Q13 Monthly interchange revenue with year-to-date running total and share of the full year
select cast(date_trunc('month', transaction_date) as date) as month_start,
       round(sum(interchange_fee_usd), 0) as interchange_usd,
       round(sum(sum(interchange_fee_usd)) over (order by date_trunc('month', transaction_date)), 0) as interchange_ytd,
       round(sum(sum(interchange_fee_usd)) over (order by date_trunc('month', transaction_date))
             / sum(sum(interchange_fee_usd)) over (), 4) as share_of_year
from marts.fct_transactions
group by date_trunc('month', transaction_date)
order by month_start;
