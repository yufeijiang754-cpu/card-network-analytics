-- Row-level DQ rule results aggregated per daily load partition (ingestion date), one row
-- per load_date x check. Feeds the pass-rate trend chart of the Data Quality Monitor.
{% set checks = [
    ('completeness', 'missing_critical_field', 'dq_missing_critical_field'),
    ('completeness', 'missing_decline_reason', 'dq_missing_decline_reason'),
    ('uniqueness', 'replay_duplicate', 'dq_is_replay_copy'),
    ('uniqueness', 'id_collision', 'dq_is_id_collision'),
    ('validity', 'negative_amount', 'dq_negative_amount'),
    ('validity', 'unrecognized_currency', 'dq_unrecognized_currency'),
    ('validity', 'currency_format_nonstandard', 'dq_currency_reformatted'),
    ('validity', 'invalid_channel', 'dq_invalid_channel'),
    ('validity', 'inconsistent_approval_flag', 'dq_inconsistent_approval'),
    ('timeliness', 'future_event_timestamp', 'dq_future_timestamp'),
    ('referential_integrity', 'orphan_merchant', 'dq_orphan_merchant'),
    ('referential_integrity', 'orphan_card', 'dq_orphan_card'),
    ('referential_integrity', 'orphan_issuer', 'dq_orphan_issuer'),
    ('referential_integrity', 'orphan_acquirer', 'dq_orphan_acquirer'),
    ('consistency', 'issuer_card_mismatch', 'dq_issuer_mismatch'),
] %}

{% for dimension, check, flag in checks %}
select
    load_date,
    '{{ dimension }}'                                   as dq_dimension,
    '{{ check }}'                                       as check_name,
    count(*)                                            as total_rows,
    sum({{ bool_to_int(flag) }})                        as failed_rows,
    1 - {{ safe_divide("sum(" ~ bool_to_int(flag) ~ ")", "count(*)") }} as pass_rate
from {{ ref('int_transactions__dq_flagged') }}
group by load_date
{% if not loop.last %}union all{% endif %}
{% endfor %}
