"""Report the four diagnostic questions from the labelled 500.

Throwaway. Prints only what the run can actually support: there are no gold labels
on real reviews, so model agreement stands in for accuracy and is reported as such.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path

DIR = Path("spike/phase3_diag")
MODELS = ("claude-sonnet-5", "claude-opus-5")
LANGUAGES = ("urdu_script", "roman_urdu", "code_switched", "english")


def load(model: str) -> dict[str, dict]:
    """Load one model's rows, keyed by review id, keeping only answered items."""
    path = DIR / f"diag_{model.replace('.', '-')}.jsonl"
    rows = {}
    for line in path.open(encoding="utf-8"):
        row = json.loads(line)
        if row["status"] in ("ok", "cached") and "label" in row:
            rows[row["review_id"]] = row
    return rows


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval - honest at the small per-language cell sizes here."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    margin = z / d * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def pct(k: int, n: int) -> str:
    """Format a rate with its Wilson interval."""
    if n == 0:
        return "     n/a"
    lo, hi = wilson(k, n)
    return f"{k / n * 100:5.1f}%  [{lo * 100:4.1f},{hi * 100:5.1f}]"


def rate_block(title: str, hits: Counter, totals: Counter) -> None:
    """Print one overall + per-language rate block."""
    print(f"\n{title}")
    hit_total, all_total = sum(hits.values()), sum(totals.values())
    print(f"  {'overall':16s} {pct(hit_total, all_total)}  n={all_total}")
    for language in LANGUAGES:
        print(f"  {language:16s} {pct(hits[language], totals[language])}  n={totals[language]}")


def cohens_kappa(pairs: list[tuple[str, str]]) -> float:
    """Chance-corrected agreement over a shared label set."""
    if not pairs:
        return float("nan")
    n = len(pairs)
    observed = sum(1 for a, b in pairs if a == b) / n
    a_counts, b_counts = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    expected = sum(a_counts[k] / n * b_counts[k] / n for k in set(a_counts) | set(b_counts))
    return (observed - expected) / (1 - expected) if expected < 1 else float("nan")


def main() -> None:
    """Print the diagnostic report."""
    data = {model: load(model) for model in MODELS}
    shared = sorted(set.intersection(*(set(rows) for rows in data.values())))
    print(f"Answered by both models: {len(shared)} of 500")
    for model in MODELS:
        print(f"  {model:20s} answered {len(data[model])}")

    totals: Counter = Counter()
    unclassifiable: Counter = Counter()
    unclassifiable_both: Counter = Counter()
    multi_intent: Counter = Counter()
    agree: Counter = Counter()
    refund_flag: Counter = Counter()
    pairs_by_language: dict[str, list[tuple[str, str]]] = defaultdict(list)

    severity_counts: Counter = Counter()
    intent_counts: Counter = Counter()
    proxy_confusion: Counter = Counter()

    primary = MODELS[1]  # Opus 5 as the reference labeller for single-model stats

    by_rating: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    complaint_total = complaint_unclassifiable = 0
    complaint_unclassifiable_both = complaint_agree = 0

    for review_id in shared:
        rows = {model: data[model][review_id] for model in MODELS}
        language = rows[primary]["language_detected"]
        totals[language] += 1

        labels = {model: rows[model]["label"] for model in MODELS}
        intents = {model: str(labels[model].get("intent")) for model in MODELS}

        if any(intents[model] == "unclassifiable" for model in MODELS):
            unclassifiable[language] += 1
        if all(intents[model] == "unclassifiable" for model in MODELS):
            unclassifiable_both[language] += 1
        if labels[primary].get("intent_secondary"):
            multi_intent[language] += 1
        if labels[primary].get("refund_requested"):
            refund_flag[language] += 1
        if intents[MODELS[0]] == intents[MODELS[1]]:
            agree[language] += 1
        pairs_by_language[language].append((intents[MODELS[0]], intents[MODELS[1]]))

        rating = rows[primary].get("rating") or 5
        both_unclassifiable = all(intents[model] == "unclassifiable" for model in MODELS)
        by_rating[rating][1] += 1
        by_rating[rating][0] += intents[primary] == "unclassifiable"
        if rating <= 2:
            complaint_total += 1
            complaint_unclassifiable += intents[primary] == "unclassifiable"
            complaint_unclassifiable_both += both_unclassifiable
            complaint_agree += intents[MODELS[0]] == intents[MODELS[1]]

        severity = str(labels[primary].get("severity"))
        severity_counts[severity] += 1
        intent_counts[intents[primary]] += 1
        proxy_confusion[(rows[primary]["severity_proxy"], severity == "financial_loss")] += 1

    rate_block("1a. UNCLASSIFIABLE — upper bound (either model)", unclassifiable, totals)
    rate_block("1b. UNCLASSIFIABLE — lower bound (both models)", unclassifiable_both, totals)
    rate_block("2. MULTI-INTENT    (Opus set a secondary intent)", multi_intent, totals)
    rate_block("3. MODEL AGREEMENT (Sonnet 5 vs Opus 5, primary intent)", agree, totals)

    all_pairs = [p for pairs in pairs_by_language.values() for p in pairs]
    print(f"\n  Cohen's kappa (overall): {cohens_kappa(all_pairs):.3f}")
    for language in LANGUAGES:
        print(f"    {language:16s} {cohens_kappa(pairs_by_language[language]):.3f}")

    rate_block("4. REFUND REQUESTED (orthogonal v2 flag)", refund_flag, totals)

    print("\n5. SEVERITY DISTRIBUTION (Opus 5)")
    total = sum(severity_counts.values())
    for severity, count in severity_counts.most_common():
        print(f"  {severity:22s} {count:4d}  {count / total * 100:5.1f}%")

    print("\n6. REGEX SEVERITY PROXY vs LABELLED financial_loss")
    tp = proxy_confusion[(True, True)]
    fp = proxy_confusion[(True, False)]
    fn = proxy_confusion[(False, True)]
    tn = proxy_confusion[(False, False)]
    print(f"  proxy+ & financial_loss : {tp:4d}")
    print(f"  proxy+ & not            : {fp:4d}")
    print(f"  proxy- & financial_loss : {fn:4d}")
    print(f"  proxy- & not            : {tn:4d}")
    if tp + fp:
        print(f"  precision {tp / (tp + fp) * 100:.1f}%   (of flagged, truly financial loss)")
    if tp + fn:
        print(f"  recall    {tp / (tp + fn) * 100:.1f}%   (of true financial loss, flagged)")

    print("\n7. THE PRAISE CONFOUND — unclassifiable by star rating (Opus 5)")
    print("   The taxonomy covers complaints; 4-5 star praise has no intent to match.")
    for rating in sorted(by_rating):
        hits_, total_ = by_rating[rating]
        print(f"  {rating} star  {pct(hits_, total_)}  n={total_}")

    print(f"\n8. COMPLAINTS ONLY (rating <= 2) — n={complaint_total}")
    print(f"  unclassifiable (Opus)      {pct(complaint_unclassifiable, complaint_total)}")
    print(f"  unclassifiable (both)      {pct(complaint_unclassifiable_both, complaint_total)}")
    print(f"  model agreement            {pct(complaint_agree, complaint_total)}")

    print(f"\n9. INTENT COVERAGE (Opus 5) — {len(intent_counts)} distinct labels used")
    for intent, count in intent_counts.most_common():
        print(f"  {intent:36s} {count:4d}")


if __name__ == "__main__":
    main()
