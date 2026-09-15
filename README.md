# UrduCX-Bench

How accurately do AI models read real Pakistani customer complaints?

**About 61% of the time — not the 95% that standard testing reports.**

This repository holds the corpus pipeline, the evaluation tooling, and the findings from a
one-person study of 54,519 public app-store reviews across 17 Pakistani mobile wallets and
telecom apps, written in Urdu script, Roman Urdu, English, and the code-switched mix people
actually type.

- **Findings, in plain language:** [The 61% Problem](https://hassan-product.github.io/UrduCX-Bench/paper/findings-summary.html)
- **What the study cannot tell you:** [LIMITATIONS.md](LIMITATIONS.md)

## The finding

Frontier models were asked to sort complaints into 26 categories. Tested on clean examples
written in-house, they scored **95%**. Tested on genuine customer reviews — same models,
same categories, same prompt — they scored **61%** against labels a person assigned by hand
without seeing the machine's answer first.

Two things followed from that:

- **Agreement is not accuracy.** Where two models gave the same answer, both were still
  wrong a substantial share of the time. Inter-model agreement is widely used as a
  confidence shortcut; on this data it fails invisibly.
- **The founding hypothesis was wrong.** The project set out to show that models handle
  Roman Urdu worse than English. Measured properly — random sampling, length-matched
  strata, blind gold labels — accuracy is flat across all four language forms. That null
  result is published alongside the rest.

## What is in the repository

Three tools, all local, none of which makes a network call while you use them:

| Tool | Command | What it does |
|---|---|---|
| **Blind adjudication** | `python -m src.adjudicate judge` | Judge items one at a time without seeing model predictions until you commit, then score the models against your labels — with confidence intervals, agreement statistics, and a power analysis that states what the sample could and could not have detected. [Docs](docs/ADJUDICATION.md) |
| **Corpus explorer** | `python -m src.explore` | Browse and filter the corpus by app, language, rating, and release, then export a slice as a judging queue. [Docs](docs/EXPLORER.md) |
| **Collection pipeline** | `src/collect/`, `src/prep/` | Checkpointed, rate-limited scrapers for both app stores; cleaning, deduplication, language labelling, and PII redaction across ASCII, Urdu-Indic, and Arabic-Indic numerals. |

Plus the human-authored 26-intent taxonomy ([config/taxonomy.yaml](config/taxonomy.yaml)),
the model roster, and 214 tests — none of which touches the network.

The adjudication harness was built for this corpus but is not tied to it. Any text
classification task with items and categories will work.

## Try it with no data

```bash
git clone https://github.com/hassan-product/UrduCX-Bench.git
cd UrduCX-Bench
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e .

python -m src.adjudicate judge --demo
```

`--demo` invents a set of complaints and runs the full interface on them, so the tool can be
tried and shown without any real customer text. Open `http://127.0.0.1:8790`.

Run the checks with `ruff check .` and `pytest`.

## Data

**The review corpus is not redistributed.** App-store terms make republishing review text a
legal grey area, so this repository ships the code that collects and processes reviews, the
taxonomy, and the findings — but not the reviews themselves. Anyone can regenerate the
corpus from the public stores with the collection pipeline.

Raw and interim data stay local and git-ignored. Every review is stripped of phone numbers,
identity numbers, account numbers and email addresses before any external processing, and
the scrubber is tested to preserve the amounts, dates and reference numbers a complaint
needs. No reviewer names or profile identifiers are ever stored.

Supporting dataset licences are recorded in [DATA_LICENSES.md](DATA_LICENSES.md).

## Method, briefly

1. **Collect** every public review for 17 products from Google Play and the App Store.
2. **Clean** and deduplicate; label each review's language deterministically.
3. **Author** a 26-intent taxonomy for what Pakistani customers complain about, with tested
   boundaries between neighbouring categories.
4. **Label** samples with frontier models under a fixed prompt, cached and versioned.
5. **Judge** hundreds of those items by hand, blind, and score the models against the human.
6. **Report** what was found, what was not, and what the design could not have detected.

Step 5 is the one most evaluations skip, and the only one that produces an accuracy number
rather than an agreement number.

## Limitations

Read [LIMITATIONS.md](LIMITATIONS.md) before citing anything here. In short: one annotator,
a corpus that is 88% English and overwhelmingly recent, a collection channel that only sees
complaints people direct at the app, and cells too small to detect a language gap under
roughly 25 points.

## License and citation

Source code is licensed under the Apache License 2.0. Any released benchmark data would be
licensed under CC BY 4.0 unless a release manifest states otherwise. Citation metadata is in
[CITATION.cff](CITATION.cff).

```bibtex
@misc{urducxbench2026,
  author = {Chaudry, Hassan},
  title  = {UrduCX-Bench: Measuring How Accurately AI Reads Real Pakistani Customer Complaints},
  year   = {2026},
  url    = {https://github.com/hassan-product/UrduCX-Bench}
}
```
