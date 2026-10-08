-- =============================================================================
-- 07 Transaction volume seasonality
-- Business question: How strong are weekly and holiday seasonality effects, and
--   which days deviate most from trend? Used for capacity planning of the
--   authorization platform and for reading KPIs (a Saturday dip is not a Tuesday dip).
-- Techniques: CTEs, centered 7-day moving average, 28-day trailing average,
--   month-over-month growth with LAG, day-of-week index
-- =============================================================================
with daily as (
    select
        d.date_day,
        d.day_name,
        d.iso_day_of_week,
        d.is_weekend,
        d.is_us_holiday,
        d.holiday_name,
        count(f.transaction_id)                         as attempts,
        coalesce(sum(f.approved_amount_usd), 0)         as approved_usd
    from marts.dim_date d
    left join marts.fct_transactions f on f.transaction_date = d.date_day
    where d.date_day between '2025-01-01' and '2025-12-31'
    group by 1, 2, 3, 4, 5, 6
),
trend as (
    select
        *,
        avg(attempts) over (order by date_day rows between 3 preceding and 3 following)   as ma7_centered,
        avg(attempts) over (order by date_day rows between 28 preceding and 1 preceding)  as trailing_28d_avg,
        attempts * 1.0 / avg(attempts) over (partition by iso_day_of_week)                as index_vs_same_weekday_avg
    from daily
)
select
    date_day,
    day_name,
    is_weekend,
    is_us_holiday,
    holiday_name,
    attempts,
    round(ma7_centered, 0)                                       as ma7_centered,
    round(attempts / nullif(trailing_28d_avg, 0) - 1, 3)         as lift_vs_trailing_28d,
    round(index_vs_same_weekday_avg, 3)                          as index_vs_same_weekday_avg
from trend
where is_us_holiday
   or abs(attempts / nullif(trailing_28d_avg, 0) - 1) >= 0.25
order by date_day;

-- Part B: day-of-week index (1.00 = average day)
select
    iso_day_of_week,
    day_name,
    round(avg(attempts), 0)                                       as avg_daily_attempts,
    round(avg(attempts) / avg(avg(attempts)) over (), 3)          as dow_index
from (
    select d.date_day, d.iso_day_of_week, d.day_name, count(*) as attempts
    from marts.fct_transactions f
    join marts.dim_date d on f.transaction_date = d.date_day
    where not d.is_us_holiday
    group by 1, 2, 3
) t
group by 1, 2
order by 1;

-- Part C: monthly volume with month-over-month growth
with monthly as (
    select
        cast(date_trunc('month', transaction_date) as date)     as month_start,
        count(*)                                                 as attempts,
        sum(approved_amount_usd)                                 as approved_usd,
        count(distinct transaction_date)                         as active_days
    from marts.fct_transactions
    group by 1
)
select
    month_start,
    attempts,
    round(approved_usd, 0)                                                   as approved_usd,
    round(attempts * 1.0 / lag(attempts) over (order by month_start) - 1, 4) as attempts_mom,
    round(attempts * 1.0 / active_days, 0)                                   as avg_daily_attempts,
    round((attempts * 1.0 / active_days)
          / lag(attempts * 1.0 / active_days) over (order by month_start) - 1, 4) as daily_rate_mom
from monthly
order by month_start;
