"""Redact PII from cleaned review text before it is sent to any external API.

Matching uses a same-length ASCII-digit view so Pakistani PII written with ASCII,
Urdu-Indic, or Arabic-Indic numerals can be found without altering the source text.
Only typed PII spans are redacted; transaction references and other long facts survive.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

DEFAULT_INPUT = Path("data/interim/reviews_phase3_sample.jsonl")
DEFAULT_OUTPUT = Path("data/interim/reviews_phase3_sample_scrubbed.jsonl")

# Patterns are applied in priority order. The named `pii` group allows account/name
# context to remain visible while only the private value is replaced.
_PATTERNS: tuple[tuple[str, str], ...] = (
    ("email", r"(?P<pii>[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"),
    ("iban", r"(?i)(?P<pii>PK\d{2}\s?[A-Z]{4}(?:\s?\d){16})(?!\d)"),
    ("cnic", r"(?<!\d)(?P<pii>\d{5}-\d{7}-\d)(?!\d)"),
    ("cnic", r"(?<!\d)(?P<pii>\d{13})(?!\d)"),
    ("cnic", r"(?<!\d)(?P<pii>\d{3}-\d{2}-\d{6})(?!\d)"),
    ("phone", r"(?<!\d)(?P<pii>(?:\+92|0092|92|0)?3\d{2}[-\s]?\d{7})(?!\d)"),
    ("phone", r"(?<!\d)(?P<pii>0\d{2,4}[-\s]\d{6,8})(?!\d)"),
    (
        "account",
        r"(?i)(?:\b(?:account|acct|a/c)\s*(?:number|no\.?|#)?|(?:اکاؤنٹ|اکاونٹ|حساب)\s*(?:نمبر)?)"
        r"\s*[:=-]?\s*(?P<pii>\d(?:[- ]?\d){7,23})(?!\d)",
    ),
    (
        "name",
        r"(?:\b[Mm]y name is|\bI am)\s+"
        r"(?P<pii>[A-Z][A-Za-z'-]*(?:\s+[A-Z][A-Za-z'-]*){0,3})(?=$|[,.!?])",
    ),
    (
        "name",
        r"(?i)\bmera na?am\s+"
        r"(?P<pii>[A-Za-z][A-Za-z'-]*(?:\s+[A-Za-z][A-Za-z'-]*){0,3}?)\s+hain?\b",
    ),
    (
        "name",
        r"میرا نام\s+(?P<pii>[\u0600-\u06FF]+(?:\s+[\u0600-\u06FF]+){0,3}?)\s+ہے",
    ),
)

_PLACEHOLDERS = {
    "email": "<EMAIL>",
    "cnic": "<CNIC>",
    "phone": "<PHONE>",
    "account": "<ACCOUNT>",
    "iban": "<IBAN>",
    "name": "<NAME>",
}

_COMPILED_PATTERNS = tuple((label, re.compile(pattern)) for label, pattern in _PATTERNS)
_DIGIT_TRANSLATION = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789",
)


def normalize_for_matching(text: str) -> str:
    """Return an equal-length ASCII-digit view used only to locate PII spans."""
    return text.translate(_DIGIT_TRANSLATION)


def scrub_text(text: str) -> tuple[str, Counter[str]]:
    """Redact PII from one string, returning the redacted text and per-type counts."""
    matching_text = normalize_for_matching(text)
    counts: Counter[str] = Counter()
    spans: list[tuple[int, int, str]] = []
    for label, pattern in _COMPILED_PATTERNS:
        for match in pattern.finditer(matching_text):
            start, end = match.span("pii")
            overlaps = any(
                start < existing_end and end > existing_start
                for existing_start, existing_end, _ in spans
            )
            if overlaps:
                continue
            spans.append((start, end, label))
            counts[label] += 1

    scrubbed = text
    for start, end, label in sorted(spans, reverse=True):
        scrubbed = scrubbed[:start] + _PLACEHOLDERS[label] + scrubbed[end:]
    return scrubbed, counts


def scrub_records(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], Counter[str]]:
    """Scrub `text_clean` on every record, adding `text_scrubbed`. Other fields are unchanged."""
    scrubbed_records: list[dict[str, Any]] = []
    total_counts: Counter[str] = Counter()
    for record in records:
        scrubbed_text, counts = scrub_text(str(record.get("text_clean", "")))
        total_counts.update(counts)
        scrubbed_records.append({**record, "text_scrubbed": scrubbed_text})
    return scrubbed_records, total_counts


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load one JSON record per line."""
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(json.loads(line))
    return records


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    """Write records as UTF-8 JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def print_report(records: list[dict[str, Any]], counts: Counter[str]) -> None:
    """Print a one-screen redaction summary."""
    flagged = sum(1 for record in records if "<" in record["text_scrubbed"])
    print(f"Records scrubbed : {len(records):,}")
    print(f"Records with PII : {flagged:,}")
    print("Redactions by type:")
    if not counts:
        print("  (none)")
    else:
        for label, count in counts.most_common():
            print(f"  {label:8} {count:,}")


def parse_args() -> argparse.Namespace:
    """Parse PII scrubbing options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    """Scrub the Phase 3 sample and write the redacted file used for auto-labelling."""
    args = parse_args()
    records = load_jsonl(args.input)
    if not records:
        raise SystemExit(f"No records found in {args.input}")
    scrubbed, counts = scrub_records(records)
    write_jsonl(args.output, scrubbed)
    print_report(scrubbed, counts)
    print(f"Wrote {len(scrubbed):,} records to {args.output}")


if __name__ == "__main__":
    main()
