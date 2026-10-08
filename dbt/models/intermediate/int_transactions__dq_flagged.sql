-- Every raw authorization record with explicit, rule-based data-quality flags and a
-- routing decision (dq_status). This is the single place where DQ policy is applied:
--   valid             -> passes all rules
--   repaired          -> had a fixable issue (currency format, missing decline reason) that was standardized
--   quarantined       -> blocking issue; excluded from marts, kept in dq.dq_transaction_quarantine
--   duplicate_dropped -> exact replay of an earlier message; dropped
{% set grace = var('dq_future_grace_minutes') %}

with txn as (

    select * from {{ ref('stg_transactions') }}

),

currencies as (

    select * from {{ ref('currencies') }}

),

-- Resolve alpha (USD), numeric (840) and symbol (US$) representations to ISO alpha codes.
currency_resolved as (

    select
        txn.*,
        coalesce(c_alpha.currency_code, c_num.currency_code, c_sym.currency_code) as currency_code
    from txn
    left join currencies as c_alpha on txn.currency_normalized = c_alpha.currency_code
    left join currencies as c_num   on txn.currency_normalized = c_num.numeric_code
    left join currencies as c_sym   on txn.currency_normalized = upper(c_sym.currency_symbol)

),

-- Duplicate analysis: an exact replay has identical business content; an id collision does not.
dup as (

    select
        *,
        row_number() over (partition by transaction_id order by loaded_at, transaction_ts) as id_occurrence,
        count(*) over (partition by transaction_id)                                         as id_count
    from (
        select
            *,
            md5(
                coalesce(cast(transaction_ts as varchar), '') || '|' || coalesce(card_id, '') || '|'
                || coalesce(merchant_id, '') || '|' || coalesce(cast(amount_local as varchar), '') || '|'
                || coalesce(currency_raw, '') || '|' || coalesce(auth_response_code, '')
            ) as content_hash
        from currency_resolved
    ) as hashed

),

dup_classified as (

    select
        *,
        min(content_hash) over (partition by transaction_id)
            <> max(content_hash) over (partition by transaction_id) as has_id_collision
    from dup

),

flagged as (

    select
        d.*,
        -- completeness
        (d.transaction_ts is null or d.card_id is null or d.merchant_id is null or d.amount_local is null
            or d.currency_raw is null or d.auth_response_code is null or d.channel is null
            or d.is_approved is null)                                                   as dq_missing_critical_field,
        coalesce(not d.is_approved and d.decline_reason_raw is null, false)            as dq_missing_decline_reason,
        -- uniqueness
        (d.id_count > 1 and not d.has_id_collision and d.id_occurrence > 1)             as dq_is_replay_copy,
        d.has_id_collision                                                              as dq_is_id_collision,
        -- validity
        coalesce(d.amount_local < 0, false)                                             as dq_negative_amount,
        (d.currency_raw is not null and d.currency_code is null)                        as dq_unrecognized_currency,
        coalesce(d.currency_code is not null and d.currency_raw <> d.currency_code, false) as dq_currency_reformatted,
        coalesce(d.channel not in ('card_present', 'card_not_present'), false)        as dq_invalid_channel,
        coalesce(d.is_approved <> (d.auth_response_code = '00'), false)               as dq_inconsistent_approval,
        -- timeliness
        coalesce(d.transaction_ts > {{ dbt.dateadd('minute', grace, 'd.loaded_at') }}, false) as dq_future_timestamp,
        -- referential integrity (NULL keys are a completeness problem, not an orphan)
        (d.merchant_id is not null and m.merchant_id is null)                           as dq_orphan_merchant,
        (d.card_id is not null and c.card_id is null)                                   as dq_orphan_card,
        (d.issuer_id is not null and i.issuer_id is null)                               as dq_orphan_issuer,
        (d.acquirer_id is not null and a.acquirer_id is null)                           as dq_orphan_acquirer,
        -- consistency across entities
        (c.card_id is not null and i.issuer_id is not null and c.issuer_id <> d.issuer_id) as dq_issuer_mismatch
    from dup_classified as d
    left join {{ ref('stg_merchants') }}   as m on d.merchant_id = m.merchant_id
    left join {{ ref('stg_cardholders') }} as c on d.card_id = c.card_id
    left join {{ ref('stg_issuers') }}     as i on d.issuer_id = i.issuer_id
    left join {{ ref('stg_acquirers') }}   as a on d.acquirer_id = a.acquirer_id

)

select
    transaction_id,
    transaction_ts,
    transaction_date,
    loaded_at,
    cast(loaded_at as date) as load_date,
    card_id,
    merchant_id,
    issuer_id,
    acquirer_id,
    amount_local,
    currency_raw,
    currency_code,
    channel,
    is_cross_border,
    auth_response_code,
    is_approved,
    decline_reason_raw,
    interchange_fee_local,
    is_fraud,
    is_chargeback,
    id_occurrence,
    id_count,
    dq_missing_critical_field,
    dq_missing_decline_reason,
    dq_is_replay_copy,
    dq_is_id_collision,
    dq_negative_amount,
    dq_unrecognized_currency,
    dq_currency_reformatted,
    dq_invalid_channel,
    dq_inconsistent_approval,
    dq_future_timestamp,
    dq_orphan_merchant,
    dq_orphan_card,
    dq_orphan_issuer,
    dq_orphan_acquirer,
    dq_issuer_mismatch,
    case
        when dq_is_replay_copy then 'duplicate_dropped'
        when dq_missing_critical_field or dq_is_id_collision or dq_negative_amount or dq_unrecognized_currency
            or dq_invalid_channel or dq_inconsistent_approval or dq_future_timestamp or dq_orphan_merchant
            or dq_orphan_card or dq_orphan_issuer or dq_orphan_acquirer or dq_issuer_mismatch
            then 'quarantined'
        when dq_currency_reformatted or dq_missing_decline_reason then 'repaired'
        else 'valid'
    end as dq_status,
    trim(
        case when dq_missing_critical_field then 'missing_critical_field ' else '' end
        || case when dq_missing_decline_reason then 'missing_decline_reason ' else '' end
        || case when dq_is_replay_copy then 'replay_duplicate ' else '' end
        || case when dq_is_id_collision then 'id_collision ' else '' end
        || case when dq_negative_amount then 'negative_amount ' else '' end
        || case when dq_unrecognized_currency then 'unrecognized_currency ' else '' end
        || case when dq_currency_reformatted then 'currency_reformatted ' else '' end
        || case when dq_invalid_channel then 'invalid_channel ' else '' end
        || case when dq_inconsistent_approval then 'inconsistent_approval ' else '' end
        || case when dq_future_timestamp then 'future_timestamp ' else '' end
        || case when dq_orphan_merchant then 'orphan_merchant ' else '' end
        || case when dq_orphan_card then 'orphan_card ' else '' end
        || case when dq_orphan_issuer then 'orphan_issuer ' else '' end
        || case when dq_orphan_acquirer then 'orphan_acquirer ' else '' end
        || case when dq_issuer_mismatch then 'issuer_mismatch ' else '' end
    ) as dq_issues
from flagged
