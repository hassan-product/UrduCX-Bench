"""Draw the 500-item Phase 3 taxonomy diagnostic sample.

Throwaway. Stratified on language x severity-proxy, not on product, because the
questions are "does the taxonomy fit real complaints" and "is the regex severity
proxy trustworthy" - neither is a per-app question at n=500.

Language strata are equal-sized (125 each) rather than corpus-proportional: the
corpus is 88% English, and a proportional draw would yield ~6 code-switched items,
which cannot show a language-specific taxonomy failure.
"""

from __future__ import annotations

import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

INPUT = Path("data/interim/reviews_phase3_sample_scrubbed.jsonl")
OUTPUT = Path("spike/phase3_diag/sample_500.jsonl")
SEED = 20260826
PER_LANGUAGE = 125
PROXY_TARGET = 60  # per language, capped by availability

MONEY = re.compile(
    r"\b(rs|rupee|rupees|pkr|paisa|paisay|pesay|paise|balance|amount|money"
    r"|transaction|transfer|payment|cash)\b",
    re.I,
)
LOSS = re.compile(
    r"\b(deduct|deducted|deduction|debited|cut|kat|kaat|katay|katy|kati|gaya|lost"
    r"|missing|gayab|stolen|not\s+received|nahi\s+mila|nahi\s+aya|nahi\s+aaya"
    r"|not\s+credited|failed|fail|refund|wapis|stuck|scam|fraud)\b",
    re.I,
)


def severity_proxy(text: str) -> bool:
    """The regex financial-loss proxy used in the pre-label per-app analysis."""
    return bool(MONEY.search(text) and LOSS.search(text))


def main() -> None:
    """Draw and write the stratified diagnostic sample."""
    rng = random.Random(SEED)
    cells: dict[tuple[str, bool], list[dict]] = defaultdict(list)
    for line in INPUT.open(encoding="utf-8"):
        record = json.loads(line)
        text = record.get("text_scrubbed") or ""
        cells[(record["language"], severity_proxy(text))].append(record)

    drawn: list[dict] = []
    for language in ("urdu_script", "roman_urdu", "code_switched", "english"):
        positives = cells[(language, True)]
        negatives = cells[(language, False)]
        take_pos = min(PROXY_TARGET, len(positives))
        take_neg = min(PER_LANGUAGE - take_pos, len(negatives))
        for pool, count, flag in ((positives, take_pos, True), (negatives, take_neg, False)):
            for record in rng.sample(pool, count):
                drawn.append({**record, "severity_proxy": flag})

    rng.shuffle(drawn)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8") as handle:
        for record in drawn:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    by_language = Counter(record["language"] for record in drawn)
    print(f"drew {len(drawn)} into {OUTPUT}")
    for language, count in by_language.most_common():
        positives = sum(
            1 for r in drawn if r["language"] == language and r["severity_proxy"]
        )
        print(f"  {language:16s} {count:4d}  (proxy+ {positives}, proxy- {count - positives})")


if __name__ == "__main__":
    main()
