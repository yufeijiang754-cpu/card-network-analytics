{#- UNIQUENESS: the combination of `columns` must identify at most one row (grain check). -#}
{% test dq_unique_combination(model, columns) %}
{{ config(meta={'dq_dimension': 'uniqueness'}) }}
select
    {{ columns | join(', ') }},
    count(*) as duplicate_count
from {{ model }}
group by {{ columns | join(', ') }}
having count(*) > 1
{% endtest %}
