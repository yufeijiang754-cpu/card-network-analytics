# Design Decisions Log

Assumptions and judgment calls made while building this project, with the
reasoning behind each. All data in this repository is **synthetic**.

## Stage 1 - Synthetic data generation

| ID | Decision | Rationale |
|----|----------|-----------|
| D-01 | Simulate **calendar year 2025** (UTC timestamps, no time-zone modelling). | One full year is enough to show seasonality, holidays, and month-over-month trends. Time-zone handling would add complexity without adding analytical value. |
| D-02 | Dimension sizes are fixed (45 issuers, 15 acquirers, 20k merchants, 150k cards) and **do not scale** with `--rows`. | Scaling only the fact table keeps the 2M and 50M datasets comparable and makes the Spark benchmark measure fact-table volume only. |
| D-03 | Generation is **chunked** (default 2M rows per chunk). Each chunk uses its own RNG stream, `default_rng([seed, chunk_idx])`. | Memory stays bounded on an 8 GB laptop when generating 50M rows, and each chunk is still reproducible. |
| D-04 | `amount` and `interchange_fee` are in **transaction (merchant) currency**. USD conversion happens in dbt using a static FX seed. | This mirrors real authorization messages, which carry the transaction currency. It also gives the currency-format DQ issue a real downstream effect, because FX joins fail on badly formatted currency codes. |
| D-05 | Added a `_loaded_at` ingestion-metadata column (event time + about 90 s average latency). | Timeliness needs a reference point. "Future timestamp" means **event time later than ingestion time**, which is physically impossible. That is more meaningful than comparing against wall-clock time for a historical dataset. |
| D-06 | Each transaction gets **at most one** injected defect. | Each detection or miss traces back to exactly one cause, so recall and precision per issue type are clean. |
| D-07 | `transaction_id` is never nulled. | It is the record locator for the answer key. Primary-key completeness is still tested in dbt. |
| D-08 | Two duplicate flavours: **exact replay** (same message re-delivered later) and **ID collision** (a different authorization reuses an id). | They need different remediations. Replays are safe to dedupe; collisions mean upstream ID generation is broken and data is lost, so they must be escalated. |
| D-09 | About 10% of future-timestamp defects are a small **1-4 minute clock skew**. | This is realistic (terminal clocks drift) and deliberately sits inside the timeliness check's 5-minute grace window. It produces explainable misses in the detection report. |
| D-10 | Invalid MCCs are injected into **merchants** (1.5% of merchants), not into transactions. | MCC is a merchant attribute assigned by the acquirer. The defect lives in reference data and spreads to every transaction at that merchant. |
| D-11 | `is_fraud` marks **all fraudulent attempts**, including ones the issuer declined. Fraud loss metrics use approved fraud only. | This lets the analysis separate fraud *attempt* rate (risk exposure) from fraud *loss* rate (what got through). |
| D-12 | Christmas Day volume is set **below** normal (x0.85), while all other holidays are above. | Most physical stores close on Dec 25. Holidays on average are still higher volume, as required. |
| D-13 | Interchange uses **illustrative** rates: category base + product uplift + CNP and cross-border uplifts, with the US Reg II (Durbin) cap for regulated debit (0.05% + $0.22). | Close enough to real published schedules to support a realistic "interchange revenue mix" analysis, and clearly labelled as not any network's actual rates. |
| D-14 | Planted business scenarios: (1) a **card-testing attack** on 6 digital-goods merchants of payment facilitator ACQ009, 18-20 Sep; (2) an **issuer outage** at ISS012 on 14 Jun, 14:00-17:00; (3) issuer ISS007 with **over-tuned CNP fraud rules**; (4) 25 **high-chargeback merchants**. | These give the analysis layer real signals to find, so the insights read like monitoring findings rather than restated generator parameters. They are documented here for transparency. |
