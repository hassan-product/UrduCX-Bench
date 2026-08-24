"""Run the Phase 2.5 script-gap pilot against the configured model roster.

Every one of the 20 human-authored complaints exists in four language forms. Each
variant is sent to each model with an identical classification prompt, so any score
difference reflects the language form rather than the question. Responses are cached
on disk keyed by provider, model, prompt version, taxonomy version, and text, so an
interrupted run resumes for free and a re-run costs nothing.

The pilot is a private development signal. Its results are not a benchmark result and
never enter `data/release/`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from src.label.taxonomy import Taxonomy, load_taxonomy
from src.pilot.authoring import LANGUAGE_FORMS, load_payload
from src.pilot.roster import ModelSpec, load_roster

DEFAULT_PILOT = Path("spike/phase2_5/complaints.json")
DEFAULT_ROSTER = Path("config/models.yaml")
DEFAULT_TAXONOMY = Path("config/taxonomy.yaml")
DEFAULT_CACHE_DIR = Path("spike/phase2_5/pilot_cache")
DEFAULT_RESULTS = Path("spike/phase2_5/pilot_results.jsonl")
DEFAULT_REPORT = Path("spike/phase2_5/pilot_report.md")

PROMPT_VERSION = 1
# Six attempts with a doubling backoff waits up to 2+4+8+16+32 = 62s before the
# final try. Google's free tier answers a quota 429 with "retry in ~40s", which the
# previous five-attempt/30s ladder could not outlast: 43 of 80 Gemini calls were
# dropped in the first full pilot run.
MAX_ATTEMPTS = 6
BACKOFF_BASE_SECONDS = 2.0
MAX_OUTPUT_TOKENS = 512

SleepFunction = Callable[[float], None]


@dataclass(frozen=True)
class ModelReply:
    """One raw model response plus the token counts used to estimate spend."""

    text: str
    input_tokens: int
    output_tokens: int


@dataclass
class RunTotals:
    """Running counters for one pilot run."""

    live_calls: int = 0
    cache_hits: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    errors: int = 0
    spend_usd: float = 0.0
    per_model_spend: dict[str, float] = field(default_factory=dict)


def build_classification_prompt(taxonomy: Taxonomy) -> str:
    """Render one fixed prompt listing every taxonomy intent and its definition.

    The prompt mirrors whatever `config/taxonomy.yaml` currently holds rather than
    duplicating intent text in code, and is identical for every model and every
    language form so the comparison stays fair.
    """
    lines = [
        "You classify customer-service complaints from Pakistani telecom and mobile-wallet apps.",
        "",
        "The complaint may be written in Urdu script, Roman Urdu, English, or a "
        "mixture of Urdu and English. Spelling is often informal or inconsistent.",
        "",
        "Choose the single intent that best describes the customer's problem:",
        "",
    ]
    for intent in taxonomy.intents:
        lines.append(f"- {intent.id}: {intent.definition}")
    lines += [
        "",
        "Reply with exactly one intent id from the list above. "
        "Output only the id, with no punctuation, quotes, or explanation.",
    ]
    return "\n".join(lines)


def parse_intent(reply: str, valid_intents: set[str]) -> str | None:
    """Extract one valid intent id from a model reply, or None if none is present."""
    cleaned = reply.strip().strip("`\"'.").strip().lower()
    if cleaned in valid_intents:
        return cleaned
    # Models sometimes wrap the id in a sentence; accept an unambiguous mention.
    mentioned = [intent for intent in valid_intents if intent in cleaned]
    if len(mentioned) == 1:
        return mentioned[0]
    return None


def cache_key(model: ModelSpec, text: str, *, taxonomy_version: int) -> str:
    """Build a cache identity that changes when anything affecting the answer changes.

    Text alone is insufficient: a reply produced under an older prompt or taxonomy
    must never be reused after either changes.
    """
    payload = "|".join(
        [
            model.provider,
            model.id,
            f"prompt_v{PROMPT_VERSION}",
            f"taxonomy_v{taxonomy_version}",
            text,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_cached(cache_dir: Path, key: str) -> ModelReply | None:
    """Return a cached reply if one exists for this exact identity."""
    path = cache_dir / f"{key}.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ModelReply(
        text=payload["text"],
        input_tokens=int(payload["input_tokens"]),
        output_tokens=int(payload["output_tokens"]),
    )


def write_cached(cache_dir: Path, key: str, reply: ModelReply) -> None:
    """Write one reply to the cache atomically."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{key}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(
            {
                "text": reply.text,
                "input_tokens": reply.input_tokens,
                "output_tokens": reply.output_tokens,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    tmp.replace(path)


def call_with_retry(
    create_fn: Callable[[str, str], ModelReply],
    system: str,
    text: str,
    *,
    sleep_fn: SleepFunction = time.sleep,
    max_attempts: int = MAX_ATTEMPTS,
) -> ModelReply:
    """Call one model, retrying transient failures with exponential backoff."""
    last_error: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return create_fn(system, text)
        except Exception as error:  # noqa: BLE001 - provider SDKs raise unrelated types
            last_error = error
            if attempt == max_attempts - 1:
                break
            sleep_fn(BACKOFF_BASE_SECONDS * (2**attempt))
    raise RuntimeError(f"All {max_attempts} attempts failed") from last_error


def build_anthropic_create(model: ModelSpec) -> Callable[[str, str], ModelReply]:
    """Return a create function for one Anthropic model."""
    from anthropic import Anthropic

    client = Anthropic()

    def create(system: str, text: str) -> ModelReply:
        kwargs: dict[str, Any] = {
            "model": model.id,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "system": system,
            "messages": [{"role": "user", "content": text}],
        }
        if model.effort:
            kwargs["output_config"] = {"effort": model.effort}
        response = client.messages.create(**kwargs)
        reply = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        )
        return ModelReply(
            text=reply,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

    return create


def build_google_create(model: ModelSpec) -> Callable[[str, str], ModelReply]:
    """Return a create function for one Google model."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])

    def create(system: str, text: str) -> ModelReply:
        config: dict[str, Any] = {
            "system_instruction": system,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
        }
        if model.disable_thinking:
            # Only for models that accept a zero budget; Gemini 3.x rejects it with a
            # 400. Left off, reasoning tokens are billed but stay well inside the
            # output allowance for a single-label classification.
            config["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
        response = client.models.generate_content(
            model=model.id,
            contents=text,
            config=types.GenerateContentConfig(**config),
        )
        usage = response.usage_metadata
        return ModelReply(
            text=response.text or "",
            input_tokens=int(usage.prompt_token_count or 0),
            output_tokens=int(usage.candidates_token_count or 0),
        )

    return create


def build_create_fn(model: ModelSpec) -> Callable[[str, str], ModelReply]:
    """Return the provider-appropriate create function for one model."""
    if model.provider == "anthropic":
        return build_anthropic_create(model)
    if model.provider == "google":
        return build_google_create(model)
    raise ValueError(f"Unsupported provider: {model.provider}")


def iter_variants(complaints: list[dict[str, Any]], *, limit: int | None = None):
    """Yield (complaint_id, gold_intent, language_form, text) for each variant."""
    selected = complaints[:limit] if limit is not None else complaints
    for complaint in selected:
        for language in LANGUAGE_FORMS:
            yield (
                complaint["complaint_id"],
                complaint["gold_intent"],
                language,
                complaint["variants"][language]["text"],
            )


def run_model(
    model: ModelSpec,
    complaints: list[dict[str, Any]],
    *,
    system: str,
    valid_intents: set[str],
    taxonomy_version: int,
    cache_dir: Path,
    totals: RunTotals,
    create_fn: Callable[[str, str], ModelReply] | None = None,
    sleep_fn: SleepFunction = time.sleep,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Classify every variant with one model, using the cache before any live call."""
    from src.label.auto_label import RequestPacer

    pacer = RequestPacer(model.min_request_interval, sleep_fn=sleep_fn)
    resolved_create = create_fn
    rows: list[dict[str, Any]] = []

    for complaint_id, gold, language, text in iter_variants(complaints, limit=limit):
        key = cache_key(model, text, taxonomy_version=taxonomy_version)
        reply = load_cached(cache_dir, key)
        if reply is not None:
            totals.cache_hits += 1
        else:
            if resolved_create is None:
                resolved_create = build_create_fn(model)
            pacer.wait()
            try:
                reply = call_with_retry(resolved_create, system, text, sleep_fn=sleep_fn)
            except RuntimeError:
                totals.errors += 1
                rows.append(
                    {
                        "model": model.id,
                        "complaint_id": complaint_id,
                        "language": language,
                        "gold_intent": gold,
                        "predicted_intent": None,
                        "correct": False,
                        "status": "error",
                    }
                )
                continue
            write_cached(cache_dir, key, reply)
            totals.live_calls += 1
            totals.input_tokens += reply.input_tokens
            totals.output_tokens += reply.output_tokens
            spend = model.estimate_usd(reply.input_tokens, reply.output_tokens)
            totals.spend_usd += spend
            totals.per_model_spend[model.id] = totals.per_model_spend.get(model.id, 0.0) + spend

        predicted = parse_intent(reply.text, valid_intents)
        rows.append(
            {
                "model": model.id,
                "complaint_id": complaint_id,
                "language": language,
                "gold_intent": gold,
                "predicted_intent": predicted,
                "correct": predicted == gold,
                "status": "ok" if predicted else "unparseable",
            }
        )
    return rows


def score(rows: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, int]]]:
    """Aggregate counts by model and language form.

    A call that never returned an answer is counted under `errors`, not as a wrong
    answer: accuracy is measured over items the model actually answered, so a
    rate-limited run cannot masquerade as a low score.
    """
    table: dict[str, dict[str, dict[str, int]]] = {}
    for row in rows:
        by_language = table.setdefault(row["model"], {})
        cell = by_language.setdefault(row["language"], {"correct": 0, "answered": 0, "errors": 0})
        if row["status"] == "error":
            cell["errors"] += 1
            continue
        cell["answered"] += 1
        cell["correct"] += int(bool(row["correct"]))
    return table


EMPTY_CELL = {"correct": 0, "answered": 0, "errors": 0}


def _percent(by_language: dict[str, dict[str, int]], language: str) -> float:
    """Return accuracy over answered items for one language form, or 0 when unseen."""
    cell = by_language.get(language, EMPTY_CELL)
    return 100 * cell["correct"] / cell["answered"] if cell["answered"] else 0.0


def render_report(
    rows: list[dict[str, Any]],
    models: list[ModelSpec],
    totals: RunTotals,
) -> str:
    """Render the accuracy grid, the Roman Urdu gaps, and the spend summary."""
    table = score(rows)
    labels = {model.id: model.label for model in models}
    lines = [
        "# Phase 2.5 script-gap pilot — results",
        "",
        "Private development signal on 20 human-authored complaints in four language "
        "forms. Not a benchmark result and not publishable as one.",
        "",
        "## Accuracy by model and language form",
        "",
        "Accuracy is measured over items the model actually answered. Calls that "
        "never returned are reported separately, never as wrong answers.",
        "",
        "| Model | Urdu script | Roman Urdu | Code-switched | English | Overall | Health |",
        "|---|---|---|---|---|---|---|",
    ]
    for model in models:
        by_language = table.get(model.id)
        if not by_language:
            continue
        cells = []
        total_correct = total_answered = total_errors = 0
        for language in LANGUAGE_FORMS:
            cell = by_language.get(language, EMPTY_CELL)
            total_correct += cell["correct"]
            total_answered += cell["answered"]
            total_errors += cell["errors"]
            pct = 100 * cell["correct"] / cell["answered"] if cell["answered"] else 0.0
            cells.append(f"{cell['correct']}/{cell['answered']} ({pct:.0f}%)")
        overall = 100 * total_correct / total_answered if total_answered else 0.0
        note = f" | {total_errors} unanswered" if total_errors else " | —"
        lines.append(
            f"| {labels[model.id]} | {cells[0]} | {cells[1]} | {cells[2]} | "
            f"{cells[3]} | {total_correct}/{total_answered} ({overall:.0f}%){note} |"
        )

    lines += [
        "",
        "## Gap against natural Roman Urdu",
        "",
        "Positive means the other form scored higher than Roman Urdu — the direction "
        "the script-gap hypothesis predicts.",
        "",
        "| Model | Urdu script − Roman | English − Roman | Code-switched − Roman |",
        "|---|---|---|---|",
    ]
    for model in models:
        by_language = table.get(model.id)
        if not by_language:
            continue
        roman = _percent(by_language, "roman_urdu")
        lines.append(
            f"| {labels[model.id]} | {_percent(by_language, 'urdu_script') - roman:+.0f} pts | "
            f"{_percent(by_language, 'english') - roman:+.0f} pts | "
            f"{_percent(by_language, 'code_switched') - roman:+.0f} pts |"
        )

    unparseable = sum(1 for row in rows if row["status"] == "unparseable")
    lines += [
        "",
        "## Run health and spend",
        "",
        f"- Live calls: {totals.live_calls}",
        f"- Cache hits: {totals.cache_hits}",
        f"- Failed after retries: {totals.errors}",
        f"- Replies with no valid intent id: {unparseable}",
        f"- Input tokens: {totals.input_tokens:,}",
        f"- Output tokens: {totals.output_tokens:,}",
        f"- Estimated spend this run: ${totals.spend_usd:.4f}",
        "",
    ]
    for model in models:
        spent = totals.per_model_spend.get(model.id)
        if spent is not None:
            lines.append(f"  - {model.label}: ${spent:.4f}")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    """Parse pilot run options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", type=Path, default=DEFAULT_PILOT)
    parser.add_argument("--roster", type=Path, default=DEFAULT_ROSTER)
    parser.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Classify only the first N complaints — use for a cost smoke test.",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=None,
        help="Restrict the run to one model id; repeatable.",
    )
    return parser.parse_args()


def main() -> None:
    """Run the pilot across the roster and write the results and report."""
    args = parse_args()
    load_dotenv(".env")

    taxonomy = load_taxonomy(args.taxonomy)
    valid_intents = {intent.id for intent in taxonomy.intents}
    system = build_classification_prompt(taxonomy)
    complaints = load_payload(args.pilot)["complaints"]
    models = load_roster(args.roster)
    if args.only:
        models = [model for model in models if model.id in set(args.only)]
        if not models:
            raise SystemExit(f"No roster model matched --only {args.only}")

    if any(model.provider == "anthropic" for model in models) and not os.getenv(
        "ANTHROPIC_API_KEY"
    ):
        raise SystemExit("ANTHROPIC_API_KEY is not set; add it to .env")
    if any(model.provider == "google" for model in models) and not os.getenv("GOOGLE_API_KEY"):
        raise SystemExit("GOOGLE_API_KEY is not set; add it to .env")

    totals = RunTotals()
    rows: list[dict[str, Any]] = []
    for model in models:
        print(f"Running {model.label} ({model.id})...", flush=True)
        rows += run_model(
            model,
            complaints,
            system=system,
            valid_intents=valid_intents,
            taxonomy_version=taxonomy.version,
            cache_dir=args.cache_dir,
            totals=totals,
            limit=args.limit,
        )

    args.results.parent.mkdir(parents=True, exist_ok=True)
    args.results.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    report = render_report(rows, models, totals)
    args.report.write_text(report, encoding="utf-8")
    print()
    print(report)
    print(f"Wrote {args.results} and {args.report}")


if __name__ == "__main__":
    main()
