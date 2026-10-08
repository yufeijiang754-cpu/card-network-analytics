-- Q5 Deduplicate the raw feed: keep the first-arriving record per transaction_id, and report how many were removed
with ranked as (
    select transaction_id, loaded_at, transaction_ts,
           row_number() over (partition by transaction_id order by loaded_at, transaction_ts) as rn
    from intermediate.int_transactions__dq_flagged   -- 1:1 with the raw feed
)
select count(*) as raw_rows,
       sum(case when rn = 1 then 1 else 0 end) as deduplicated_rows,
       sum(case when rn > 1 then 1 else 0 end) as removed_duplicates
from ranked;
