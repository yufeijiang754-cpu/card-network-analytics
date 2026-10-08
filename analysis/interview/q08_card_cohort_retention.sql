-- Q8 Card activity cohorts: of cards first seen in month M, what share is active k months later?
with first_seen as (
    select card_id, min(date_trunc('month', transaction_date)) as cohort_month
    from marts.fct_transactions
    group by card_id
),
activity as (
    select distinct f.card_id, fs.cohort_month,
           datediff('month', fs.cohort_month, date_trunc('month', f.transaction_date)) as months_since
    from marts.fct_transactions f
    join first_seen fs on f.card_id = fs.card_id
)
select cast(cohort_month as date) as cohort_month,
       count(distinct case when months_since = 0 then card_id end) as cohort_size,
       round(count(distinct case when months_since = 1 then card_id end) * 1.0
             / count(distinct case when months_since = 0 then card_id end), 3) as m1_retention,
       round(count(distinct case when months_since = 3 then card_id end) * 1.0
             / count(distinct case when months_since = 0 then card_id end), 3) as m3_retention
from activity
group by cohort_month
order by cohort_month;
