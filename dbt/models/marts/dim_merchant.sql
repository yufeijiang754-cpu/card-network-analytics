-- Merchant dimension: conformed merchant attributes incl. MCC classification and acquirer.
select
    m.merchant_id,
    m.merchant_name,
    m.mcc,
    coalesce(m.mcc_description, 'Unknown / invalid MCC') as mcc_description,
    m.mcc_category,
    m.mcc_risk_tier,
    m.is_valid_mcc,
    m.country_code                  as merchant_country,
    co.country_name                 as merchant_country_name,
    co.region                       as merchant_region,
    m.acquirer_id,
    a.acquirer_name,
    a.acquirer_type,
    m.onboarding_date
from {{ ref('int_merchants__classified') }} as m
left join {{ ref('stg_acquirers') }} as a  on m.acquirer_id = a.acquirer_id
left join {{ ref('countries') }}      as co on m.country_code = co.country_code
