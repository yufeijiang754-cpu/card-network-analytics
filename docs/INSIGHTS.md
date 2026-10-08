# Key Insights

> **Read this first.** Every number below comes from **synthetic** data (2.0M authorizations,
> calendar year 2025) produced by this repo's generator. Several patterns were deliberately
> planted to test whether the analytics layer can find them; they are disclosed in
> `DECISIONS.md` (D-14). The value here is the **method**: how each signal is detected,
> quantified and turned into an action. The specific dollar amounts are not real.
> Reproduce every figure with `make analysis` (results land in `analysis/results/`).

Network baseline: **1.97M trusted authorizations**, **$126.6M approved volume**,
**93.2% approval rate** (CNP 89.8%), **21.9 bps fraud loss rate**, **$2.07M interchange**.

---

## 1. CNP and cross-border carry most of the fraud loss on a minority of the volume

**Evidence** (`analysis/03_cross_border_fraud.sql`, `06_cnp_risk_analysis.sql`)

| Segment | Fraud attempt rate | Fraud loss rate | Relative risk vs. domestic CP |
|---|---|---|---|
| Domestic card-present | 3.6 bps | 4.5 bps | 1.0x |
| Cross-border card-present | 8.1 bps | 8.5 bps | 2.3x |
| Domestic card-not-present | 65.1 bps | 32.7 bps | 18.3x |
| Cross-border card-not-present | 124.0 bps | 120.2 bps | **34.8x** |

- CNP is **40% of approved volume but 87% of fraud losses**.
- Cross-border is **11.5% of volume but 39% of losses**.
- **Travel** (airlines, hotels) alone is 48% of CNP fraud loss, at 70 bps.
- Issuers catch only about 56% of cross-border CNP fraud attempts, versus 66% for domestic CNP.

**So what?** Fraud spend should follow the loss concentration, not the volume. A blanket rule
tightening across all traffic would add false declines on the 60% of volume that produces 13% of losses.

**Recommendations**
1. Prioritize **network tokenization** and **3-D Secure / risk-based authentication** for cross-border CNP, starting with Travel and E-commerce MCCs (73% of CNP fraud loss combined).
2. Give issuers network-level risk scores specific to **cross-border CNP**, where their own models perform worst (lowest catch rate).
3. Track fraud loss bps **by segment**, not just in aggregate. An improving overall number can hide a deteriorating cross-border CNP segment.

---

## 2. A card-testing attack hit one payment facilitator's merchants, and 444 stolen cards were "validated"

**Evidence** (`analysis/06_cnp_risk_analysis.sql` part A, `02_decline_reason_trend.sql`)

- From 18-20 Sep 2025, CNP declines with code **14 (invalid card) / 54 (expired)** at
  acquirer **ACQ009 "Nimbus PayFac"** ran at **190-210x** its 28-day trailing median
  (387-423 per day vs. a baseline of about 2).
- 87% of those attempts were under $5, compared with a normal small-ticket share of 3-10%.
- **2,370 small-ticket attempts on 2,350 distinct cards**: one card, one try. That is the
  signature of enumeration or testing of stolen credentials.
- **444 attempts were approved**. Those cards are now known-good to the attacker. 311 of the
  approved transactions were later charged back.
- The attack is visible network-wide: in September, *Invalid Card Number* jumped from 4.6% to
  10.1% of all declines (+544 bps MoM).
- The 5 targeted merchants are also the top 5 of the chargeback anomaly list (21-48% chargeback rates).

**Method note:** a mean/standard-deviation baseline flagged only day 1. The attack inflated its
own baseline and masked days 2-3. Switching to a **trailing median** detects all three days.

**So what?** Card testing is cheap for attackers and expensive later: the validated cards are
sold and used for high-value fraud elsewhere on the network.

**Recommendations**
1. Real-time **velocity rule at the network level**: more than N declines with code 14/54 per merchant per hour, mostly under $5, triggers a step-up or block for that merchant ID.
2. **Proactively alert issuers** with the list of the 444 cards approved during the attack window, so they can reissue or monitor before the downstream fraud hits.
3. Review **ACQ009's sub-merchant onboarding**. Payment facilitators concentrate this risk, and all targeted merchants came from one PayFac.

---

## 3. One issuer's CNP approval rate is 11 points below peers: likely over-tuned fraud rules

**Evidence** (`analysis/04_issuer_performance_ranking.sql` part A)

- Issuer **ISS007** approves **78.9%** of CNP attempts, compared with **90.0%** for all other
  issuers combined. Its peer z-score is **-4.6**, the worst of 45 issuers.
- Its card-present approval rate is close to peers (93.6% vs. 94.9%). The gap is CNP-specific.
- Its "do not honor" (05) rate is **5.5%**, about 2.5x the peer level. Code 05 is the generic
  code issuer fraud engines return.
- Yet its fraud loss rate (17.1 bps) is **not** better than peers'. The extra declines are not buying lower losses.

**So what?** These are probably **false declines**: good customers turned away. At ISS007's
volume that is about 1,090 lost CNP sales per year (about $94k of spend at an $86 average
ticket). False declines also push cardholders to use a different card, a share-of-wallet loss
that is larger than the interchange itself.

**Recommendations**
1. Share the benchmark with ISS007's relationship team: CNP approval rate, 05-code share and peer ranking.
2. Offer network **risk-scoring and tokenized-credential data** so the issuer can approve more confidently instead of defaulting to 05.
3. Add **"CNP approval rate vs. peer median"** to the issuer scorecard, with alerts below -3 sd.

---

## 4. Availability incident: ISS012 was effectively offline for 3 hours, with no stand-in

**Evidence** (`analysis/04_issuer_performance_ranking.sql` part B)

- On **14 Jun 2025, 14:00-17:00 UTC**, 73-87% of ISS012's authorizations returned code **91
  (issuer unavailable)**, against a normal level of about 0.3%.
- **100 transactions ($8.2k) were declined** purely for technical reasons. Code 91 is a soft
  decline, so many of those purchases were retried on another card or abandoned.

**So what?** Technical declines are the most avoidable kind. The cardholder had funds and
the issuer would most likely have approved.

**Recommendations**
1. Enable **stand-in processing (STIP)** for ISS012: when the issuer times out, the network approves low-risk transactions within pre-agreed limits.
2. Monitor **hourly code-91 rate per issuer** (the query is ready to run as an alert) with a threshold around 20% at 10+ attempts per hour.

---

## 5. Interchange: premium credit drives revenue; regulated debit is 21% of volume but 5% of interchange

**Evidence** (`analysis/08_interchange_revenue_mix.sql`)

| Card segment | Share of volume | Share of interchange | Effective rate |
|---|---|---|---|
| Credit - Rewards | 20.3% | 27.8% | 2.24% |
| Credit - Classic | 22.9% | 27.2% | 1.94% |
| Credit - Premium | 13.8% | 21.1% | 2.48% |
| Debit - Exempt | 16.0% | 9.8% | 1.00% |
| Credit - Business | 5.8% | 9.1% | 2.59% |
| Debit - Regulated (Reg II cap) | 21.3% | **5.0%** | **0.38%** |

- Credit cards generate **85.2%** of interchange on 62.8% of the volume.
- Regulated debit earns about **$0.25 per transaction**, versus $1.34-1.78 for credit.

**So what?** For a network competing for issuer portfolios, interchange economics drive
issuer decisions. Regulated debit migrates on cost and acceptance, not interchange. Premium
and rewards credit portfolios are where the issuer revenue case is strongest.

**Recommendations**
1. Lead issuer acquisition pitches with **premium / rewards credit** and **exempt (small-issuer) debit**, where interchange economics favour the issuer.
2. For regulated debit, compete on **routing cost, authorization performance and fraud tools**. Insights 1-4 are exactly that pitch.

---

## Supporting observations

- **Seasonality** (`07_volume_seasonality.sql`): Saturday is 1.18x the average day and Monday 0.91x. Black Friday hit **2.06x** a normal Friday (+109% vs. trailing 28 days), Cyber Monday 1.88x. December daily volume was +10% MoM. Christmas Day was the only holiday *below* trend (-24%). Capacity planning should target Black Friday peaks of about 2x normal daily volume.
- **Approval by MCC** (`01_auth_rate_by_mcc.sql`): the lowest approval rates are all CNP-heavy: Digital Goods (88.1-89.0%), Airlines (89.5%), Catalog e-commerce (90.0%). About 3,900 excess declines in MCC 5815 alone versus the network average.
- **Chargebacks** (`05_chargeback_anomaly_detection.sql`): a "rate >= 1% **and** >= 5 disputes" rule cut alerts from 297 (rate only) to 47. 25 of those 47 are confirmed problem merchants (20 of the 25 planted high-dispute merchants + the 5 card-testing victims). Peer z-scores are weak in Digital Goods because the attacked merchants inflate the peer standard deviation, another case for robust statistics.
- **Data quality impact**: 1.6% of raw records were quarantined before reaching these numbers (see `docs/DATA_QUALITY_SCORECARD.md`). Without the DQ layer, the 4,000 replay duplicates alone would overstate volume, and the 6,000 malformed currency codes would have failed FX conversion.
