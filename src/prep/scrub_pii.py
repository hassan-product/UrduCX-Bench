"""Redact PII from cleaned review text before it is sent to any external API.

Regex-based redaction for phone numbers, CNIC-shaped numbers, email addresses, and
generic long account/reference numbers. This must run on the Phase 3 sample before
`auto_label.py` sends any review text to an LLM provider.
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

# Applied in order, most specific first, so digits consumed by an earlier pattern
# (now a placeholder token) cannot also match a later, looser pattern.
_EMAIL_RE = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
_CNIC_DASHED_RE = r"\b\d{5}-\d{7}-\d\b"
_CNIC_PLAIN_RE = r"\b\d{13}\b"
_PHONE_MOBILE_RE = r"(?:\+92[-\s]?|0)3\d{2}[-\s]?\d{7}\b"
_PHONE_LANDLINE_RE = r"\b0\d{2,4}[-\s]\d{6,8}\b"
_ACCOUNT_RE = r"\b\d{9,}\b"

_PATTERNS: tuple[tuple[str, str], ...] = (
    ("email", _EMAIL_RE),
    ("cnic", _CNIC_DASHED_RE),
    ("cnic", _CNIC_PLAIN_RE),
    ("phone", _PHONE_MOBILE_RE),
    ("phone", _PHONE_LANDLINE_RE),
    ("account", _ACCOUNT_RE),
)

_PLACEHOLDERS = {
    "email": "<EMAIL>",
    "cnic": "<CNIC>",
    "phone": "<PHONE>",
    "account": "<ACCOUNT>",
}

_COMPILED_PATTERNS = tuple((label, re.compile(pattern)) for label, pattern in _PATTERNS)


def scrub_text(text: str) -> tuple[str, Counter[str]]:
    """Redact PII from one string, returning the redacted text and per-type counts."""
    scrubbed = text
    counts: Counter[str] = Counter()
    for label, pattern in _COMPILED_PATTERNS:
        matches = pattern.findall(scrubbed)
        if not matches:
            continue
        counts[label] += len(matches)
        scrubbed = pattern.sub(_PLACEHOLDERS[label], scrubbed)
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
