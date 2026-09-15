"""Retest the script-gap hypothesis on real reviews, with human gold labels.

The Phase 2.5 pilot tested this on 20 authored complaints rendered in four scripts - the
right instrument, because content is held constant, but too small to conclude from. The
Phase 3 diagnostic could not answer it either: its sample was enriched for model
disagreement, which distorts accuracy, and splitting 125 judgements four ways left cells
of 5-9 items.

This pass fixes both. Sampling is random within each language (no enrichment), and each
non-Urdu stratum is matched to the Urdu-script length distribution, because Urdu-script
complaints run a median 23 words against English's 14 - a difference large enough that an
unmatched comparison would measure verbosity as much as script.

What it can answer: does a model do worse on the Urdu-script portion of a real corpus?
What it still cannot: whether script itself is the cause. Language remains confounded with
subject matter (Urdu-script reviews skew to UX complaints, English to OTP), and only a
parallel corpus can separate those. The intent mix is reported so a reader can judge.
"""

from __future__ import annotations

import json
import os
import random
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from anthropic import Anthropic
from dotenv import load_dotenv
from src.label.auto_label import (
    build_response_schema,
    build_system_prompt,
    cache_key,
    call_model,
    load_cached_label,
    write_cached_label,
)
from src.label.taxonomy import load_taxonomy

DIR = Path("spike/phase3_diag")
SOURCE = Path("data/interim/reviews_phase3_sample_scrubbed.jsonl")
JUDGED = DIR / "adjudications.jsonl"
WORKLIST = DIR / "urdu_pass_worklist.jsonl"
CACHE_DIR = DIR / "urdu_pass_cache"
TAXONOMY = Path("config/taxonomy.yaml")

# Haiku 4.5 is added last and deliberately. It was excluded from the diagnostic because
# its lower ceiling would have mixed model skill into the ambiguity signal - a sound reason
# for that experiment, and no reason at all to leave the question unasked. It is also the
# only model in the Phase 2.5 pilot that answered the same complaint differently depending
# on the script it was written in (14/20 stable, against 18 and 20), and it is the class of
# model actually deployed for high-volume triage. Frontier models showing no gap does not
# establish that cheaper ones do not.
MODELS = ("claude-sonnet-5", "claude-opus-5", "claude-haiku-4-5")
LANGUAGES = ("urdu_script", "roman_urdu", "code_switched", "english")
PER_LANGUAGE = 60
MIN_WORDS = 5
MAX_RATING = 3
SEED = 20260829


def length_bucket(text: str) -> str:
    """Coarse length bands, used to match strata rather than to analyse."""
    words = len((text or "").split())
    if words < 10:
        return "short"
    if words < 20:
        return "medium"
    if words < 40:
        return "long"
    return "very_long"


def draw(per_language: int = PER_LANGUAGE) -> list[dict[str, Any]]:
    """Draw a length-matched, unenriched sample for each language form."""
    rng = random.Random(SEED)
    judged = {
        json.loads(line)["review_id"] for line in JUDGED.open(encoding="utf-8") if line.strip()
    }

    pools: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for line in SOURCE.open(encoding="utf-8"):
        row = json.loads(line)
        text = row.get("text_scrubbed") or ""
        if row["review_id"] in judged:
            continue
        if (row.get("rating") or 5) > MAX_RATING or len(text.split()) < MIN_WORDS:
            continue
        pools[row["language"]][length_bucket(text)].append(row)

    # Urdu script is the scarcest stratum, so its length profile sets the target and
    # every other language is drawn to match it.
    urdu = pools["urdu_script"]
    target_n = min(per_language, sum(len(v) for v in urdu.values()))
    total_urdu = sum(len(v) for v in urdu.values())
    shape = {bucket: round(len(rows) / total_urdu * target_n) for bucket, rows in urdu.items()}

    drawn: list[dict[str, Any]] = []
    for language in LANGUAGES:
        for bucket, want in shape.items():
            available = pools[language].get(bucket, [])
            take = min(want, len(available))
            for row in rng.sample(available, take):
                drawn.append({**row, "length_bucket": bucket})
    rng.shuffle(drawn)
    return drawn


def main() -> None:
    """Draw the sample, label it with both models, and write the worklist."""
    load_dotenv(Path(".env"))
    rows = draw()

    counts = Counter(r["language"] for r in rows)
    print(f"drew {len(rows)} reviews (length-matched to the Urdu-script profile)")
    for language in LANGUAGES:
        buckets = Counter(r["length_bucket"] for r in rows if r["language"] == language)
        print(f"  {language:16s} {counts[language]:3d}   {dict(buckets)}")

    taxonomy = load_taxonomy(TAXONOMY)
    prompt = build_system_prompt(taxonomy)
    schema = build_response_schema(taxonomy)
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    def label(row: dict[str, Any], model: str) -> str | None:
        text = str(row.get("text_scrubbed") or "")
        key = cache_key(text, model=model, taxonomy_version=taxonomy.version)
        cached = load_cached_label(CACHE_DIR, key)
        if cached is None:
            try:
                cached, _, _ = call_model(
                    client.messages.create,
                    model=model,
                    system_prompt=prompt,
                    review_text=text,
                    response_schema=schema,
                )
            except Exception as error:  # reported, never scored as an answer
                print(f"  failed {row['review_id'][:8]} on {model}: {str(error)[:80]}")
                return None
            write_cached_label(CACHE_DIR, key, cached)
        return cached["intent"]

    def work(row: dict[str, Any]) -> dict[str, Any]:
        return {**row, "models": {m: label(row, m) for m in MODELS}}

    print("\nlabelling with both models...")
    results = [work(rows[0])]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results.extend(pool.map(work, rows[1:]))

    results = [r for r in results if any(r["models"].values())]
    with WORKLIST.open("w", encoding="utf-8") as handle:
        for row in results:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"\nwrote {len(results)} labelled items to {WORKLIST}")
    print("\nmodel agreement before any human judgement (a free preview):")
    for language in LANGUAGES:
        group = [r for r in results if r["language"] == language]
        if not group:
            continue
        answers = [{m: i for m, i in r["models"].items() if i} for r in group]
        same = sum(1 for a in answers if len(set(a.values())) == 1)
        print(f"  {language:16s} {same:3d}/{len(group):<3d} = {same / len(group) * 100:5.1f}%")


if __name__ == "__main__":
    main()
