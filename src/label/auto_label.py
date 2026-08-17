"""Auto-label the PII-scrubbed Phase 3 sample against the human-authored taxonomy.

Sends each scrubbed review to an LLM (default: Claude Haiku 4.5), requesting structured
JSON output (intent, language, severity, confidence, one-sentence rationale). Every
response is cached to disk keyed by a content hash of the scrubbed text, so an
interrupted run resumes for free and re-running an already-labelled sample costs ~$0.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from anthropic import Anthropic, APIStatusError, RateLimitError
from dotenv import load_dotenv

from src.label.taxonomy import Taxonomy, load_taxonomy
from src.prep.scrub_pii import load_jsonl, write_jsonl

DEFAULT_INPUT = Path("data/interim/reviews_phase3_sample_scrubbed.jsonl")
DEFAULT_OUTPUT = Path("data/interim/reviews_phase3_labeled.jsonl")
DEFAULT_TAXONOMY = Path("config/taxonomy.yaml")
DEFAULT_CACHE_DIR = Path("data/interim/label_cache")
DEFAULT_MODEL = "claude-haiku-4-5"

MIN_REQUEST_INTERVAL = 0.5
MAX_ATTEMPTS = 5
BACKOFF_BASE_SECONDS = 2.0

# Decision 17 (PROGRESS_LOG.md): Haiku 4.5 chosen at ~$1/$5 per MTok input/output.
# Update both constants if published pricing changes; this is a spend estimate, not a bill.
PRICE_PER_MTOK_INPUT = 1.0
PRICE_PER_MTOK_OUTPUT = 5.0

REQUIRED_LABEL_FIELDS = ("intent", "language", "severity", "confidence", "rationale")
RETRYABLE_ERRORS = (RateLimitError, APIStatusError)

SleepFunction = Callable[[float], None]
ClockFunction = Callable[[], float]
CreateFunction = Callable[..., Any]


class RequestPacer:
    """Keep starts of consecutive API calls at least one interval apart."""

    def __init__(
        self,
        interval: float,
        *,
        sleep_fn: SleepFunction = time.sleep,
        clock_fn: ClockFunction = time.monotonic,
    ) -> None:
        self.interval = interval
        self.sleep_fn = sleep_fn
        self.clock_fn = clock_fn
        self.last_request_at: float | None = None

    def wait(self) -> None:
        """Wait until another request may start, then record its start time."""
        now = self.clock_fn()
        if self.last_request_at is not None:
            remaining = self.interval - (now - self.last_request_at)
            if remaining > 0:
                self.sleep_fn(remaining)
                now = self.clock_fn()
        self.last_request_at = now


def content_hash(text: str) -> str:
    """Hash scrubbed review text into a stable, resumable cache key."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_system_prompt(taxonomy: Taxonomy) -> str:
    """Render the taxonomy into an instruction prompt for the labelling call."""
    lines = [
        "You are labelling one customer-service review from a Pakistani telecom or "
        "mobile-wallet app. Choose exactly one intent id from the list below, plus a "
        "language and severity label, a confidence score, and a one-sentence rationale.",
        "",
        "Intents:",
    ]
    lines.extend(f"- {intent.id}: {intent.definition}" for intent in taxonomy.intents)
    lines.append("")
    lines.append(f"Language must be one of: {', '.join(taxonomy.languages)}")
    lines.append(f"Severity must be one of: {', '.join(taxonomy.severities)}")
    lines.append("")
    lines.append(
        "Respond with a single JSON object only, no prose, matching exactly: "
        '{"intent": str, "language": str, "severity": str, "confidence": float in [0,1], '
        '"rationale": str (one sentence)}.'
    )
    return "\n".join(lines)


def parse_label_response(raw_text: str) -> dict[str, Any]:
    """Parse and validate one structured labelling response."""
    payload = json.loads(raw_text)
    missing = [field for field in REQUIRED_LABEL_FIELDS if field not in payload]
    if missing:
        raise ValueError(f"Label response missing fields: {missing}")
    return {
        "intent": str(payload["intent"]),
        "language": str(payload["language"]),
        "severity": str(payload["severity"]),
        "confidence": float(payload["confidence"]),
        "rationale": str(payload["rationale"]),
    }


def call_model(
    create_fn: CreateFunction,
    *,
    model: str,
    system_prompt: str,
    review_text: str,
    sleep_fn: SleepFunction = time.sleep,
) -> tuple[dict[str, Any], int, int]:
    """Call the model once for one review, retrying on rate limit/transient errors."""
    last_error: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            response = create_fn(
                model=model,
                max_tokens=300,
                system=system_prompt,
                messages=[{"role": "user", "content": review_text}],
            )
            raw_text = "".join(
                block.text for block in response.content if getattr(block, "type", None) == "text"
            )
            label = parse_label_response(raw_text)
            return label, response.usage.input_tokens, response.usage.output_tokens
        except RETRYABLE_ERRORS as error:
            last_error = error
            if attempt == MAX_ATTEMPTS - 1:
                break
            sleep_fn(BACKOFF_BASE_SECONDS * (2**attempt))
    raise RuntimeError(f"Labelling call failed after {MAX_ATTEMPTS} attempts") from last_error


def load_cached_label(cache_dir: Path, key: str) -> dict[str, Any] | None:
    """Return a cached label response if this exact scrubbed text was already labelled."""
    cache_path = cache_dir / f"{key}.json"
    if not cache_path.exists():
        return None
    return json.loads(cache_path.read_text(encoding="utf-8"))


def write_cached_label(cache_dir: Path, key: str, payload: dict[str, Any]) -> None:
    """Persist one labelling response, keyed by content hash, so re-runs cost ~$0."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{key}.json"
    tmp_path = cache_path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(cache_path)


def label_records(
    records: list[dict[str, Any]],
    *,
    create_fn: CreateFunction,
    model: str,
    taxonomy: Taxonomy,
    cache_dir: Path,
    pacer: RequestPacer,
    sleep_fn: SleepFunction = time.sleep,
    limit: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Label every record, serving cached responses first and pacing live calls."""
    system_prompt = build_system_prompt(taxonomy)
    labeled: list[dict[str, Any]] = []
    spend = {"input_tokens": 0, "output_tokens": 0, "cache_hits": 0, "live_calls": 0}

    for record in records[:limit] if limit else records:
        text = str(record.get("text_scrubbed", ""))
        key = content_hash(text)
        cached = load_cached_label(cache_dir, key)
        if cached is not None:
            spend["cache_hits"] += 1
            label = cached
        else:
            pacer.wait()
            label, input_tokens, output_tokens = call_model(
                create_fn,
                model=model,
                system_prompt=system_prompt,
                review_text=text,
                sleep_fn=sleep_fn,
            )
            spend["input_tokens"] += input_tokens
            spend["output_tokens"] += output_tokens
            spend["live_calls"] += 1
            write_cached_label(cache_dir, key, label)

        labeled.append(
            {
                **record,
                "label_intent": label["intent"],
                "label_language": label["language"],
                "label_severity": label["severity"],
                "label_confidence": label["confidence"],
                "label_rationale": label["rationale"],
            }
        )

    return labeled, spend


def estimate_spend_usd(spend: dict[str, Any]) -> float:
    """Estimate USD spend for this run from token counts (see pricing constants above)."""
    input_cost = spend["input_tokens"] / 1_000_000 * PRICE_PER_MTOK_INPUT
    output_cost = spend["output_tokens"] / 1_000_000 * PRICE_PER_MTOK_OUTPUT
    return input_cost + output_cost


def print_report(spend: dict[str, Any]) -> None:
    """Print a one-screen cache/spend summary."""
    print(f"Cache hits   : {spend['cache_hits']:,}")
    print(f"Live calls   : {spend['live_calls']:,}")
    print(f"Input tokens : {spend['input_tokens']:,}")
    print(f"Output tokens: {spend['output_tokens']:,}")
    print(f"Estimated spend this run: ${estimate_spend_usd(spend):.2f}")


def parse_args() -> argparse.Namespace:
    """Parse auto-labelling options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--limit", type=int, default=None, help="Label only the first N records")
    return parser.parse_args()


def main() -> None:
    """Label the scrubbed Phase 3 sample and write the labelled file plus spend report."""
    load_dotenv()
    args = parse_args()
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("ANTHROPIC_API_KEY is not set (add it to a local .env file)")

    records = load_jsonl(args.input)
    if not records:
        raise SystemExit(f"No records found in {args.input}")
    taxonomy = load_taxonomy(args.taxonomy)

    client = Anthropic(api_key=api_key)
    pacer = RequestPacer(MIN_REQUEST_INTERVAL)
    labeled, spend = label_records(
        records,
        create_fn=client.messages.create,
        model=args.model,
        taxonomy=taxonomy,
        cache_dir=args.cache_dir,
        pacer=pacer,
        limit=args.limit,
    )

    write_jsonl(args.output, labeled)
    print_report(spend)
    print(f"Wrote {len(labeled):,} labelled records to {args.output}")


if __name__ == "__main__":
    main()
