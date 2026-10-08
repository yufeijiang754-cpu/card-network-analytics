-- Q12 Peak hour of day for each weekday
select day_name, transaction_hour as peak_hour, attempts
from (
    select d.iso_day_of_week, d.day_name, f.transaction_hour, count(*) as attempts,
           row_number() over (partition by d.iso_day_of_week order by count(*) desc) as rn
    from marts.fct_transactions f
    join marts.dim_date d on f.transaction_date = d.date_day
    group by 1, 2, 3
) t
where rn = 1
order by iso_day_of_week;
