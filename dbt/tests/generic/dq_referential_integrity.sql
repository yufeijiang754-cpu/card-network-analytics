{#- REFERENTIAL INTEGRITY: every non-null foreign key must exist in the parent entity.
    Returns the child record key (not just the orphan value) so each failure is traceable. -#}
{% test dq_referential_integrity(model, column_name, to, field, key_column) %}
{{ config(meta={'dq_dimension': 'referential_integrity'}) }}
select
    child.{{ key_column }} as record_key,
    child.{{ column_name }} as orphan_value
from {{ model }} as child
left join {{ to }} as parent
    on child.{{ column_name }} = parent.{{ field }}
where child.{{ column_name }} is not null
  and parent.{{ field }} is null
{% endtest %}
