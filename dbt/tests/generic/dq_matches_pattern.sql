{#- VALIDITY (format): value must fully match a regular expression, e.g. ISO 4217 '[A-Z]{3}'.
    Use character classes like [0-9] rather than \d so the pattern is portable to Snowflake. -#}
{% test dq_matches_pattern(model, column_name, pattern, key_column) %}
{{ config(meta={'dq_dimension': 'validity'}) }}
select
    {{ key_column }} as record_key,
    cast({{ column_name }} as varchar) as failing_value
from {{ model }}
where {{ column_name }} is not null
  and not {{ regex_full_match(column_name, pattern) }}
{% endtest %}
