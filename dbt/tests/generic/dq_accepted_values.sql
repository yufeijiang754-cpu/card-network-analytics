{#- VALIDITY (enumeration): value must be one of a fixed list. -#}
{% test dq_accepted_values(model, column_name, values, key_column) %}
{{ config(meta={'dq_dimension': 'validity'}) }}
select
    {{ key_column }} as record_key,
    cast({{ column_name }} as varchar) as failing_value
from {{ model }}
where {{ column_name }} is not null
  and {{ column_name }} not in ({% for v in values %}'{{ v }}'{{ ", " if not loop.last }}{% endfor %})
{% endtest %}
