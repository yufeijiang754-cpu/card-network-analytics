-- Issuer dimension with portfolio size (cards on file) for normalisation of metrics.
with cards as (

    select
        issuer_id,
        count(*)                                                         as cards_on_file,
        sum({{ bool_to_int("card_type = 'Credit'") }})                   as credit_cards_on_file,
        sum({{ bool_to_int("card_type = 'Debit'") }})                    as debit_cards_on_file
    from {{ ref('stg_cardholders') }}
    group by issuer_id

)

select
    i.issuer_id,
    i.issuer_name,
    i.country_code                  as issuer_country,
    co.country_name                 as issuer_country_name,
    co.region                       as issuer_region,
    i.issuer_type,
    i.asset_size_tier,
    i.is_regulated_debit,
    i.onboarded_date,
    coalesce(c.cards_on_file, 0)        as cards_on_file,
    coalesce(c.credit_cards_on_file, 0) as credit_cards_on_file,
    coalesce(c.debit_cards_on_file, 0)  as debit_cards_on_file
from {{ ref('stg_issuers') }} as i
left join cards as c           on i.issuer_id = c.issuer_id
left join {{ ref('countries') }} as co on i.country_code = co.country_code
