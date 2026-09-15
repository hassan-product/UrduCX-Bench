"""Compare the blind re-check pass against the original judgements.

With no second annotator available, test-retest is the measurable substitute: the same
person labels the same reviews again, days later, without seeing the earlier answer. It
does not address the deeper problem that the annotator wrote the taxonomy - nothing but a
second person does - but it does answer whether the task is stable or arbitrary, which is
otherwise unknown.

A low score is a publishable result, not a failure: it would mean the task is genuinely
hard and no annotator could do much better.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

DIR = Path("spike/phase3_diag")
FIRST = DIR / "adjudications.jsonl"
SECOND = DIR / "adjudications_recheck.jsonl"
SAMPLE = DIR / "sample_500.jsonl"


def load(path: Path) -> dict[str, dict]:
    """Judgements keyed by review id."""
    if not path.exists():
        return {}
    return {
        json.loads(line)["review_id"]: json.loads(line)
        for line in path.open(encoding="utf-8")
        if line.strip()
    }


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson interval."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    margin = z / d * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def kappa(pairs: list[tuple[str, str]]) -> float:
    """Chance-corrected agreement over the shared label set."""
    if not pairs:
        return float("nan")
    n = len(pairs)
    observed = sum(1 for a, b in pairs if a == b) / n
    first, second = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    expected = sum(first[k] / n * second[k] / n for k in set(first) | set(second))
    return (observed - expected) / (1 - expected) if expected < 1 else float("nan")


def main() -> None:
    """Report self-agreement and where the two passes diverged."""
    first, second = load(FIRST), load(SECOND)
    shared = sorted(set(first) & set(second))
    if not shared:
        print("No re-check judgements yet. Run:")
        print("  python -m spike.phase3_diag.adjudicate --mode recheck --n 50")
        return

    meta = {
        json.loads(line)["review_id"]: json.loads(line) for line in SAMPLE.open(encoding="utf-8")
    }

    pairs = [(first[r]["human_intent"], second[r]["human_intent"]) for r in shared]
    same = sum(1 for a, b in pairs if a == b)
    lo, hi = wilson(same, len(pairs))

    print(f"Blind re-check: {len(shared)} reviews judged twice\n")
    print(
        f"  same answer both times   {same}/{len(pairs)} = {same / len(pairs) * 100:.1f}%"
        f"  [{lo * 100:.1f}, {hi * 100:.1f}]"
    )
    print(f"  Cohen's kappa            {kappa(pairs):.3f}")

    print("\n  Reading: >0.80 near-perfect, 0.61-0.80 substantial, 0.41-0.60 moderate.")
    print("  A moderate score is reportable - it bounds what any annotator could reach.")

    changed = [r for r in shared if first[r]["human_intent"] != second[r]["human_intent"]]
    if changed:
        print(f"\n  Changed on {len(changed)}:")
        for r in changed[:12]:
            text = (meta.get(r, {}).get("text_scrubbed") or "")[:56]
            print(f"    {first[r]['human_intent'][:28]:28s} -> {second[r]['human_intent'][:28]}")
            print(f"      {text}")

        pairs_c = Counter(
            tuple(sorted((first[r]["human_intent"], second[r]["human_intent"]))) for r in changed
        )
        repeated = [(p, c) for p, c in pairs_c.most_common() if c > 1]
        if repeated:
            print("\n  Intent pairs confused more than once - candidates for a v3 boundary:")
            for (a, b), count in repeated:
                print(f"    {a} <-> {b}   ({count}x)")


if __name__ == "__main__":
    main()
