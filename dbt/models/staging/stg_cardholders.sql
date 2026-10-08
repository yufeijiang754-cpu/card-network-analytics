with source as (

    select * from {{ source('raw', 'cardholders') }}

)

select
    cast(card_id as varchar)            as card_id,
    cast(issuer_id as varchar)          as issuer_id,
    upper(cast(home_country as varchar)) as home_country,
    cast(card_type as varchar)          as card_type,
    cast(card_product as varchar)       as card_product,
    cast(credit_limit as decimal(18, 2)) as credit_limit_usd,
    cast(card_open_date as date)        as card_open_date
from source
