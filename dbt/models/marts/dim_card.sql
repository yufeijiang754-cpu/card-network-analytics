-- Card dimension (tokenized; no PAN or personal data).
select
    c.card_id,
    c.issuer_id,
    c.home_country                  as card_country,
    c.card_type,
    c.card_product,
    c.credit_limit_usd,
    case
        when c.credit_limit_usd is null then 'n/a (debit)'
        when c.credit_limit_usd < 5000 then '< 5k'
        when c.credit_limit_usd < 15000 then '5k - 15k'
        else '15k+'
    end                             as credit_limit_band,
    c.card_open_date
from {{ ref('stg_cardholders') }} as c
