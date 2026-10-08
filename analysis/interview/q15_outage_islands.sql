-- Q15 Gaps and islands: longest run of consecutive hours in which an issuer returned code 91 on >20% of attempts
with hourly as (
    select issuer_id, date_trunc('hour', transaction_ts) as hour_start,
           count(*) as attempts,
           sum(case when auth_response_code = '91' then 1 else 0 end) as code_91
    from marts.fct_transactions
    group by 1, 2
),
bad as (
    select issuer_id, hour_start
    from hourly
    where attempts >= 10 and code_91 * 1.0 / attempts > 0.2
),
islands as (
    select issuer_id, hour_start,
           hour_start - to_hours(row_number() over (partition by issuer_id order by hour_start)) as island_id
    from bad
)
select issuer_id,
       min(hour_start) as incident_start,
       max(hour_start) + interval 1 hour as incident_end,
       count(*) as hours
from islands
group by issuer_id, island_id
order by hours desc, incident_start;
