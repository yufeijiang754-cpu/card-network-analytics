{#- TIMELINESS: an event cannot happen after the platform received it. Compares the event
    timestamp with a reference timestamp (ingestion time) plus a grace period that tolerates
    terminal clock drift. -#}
{% test dq_not_in_future(model, column_name, reference_column, key_column, grace_minutes=5) %}
{{ config(meta={'dq_dimension': 'timeliness'}) }}
select
    {{ key_column }} as record_key,
    {{ column_name }} as event_ts,
    {{ reference_column }} as reference_ts
from {{ model }}
where {{ column_name }} > {{ dbt.dateadd('minute', grace_minutes, reference_column) }}
{% endtest %}
