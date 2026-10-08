{#- VALIDITY (domain): value must exist in an authoritative reference list (seed), e.g. ISO 18245
    MCC codes or supported currencies. Unlike referential integrity, the target is a code list,
    not a business entity. -#}
{% test dq_in_reference_list(model, column_name, to, field, key_column) %}
{{ config(meta={'dq_dimension': 'validity'}) }}
select
    src.{{ key_column }} as record_key,
    cast(src.{{ column_name }} as varchar) as failing_value
from {{ model }} as src
left join {{ to }} as ref
    on cast(src.{{ column_name }} as varchar) = cast(ref.{{ field }} as varchar)
where src.{{ column_name }} is not null
  and ref.{{ field }} is null
{% endtest %}
