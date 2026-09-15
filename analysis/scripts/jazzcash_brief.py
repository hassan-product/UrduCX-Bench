"""Build an unbiased JazzCash complaint profile, benchmarked against Easypaisa.

Everything labelled so far was drawn for a research question - stratified by language, or
deliberately enriched for rare intents - so none of it describes what JazzCash users
actually complain about. This draws a plain random sample of complaints per app and labels
it, which is the only way to get a distribution that means anything.

The labels are model-produced, and the Phase 3 diagnostic measured those at roughly 63%
agreement with a human on real reviews. Both models label every item so their disagreement
rate can be reported per category as an honest uncertainty band, rather than presenting a
single confident number that is not warranted.
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
from src.prep.scrub_pii import scrub_records

CORPUS = Path("data/interim/reviews_cleaned.jsonl")
OUT = Path("spike/phase3_diag/jazzcash_brief.jsonl")
CACHE_DIR = Path("spike/phase3_diag/brief_cache")
TAXONOMY = Path("config/taxonomy.yaml")

MODELS = ("claude-sonnet-5", "claude-opus-5")
GROUPS = {
    "JazzCash": {"jazzcash", "jazzcash_business", "jazzcash_retailer"},
    "Easypaisa": {"easypaisa"},
}
PER_GROUP = 250
MIN_WORDS = 5
MAX_RATING = 3
SEED = 20260829


def main() -> None:
    """Draw, scrub, label, and summarise."""
    load_dotenv(Path(".env"))
    rng = random.Random(SEED)

    pools: dict[str, list[dict]] = defaultdict(list)
    for raw in CORPUS.open(encoding="utf-8"):
        row = json.loads(raw)
        text = row.get("text_clean") or ""
        if (row.get("rating") or 5) > MAX_RATING or len(text.split()) < MIN_WORDS:
            continue
        for group, products in GROUPS.items():
            if row["product_id"] in products:
                pools[group].append(row)

    drawn: list[dict[str, Any]] = []
    for group, pool in pools.items():
        take = min(PER_GROUP, len(pool))
        print(f"  {group:12s} {len(pool):5d} complaints available, drawing {take}")
        drawn.extend({**r, "group": group} for r in rng.sample(pool, take))

    scrubbed, counts = scrub_records(drawn)
    print(f"\nscrubbed {len(scrubbed)}; redactions: {dict(counts)}")

    taxonomy = load_taxonomy(TAXONOMY)
    prompt = build_system_prompt(taxonomy)
    schema = build_response_schema(taxonomy)
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    def one(row: dict[str, Any], model: str) -> dict[str, Any] | None:
        text = str(row.get("text_scrubbed") or row.get("text_clean") or "")
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
            except Exception:
                return None
            write_cached_label(CACHE_DIR, key, cached)
        return cached

    def work(row: dict[str, Any]) -> dict[str, Any]:
        return {**row, "labels": {m: one(row, m) for m in MODELS}}

    print("\nlabelling with both models...")
    results = [work(scrubbed[0])]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results.extend(pool.map(work, scrubbed[1:]))
    results = [r for r in results if all(r["labels"].values())]

    with OUT.open("w", encoding="utf-8") as handle:
        for row in results:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"wrote {len(results)} -> {OUT}")

    ref = MODELS[1]
    print("\n" + "=" * 72)
    print("COMPLAINT MIX — random sample of 1-3 star reviews, both apps")
    print("=" * 72)
    mixes = {}
    for group in GROUPS:
        rows = [r for r in results if r["group"] == group]
        mix = Counter(
            r["labels"][ref]["intent"]
            for r in rows
            if r["labels"][ref]["intent"] != "unclassifiable"
        )
        mixes[group] = (mix, sum(mix.values()))

    keys = [k for k, _ in (mixes["JazzCash"][0] + mixes["Easypaisa"][0]).most_common(12)]
    print(f"  {'category':34s} {'JazzCash':>9s} {'Easypaisa':>10s} {'gap':>7s}")
    for k in keys:
        j = mixes["JazzCash"][0][k] / mixes["JazzCash"][1] * 100
        e = mixes["Easypaisa"][0][k] / mixes["Easypaisa"][1] * 100
        mark = "  <<" if j - e > 3 else ("  >>" if e - j > 3 else "")
        print(f"  {k:34s} {j:8.1f}% {e:9.1f}% {j - e:+6.1f}{mark}")

    print("\n" + "=" * 72)
    print("SEVERITY MIX")
    print("=" * 72)
    for group in GROUPS:
        rows = [r for r in results if r["group"] == group]
        sev = Counter(r["labels"][ref]["severity"] for r in rows)
        total = sum(sev.values())
        line = "  ".join(
            f"{s.replace('_', ' ')} {sev[s] / total * 100:.1f}%"
            for s in ("financial_loss", "service_disruption", "friction", "informational")
        )
        print(f"  {group:12s} {line}")

    print("\n" + "=" * 72)
    print("HOW MUCH TO TRUST THIS")
    print("=" * 72)
    for group in GROUPS:
        rows = [r for r in results if r["group"] == group]
        same = sum(
            1 for r in rows if r["labels"][MODELS[0]]["intent"] == r["labels"][ref]["intent"]
        )
        print(f"  {group:12s} the two models agree on {same / len(rows) * 100:.1f}% of items")
    print("\n  Against human gold labels these models ran ~63% on real reviews, so read")
    print("  every figure above as indicative of shape, not as a measured rate. Gaps")
    print("  smaller than a few points are inside the noise.")


if __name__ == "__main__":
    main()
