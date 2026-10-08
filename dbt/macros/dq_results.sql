{#-
    Data-quality results log.
    on-run-start  -> create_dq_results_table(): makes sure <db>.dq.dq_results exists
    on-run-end    -> log_dq_results(results):   appends one row per executed data test with
                                                 dimension, failed rows, total rows, pass rate and
                                                 threshold status
    Works on DuckDB and Snowflake (plain ANSI DDL/DML).
-#}

{% macro dq_results_relation() -%}
    {{ target.database }}.dq.dq_results
{%- endmacro %}

{% macro create_dq_results_table() %}
    create schema if not exists {{ target.database }}.dq;
    create table if not exists {{ dq_results_relation() }} (
        run_id             varchar,
        run_started_at     timestamp,
        run_date           date,
        model              varchar,
        dimension          varchar,
        check_name         varchar,
        test_node_name     varchar,
        test_type          varchar,
        column_name        varchar,
        severity           varchar,
        status             varchar,
        failed_rows        bigint,
        total_rows         bigint,
        pass_rate          double,
        threshold          double,
        threshold_status   varchar,
        failures_relation  varchar,
        execution_seconds  double
    );
{% endmacro %}

{# Map built-in dbt tests to a DQ dimension; custom dq_* tests declare meta.dq_dimension. #}
{% macro _dq_dimension_for(node) %}
    {%- set builtin = {
        'not_null': 'completeness', 'unique': 'uniqueness', 'accepted_values': 'validity',
        'relationships': 'referential_integrity'} -%}
    {%- set meta_dim = node.config.meta.get('dq_dimension') if node.config.meta else none -%}
    {%- set test_name = node.test_metadata.name if node.test_metadata else 'singular' -%}
    {{- return(meta_dim or builtin.get(test_name, 'other')) -}}
{% endmacro %}

{# Resolve the tested relation (model or source) and a readable name for it.
   Model tests carry attached_node. Source tests do not, and relationship-style tests depend on
   two sources, so the tested source is parsed from the test's `model` kwarg,
   e.g. "{{ get_where_subquery(source('raw', 'transactions')) }}". #}
{% macro _dq_tested_relation(node) %}
    {%- set uid = node.attached_node -%}
    {%- if not uid -%}
        {%- set model_kw = node.test_metadata.kwargs.get('model', '') if node.test_metadata else '' -%}
        {%- if "source(" in model_kw -%}
            {%- set parts = model_kw.split("source(")[1].split(")")[0].split("'") -%}
            {%- set uid = 'source.' ~ project_name ~ '.' ~ parts[1] ~ '.' ~ parts[3] -%}
        {%- else -%}
            {%- set uid = node.depends_on.nodes | first -%}
        {%- endif -%}
    {%- endif -%}
    {%- if uid.startswith('source.') -%}
        {%- set n = graph.sources[uid] -%}
        {{- return({'name': n.source_name ~ '.' ~ n.name, 'relation': n.relation_name}) -}}
    {%- else -%}
        {%- set n = graph.nodes[uid] -%}
        {{- return({'name': n.name, 'relation': n.relation_name}) -}}
    {%- endif -%}
{% endmacro %}

{% macro log_dq_results(results) %}
    {% if not execute %}{{ return('') }}{% endif %}
    {% set test_results = results | selectattr('node.resource_type', 'equalto', 'test') | list %}
    {% if test_results | length == 0 %}{{ return('') }}{% endif %}

    {% set thresholds = var('dq_thresholds', {}) %}
    {% set row_counts = {} %}
    {% set values = [] %}
    {% for res in test_results %}
        {% set node = res.node %}
        {% set tested = _dq_tested_relation(node) %}
        {% if tested.relation not in row_counts %}
            {% set q = run_query('select count(*) from ' ~ tested.relation) %}
            {% do row_counts.update({tested.relation: q.columns[0].values()[0]}) %}
        {% endif %}
        {% set total = row_counts[tested.relation] | int %}
        {% set failed = (res.failures if res.failures is not none else 0) | int %}
        {% set dimension = _dq_dimension_for(node) %}
        {% set pass_rate = (1 - failed / total) if total > 0 else 1 %}
        {% set threshold = node.config.meta.get('dq_threshold', thresholds.get(dimension, 1.0)) if node.config.meta else thresholds.get(dimension, 1.0) %}
        {% if res.status == 'error' %}
            {% set threshold_status = 'ERROR' %}
        {% elif pass_rate >= threshold %}
            {% set threshold_status = 'WITHIN_THRESHOLD' %}
        {% else %}
            {% set threshold_status = 'BREACH' %}
        {% endif %}
        {% set test_type = node.test_metadata.name if node.test_metadata else 'singular' %}
        {% set column_name = node.column_name or '' %}
        {% set check_name = test_type ~ ((':' ~ column_name) if column_name else '') %}
        {% set row %}
        ('{{ invocation_id }}', cast('{{ run_started_at.strftime("%Y-%m-%d %H:%M:%S") }}' as timestamp),
         cast('{{ run_started_at.strftime("%Y-%m-%d") }}' as date),
         '{{ tested.name }}', '{{ dimension }}', '{{ check_name }}', '{{ node.name }}', '{{ test_type }}', '{{ column_name }}',
         '{{ node.config.severity | lower }}', '{{ res.status }}', {{ failed }}, {{ total }},
         {{ pass_rate }}, {{ threshold }}, '{{ threshold_status }}',
         '{{ (node.relation_name or "") | replace("'", "''") }}', {{ res.execution_time | round(3) }})
        {% endset %}
        {% do values.append(row) %}
    {% endfor %}

    {% set insert_sql %}
        insert into {{ dq_results_relation() }}
        (run_id, run_started_at, run_date, model, dimension, check_name, test_node_name, test_type, column_name, severity,
         status, failed_rows, total_rows, pass_rate, threshold, threshold_status, failures_relation,
         execution_seconds)
        values {{ values | join(',\n') }}
    {% endset %}
    {% do run_query(insert_sql) %}
    {% do log("dq_results: logged " ~ (values | length) ~ " test results to " ~ dq_results_relation(), info=true) %}
    {{ return('') }}
{% endmacro %}
