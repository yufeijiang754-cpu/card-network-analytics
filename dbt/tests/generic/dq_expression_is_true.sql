{#- CONSISTENCY / VALIDITY: a row-level business rule must hold. Rows where the expression is NULL
    are ignored (missing inputs are reported by completeness checks). -#}
{% test dq_expression_is_true(model, expression, key_column, dimension="consistency", column_name=none) %}
{{ config(meta={'dq_dimension': dimension}) }}
select
    {{ key_column }} as record_key
from {{ model }}
where not ({{ expression }})
{% endtest %}
