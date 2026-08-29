# Paper outline — draft 1

**Status:** structure and number placement only. No prose written yet.
**Every figure below is on disk and reproducible** (`spike/phase3_diag/`).

---

## Working title

> **Agreement Is Not Accuracy: Authored Benchmark Items Overstate LLM Performance
> on Real Urdu and Roman-Urdu Customer Complaints**

Alternative, if the venue prefers the resource framing:
*Measuring the Authored-to-Real Gap in Multilingual Complaint Classification*

## The claim in one sentence

Two frontier models score 95% on complaints written to exercise a taxonomy and ~63% on
real complaints from the same domain; they agree with each other 100% of the time on the
authored set and 74.9% on the real one; and where they do agree, they are both wrong 31%
of the time — so neither an authored test set nor inter-model agreement is a safe stand-in
for human labels.

## Why anyone outside Pakistan should care

Three practices under test are near-universal, not Urdu-specific:

1. Building an evaluation set by authoring items against your own label scheme.
2. Using inter-model agreement as a proxy for correctness when gold labels are expensive.
3. Using keyword or regex heuristics to find "severe" cases in a multilingual corpus.

All three are measured here and all three fail in a quantified way.

---

## Section map

### 1. Introduction
- The three practices above; each is cheap, standard, and rarely validated.
- Contribution list:
  - a 32-point authored-to-real accuracy gap under identical conditions
  - 30.8% joint error rate where two models agree
  - a three-way decomposition of *why* models disagree on real text
  - a channel-bias result about what public reviews can and cannot contain
  - a released corpus, taxonomy, and human gold labels

### 2. Related work
- Multilingual/low-resource complaint and intent classification. Position against
  Banking77 (English, 77 intents), FINCORP / X-FinCORP (English complaints with severity),
  ATIS-Urdu (26 flight intents), Urdu Web Queries (8,519 queries, 3 intents), RUSA-19
  (10,021 sentences), RUSAS (37,094), ERUPD (75,146 parallel sentences).
- **The gap:** no published corpus combines Urdu/Roman-Urdu, financial complaints, an
  intent taxonomy, and severity. Confirmed by search, recorded in `PROGRESS_LOG.md` §3.
- **Do not claim scale.** RUSAS and ERUPD are larger. The contribution is domain, labels,
  and severity — not size.
- LLM-as-annotator and agreement-as-proxy literature; this paper is a negative result
  against a common shortcut.

### 3. Data
- 54,519 cleaned reviews, 17 Pakistani wallet/telecom apps, Google Play + Apple.
- Language mix: English 87.9%, Roman Urdu 10.2%, Urdu script 1.5%, code-switched 0.4%.
  **State this plainly** — it is a Pakistani financial complaint corpus *containing* Urdu,
  not an Urdu corpus.
- PII scrubbing; ids-and-labels release rather than review text (Google terms).
- **Temporal honesty:** 71.6% is 2026; 2015 contributes 7 reviews. Not longitudinal.
  Forward collection started 2026-08-26 (5,851 reviews in the first pass).

### 4. Taxonomy
- 24 intents in 6 families; definitions, 2 positive + 1 negative example each, plus a
  boundary rationale per intent.
- v1 → v2: the `refund_request` collision caused **61% of all pilot errors**; the fix was a
  precedence rule (the concrete failure is the intent; the money-back ask is an orthogonal
  flag). **Validated on real data** — `refund_request` appears as a primary intent only 4
  times across 569 hunted candidates.

### 5. Experimental design
- Two models chosen for *tied* capability (Sonnet 5, Opus 5 — both 95% in the pilot), so a
  disagreement indicates an ambiguous item rather than a weaker model.
- 500-item diagnostic, stratified equally by language form (not corpus-proportional: a
  proportional draw yields ~6 code-switched items).
- Structured outputs with the intent field enum-bound to the taxonomy.
- **Blind adjudication:** model predictions withheld from the payload, not merely hidden in
  the interface; returned only after a judgement is saved. 100 disagreements + 25 controls,
  shuffled and indistinguishable.

### 6. Results

#### 6.1 The authored-to-real gap — *headline*
| Set | Inter-model agreement | Accuracy vs gold |
|---|---|---|
| Authored (n=80) | 100% | 95% |
| Real complaints (n=125 / 275) | 74.9% | **~63%** |

Identical models, taxonomy, prompt, and metric. Only authored-vs-real varies.
Corrected accuracy: Sonnet 61.3%, Opus 62.9%.
**Report the reweighting explicitly** — raw accuracy on the judged set is 38.4%/44.8%,
which understates truth because the judged set is 79% disagreements against a 20.4%
population base rate.

#### 6.2 Agreement is not accuracy
- Where both models agreed, the human disagreed with both on **8/26 = 30.8%** [16.5, 50.0].
- Inter-model agreement cannot surface this class of error by construction.
- Widest interval in the paper; **state the n honestly** and frame as indicative.

#### 6.3 Decomposing the disagreements (n=99)
| | | |
|---|---|---|
| one model right — real difficulty | 68.7% | [59.0, 77.0] |
| neither right — taxonomy ambiguity | 25.3% | [17.7, 34.6] |
| no intent fits — coverage gap | 6.1% | [2.8, 12.6] |

Annotator bias check: sided with Sonnet 44.1%, Opus 55.9%; 50% inside the interval.

#### 6.4 No script gap, and where an apparent one came from
- Agreement flat across forms over all 490: 78.0 / 75.0 / 85.4 / 79.8; κ 0.72–0.82.
- Phase 2.5: sharpening two intent definitions moved consistency wobbles from 7-of-9
  concentrated in the two messy forms to evenly spread (2/2/2/1).
- **Frame as a methods caution, not proof of absence.** 490 items support a strong failure
  to detect a gap.
- **Do not report per-language gold accuracy.** Agreement cells of 5–9 items; one item
  swings a language 8–13 points.

#### 6.5 Keyword heuristics fail asymmetrically by script
- Regex financial-loss detector: 70.2% precision, 71.3% recall.
- False negatives: Urdu script 17, code-switched 11, Roman Urdu 6, **English 1**.

#### 6.6 Channel bias — what public reviews cannot contain
- `fake_payment_screenshot`: **0 examples in 54,519** under two independent searches
  (keyword; then scenario requiring counterparty + payment-proof + forgery + non-receipt).
- `scam_impersonation_report`: well represented (18/50 hunted).
- Mechanism: an app-store review is addressed to the app. Counterparty fraud leaves the
  platform blameless, so the victim goes to police, not the store.
- **Generalises:** any complaint corpus built from public reviews inherits this.

### 7. Discussion
- If you author your eval set, expect to overstate by ~30 points on real text.
- If you use agreement as ground truth, expect ~30% joint error on messy multilingual input.
- Roughly a third of "model error" on real text is the label scheme, not the model —
  so a disagreement audit is a taxonomy diagnostic, not just a quality check.
- Coverage is a property of the *collection channel*, not only the taxonomy.

### 8. Limitations
Draw from `LIMITATIONS.md`; the ones that must appear:
- Single annotator; no inter-annotator agreement. **Largest weakness — state first.**
- 26 controls is thin for the 30.8% claim.
- Corpus is 88% English and a 2026 snapshot.
- Multi-intent rate **unvalidated** — models reported 11.8%, the human pass recorded 0
  secondary intents because the field was optional. Do not report 11.8% as validated.
- Gold labels come from the taxonomy's author: an upper bound on achievable agreement.

### 9. Release
- Review ids + derived labels + rehydration script (not review text).
- 24-intent taxonomy v2 with a proposed v3 `support_unresponsive`
  (6.0% of the corpus, 3,260 reviews, currently homeless — two intents explicitly push it
  away in their negative examples).
- 125 human gold labels; both models' predictions on all 490.

---

## Open decisions before drafting

1. **Venue.** WNUT fits the finding (noisy user text). LREC fits if the corpus leads.
2. **Naming apps.** Findings need no app names; the dataset does. Recommend anonymising in
   the paper, shipping identifiers under a research licence, and taking Pakistani legal
   advice before either.
3. **Second annotator.** Even 50 doubly-annotated items would convert the largest weakness
   into a reported κ. Worth one paid afternoon.
4. Whether to run the full 9,000 before submission or ship the 500-item subset.
