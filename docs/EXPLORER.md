# Corpus explorer

Browse the review corpus locally: filter it, see what the filter contains, and export a
slice to judge.

```bash
python -m src.explore
```

Opens on **http://127.0.0.1:8800**. Makes no network calls of any kind. The corpus never
leaves the machine.

## What it shows

**Overview** — counts and negative-review share across provider, language, platform and
year, for whatever is currently filtered.

**Releases** — negative share per app version, worst first. This is the corpus's most
useful free signal: rating and version are both recorded on every review, so it needs no
labelling and carries no model error. It answers *did this release make things worse, and
did the next one fix it.* Versions under 40 reviews are dropped rather than ranked — a
release showing 100% negative on nine reviews is noise wearing a headline.

**Over time** — volume and negative share by month. A spike in both at once is what an
outage looks like from outside.

**Reviews** — the matching reviews themselves.

**Issue types** — only over reviews that carry a label, and it says so on the panel.

## Filters

All combinable; every count updates against the whole selection.

| Filter | Coverage |
|---|---|
| Provider, rating, language, platform, year | every review |
| App version | ~80% |
| Free-text search | any script |
| Mentions *(keyword groups)* | every review |
| Issue type | only labelled reviews |

## Keyword groups are a search box, not a classifier

The **Mentions** filters find reviews containing a family of words — money, OTP, card,
fraud, unanswered support. Every pattern carries Urdu-script, Roman-Urdu and English forms,
because a Latin-only word list misses financial-loss complaints in Urdu script roughly
seventeen times for every one it misses in English.

They are deliberately not presented as issue types. The study this corpus comes from
measured keyword classification at 70% precision and 71% recall. Labelling a review
`otp_not_received` because it contains the letters OTP is exactly the shortcut that study
exists to warn against. Use them to *find* reviews, then judge the reviews.

## The loop

**Export for judging** writes the current filter as a JSONL in the shape
`src.adjudicate` reads:

```bash
python -m src.explore                       # filter, then Export
python -m src.adjudicate judge \
  --items ~/Downloads/slice_141.jsonl \
  --labels config/taxonomy.yaml \
  --out data/gold.jsonl
```

Export carries no labels and no model predictions, so judging starts blind even on rows
that already have a label recorded elsewhere.

That loop is the point of the tool: find the reviews worth looking at, then look at them
properly. It costs nothing and it is how the labelled fraction grows without a labelling
run.

## What it will not do

**It will not infer an issue type it does not have.** Reviews without a label show no
label. Roughly 4% of the corpus is labelled, and the interface reports that fraction
rather than hiding it — a filter that silently searched 4% of the data while appearing to
search all of it would be worse than no filter at all.

**It will not publish anything.** Bound to localhost, no outbound requests. The corpus is
public review text, but reading it and republishing it are different acts, and the tool
keeps the second one a deliberate choice.
