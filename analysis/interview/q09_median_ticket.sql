-- Q9 Median and 90th-percentile approved ticket size by MCC category
select mcc_category,
       round(percentile_cont(0.5) within group (order by amount_usd), 2) as median_ticket_usd,
       round(percentile_cont(0.9) within group (order by amount_usd), 2) as p90_ticket_usd,
       round(avg(amount_usd), 2) as mean_ticket_usd
from marts.fct_transactions
where is_approved
group by mcc_category
order by median_ticket_usd desc;
