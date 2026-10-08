{#- TIMELINESS: records must be ingested within `max_hours` of the event (late-arrival SLA). -#}
{% test dq_max_latency(model, column_name, reference_column, key_column, max_hours=24) %}
{{ config(meta={'dq_dimension': 'timeliness'}) }}
select
    {{ key_column }} as record_key,
    {{ column_name }} as event_ts,
    {{ reference_column }} as reference_ts
from {{ model }}
where {{ reference_column }} > {{ dbt.dateadd('hour', max_hours, column_name) }}
{% endtest %}
