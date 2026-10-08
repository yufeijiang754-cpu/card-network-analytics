with source as (

    select * from {{ source('raw', 'acquirers') }}

)

select
    cast(acquirer_id as varchar)        as acquirer_id,
    cast(acquirer_name as varchar)      as acquirer_name,
    upper(cast(country_code as varchar)) as country_code,
    cast(acquirer_type as varchar)      as acquirer_type
from source
