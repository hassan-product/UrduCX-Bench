"""Re-run the 20 authored complaints under the same conditions as the real reviews.

The headline claim - authored benchmark items overstate inter-model agreement - only
holds if both sides are measured identically. The Phase 2.5 pilot used taxonomy v1 and
the definitions-only prompt; the Phase 3 diagnostic used taxonomy v2, the full prompt
with boundary examples, and structured outputs. Comparing those two directly invites the
obvious objection, so this re-measures the authored set under the diagnostic's exact
conditions and reports both sides side by side.

Accuracy against the authored gold labels is reported too, since these items - unlike
the real reviews - have one.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
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

COMPLAINTS = Path("spike/phase2_5/complaints.json")
CACHE_DIR = Path("spike/phase3_diag/authored_cache")
OUTPUT = Path("spike/phase3_diag/authored_results.jsonl")
TAXONOMY = Path("config/taxonomy.yaml")

MODELS = ("claude-sonnet-5", "claude-opus-5")
LANGUAGES = ("urdu_script", "roman_urdu", "code_switched", "english")
REAL_AGREEMENT = (206, 275)  # from the Phase 3 diagnostic, complaints only


def main() -> None:
    """Label every authored variant with both models and compare against real data."""
    load_dotenv(Path(".env"))
    payload = json.loads(COMPLAINTS.read_text(encoding="utf-8"))
    taxonomy = load_taxonomy(TAXONOMY)
    prompt = build_system_prompt(taxonomy)
    schema = build_response_schema(taxonomy)
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    jobs = [
        {
            "complaint_id": complaint["complaint_id"],
            "gold_intent": complaint["gold_intent"],
            "language": language,
            "text": complaint["variants"][language]["text"],
            "model": model,
        }
        for complaint in payload["complaints"]
        for language in LANGUAGES
        for model in MODELS
    ]

    def work(job: dict[str, Any]) -> dict[str, Any]:
        key = cache_key(job["text"], model=job["model"], taxonomy_version=taxonomy.version)
        cached = load_cached_label(CACHE_DIR, key)
        if cached is None:
            label, _, _ = call_model(
                client.messages.create,
                model=job["model"],
                system_prompt=prompt,
                review_text=job["text"],
                response_schema=schema,
            )
            write_cached_label(CACHE_DIR, key, label)
            cached = label
        return {**job, "predicted_intent": cached["intent"]}

    results = [work(jobs[0])]  # warm the prompt cache before fanning out
    with ThreadPoolExecutor(max_workers=8) as pool:
        results.extend(pool.map(work, jobs[1:]))

    with OUTPUT.open("w", encoding="utf-8") as handle:
        for row in results:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    predictions: dict[tuple[str, str], dict[str, str]] = defaultdict(dict)
    for row in results:
        predictions[(row["complaint_id"], row["language"])][row["model"]] = row["predicted_intent"]

    gold = {c["complaint_id"]: c["gold_intent"] for c in payload["complaints"]}

    print("AUTHORED SET — taxonomy v2, full prompt, structured outputs")
    print("\n  accuracy against authored gold labels")
    for model in MODELS:
        hits = sum(
            1 for (cid, _lang), preds in predictions.items() if preds.get(model) == gold[cid]
        )
        total = sum(1 for preds in predictions.values() if model in preds)
        print(f"    {model:20s} {hits}/{total} = {hits / total * 100:5.1f}%")

    print("\n  inter-model agreement (the metric used on real reviews)")
    per_language: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for (_cid, language), preds in predictions.items():
        if all(model in preds for model in MODELS):
            per_language[language][1] += 1
            per_language[language][0] += preds[MODELS[0]] == preds[MODELS[1]]

    hits = sum(v[0] for v in per_language.values())
    total = sum(v[1] for v in per_language.values())
    print(f"    {'overall':20s} {hits}/{total} = {hits / total * 100:5.1f}%")
    for language in LANGUAGES:
        k, n = per_language[language]
        print(f"    {language:20s} {k}/{n} = {k / n * 100:5.1f}%")

    real_hits, real_total = REAL_AGREEMENT
    authored = hits / total * 100
    real = real_hits / real_total * 100
    print("\nHEADLINE — identical models, taxonomy, prompt and metric")
    print(f"  authored complaints (n={total:3d}) : {authored:5.1f}% agreement")
    print(f"  real complaints     (n={real_total:3d}) : {real:5.1f}% agreement")
    print(f"  gap                            : {authored - real:+5.1f} points")


if __name__ == "__main__":
    main()
