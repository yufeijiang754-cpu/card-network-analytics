-- Merchants enriched with ISO 18245 MCC reference data. Merchants whose MCC is
-- not in the reference list are KEPT (their transactions are real) but classified
-- as 'Unclassified' and flagged for the merchant data steward.
select
    m.merchant_id,
    m.merchant_name,
    m.mcc,
    mcc.mcc_description,
    coalesce(mcc.mcc_category, 'Unclassified')  as mcc_category,
    coalesce(mcc.risk_tier, 'unknown')           as mcc_risk_tier,
    mcc.mcc is not null                          as is_valid_mcc,
    m.country_code,
    m.acquirer_id,
    m.onboarding_date
from {{ ref('stg_merchants') }} as m
left join {{ ref('mcc_codes') }} as mcc
    on m.mcc = mcc.mcc
