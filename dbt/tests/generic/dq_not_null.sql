{#- COMPLETENESS: column must be populated. Optional `condition` makes the requirement
    conditional (e.g. decline_reason is required only when the transaction was declined).
    Returns the record key of each failing row so results can be traced and scored. -#}
{% test dq_not_null(model, column_name, key_column, condition=none) %}
{{ config(meta={'dq_dimension': 'completeness'}) }}
select
    {{ key_column }} as record_key,
    '{{ column_name }}' as failing_column
from {{ model }}
where {{ column_name }} is null
  {% if condition %}and ({{ condition }}){% endif %}
{% endtest %}
