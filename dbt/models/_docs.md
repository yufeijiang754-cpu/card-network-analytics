{% docs __overview__ %}
# Card Payment Network Analytics & Data Quality Platform

A portfolio project that models the **authorization data of a card payment network**
(issuers, acquirers, merchants, cards) end to end: raw feed -> data-quality controls -> trusted
star schema -> KPIs. **All data is synthetic.**

**Layers**
- `raw` (sources): untrusted network-switch extracts (Parquet on DuckDB / RAW tables on Snowflake)
- `staging`: 1:1 renames and casts, no filtering
- `intermediate`: DQ rule evaluation and routing (`int_transactions__dq_flagged`), enrichment
- `marts`: star schema (`fct_transactions` + dims) and aggregates for BI
- `dq`: quarantine queue and per-partition DQ metrics; `dq.dq_results` holds per-run test results

Use the lineage graph (bottom-right button) to trace any KPI back to its raw source.
{% enddocs %}

{% docs approval_rate %}
**Authorization approval rate** = approved authorizations / all authorization attempts
(count-based). Approved means ISO 8583 response code `00`. A key network health KPI: declines
cost merchants sales and cardholders trust. Low approval rates can come from cardholder
behaviour (insufficient funds), issuer risk policy (false declines) or technical failures.
{% enddocs %}

{% docs fraud_loss_rate_bps %}
**Fraud loss rate (basis points)** = USD amount of *approved* transactions later confirmed
fraudulent / total approved USD amount x 10,000. 1 bp = 0.01%. This is the standard
industry way to express fraud losses relative to sales volume. Declined fraud attempts are
excluded because they caused no loss.
{% enddocs %}

{% docs chargeback_rate %}
**Chargeback rate** = approved transactions later disputed (chargeback raised) / approved
transactions (count-based). Networks monitor merchants whose chargeback rate exceeds about
0.9-1% and place them in excessive-chargeback programs.
{% enddocs %}

{% docs interchange_fee_usd %}
**Interchange fee (USD)**: fee paid by the acquirer (and ultimately the merchant) to the
issuer for each approved transaction, converted to USD with the static FX table. It is set by
network rate schedules and varies by MCC, card product, channel (CNP is higher), cross-border
status, and for US debit by whether the issuer is regulated under Reg II (Durbin cap
0.05% + $0.21 + $0.01 fraud adjustment). Zero for declined transactions. Rates are illustrative.
{% enddocs %}

{% docs effective_interchange_rate %}
**Effective interchange rate** = interchange fee USD / approved amount USD. The blended "all-in"
percentage the issuer earns on sales volume, including the fixed per-transaction component.
{% enddocs %}

{% docs channel %}
**Channel**: `card_present` (CP) means the physical card was at a terminal (chip, swipe,
contactless). `card_not_present` (CNP) covers e-commerce, in-app, phone and mail order. CNP
lacks EMV chip cryptograms, so it carries much higher fraud risk and higher interchange.
{% enddocs %}

{% docs is_cross_border %}
**Cross-border**: true when the card's issuing country differs from the merchant's country.
Cross-border transactions carry extra network assessments and FX, and show higher decline
and fraud rates.
{% enddocs %}

{% docs mcc %}
**Merchant Category Code (ISO 18245)**: 4-digit code assigned by the acquirer that classifies
the merchant's line of business (e.g. 5411 grocery, 5812 restaurants, 4511 airlines). It
drives interchange category, risk rules and rewards. Codes not in the reference list are
treated as invalid and roll up to the category 'Unclassified'.
{% enddocs %}

{% docs mcc_category %}
Business grouping of MCCs used for reporting (Grocery, Dining, Fuel, Travel, Transportation,
Retail, E-commerce, Digital Goods, Subscriptions, Health, Utilities, Gambling). 'Unclassified'
means the merchant's MCC failed validation.
{% enddocs %}

{% docs auth_response_code %}
ISO 8583 field 39 style **authorization response code** returned by the issuer: `00` approved,
`51` insufficient funds, `05` do not honor, `61` exceeds limit, `54` expired card,
`55` incorrect PIN, `57` not permitted, `14` invalid card number, `91` issuer unavailable,
`59` suspected fraud.
{% enddocs %}

{% docs decline_type %}
**Soft** declines are temporary conditions that may succeed on retry (51, 61, 05, 91, 55).
**Hard** declines should not be retried (14, 54, 57, 59). The split matters for merchant retry
logic and for network rules that limit excessive retries.
{% enddocs %}

{% docs is_fraud %}
True when the transaction was later confirmed fraudulent (fraud reported by the cardholder or
issuer). Includes declined attempts, so *fraud attempt rate* = is_fraud / all attempts, while
*fraud loss* uses only approved fraudulent transactions.
{% enddocs %}

{% docs is_chargeback %}
True when an approved transaction was later disputed and a chargeback was raised against the
merchant (fraud or non-fraud reason codes).
{% enddocs %}

{% docs dq_status %}
Routing decision of the data-quality layer:
`valid` passed all rules; `repaired` had a fixable issue (non-standard currency format,
missing decline reason) that was standardized; `quarantined` had a blocking issue and is
excluded from marts; `duplicate_dropped` is an exact replay of an earlier message.
Marts contain only `valid` and `repaired` rows.
{% enddocs %}

{% docs dq_issues %}
Space-separated list of every data-quality rule the record violated (empty when valid).
{% enddocs %}

{% docs amount_usd %}
Transaction amount converted from transaction currency to USD with the static FX reference
table (`reference.currencies`). Use this for any cross-currency aggregation.
{% enddocs %}

{% docs transaction_date %}
Calendar date (UTC) of the authorization event. The default reporting date for network KPIs.
{% enddocs %}

{% docs loaded_at %}
Timestamp (UTC) when the record was ingested by the data platform. Drives incremental loads
and the timeliness check (event time must not be after ingestion time + 5 minutes grace).
{% enddocs %}
