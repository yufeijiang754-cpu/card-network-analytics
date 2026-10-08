{#- VALIDITY: numeric values must lie within [min_value, max_value] (NULLs are a completeness concern). -#}
{% test dq_value_in_range(model, column_name, min_value=none, max_value=none, key_column=none) %}
{{ config(meta={'dq_dimension': 'validity'}) }}
select
    {% if key_column %}{{ key_column }} as record_key,{% endif %}
    {{ column_name }} as failing_value
from {{ model }}
where {{ column_name }} is not null
  and (
      {% if min_value is not none %}{{ column_name }} < {{ min_value }}{% else %}1 = 0{% endif %}
      or {% if max_value is not none %}{{ column_name }} > {{ max_value }}{% else %}1 = 0{% endif %}
  )
{% endtest %}
