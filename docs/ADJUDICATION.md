# Blind evaluation harness

A local tool for finding out how accurate a classifier actually is.

You point it at a file of items, a file of categories, and it walks you through judging
them one at a time — without ever showing you what the models guessed until after you've
committed. Then it scores the models against your judgements.

It was built to study Urdu and Roman-Urdu customer complaints, but nothing in it is
specific to that. Any classification task with text and categories will work.

## Why it exists

Most teams check a classifier by writing test cases themselves. On real Pakistani
customer complaints that method reported **95% accuracy** where the truth was **61%** —
a 34-point overstatement, because questions you write yourself are the questions you
already know how to answer.

The obvious alternative is to run two models and trust them where they agree. On the
same data, **every model agreed with the others and all were wrong 22% of the time**.
Agreement looks like confidence and isn't.

The only method that worked was a person reading items and deciding, without seeing the
machine's answer first. This tool makes that method cheap enough to actually do.

## Try it with no data of your own

```bash
python -m src.adjudicate judge --demo
```

Writes a synthetic dataset to `demo_data/` and opens the app on it: 120 invented support
tickets, nine labels, two models that disagree often enough for the controls pass to mean
something, and one region given a genuine deficit so the subgroup test has something to
find. Delete the directory when you're done.

Real evaluation data is customer text and does not travel. The demo exists so the tool can
be shown working without it.

## Install

Python 3.11+, no third-party dependencies beyond PyYAML.

```bash
python -m pip install -r requirements.txt
```

## Judge

Judging and results are one application. The pass and the blindness setting are controls
in the interface, not flags you restart to change.

```bash
python -m src.adjudicate judge \
  --items   data/tickets.jsonl \
  --labels  config/categories.yaml \
  --out     data/gold.jsonl
```

Open **http://127.0.0.1:8790**. Progress saves after every judgement; closing the tab
and restarting picks up where you left off.

### Items file

One JSON object per line. `id` and `text` are required; everything else is optional.

```json
{"id": "t_4471",
 "text": "paisay kat gaye lekin transfer nahi hua, helpline bhi jawab nahi de rahi",
 "meta": {"language": "roman_urdu", "product": "wallet_a", "rating": 1},
 "predictions": {"model-a": "transfer_failed", "model-b": "support_unresponsive"}}
```

`predictions` is optional — without it this is a plain annotation tool. With two or more
models it also measures agreement, and finds the cases where they are wrong together.

Fields from a review corpus (`review_id`, `text_scrubbed`, `models`) are accepted as
aliases, so an existing dataset usually loads without rewriting.

### Labels file

```yaml
version: 1
labels:
  - id: transfer_failed
    group: money_movement
    definition: >-
      A transfer failed to reach the recipient but the sender's balance was reduced.
    positive_examples:
      - "Sent Rs 5000, shows failed, amount still deducted"
      - "paisay bhejay lekin pohanchay nahi, balance kat gaya"
    negative_example: "Sent Rs 5000 to the wrong account number by mistake"
    negative_rationale: >-
      The transfer succeeded and landed somewhere, just with the wrong recipient.
```

The examples matter more than the definitions. When two categories both seem to fit, the
negative example and its rationale are what decide it — for a human and for a model.

**`version` is load-bearing.** Judgements record it, so changing your categories reopens
exactly the judgements that change could have affected, and leaves the rest alone.

## Score

```bash
python -m src.adjudicate score \
  --items data/tickets.jsonl \
  --gold  data/gold.jsonl \
  --by    language
```

Reports accuracy per model with confidence intervals, inter-model agreement with Cohen's
kappa, the joint-error rate, and — if you pass `--by` — a subgroup breakdown with a
permutation test and a power statement.

## Reading the results

Each row is an estimate with its uncertainty:

```
49.0–62.5   ────────▉▉▉▉▉▉│▉▉▉▉▉▉────────
             band = the plausible range
                          tick = the single best guess
```

**The band is the finding; the tick is only its midpoint.** Two rows whose bands overlap
are not reliably different, however far apart their percentages look. A very wide band
means few items in that cell, not a worse model.

Every technical term in the interface carries a plain-language tooltip on hover or focus.

## Passes

Switch between these in the header dropdown; each shows its item count.

| Pass | Purpose |
|---|---|
| all | everything not yet judged |
| controls | only items the models already agree on |
| recheck | items already judged, served blind again |
| revisit | items judged under an older `version` of the labels |

**`controls`** is how joint error becomes visible. Where models agree, inter-model
agreement can never reveal that they are all wrong — only a human can.

**`recheck`** is for when no second annotator is available. Wait a week, judge 50 items
again without seeing your earlier answers, and compare. It cannot tell you whether one
person is right, but it does tell you whether the task is stable or arbitrary. A low
score is a real finding: it bounds what any annotator could achieve.

## The protocol, and why it is enforced rather than suggested

Three properties are built in because each one, left to discipline, quietly stops
holding — and a pass that stops being blind still produces a full file of judgements.

**Predictions are withheld from the payload, not hidden in the page.** `/next` returns
the id, the text and the metadata. There is nothing to reveal in devtools, because
nothing was sent.

**Controls are indistinguishable from the rest.** They are shuffled in, so the record can
show the annotator was not simply agreeing with a preferred model.

**Regimes never pool.** `--show-predictions` stamps `blind: false` on every judgement it
collects, and scoring excludes those unless you ask for them. Two protocols reported as
one number is not a number.

## Reading a null result

If a subgroup breakdown shows no difference, `score` also prints the smallest difference
the design could have detected:

```
spread 10.6 pts, p = 0.697 — no significant difference
this design could detect 28 pts at 80% power (n=48 in the smallest group)
a difference this size would need n=341 per group to confirm; read the null as a bound,
not a zero
```

"No difference" and "we could not have seen one" produce identical tables. The power line
is what separates them, and without it a null result is unreadable.

## Two things it deliberately does not do

**It does not call models.** Labelling and adjudicating stay separate; you may already
have predictions, and mixing the two makes both harder to reason about.

**It does not run anywhere but localhost.** The material being judged is usually customer
text. The right place for that is the machine already holding it.
