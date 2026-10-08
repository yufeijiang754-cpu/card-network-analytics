{#- Use the custom schema name as-is (staging, intermediate, marts, dq, ...) instead of
    dbt's default "<target_schema>_<custom>" concatenation. Keeps schema names identical
    across DuckDB and Snowflake, which simplifies BI connections and documentation. -#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
