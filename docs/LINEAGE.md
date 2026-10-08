# Data Lineage

Auto-generated from `dbt/target/manifest.json` by `scripts/export_lineage.py`. For the interactive
version with column-level documentation run `make docs` (dbt docs serve).

Colour key: red = raw sources, grey = reference seeds, blue = staging, yellow = intermediate,
purple = data quality, green = marts.

```mermaid
flowchart LR
    n0["agg_daily_network_metrics"]:::marts
    n1["agg_mcc_metrics"]:::marts
    n2["dim_acquirer"]:::marts
    n3["dim_card"]:::marts
    n4["dim_date"]:::marts
    n5["dim_issuer"]:::marts
    n6["dim_merchant"]:::marts
    n7["dq_daily_partition_metrics"]:::dq
    n8["dq_transaction_quarantine"]:::dq
    n9["fct_transactions"]:::marts
    n10["int_merchants__classified"]:::intermediate
    n11["int_transactions__dq_flagged"]:::intermediate
    n12["int_transactions__enriched"]:::intermediate
    n13["stg_acquirers"]:::staging
    n14["stg_cardholders"]:::staging
    n15["stg_issuers"]:::staging
    n16["stg_merchants"]:::staging
    n17["stg_transactions"]:::staging
    n18["auth_response_codes"]:::seed
    n19["countries"]:::seed
    n20["currencies"]:::seed
    n21["mcc_codes"]:::seed
    n22["us_holidays"]:::seed
    n23["raw.acquirers"]:::source
    n24["raw.cardholders"]:::source
    n25["raw.issuers"]:::source
    n26["raw.merchants"]:::source
    n27["raw.transactions"]:::source
    n23 --> n13
    n27 --> n17
    n24 --> n14
    n26 --> n16
    n25 --> n15
    n11 --> n7
    n11 --> n8
    n10 --> n6
    n13 --> n6
    n19 --> n6
    n14 --> n3
    n13 --> n2
    n9 --> n1
    n9 --> n0
    n22 --> n4
    n12 --> n9
    n14 --> n5
    n15 --> n5
    n19 --> n5
    n16 --> n10
    n21 --> n10
    n17 --> n11
    n20 --> n11
    n16 --> n11
    n14 --> n11
    n15 --> n11
    n13 --> n11
    n11 --> n12
    n10 --> n12
    n14 --> n12
    n15 --> n12
    n20 --> n12
    n18 --> n12
    classDef source fill:#fde2e2,stroke:#c0392b
    classDef seed fill:#eeeeee,stroke:#7f8c8d
    classDef staging fill:#e3f2fd,stroke:#1e88e5
    classDef intermediate fill:#fff8e1,stroke:#f9a825
    classDef marts fill:#e8f5e9,stroke:#43a047
    classDef dq fill:#f3e5f5,stroke:#8e24aa
```
