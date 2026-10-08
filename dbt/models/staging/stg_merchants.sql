with source as (

    select * from {{ source('raw', 'merchants') }}

)

select
    cast(merchant_id as varchar)        as merchant_id,
    cast(merchant_name as varchar)      as merchant_name,
    trim(cast(mcc as varchar))          as mcc,
    upper(cast(country_code as varchar)) as country_code,
    cast(acquirer_id as varchar)        as acquirer_id,
    cast(onboarding_date as date)       as onboarding_date
from source
