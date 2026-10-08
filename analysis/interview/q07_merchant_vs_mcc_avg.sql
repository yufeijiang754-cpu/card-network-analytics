-- Q7 Merchants (>= 200 approved) whose chargeback rate is more than 3x their MCC's average
with m as (
    select merchant_id, mcc,
           sum(case when is_approved then 1 else 0 end) as approved,
           sum(case when is_chargeback then 1 else 0 end) as chargebacks
    from marts.fct_transactions
    group by 1, 2
)
select merchant_id, mcc, approved, chargebacks,
       round(chargebacks * 1.0 / approved, 4) as cb_rate,
       round(avg(chargebacks * 1.0 / approved) over (partition by mcc), 4) as mcc_avg_cb_rate
from m
where approved >= 200
qualify chargebacks * 1.0 / approved > 3 * avg(chargebacks * 1.0 / approved) over (partition by mcc)
order by cb_rate desc;
