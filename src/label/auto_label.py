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
LABEL_EFFORT = "low"  # classification, not reasoning
MAX_LABEL_TOKENS = 700

# `effort` is rejected outright by pre-4.6 models: Haiku 4.5 returns
# "This model does not support the effort parameter" as a 400. Sending it
# unconditionally made the whole roster silently un-runnable for cheaper models -
# which are the ones actually deployed for high-volume work.
MODELS_WITHOUT_EFFORT = frozenset({"claude-haiku-4-5", "claude-sonnet-4-5"})


def supports_effort(model: str) -> bool:
    """Whether this model accepts output_config.effort."""
    return model not in MODELS_WITHOUT_EFFORT


MAX_ATTEMPTS = 5
BACKOFF_BASE_SECONDS = 2.0

# Decision 17 (PROGRESS_LOG.md): Haiku 4.5 chosen at ~$1/$5 per MTok input/output.
# Update both constants if published pricing changes; this is a spend estimate, not a bill.
PRICE_PER_MTOK_INPUT = 1.0
PRICE_PER_MTOK_OUTPUT = 5.0

# Bump when build_system_prompt changes shape: the rendered prompt is part of cache
# identity, so a prompt change must invalidate every previously cached reply.
PROMPT_VERSION = 3

UNCLASSIFIABLE = "unclassifiable"

# Extended per the Phase 3 diagnostic (spike/phase3_diag): 11.8% of real reviews carry a
# second distinct intent, so single-label discards signal on ~1 in 8. `refund_requested`
# and `intent_secondary` are named by the taxonomy v2 precedence rule itself.
REQUIRED_LABEL_FIELDS = (
    "intent",
    "intent_secondary",
    "refund_requested",
    "language",
    "severity",
    "confidence",
    "rationale",
)
RETRYABLE_ERRORS = (RateLimitError, APIStatusError)


def is_retryable(error: Exception) -> bool:
    """Only rate limits and server faults are worth retrying.

    A 400 (malformed request, bad schema) fails identically every time; retrying it
    multiplies a single mistake by MAX_ATTEMPTS across the whole run.
    """
    if isinstance(error, RateLimitError):
        return True
    status = getattr(error, "status_code", None)
    return status is not None and (status == 429 or status >= 500)


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


def cache_key(text: str, *, model: str, taxonomy_version: int) -> str:
    """Hash the full request identity, not just the text.

    Keying on text alone lets one model serve another model's reply, and lets a
    stale reply survive a prompt or taxonomy change. Mirrors `src/pilot/run_pilot.py`.
    """
    payload = "|".join((model, f"prompt_v{PROMPT_VERSION}", f"taxonomy_v{taxonomy_version}", text))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_system_prompt(taxonomy: Taxonomy) -> str:
    """Render the taxonomy into an instruction prompt for the labelling call."""
    lines = [
        "You are labelling one customer-service review from a Pakistani telecom or "
        "mobile-wallet app. Choose the single best intent id from the list below, plus a "
        "language and severity label, a confidence score, and a one-sentence rationale.",
        "",
        "Intents:",
    ]
    for intent in taxonomy.intents:
        lines.append(f"- {intent.id} ({intent.family})")
        lines.append(f"    definition: {intent.definition.strip()}")
        for example in intent.positive_examples:
            lines.append(f"    positive: {example}")
        lines.append(f"    NOT this intent: {intent.negative_example}")
        lines.append(f"    because: {intent.negative_rationale.strip()}")
    lines.append("")
    lines.append(f"Language must be one of: {', '.join(taxonomy.languages)}")
    lines.append(f"Severity must be one of: {', '.join(taxonomy.severities)}")
    lines.append("")
    lines.append(
        f'Use "{UNCLASSIFIABLE}" for the intent when no listed intent genuinely fits - '
        "praise, an unreadable fragment, or a subject none of the intents covers. Do not "
        "force such a review into the nearest intent."
    )
    lines.append(
        "Set intent_secondary only when the review reports a genuinely separate second "
        "matter, not a restatement of the first; otherwise null."
    )
    lines.append(
        "Set refund_requested independently of the intent: true whenever the user asks for "
        "money back, even when the intent is the underlying failure (taxonomy v2 precedence)."
    )
    return "\n".join(lines)


def build_response_schema(taxonomy: Taxonomy) -> dict[str, Any]:
    """Constrain the reply to the taxonomy's own vocabulary.

    Enum-bound fields make a hallucinated intent id structurally impossible rather than
    merely unlikely, and remove the free-text JSON parse failures the diagnostic saw.
    """
    intent_ids = [intent.id for intent in taxonomy.intents]
    return {
        "type": "json_schema",
        "schema": {
            "type": "object",
            "properties": {
                "intent": {"type": "string", "enum": [*intent_ids, UNCLASSIFIABLE]},
                "intent_secondary": {
                    "anyOf": [{"type": "string", "enum": intent_ids}, {"type": "null"}]
                },
                "refund_requested": {"type": "boolean"},
                "language": {"type": "string", "enum": list(taxonomy.languages)},
                "severity": {"type": "string", "enum": list(taxonomy.severities)},
                # The API rejects minimum/maximum on "number"; the range is enforced
                # in parse_label_response instead.
                "confidence": {"type": "number"},
                "rationale": {"type": "string"},
            },
            "required": list(REQUIRED_LABEL_FIELDS),
            "additionalProperties": False,
        },
    }


def _bounded_confidence(value: Any) -> float:
    """Coerce confidence into [0, 1]; the response schema cannot express the bound."""
    confidence = float(value)
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(f"confidence {confidence} outside [0, 1]")
    return confidence


def parse_label_response(raw_text: str) -> dict[str, Any]:
    """Parse and validate one structured labelling response."""
    payload = json.loads(raw_text)
    missing = [field for field in REQUIRED_LABEL_FIELDS if field not in payload]
    if missing:
        raise ValueError(f"Label response missing fields: {missing}")
    secondary = payload["intent_secondary"]
    return {
        "intent": str(payload["intent"]),
        "intent_secondary": None if secondary is None else str(secondary),
        "refund_requested": bool(payload["refund_requested"]),
        "language": str(payload["language"]),
        "severity": str(payload["severity"]),
        "confidence": _bounded_confidence(payload["confidence"]),
        "rationale": str(payload["rationale"]),
    }


def call_model(
    create_fn: CreateFunction,
    *,
    model: str,
    system_prompt: str,
    review_text: str,
    response_schema: dict[str, Any] | None = None,
    sleep_fn: SleepFunction = time.sleep,
) -> tuple[dict[str, Any], int, int]:
    """Call the model once for one review, retrying on rate limit/transient errors."""
    last_error: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            output_config: dict[str, Any] = (
                {"effort": LABEL_EFFORT} if supports_effort(model) else {}
            )
            if response_schema is not None:
                output_config["format"] = response_schema
            response = create_fn(
                model=model,
                # 300 truncated rationales mid-string on longer non-English reviews,
                # which surfaced as a JSON parse failure rather than a length error.
                # Urdu script and Roman Urdu also tokenize less efficiently than English,
                # so an identical budget silently favours English inputs.
                max_tokens=MAX_LABEL_TOKENS,
                output_config=output_config,
                system=[
                    {
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": review_text}],
            )
            raw_text = "".join(
                block.text for block in response.content if getattr(block, "type", None) == "text"
            )
            label = parse_label_response(raw_text)
            return label, response.usage.input_tokens, response.usage.output_tokens
        except RETRYABLE_ERRORS as error:
            if not is_retryable(error):
                raise
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
    response_schema = build_response_schema(taxonomy)
    labeled: list[dict[str, Any]] = []
    spend = {"input_tokens": 0, "output_tokens": 0, "cache_hits": 0, "live_calls": 0}

    for record in records[:limit] if limit else records:
        text = str(record.get("text_scrubbed", ""))
        key = cache_key(text, model=model, taxonomy_version=taxonomy.version)
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
                response_schema=response_schema,
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
                "label_intent_secondary": label["intent_secondary"],
                "label_refund_requested": label["refund_requested"],
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
