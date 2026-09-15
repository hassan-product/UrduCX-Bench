"""Top up the intents the first hunt showed were reachable.

The hunt labelled the 50 best-matching candidates per intent. Five intents came back
viable but short of the >=30 target, so this takes the *next* slice of the same ranking
for those five only. Everything else - patterns, scrubbing, model, cache - is reused, so
a candidate already labelled by the hunt is served from cache and costs nothing.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from anthropic import Anthropic
from dotenv import load_dotenv
from hunt_starved import (  # sibling script in this directory
    CACHE_DIR,
    CORPUS,
    MIN_WORDS,
    MODEL,
    PATTERNS,
    score,
)
from src.label.auto_label import (
    build_response_schema,
    build_system_prompt,
    cache_key,
    call_model,
    load_cached_label,
    write_cached_label,
)
from src.label.taxonomy import load_taxonomy
from src.prep.scrub_pii import scrub_records

OUTPUT = Path("spike/phase3_diag/topup_results.jsonl")
HUNT_RESULTS = Path("spike/phase3_diag/hunt_results.jsonl")
TAXONOMY = Path("config/taxonomy.yaml")
TARGET = 30

# Candidates already spent, and how many confirmed examples each intent has so far.
ALREADY_RANKED = 50
# Confirmed examples held at the start of the current run. Update after each run.
NEEDED: dict[str, int] = {
    "refund_request": 10,
    "bill_payment_not_reflected": 28,
    "scam_impersonation_report": 18,
    "account_compromised": 20,
    "loan_repayment_dispute": 25,
}


def next_slice(
    rows: list[dict[str, Any]], intent: str, want: int, seen: set[str]
) -> list[dict[str, Any]]:
    """Take the next unlabelled candidates below the slice the hunt already used.

    Filtering by `seen` rather than by a fixed window means repeated runs advance down
    the ranking instead of redrawing the same candidates.
    """
    groups = [re.compile(p, re.I | re.UNICODE) for p in PATTERNS[intent]]
    scored = []
    for row in rows:
        text = row.get("text_clean") or ""
        if len(text.split()) < MIN_WORDS:
            continue
        hits = score(text, groups)
        if hits:
            scored.append((hits, row))
    scored.sort(key=lambda pair: -pair[0])
    fresh = [row for _, row in scored[ALREADY_RANKED:] if row["review_id"] not in seen]
    return fresh[:want]


def main() -> None:
    """Label the next candidate slice for each short intent and report new totals."""
    load_dotenv(Path(".env"))
    rows = [json.loads(line) for line in CORPUS.open(encoding="utf-8")]
    seen: set[str] = set()
    for path in (HUNT_RESULTS, OUTPUT):
        if path.exists():
            seen |= {json.loads(line)["review_id"] for line in path.open(encoding="utf-8")}

    flat: list[dict[str, Any]] = []
    for intent, found in NEEDED.items():
        # Yield so far predicts how many more candidates it takes to reach the target.
        # Yield decays further down the ranking, so the rate observed in the first slice
        # over-predicts. Floor the draw so a near-miss does not need several more runs.
        rate = max(found / ALREADY_RANKED, 0.05)
        want = min(400, max(25, round((TARGET - found) / rate)))
        picked = next_slice(rows, intent, want, seen)
        print(f"  {intent:34s} have {found:2d}, drawing {len(picked):3d} more")
        flat.extend({**row, "hunted_for": intent} for row in picked)

    scrubbed, counts = scrub_records(flat)
    print(f"\nscrubbed {len(scrubbed)}; redactions: {dict(counts)}")

    taxonomy = load_taxonomy(TAXONOMY)
    prompt = build_system_prompt(taxonomy)
    schema = build_response_schema(taxonomy)
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    def work(record: dict[str, Any]) -> dict[str, Any]:
        text = str(record.get("text_scrubbed") or record.get("text_clean") or "")
        key = cache_key(text, model=MODEL, taxonomy_version=taxonomy.version)
        cached = load_cached_label(CACHE_DIR, key)
        if cached is not None:
            return {**record, "label": cached, "status": "cached"}
        try:
            label, _, _ = call_model(
                client.messages.create,
                model=MODEL,
                system_prompt=prompt,
                review_text=text,
                response_schema=schema,
            )
        except Exception as error:
            return {**record, "status": "failed", "error": str(error)[:200]}
        write_cached_label(CACHE_DIR, key, label)
        return {**record, "label": label, "status": "ok"}

    results = [work(scrubbed[0])]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results.extend(pool.map(work, scrubbed[1:]))

    # Merge with any earlier top-up rather than overwriting it: this script is meant to be
    # re-run as intents fill up, and a plain "w" silently discarded the previous pass.
    merged: dict[str, dict[str, Any]] = {}
    if OUTPUT.exists():
        for line in OUTPUT.open(encoding="utf-8"):
            row = json.loads(line)
            merged[row["review_id"]] = row
    for row in results:
        merged[row["review_id"]] = row
    with OUTPUT.open("w", encoding="utf-8") as handle:
        for row in merged.values():
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    # Combined totals across hunt + top-up, counting primary and secondary labels.
    totals: Counter = Counter()
    for path in (HUNT_RESULTS, OUTPUT):
        for line in path.open(encoding="utf-8"):
            row = json.loads(line)
            if "label" not in row:
                continue
            totals[row["label"]["intent"]] += 1
            if row["label"].get("intent_secondary"):
                totals[row["label"]["intent_secondary"]] += 1

    print(f"\n{'intent':34s} {'before':>7s} {'after':>6s}   status")
    print("-" * 70)
    for intent, before in NEEDED.items():
        after = totals[intent]
        mark = "REACHED >=30" if after >= TARGET else f"short by {TARGET - after}"
        print(f"{intent:34s} {before:7d} {after:6d}   {mark}")

    failed = sum(1 for r in results if r["status"] == "failed")
    print(f"\nlabelled {len(results) - failed} of {len(results)} ({failed} failed) -> {OUTPUT}")


if __name__ == "__main__":
    main()
