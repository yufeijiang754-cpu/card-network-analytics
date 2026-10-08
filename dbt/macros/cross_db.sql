{#- Small cross-database helpers so the same models run on DuckDB (dev) and Snowflake. -#}

{# Full-string regular-expression match -> boolean #}
{% macro regex_full_match(expr, pattern) -%}
    {{ return(adapter.dispatch('regex_full_match', 'card_network')(expr, pattern)) }}
{%- endmacro %}
{% macro default__regex_full_match(expr, pattern) -%}
    regexp_like({{ expr }}, '{{ pattern }}')
{%- endmacro %}
{% macro duckdb__regex_full_match(expr, pattern) -%}
    regexp_full_match({{ expr }}, '{{ pattern }}')
{%- endmacro %}

{# ISO day of week: Monday = 1 ... Sunday = 7 #}
{% macro iso_day_of_week(expr) -%}
    {{ return(adapter.dispatch('iso_day_of_week', 'card_network')(expr)) }}
{%- endmacro %}
{% macro default__iso_day_of_week(expr) -%}
    dayofweekiso({{ expr }})
{%- endmacro %}
{% macro duckdb__iso_day_of_week(expr) -%}
    isodow({{ expr }})
{%- endmacro %}

{# Integer sequence 0..n-1 without warehouse-specific generators (cross-joined digits). #}
{% macro integer_sequence(n) -%}
    {%- set digits = (n | string) | length -%}
    with d as (
        select 0 as x union all select 1 union all select 2 union all select 3 union all select 4
        union all select 5 union all select 6 union all select 7 union all select 8 union all select 9
    )
    select
        {% for i in range(digits) -%}
        d{{ i }}.x * {{ 10 ** i }}{{ " + " if not loop.last }}
        {%- endfor %} as n
    from {% for i in range(digits) -%}
        d as d{{ i }}{{ ", " if not loop.last }}
    {%- endfor %}
{%- endmacro %}

{# Safe ratio: NULL when the denominator is zero #}
{% macro safe_divide(numerator, denominator) -%}
    ({{ numerator }}) / nullif({{ denominator }}, 0)
{%- endmacro %}

{# 1 / 0 indicator from a boolean expression (portable: Snowflake cannot always cast boolean->int) #}
{% macro bool_to_int(expr) -%}
    case when {{ expr }} then 1 else 0 end
{%- endmacro %}
