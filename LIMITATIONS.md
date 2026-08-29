# Limitations

The first release is expected to have several important limitations:

- A single primary annotator may introduce systematic judgment bias.
- App-store reviews overrepresent negative experiences and users willing to post publicly.
- Public evaluation splits can be incorporated into future model training data.
- Telecom and mobile-wallet language does not represent all Urdu customer-service settings.
- Text-only evaluation does not measure speech recognition or spoken interaction quality.
- Roman Urdu spelling varies heavily by region, dialect, and individual practice.
- PII redaction uses typed patterns and explicit self-identification phrases rather than general
	name detection. Names or identifiers written in unexpected forms may remain and require manual
	review before release or external processing.

## Measured limitations

Established by the Phase 3 diagnostic (500 stratified reviews, labelled independently by
Claude Sonnet 5 and Claude Opus 5) and the starved-intent hunt over all 54,519 reviews.

### The collection channel sees only platform-directed complaints

An app-store review is addressed to the app. People write one to blame the app or to demand
it change something, so the corpus records a wrong only when the platform is a plausible
target for it.

Fraud makes the boundary visible. `scam_impersonation_report`, where the fraudster poses as
company staff, is well represented — the user blames the company. `fake_payment_screenshot`,
where a counterparty shows a merchant a forged payment receipt, returned **zero examples**
under two independent searches: a keyword search across the corpus, and a scenario search
requiring counterparty, payment-proof, forgery and non-receipt signals together. In that
scam the app behaved correctly and a human deceived a merchant, so there is nothing to
complain to the app about; the victim goes to the police or the FIA cybercrime wing.

The intent is retained and marked out-of-channel rather than merged or dropped. It is a real
category that an operator-side complaint system meets routinely, and folding it into
`scam_impersonation_report` would conflate counterparty fraud with company impersonation.

Any complaint corpus built from public reviews inherits this bias, not only this one.

### Keyword and regex matching fails asymmetrically across scripts

A regex financial-loss detector built from English and Roman Urdu tokens reached 70.2%
precision and 71.3% recall against labelled `financial_loss`. Its misses were not evenly
spread: **17 in Urdu script and 11 code-switched, against 1 in English.** Latin-token
patterns are close to blind on Urdu-script complaints, so any keyword-derived statistic over
this corpus understates non-English harm.

### Complaint vocabulary does not match category names

In this corpus "scam", "fraud" and "unauthorized" usually describe an unwanted subscription
charge by the provider, not a third party. Retrieval built on those words returns
`unauthorized_vas_deduction` complaints rather than `account_compromised` or
`scam_impersonation_report` ones. A confusion matrix computed over keyword-retrieved
candidates therefore measures the retrieval, not the taxonomy.

### Taxonomy coverage on real complaints

Among reviews rated 1–2 stars (n=275), 13.1% received no intent from the reference labeller
and 6.9% were called unclassifiable by both models. Coverage is far lower on 4–5 star reviews
(63.5% unclassifiable at 5 stars) because the taxonomy describes complaints and praise has no
matching intent; that is a scope boundary, not a coverage gap.

11.8% of reviews carried a genuine second intent, so a single-label release discards a
distinct matter on roughly one review in eight.

### Intent support is uneven and cannot be evened out from this corpus

Targeted retrieval over all 54,519 reviews, taking the 50 best-matching candidates per
starved intent, found `otp_not_received` abundant (45/50); `loan_repayment_dispute` (25),
`account_compromised` (20), `scam_impersonation_report` (18), `bill_payment_not_reflected`
(11) and `refund_request` (10) reachable with further sampling; and `cash_out_agent_problem`
(1), `transfer_to_wrong_recipient` (3), `harassment_or_abuse_via_platform` (3),
`sim_or_number_issue` (4) and `information_request` (4) close to exhausted at the top of the
ranking. These yields describe retrieval precision over ranked candidates, not corpus-wide
frequency.

### The corpus is a current snapshot, not a longitudinal series

71.6% of reviews date from 2026 and only 2,378 (4.4%) precede 2024; 2015 contributes 7.
App stores serve a recent window, so earlier history cannot be recovered — by anyone.
Longitudinal claims are unsupported. Forward collection began 2026-08-26
(`src/collect/refresh_reviews.py`); any time series must be built from that date onward.

### No script gap, measured properly

The project's founding hypothesis was that models handle Urdu-script and Roman-Urdu
customer complaints worse than English. Three attempts were made to test it, and only the
third could answer:

- **Phase 2.5** used 20 authored complaints in four scripts. The right instrument, since
  content is held constant, but at n=20 a single item moved a language by 5 points.
- **The Phase 3 diagnostic** enriched its sample for model disagreement, which distorts
  accuracy, and splitting 125 judgements four ways left cells of 5-9 items.
- **The Urdu pass** (2026-08-30) sampled randomly within each language, matched every
  stratum to the Urdu-script length profile, and collected human gold labels blind.

Accuracy against human gold, 204 blind judgements, ~50 per language:

| Language | Sonnet 5 | Opus 5 |
|---|---|---|
| Urdu script | 62.0% [48.2, 74.1] | 64.0% [50.1, 75.9] |
| Roman Urdu | 68.6% [55.0, 79.7] | 64.7% [51.0, 76.4] |
| Code-switched | 63.6% [50.4, 75.1] | 56.4% [43.3, 68.6] |
| English | 60.4% [46.3, 73.0] | 54.2% [40.3, 67.4] |

English ranks last for both models and Roman Urdu first; the spread is 8-10 points and
every interval overlaps every other. The hypothesis is not supported. Performance is
uniform across script at roughly 55-65%, which independently replicates the ~63% measured
on a separate sample two days earlier.

Two caveats bound this. Length was matched by design; **subject matter was not** - Urdu-script
reviews skew toward UX complaints and English toward OTP, so a residual content confound
remains that only a parallel corpus could remove. And 22 judgements made with the model
answers visible were excluded rather than pooled, leaving a single-protocol result.

### Skipped items must not be scored as errors

Thirteen reviews the annotator skipped were initially counted in the denominator as model
misses. They were unevenly distributed - 6 Urdu script against 2 English - and suppressed
Urdu-script accuracy by roughly 6 points, manufacturing a gap in the direction of the
hypothesis. This is the same defect as Issue 13, where rate-limited API calls were scored
as wrong answers. Both times the error flattered the prior. An unanswered item is not a
wrong answer, in either direction.

### Agreement is not accuracy

Real reviews have no gold labels, so inter-model agreement is reported in place of accuracy
and must not be read as accuracy. Two models can agree and both be wrong. On the authored
Phase 2.5 items, which do have gold labels, the two models agreed with each other on 80/80
while each scored 76/80 against gold — they made the same four errors. Human verification is
required before any accuracy claim.

Annotation agreement against human labels and final exclusions will be added before the first
benchmark release.
