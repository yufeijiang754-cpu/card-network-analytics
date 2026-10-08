# Data Quality Detection Report

_Generated 2026-10-07 22:12:55 by `dq/compare_answer_key.py` from the latest dbt test artifacts. Synthetic data._

## Summary

- Injected defects (answer key): **41,900**
- Detected by the test designed for that defect: **41,472**  ->  overall recall **98.98%**
- Missed: **428** (all explained below)
- Raw-layer tests flagging 0 records outside the answer key: **19/19** (precision 100.00% overall)

## Expectations

| Expectation | Result |
|---|---|
| injected 'currency_format' is flagged by >=1 raw-layer test (status=warn) | PASS |
| injected 'duplicate_transaction_id' is flagged by >=1 raw-layer test (status=warn) | PASS |
| injected 'future_timestamp' is flagged by >=1 raw-layer test (status=warn) | PASS |
| injected 'invalid_mcc' is flagged by >=1 raw-layer test (status=warn) | PASS |
| injected 'negative_amount' is flagged by >=1 raw-layer test (status=warn) | PASS |
| injected 'null_value' is flagged by >=1 raw-layer test (status=warn) | PASS |
| injected 'orphan_foreign_key' is flagged by >=1 raw-layer test (status=warn) | PASS |
| all 44 trusted-layer tests (intermediate/marts/dq/seeds) pass | PASS |
| no test errored | PASS |
| every miss has an explanation | PASS |
| overall recall >= 98% | PASS |

## Recall by injected issue

| dq_dimension          | table_name   | issue_type               | column_name        |   injected |   detected | recall   |
|:----------------------|:-------------|:-------------------------|:-------------------|-----------:|-----------:|:---------|
| validity              | merchants    | invalid_mcc              | mcc                |        300 |        300 | 100.00%  |
| validity              | transactions | currency_format          | currency           |       6000 |       6000 | 100.00%  |
| uniqueness            | transactions | duplicate_transaction_id | transaction_id     |       5600 |       5600 | 100.00%  |
| timeliness            | transactions | future_timestamp         | timestamp          |       4000 |       3572 | 89.30%   |
| validity              | transactions | negative_amount          | amount             |       4000 |       4000 | 100.00%  |
| completeness          | transactions | null_value               | amount             |       3000 |       3000 | 100.00%  |
| completeness          | transactions | null_value               | auth_response_code |       1200 |       1200 | 100.00%  |
| completeness          | transactions | null_value               | card_id            |       2000 |       2000 | 100.00%  |
| completeness          | transactions | null_value               | channel            |        800 |        800 | 100.00%  |
| completeness          | transactions | null_value               | currency           |       1200 |       1200 | 100.00%  |
| completeness          | transactions | null_value               | decline_reason     |        800 |        800 | 100.00%  |
| completeness          | transactions | null_value               | merchant_id        |       2000 |       2000 | 100.00%  |
| completeness          | transactions | null_value               | timestamp          |       1000 |       1000 | 100.00%  |
| referential_integrity | transactions | orphan_foreign_key       | acquirer_id        |       1000 |       1000 | 100.00%  |
| referential_integrity | transactions | orphan_foreign_key       | card_id            |       2400 |       2400 | 100.00%  |
| referential_integrity | transactions | orphan_foreign_key       | issuer_id          |       1600 |       1600 | 100.00%  |
| referential_integrity | transactions | orphan_foreign_key       | merchant_id        |       5000 |       5000 | 100.00%  |

## Precision by test

`flagged_other_injected_defect` = the record is defective, but under a different injected issue type (would indicate a test with overlapping scope). `unexplained_flags` = records not in the answer key at all, i.e. true false positives.

| test_type                | table_name   | column_name        | target_issue             |   flagged_records |   true_positives |   flagged_other_injected_defect |   unexplained_flags | precision   |
|:-------------------------|:-------------|:-------------------|:-------------------------|------------------:|-----------------:|--------------------------------:|--------------------:|:------------|
| dq_in_reference_list     | merchants    | mcc                | invalid_mcc              |               300 |              300 |                               0 |                   0 | 100.00%     |
| dq_in_reference_list     | transactions | currency           | currency_format          |              6000 |             6000 |                               0 |                   0 | 100.00%     |
| dq_matches_pattern       | merchants    | mcc                | invalid_mcc              |               201 |              201 |                               0 |                   0 | 100.00%     |
| dq_matches_pattern       | transactions | currency           | currency_format          |              6000 |             6000 |                               0 |                   0 | 100.00%     |
| dq_not_in_future         | transactions | timestamp          | future_timestamp         |              3572 |             3572 |                               0 |                   0 | 100.00%     |
| dq_not_null              | transactions | amount             | null_value               |              3000 |             3000 |                               0 |                   0 | 100.00%     |
| dq_not_null              | transactions | auth_response_code | null_value               |              1200 |             1200 |                               0 |                   0 | 100.00%     |
| dq_not_null              | transactions | card_id            | null_value               |              2000 |             2000 |                               0 |                   0 | 100.00%     |
| dq_not_null              | transactions | channel            | null_value               |               800 |              800 |                               0 |                   0 | 100.00%     |
| dq_not_null              | transactions | currency           | null_value               |              1200 |             1200 |                               0 |                   0 | 100.00%     |
| dq_not_null              | transactions | decline_reason     | null_value               |               800 |              800 |                               0 |                   0 | 100.00%     |
| dq_not_null              | transactions | merchant_id        | null_value               |              2000 |             2000 |                               0 |                   0 | 100.00%     |
| dq_not_null              | transactions | timestamp          | null_value               |              1000 |             1000 |                               0 |                   0 | 100.00%     |
| dq_referential_integrity | transactions | acquirer_id        | orphan_foreign_key       |              1000 |             1000 |                               0 |                   0 | 100.00%     |
| dq_referential_integrity | transactions | card_id            | orphan_foreign_key       |              2400 |             2400 |                               0 |                   0 | 100.00%     |
| dq_referential_integrity | transactions | issuer_id          | orphan_foreign_key       |              1600 |             1600 |                               0 |                   0 | 100.00%     |
| dq_referential_integrity | transactions | merchant_id        | orphan_foreign_key       |              5000 |             5000 |                               0 |                   0 | 100.00%     |
| dq_unique                | transactions | transaction_id     | duplicate_transaction_id |              5600 |             5600 |                               0 |                   0 | 100.00%     |
| dq_value_in_range        | transactions | amount             | negative_amount          |              4000 |             4000 |                               0 |                   0 | 100.00%     |

## Why were defects missed?

| issue_type       | reason                                                                                                                                                                                |   missed |
|:-----------------|:--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------:|
| future_timestamp | Event time is only <1-4 min> ahead of ingestion time: inside the 5-minute grace window that tolerates terminal clock drift. Missed by design (trade-off: false positives vs. recall). |      428 |

## Coverage notes (format check vs. domain check)

The MCC **format** check (`[0-9]{4}`) cannot catch codes like `0000` or `1234`. They are well-formed but do not exist in ISO 18245. Those are caught only by the **reference-list** check, which is why both layers exist. Per-test catch counts:

| test_type            | column_name   | target_issue    |   true_positives |
|:---------------------|:--------------|:----------------|-----------------:|
| dq_in_reference_list | mcc           | invalid_mcc     |              300 |
| dq_in_reference_list | currency      | currency_format |             6000 |
| dq_matches_pattern   | mcc           | invalid_mcc     |              201 |
| dq_matches_pattern   | currency      | currency_format |             6000 |

## Timeliness grace-window sensitivity

Recall of the future-timestamp check under different clock-skew tolerances. A smaller window catches more injected skew. In production it would also flag legitimate terminals with drifting clocks, which this synthetic data does not model, so the window is a business decision, not a purely technical one.

|   grace_minutes |   injected |   detected | recall   |
|----------------:|-----------:|-----------:|:---------|
|               0 |       4000 |       4000 | 100.00%  |
|               1 |       4000 |       4000 | 100.00%  |
|               2 |       4000 |       3850 | 96.25%   |
|               5 |       4000 |       3572 | 89.30%   |
|              10 |       4000 |       3572 | 89.30%   |
|              60 |       4000 |       3572 | 89.30%   |
