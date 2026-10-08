-- Q11 Top cross-border corridors (card country -> merchant region) by approved volume, with fraud loss bps
select c.card_country,
       m.merchant_region,
       count(*) as attempts,
       round(sum(f.approved_amount_usd), 0) as approved_usd,
       round(sum(f.fraud_loss_amount_usd) * 10000 / nullif(sum(f.approved_amount_usd), 0), 1) as fraud_loss_bps
from marts.fct_transactions f
join marts.dim_merchant m on f.merchant_id = m.merchant_id
join marts.dim_card c on f.card_id = c.card_id
where f.is_cross_border
group by 1, 2
order by approved_usd desc
limit 10;
