-- Calendar dimension (one row per day) with US holiday and weekend attributes.
{% set start = var('dim_date_start') %}
{% set end = var('dim_date_end') %}

with seq as (

    {{ integer_sequence(1200) }}

),

days as (

    select cast({{ dbt.dateadd('day', 'n', "cast('" ~ start ~ "' as date)") }} as date) as date_day
    from seq

)

select
    d.date_day,
    extract(year from d.date_day)                                   as year_number,
    extract(quarter from d.date_day)                                as quarter_number,
    extract(month from d.date_day)                                  as month_number,
    cast(date_trunc('month', d.date_day) as date)                   as month_start_date,
    extract(day from d.date_day)                                    as day_of_month,
    {{ iso_day_of_week('d.date_day') }}                             as iso_day_of_week,
    case {{ iso_day_of_week('d.date_day') }}
        when 1 then 'Monday' when 2 then 'Tuesday' when 3 then 'Wednesday' when 4 then 'Thursday'
        when 5 then 'Friday' when 6 then 'Saturday' else 'Sunday'
    end                                                             as day_name,
    {{ iso_day_of_week('d.date_day') }} in (6, 7)                   as is_weekend,
    h.holiday_date is not null                                      as is_us_holiday,
    h.holiday_name,
    ({{ iso_day_of_week('d.date_day') }} in (6, 7) or h.holiday_date is not null) as is_peak_day
from days as d
left join {{ ref('us_holidays') }} as h
    on d.date_day = h.holiday_date
where d.date_day <= cast('{{ end }}' as date)
