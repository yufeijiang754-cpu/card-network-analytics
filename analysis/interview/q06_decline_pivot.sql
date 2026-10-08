-- Q6 Decline-reason share by channel (pivot with conditional aggregation)
select decline_reason,
       round(sum(case when channel = 'card_present' then 1 else 0 end) * 1.0
             / sum(sum(case when channel = 'card_present' then 1 else 0 end)) over (), 4) as cp_share,
       round(sum(case when channel = 'card_not_present' then 1 else 0 end) * 1.0
             / sum(sum(case when channel = 'card_not_present' then 1 else 0 end)) over (), 4) as cnp_share
from marts.fct_transactions
where not is_approved
group by decline_reason
order by cnp_share desc;
