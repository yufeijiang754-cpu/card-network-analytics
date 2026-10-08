-- Q10 Issuers in the bottom decile of CNP approval rate (min 2,000 CNP attempts)
with i as (
    select issuer_id,
           count(*) as cnp_attempts,
           avg(case when is_approved then 1.0 else 0 end) as cnp_approval_rate
    from marts.fct_transactions
    where channel = 'card_not_present'
    group by issuer_id
    having count(*) >= 2000
)
select issuer_id, cnp_attempts, round(cnp_approval_rate, 4) as cnp_approval_rate
from (select *, ntile(10) over (order by cnp_approval_rate) as decile from i) t
where decile = 1
order by cnp_approval_rate;
