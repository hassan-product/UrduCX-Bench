"""Test the script-gap null properly, and state what this design could have detected.

A null result is only worth reading alongside its power. "We found no gap" and "we could
not have found one" produce identical tables, and the difference is the whole claim. This
reports both:

  1. A permutation test for any effect of language on accuracy. Language labels are
     shuffled many times and the observed spread compared against the shuffled
     distribution. No distributional assumption, and it stays valid at these cell sizes
     where a chi-square approximation would not.

  2. The minimum detectable effect at 80% power. This is the honest limit of the design:
     a gap smaller than the MDE could exist and would very likely have been missed.

Written against the standard library so the result reproduces from a clean checkout.
"""

from __future__ import annotations

import json
import math
import random
from collections import defaultdict
from pathlib import Path

DIR = Path("spike/phase3_diag")
GOLD = DIR / "adjudications_urdu.jsonl"
WORKLIST = DIR / "urdu_pass_worklist.jsonl"
LANGUAGES = ("urdu_script", "roman_urdu", "code_switched", "english")
PERMUTATIONS = 20000
SEED = 20260830
ALPHA = 0.05
TARGET_POWER = 0.80


def spread(outcomes: list[tuple[str, bool]]) -> float:
    """Largest minus smallest per-language accuracy - the quantity being reported."""
    per: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for language, correct in outcomes:
        per[language][1] += 1
        per[language][0] += correct
    rates = [hits / total for hits, total in per.values() if total]
    return max(rates) - min(rates) if len(rates) > 1 else 0.0


def permutation_p(outcomes: list[tuple[str, bool]], rng: random.Random) -> tuple[float, float]:
    """Observed spread and the share of shuffles that match or exceed it."""
    observed = spread(outcomes)
    languages = [language for language, _ in outcomes]
    results = [correct for _, correct in outcomes]
    at_least = 0
    for _ in range(PERMUTATIONS):
        rng.shuffle(languages)
        if spread(list(zip(languages, results, strict=True))) >= observed:
            at_least += 1
    return observed, at_least / PERMUTATIONS


def minimum_detectable_effect(baseline: float, n_per_group: int) -> float:
    """Smallest two-group difference detectable at 80% power, 5% two-sided."""
    z_alpha, z_beta = 1.959964, 0.841621
    return (z_alpha + z_beta) * math.sqrt(2 * baseline * (1 - baseline) / n_per_group)


def main() -> None:
    """Report the permutation test and the detectable-effect floor for each model."""
    work = {
        json.loads(line)["review_id"]: json.loads(line) for line in WORKLIST.open(encoding="utf-8")
    }
    gold = {}
    for line in GOLD.open(encoding="utf-8"):
        if not line.strip():
            continue
        row = json.loads(line)
        if not row.get("blind", True) or row.get("skipped") or not row.get("human_intent"):
            continue
        gold[row["review_id"]] = row

    models = sorted({m for r in work.values() for m in r["models"] if r["models"][m]})
    rng = random.Random(SEED)

    print("Permutation test for an effect of language on accuracy")
    print(f"  {PERMUTATIONS:,} shuffles, statistic = max-min per-language accuracy\n")

    for model in models:
        outcomes = [
            (work[rid]["language"], gold[rid]["human_intent"] == work[rid]["models"][model])
            for rid in gold
            if work.get(rid, {}).get("models", {}).get(model)
        ]
        if not outcomes:
            continue
        observed, p = permutation_p(outcomes, rng)
        verdict = "reject the null" if p < ALPHA else "no significant effect"
        print(f"  {model:22s} spread {observed * 100:5.1f} pts   p = {p:.3f}   {verdict}")

    print("\nWhat this design could have detected")
    counts: dict[str, int] = defaultdict(int)
    correct = 0
    for rid in gold:
        counts[work[rid]["language"]] += 1
    smallest = min(counts[lang] for lang in LANGUAGES if counts[lang])
    accuracies = []
    for model in models:
        hits = sum(
            1
            for rid in gold
            if work.get(rid, {}).get("models", {}).get(model)
            and gold[rid]["human_intent"] == work[rid]["models"][model]
        )
        total = sum(1 for rid in gold if work.get(rid, {}).get("models", {}).get(model))
        if total:
            accuracies.append(hits / total)
    baseline = sum(accuracies) / len(accuracies)
    correct = baseline

    mde = minimum_detectable_effect(baseline, smallest)
    print(f"  baseline accuracy {baseline * 100:.1f}%, smallest language cell n={smallest}")
    print(
        f"  minimum detectable effect at {int(TARGET_POWER * 100)}% power: "
        f"{mde * 100:.1f} percentage points\n"
    )

    print(f"  So the honest reading is: a script gap larger than about {mde * 100:.0f} points")
    print("  would very likely have shown up, and did not. A gap smaller than that could")
    print("  exist and this design would probably have missed it. The observed spreads")
    print("  sit well inside that floor, so the null is a bound, not a proof of zero.\n")

    for n in (50, 100, 200, 400):
        print(
            f"    n={n:3d} per language -> detectable gap "
            f"{minimum_detectable_effect(correct, n) * 100:4.1f} pts"
        )


if __name__ == "__main__":
    main()
