"""Decompose the authored-versus-real agreement gap using the human gold labels.

The diagnostic established that two frontier models agree on 100% of authored complaints
and 74.9% of real ones. That is an observation. This turns it into an explanation by
asking, for every review where the models disagreed, which of four things was true:

  one model right   - the item is hard, but the taxonomy handles it
  neither right     - both models missed a label the taxonomy does contain (ambiguity)
  no intent fits    - the taxonomy has no home for it (coverage gap)

Controls - reviews where the models agreed - do the opposite job. They catch the case
neither agreement nor disagreement can reveal: both models confidently wrong together.
They also test whether the annotator systematically favoured one model.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

JUDGEMENTS = Path("spike/phase3_diag/adjudications.jsonl")
SAMPLE = Path("spike/phase3_diag/sample_500.jsonl")
SONNET, OPUS = "claude-sonnet-5", "claude-opus-5"
UNCLASSIFIABLE = "unclassifiable"


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson interval - honest at these cell sizes, unlike a normal approximation."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    margin = z / d * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def line(label: str, k: int, n: int, width: int = 34) -> str:
    """One rate row with its interval."""
    if n == 0:
        return f"  {label:<{width}}      n/a"
    lo, hi = wilson(k, n)
    pct, band = k / n * 100, f"[{lo * 100:4.1f},{hi * 100:5.1f}]"
    return f"  {label:<{width}} {k:4d}/{n:<4d} {pct:5.1f}%  {band}"


def main() -> None:
    """Print the decomposition, the control check, and model accuracy against gold."""
    rows = [json.loads(line_) for line_ in JUDGEMENTS.open(encoding="utf-8") if line_.strip()]
    rows = [r for r in rows if not r.get("skipped") and r.get("human_intent")]
    meta = {
        json.loads(line_)["review_id"]: json.loads(line_) for line_ in SAMPLE.open(encoding="utf-8")
    }

    disagreements = [r for r in rows if r["models"][SONNET] != r["models"][OPUS]]
    controls = [r for r in rows if r["models"][SONNET] == r["models"][OPUS]]

    print(f"Human gold labels: {len(rows)}")
    print(f"  disagreements {len(disagreements)}   controls {len(controls)}\n")

    # --- 1. The decomposition -------------------------------------------------
    sonnet_right = opus_right = neither_real = coverage_gap = 0
    reasons: Counter = Counter()
    neither_examples = []

    for r in disagreements:
        human, s, o = r["human_intent"], r["models"][SONNET], r["models"][OPUS]
        if human == UNCLASSIFIABLE and s != UNCLASSIFIABLE and o != UNCLASSIFIABLE:
            coverage_gap += 1
            reasons[r.get("unclassifiable_reason") or "unrecorded"] += 1
        elif human == s and human != o:
            sonnet_right += 1
        elif human == o and human != s:
            opus_right += 1
        else:
            neither_real += 1
            neither_examples.append((r["review_id"], human, s, o))

    n = len(disagreements)
    print("=" * 66)
    print("1. WHAT THE MODEL DISAGREEMENTS ACTUALLY WERE")
    print("=" * 66)
    print(line("Sonnet 5 right, Opus wrong", sonnet_right, n))
    print(line("Opus 5 right, Sonnet wrong", opus_right, n))
    print(line("neither right - taxonomy ambiguity", neither_real, n))
    print(line("no intent fits - coverage gap", coverage_gap, n))
    one_right = sonnet_right + opus_right
    print()
    print(line("REAL DIFFICULTY (one model right)", one_right, n))
    print(line("TAXONOMY PROBLEM (the rest)", neither_real + coverage_gap, n))

    if reasons:
        print("\n  coverage-gap reasons:")
        for reason, count in reasons.most_common():
            print(f"    {reason:<32s} {count}")

    # --- 2. Annotator bias check ----------------------------------------------
    print("\n" + "=" * 66)
    print("2. DID THE ANNOTATOR FAVOUR EITHER MODEL?")
    print("=" * 66)
    if one_right:
        lo, hi = wilson(sonnet_right, one_right)
        print(line("sided with Sonnet 5", sonnet_right, one_right))
        print(line("sided with Opus 5", opus_right, one_right))
        verdict = (
            "balanced - 50% sits inside the interval"
            if lo <= 0.5 <= hi
            else "SKEWED - 50% falls outside the interval"
        )
        print(f"\n  {verdict}")

    # --- 3. Controls: both models wrong together ------------------------------
    print("\n" + "=" * 66)
    print("3. CONTROLS - WHERE THE MODELS AGREED WITH EACH OTHER")
    print("=" * 66)
    both_wrong = [r for r in controls if r["human_intent"] != r["models"][SONNET]]
    print(line("human agreed with both", len(controls) - len(both_wrong), len(controls)))
    print(line("BOTH MODELS WRONG together", len(both_wrong), len(controls)))
    print("\n  Agreement between models cannot detect this case; only gold labels can.")
    for r in both_wrong[:6]:
        text = (meta.get(r["review_id"], {}).get("text_scrubbed") or "")[:58]
        print(f"    human {r['human_intent'][:26]:26s} | both said {r['models'][SONNET][:24]}")
        print(f"      {text}")

    # --- 4. Model accuracy against gold ---------------------------------------
    print("\n" + "=" * 66)
    print("4. MODEL ACCURACY AGAINST HUMAN GOLD (all judged items)")
    print("=" * 66)
    for name, key in (("Claude Sonnet 5", SONNET), ("Claude Opus 5", OPUS)):
        hits = sum(1 for r in rows if r["human_intent"] == r["models"][key])
        print(line(name, hits, len(rows)))
    agreed_both = sum(
        1 for r in rows if r["human_intent"] == r["models"][SONNET] == r["models"][OPUS]
    )
    print(line("both models correct together", agreed_both, len(rows)))

    # --- 5. Reweighting ---------------------------------------------------------
    # The judged set is ~4x enriched for disagreements (79% here vs 20% in the 490),
    # because disagreements are what the decomposition needs. Raw accuracy on it is
    # therefore far below true accuracy and must not be reported as a model score.
    def population_disagreement_rate() -> float:
        """Share of the full 490 labelled reviews where the two models differ."""

        def intents(model: str) -> dict[str, str]:
            path = Path(f"spike/phase3_diag/diag_{model.replace('.', '-')}.jsonl")
            out = {}
            for raw in path.open(encoding="utf-8"):
                row = json.loads(raw)
                if row["status"] in ("ok", "cached") and "label" in row:
                    out[row["review_id"]] = row["label"]["intent"]
            return out

        first, second = intents(SONNET), intents(OPUS)
        shared = set(first) & set(second)
        return sum(1 for k in shared if first[k] != second[k]) / len(shared)

    rate = population_disagreement_rate()
    print("\n" + "=" * 66)
    print("5. ACCURACY REWEIGHTED TO POPULATION BASE RATES")
    print("=" * 66)
    print(
        f"  disagreements are {rate * 100:.1f}% of the 490 but "
        f"{len(disagreements) / len(rows) * 100:.1f}% of what was judged,"
    )
    print("  so raw accuracy on the judged set understates the true figure.\n")
    for name, key in (("Claude Sonnet 5", SONNET), ("Claude Opus 5", OPUS)):
        on_dis = sum(1 for r in disagreements if r["human_intent"] == r["models"][key])
        on_agr = sum(1 for r in controls if r["human_intent"] == r["models"][key])
        raw = sum(1 for r in rows if r["human_intent"] == r["models"][key]) / len(rows)
        corrected = rate * (on_dis / len(disagreements)) + (1 - rate) * (on_agr / len(controls))
        print(f"  {name:<18s} raw {raw * 100:5.1f}%   corrected {corrected * 100:5.1f}%")

    print("\n  Per-language accuracy is NOT reported. Splitting 125 judgements four ways")
    print("  leaves agreement cells of 5-9 items; one item swings a language by 8-13")
    print("  points. This design was built to decompose disagreements, and cannot")
    print("  support per-language accuracy. The flat agreement result across language")
    print("  forms stands on its own measurement over all 490 (n~123 per form).")

    # --- 6. Where the human said no intent fits, overall ------------------------
    all_unc = [r for r in rows if r["human_intent"] == UNCLASSIFIABLE]
    print("\n" + "=" * 66)
    print("6. EVERY 'NO INTENT FITS' JUDGEMENT")
    print("=" * 66)
    print(line("human called it unclassifiable", len(all_unc), len(rows)))
    breakdown = Counter(r.get("unclassifiable_reason") or "unrecorded" for r in all_unc)
    for reason, count in breakdown.most_common():
        print(f"    {reason:<32s} {count}")


if __name__ == "__main__":
    main()
