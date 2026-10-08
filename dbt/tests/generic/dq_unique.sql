{#- UNIQUENESS: each non-null value may appear only once. Returns one row per duplicated value. -#}
{% test dq_unique(model, column_name) %}
{{ config(meta={'dq_dimension': 'uniqueness'}) }}
select
    {{ column_name }} as record_key,
    count(*) as occurrences
from {{ model }}
where {{ column_name }} is not null
group by {{ column_name }}
having count(*) > 1
{% endtest %}
