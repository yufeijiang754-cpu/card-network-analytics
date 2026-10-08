-- Acquirer dimension.
select
    a.acquirer_id,
    a.acquirer_name,
    a.country_code                  as acquirer_country,
    a.acquirer_type
from {{ ref('stg_acquirers') }} as a
