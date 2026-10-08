-- Records excluded from the trusted marts, with the reasons why. This is the work
-- queue for data stewards / upstream teams (replay duplicates are dropped, not queued).
select
    transaction_id,
    load_date,
    loaded_at,
    transaction_ts,
    card_id,
    merchant_id,
    issuer_id,
    acquirer_id,
    amount_local,
    currency_raw,
    channel,
    auth_response_code,
    is_approved,
    dq_issues,
    case
        when dq_orphan_merchant or dq_orphan_card or dq_orphan_issuer or dq_orphan_acquirer or dq_issuer_mismatch
            then 'Reference data team / partner onboarding'
        when dq_is_id_collision then 'Network switch engineering'
        else 'Upstream feed owner'
    end as remediation_owner
from {{ ref('int_transactions__dq_flagged') }}
where dq_status = 'quarantined'
