with source as (

    select * from {{ source('raw', 'issuers') }}

)

select
    cast(issuer_id as varchar)          as issuer_id,
    cast(issuer_name as varchar)        as issuer_name,
    upper(cast(country_code as varchar)) as country_code,
    cast(issuer_type as varchar)        as issuer_type,
    cast(asset_size_tier as varchar)    as asset_size_tier,
    cast(is_regulated_debit as boolean) as is_regulated_debit,
    cast(onboarded_date as date)        as onboarded_date
from source
