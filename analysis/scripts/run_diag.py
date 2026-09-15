"""Label the 500-item diagnostic sample with the extended v2 schema.

Throwaway. Answers four questions the project has never asked of real data:

1. unclassifiable rate  - do real complaints fall outside the 24 intents?
2. multi-intent rate    - is single-label (T1) tenable? (V2 open question 4)
3. model agreement      - a proxy for accuracy where no gold labels exist
4. proxy validation     - does the regex severity proxy match a real severity label?

Failed calls are reported separately and never scored as answers (Issue 13).
"""

from __future__ import annotations

import argparse
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from anthropic import Anthropic
from dotenv import load_dotenv
from src.label.auto_label import (
    MAX_ATTEMPTS,
    RETRYABLE_ERRORS,
    build_system_prompt,
    load_cached_label,
    write_cached_label,
)
from src.label.taxonomy import Taxonomy, load_taxonomy

SAMPLE = Path("spike/phase3_diag/sample_500.jsonl")
OUTPUT_DIR = Path("spike/phase3_diag")
CACHE_DIR = Path("spike/phase3_diag/diag_cache")
TAXONOMY = Path("config/taxonomy.yaml")

DIAG_PROMPT_VERSION = 1
# Two models that tied at 95% in the Phase 2.5 pilot. Where they disagree on a real
# review, the item or the taxonomy is ambiguous - not one model weaker than the other.
# Haiku 4.5 is excluded: it scored 86%, and its minimum cacheable prefix is above this
# prompt's ~3.8k tokens, so it would run uncached and muddy agreement with model skill.
MODELS = ("claude-sonnet-5", "claude-opus-5")
PRICING = {  # USD per MTok (input, output)
    "claude-sonnet-5": (2.0, 10.0),
    "claude-opus-5": (5.0, 25.0),
}
CACHE_WRITE_MULTIPLIER = 1.25
CACHE_READ_MULTIPLIER = 0.10
EFFORT = "low"  # classification, not reasoning; keeps thinking tokens off the bill
WORKERS = 8

EXTENDED_INSTRUCTIONS = """
Output schema (JSON object only, no prose):
{
  "intent": one intent id above, or "unclassifiable" if no intent genuinely fits,
  "intent_secondary": a second intent id if the review clearly reports two distinct
                      matters, otherwise null,
  "refund_requested": true if the user asks for money back, else false,
  "language": one of the language labels,
  "severity": one of the severity labels,
  "confidence": float in [0,1],
  "rationale": one sentence
}

Use "unclassifiable" honestly. A review that is empty praise, an unreadable fragment,
or about something none of the 24 intents covers is unclassifiable - do not force it
into the nearest intent. Set intent_secondary only for a genuinely separate second
matter, not for a restatement of the primary one.
""".strip()

REQUIRED = (
    "intent",
    "intent_secondary",
    "refund_requested",
    "language",
    "severity",
    "confidence",
    "rationale",
)

_print_lock = threading.Lock()


def build_diag_prompt(taxonomy: Taxonomy) -> str:
    """Taxonomy rendering from the fixed labeller, plus the extended output schema."""
    base = build_system_prompt(taxonomy)
    base = base.split("Respond with a single JSON object only")[0].rstrip()
    return f"{base}\n\n{EXTENDED_INSTRUCTIONS}"


def diag_cache_key(text: str, *, model: str, taxonomy_version: int) -> str:
    """Cache identity for this diagnostic: model, prompt shape, taxonomy, text."""
    import hashlib

    payload = "|".join(
        (model, f"diag_v{DIAG_PROMPT_VERSION}", f"taxonomy_v{taxonomy_version}", text)
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def parse(raw: str) -> dict[str, Any]:
    """Parse one extended-schema reply, tolerating a fenced code block."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        text = text[4:] if text.startswith("json") else text
    payload = json.loads(text)
    missing = [field for field in REQUIRED if field not in payload]
    if missing:
        raise ValueError(f"missing fields: {missing}")
    return payload


def label_one(
    client: Anthropic, record: dict, *, model: str, prompt: str, taxonomy_version: int
) -> dict[str, Any]:
    """Label one review, serving the disk cache first; returns a status envelope."""
    text = str(record.get("text_scrubbed", ""))
    key = diag_cache_key(text, model=model, taxonomy_version=taxonomy_version)

    cached = load_cached_label(CACHE_DIR, key)
    if cached is not None:
        return {"status": "cached", "label": cached, "input_tokens": 0, "output_tokens": 0}

    last_error: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=400,
                output_config={"effort": EFFORT},
                system=[
                    {"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}}
                ],
                messages=[{"role": "user", "content": text}],
            )
            raw = "".join(
                b.text for b in response.content if getattr(b, "type", None) == "text"
            )
            label = parse(raw)
            write_cached_label(CACHE_DIR, key, label)
            return {
                "status": "ok",
                "label": label,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "cache_read": getattr(response.usage, "cache_read_input_tokens", 0) or 0,
                "cache_write": getattr(response.usage, "cache_creation_input_tokens", 0) or 0,
            }
        except RETRYABLE_ERRORS as error:
            last_error = error
            if attempt < MAX_ATTEMPTS - 1:
                import time

                time.sleep(2.0 * (2**attempt))
        except (ValueError, json.JSONDecodeError) as error:
            return {"status": "unparseable", "error": str(error)}
    return {"status": "failed", "error": str(last_error)}


def run_model(client: Anthropic, records: list[dict], model: str, taxonomy: Taxonomy) -> None:
    """Label the whole sample with one model and write results plus a spend line."""
    prompt = build_diag_prompt(taxonomy)
    with _print_lock:
        print(f"\n=== {model} — prompt {len(prompt):,} chars ===")

    # Warm the prompt cache with one call before fanning out, so the other 499 read it.
    first = label_one(
        client, records[0], model=model, prompt=prompt, taxonomy_version=taxonomy.version
    )

    def work(record: dict) -> dict:
        return label_one(
            client, record, model=model, prompt=prompt, taxonomy_version=taxonomy.version
        )

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        rest = list(pool.map(work, records[1:]))

    results = [first, *rest]
    rows = []
    tallies = {"ok": 0, "cached": 0, "failed": 0, "unparseable": 0}
    input_tokens = output_tokens = cache_read = cache_write = 0
    for record, result in zip(records, results, strict=True):
        tallies[result["status"]] += 1
        input_tokens += result.get("input_tokens", 0)
        output_tokens += result.get("output_tokens", 0)
        cache_read += result.get("cache_read", 0)
        cache_write += result.get("cache_write", 0)
        rows.append(
            {
                "review_id": record["review_id"],
                "product_id": record["product_id"],
                "language_detected": record["language"],
                "rating": record.get("rating"),
                "severity_proxy": record["severity_proxy"],
                "status": result["status"],
                **({"label": result["label"]} if "label" in result else {}),
                **({"error": result["error"]} if "error" in result else {}),
            }
        )

    out = OUTPUT_DIR / f"diag_{model.replace('.', '-')}.jsonl"
    with out.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    price_in, price_out = PRICING[model]
    spend = (
        input_tokens / 1e6 * price_in
        + cache_write / 1e6 * price_in * CACHE_WRITE_MULTIPLIER
        + cache_read / 1e6 * price_in * CACHE_READ_MULTIPLIER
        + output_tokens / 1e6 * price_out
    )
    with _print_lock:
        print(f"  {tallies}")
        print(
            f"  uncached in {input_tokens:,} | cache write {cache_write:,} "
            f"| cache read {cache_read:,} | out {output_tokens:,}"
        )
        print(f"  spend ${spend:.4f} -> {out}")


def main() -> None:
    """Run the diagnostic across the configured models."""
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--models", nargs="*", default=list(MODELS))
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("ANTHROPIC_API_KEY is not set")

    records = [json.loads(line) for line in SAMPLE.open(encoding="utf-8")]
    if args.limit:
        records = records[: args.limit]
    taxonomy = load_taxonomy(TAXONOMY)
    client = Anthropic(api_key=api_key)

    print(f"{len(records)} records, taxonomy v{taxonomy.version}")
    for model in args.models:
        run_model(client, records, model, taxonomy)


if __name__ == "__main__":
    main()
