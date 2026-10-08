{#- TIMELINESS (freshness): the newest record must be no older than `max_age_hours` relative to
    the as-of timestamp (var dq_as_of_ts; defaults to the current timestamp in production). -#}
{% test dq_recency(model, column_name, max_age_hours=36) %}
{{ config(meta={'dq_dimension': 'timeliness'}) }}
{% set as_of = var('dq_as_of_ts', none) %}
select
    max({{ column_name }}) as newest_record_ts
from {{ model }}
having max({{ column_name }}) < {{ dbt.dateadd('hour', -1 * max_age_hours,
        ("cast('" ~ as_of ~ "' as timestamp)") if as_of else dbt.current_timestamp()) }}
{% endtest %}
