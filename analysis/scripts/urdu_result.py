"""Score the Urdu pass: does model accuracy differ by script, against human gold labels?

Only blind judgements are scored. Items judged with the model answers on screen were
collected under a different protocol and are excluded rather than pooled, so every
figure below comes from one consistent regime.

Reads the gold labels from the Urdu pass and reports per-language accuracy with intervals.
Sampling was random within language and matched on length, so length is controlled. Subject
matter is not - the intent mix is printed so a reader can see what remains confounded.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

DIR = Path("spike/phase3_diag")
GOLD = DIR / "adjudications_urdu.jsonl"
WORKLIST = DIR / "urdu_pass_worklist.jsonl"
MODELS = ("claude-sonnet-5", "claude-opus-5", "claude-haiku-4-5")
LANGUAGES = ("urdu_script", "roman_urdu", "code_switched", "english")


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson interval."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    margin = z / d * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def row(label: str, k: int, n: int) -> str:
    """One rate with its interval."""
    if n == 0:
        return f"  {label:<16s}      no data"
    lo, hi = wilson(k, n)
    return f"  {label:<16s} {k:3d}/{n:<3d} {k / n * 100:5.1f}%  [{lo * 100:4.1f},{hi * 100:5.1f}]"


def main() -> None:
    """Report per-language agreement and, once gold labels exist, accuracy."""
    work = {
        json.loads(line)["review_id"]: json.loads(line) for line in WORKLIST.open(encoding="utf-8")
    }
    gold, excluded, skipped = {}, 0, 0
    if GOLD.exists():
        for line in GOLD.open(encoding="utf-8"):
            if not line.strip():
                continue
            judgement = json.loads(line)
            # Judgements made while the model answers were visible were collected under a
            # different protocol and are dropped, not pooled. Excluding them keeps the
            # reported result single-protocol; the flag stays in the data so the exclusion
            # is reproducible.
            if not judgement.get("blind", True):
                excluded += 1
                continue
            # A skipped item is an unanswered question, not a wrong answer. Leaving it in
            # the denominator scores it as a model miss and understates accuracy - the
            # same defect as Issue 13, where failed API calls were counted as errors.
            if judgement.get("skipped") or not judgement.get("human_intent"):
                skipped += 1
                continue
            gold[judgement["review_id"]] = judgement

    print(f"Urdu pass: {len(work)} labelled, {len(gold)} judged by hand")
    if excluded:
        print(f"  ({excluded} excluded: judged with model answers visible)")
    if skipped:
        print(f"  ({skipped} excluded: skipped, no answer given)")
    print()
    print("MODEL-vs-MODEL AGREEMENT (no human needed)")
    for lang in LANGUAGES:
        group = [r for r in work.values() if r["language"] == lang]
        answers = [{m: i for m, i in r["models"].items() if i} for r in group]
        same = sum(1 for a in answers if len(set(a.values())) == 1)
        print(row(lang, same, len(group)))

    if not gold:
        print("\nNo gold labels yet. Run:")
        print("  python -m spike.phase3_diag.adjudicate --mode urdu")
        return

    print("\nACCURACY AGAINST HUMAN GOLD")
    spreads = {}
    for key in MODELS:
        present = [r for r in gold if work.get(r, {}).get("models", {}).get(key)]
        if not present:
            continue
        print(f"\n  {key}")
        rates = {}
        for lang in LANGUAGES:
            ids = [r for r in present if work[r]["language"] == lang]
            hits = sum(1 for r in ids if gold[r]["human_intent"] == work[r]["models"][key])
            if ids:
                rates[lang] = hits / len(ids)
            print("  " + row(lang, hits, len(ids)))
        if len(rates) > 1:
            best = max(rates, key=rates.get)
            worst = min(rates, key=rates.get)
            spread = (rates[best] - rates[worst]) * 100
            spreads[key] = spread
            print(f"    spread {spread:.1f} pts   best {best}, worst {worst}")

    if spreads:
        print("\nIS THERE A SCRIPT GAP?")
        print("  A gap large enough to matter operationally would show as a wide spread")
        print("  with non-overlapping intervals. Read the intervals above, not the point")
        print("  estimates: at ~50 per language only a ~20 point gap is detectable.\n")
        for key, spread in spreads.items():
            verdict = "no detectable gap" if spread < 20 else "GAP — investigate"
            print(f"  {key:22s} {spread:5.1f} pts   {verdict}")

    print("\nWHAT IS STILL CONFOUNDED — intent mix per language (human labels)")
    for lang in LANGUAGES:
        ids = [r for r in gold if work.get(r, {}).get("language") == lang]
        mix = Counter(gold[r]["human_intent"] for r in ids)
        top = ", ".join(f"{k} {v}" for k, v in mix.most_common(3))
        print(f"  {lang:16s} {top}")

    print("\n  Length was matched by design. Subject matter was not: if one language")
    print("  concentrates in intents that are intrinsically harder, that shows up as a")
    print("  script effect and is not one. Read the mix above before concluding.")


if __name__ == "__main__":
    main()
