"""Clean raw reviews: normalise text, drop junk, remap product IDs, and deduplicate.

This is the first Phase 2 step. Language detection and PII redaction run later; this module
only produces a filtered JSONL file plus a drop-reason report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from src.collect.review_schema import REVIEW_FIELDS

DEFAULT_REVIEWS_DIR = Path("data/raw/reviews")
DEFAULT_REGISTRY = Path("config/source_registry.yaml")
DEFAULT_OUTPUT = Path("data/interim/reviews_cleaned.jsonl")

MIN_WORD_COUNT = 3
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_WORD_RE = re.compile(r"[A-Za-z0-9\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]+")

CLEAN_FIELDS = (*REVIEW_FIELDS, "text_clean", "text_hash", "language")

LANGUAGE_VALUES = ("urdu_script", "roman_urdu", "english", "code_switched")
_ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_ROMAN_URDU_MARKERS = {
    "acha",
    "aya",
    "bohat",
    "gaya",
    "gayi",
    "hai",
    "hain",
    "ho",
    "kar",
    "kiya",
    "kya",
    "lagta",
    "lekin",
    "liye",
    "mein",
    "mera",
    "nahi",
    "raha",
    "rahi",
    "se",
    "wala",
    "waly",
    "yeh",
    "yahan",
}
_TOKEN_RE = re.compile(r"[A-Za-z]+")


def load_product_map(registry_path: Path) -> dict[tuple[str, str], str]:
    """Map each (platform, platform_app_id) pair to the registry product_id."""
    payload = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    products = payload.get("products", [])
    mapping: dict[tuple[str, str], str] = {}
    for product in products:
        product_id = str(product["product_id"])
        for listing in product.get("listings", []):
            key = (str(listing["platform"]), str(listing["platform_app_id"]))
            mapping[key] = product_id
    if not mapping:
        raise ValueError(f"No listings found in {registry_path}")
    return mapping


def remap_product_id(record: dict[str, Any], product_map: dict[tuple[str, str], str]) -> str:
    """Prefer the registry product ID; keep the stored value if the listing is unknown."""
    key = (str(record.get("platform", "")), str(record.get("platform_app_id", "")))
    return product_map.get(key, str(record.get("product_id", "")))


def normalise_text(text: Any) -> str:
    """Strip markup, collapse whitespace, and trim."""
    if text is None:
        return ""
    cleaned = _HTML_TAG_RE.sub(" ", str(text))
    cleaned = cleaned.replace("\u00a0", " ")
    return _WHITESPACE_RE.sub(" ", cleaned).strip()


def word_count(text: str) -> int:
    """Count Latin or Arabic letter/number tokens."""
    return len(_WORD_RE.findall(text))


def detect_language(text: str) -> str:
    """Classify script/register using deterministic Unicode and Roman Urdu markers."""
    has_arabic = bool(_ARABIC_RE.search(text))
    has_latin = bool(_LATIN_RE.search(text))
    if has_arabic and has_latin:
        return "code_switched"
    if has_arabic:
        return "urdu_script"

    tokens = {token.lower() for token in _TOKEN_RE.findall(text)}
    if tokens & _ROMAN_URDU_MARKERS:
        return "roman_urdu"
    return "english"


def drop_reason(text_clean: str) -> str | None:
    """Return why a review should be dropped, or None if it should be kept."""
    if not text_clean:
        return "empty"
    tokens = word_count(text_clean)
    if tokens == 0:
        return "emoji_only"
    if tokens < MIN_WORD_COUNT:
        return "too_short"
    return None


def text_hash(text_clean: str) -> str:
    """Stable hash of already-normalised text, used for near-exact deduplication."""
    return hashlib.sha256(text_clean.encode("utf-8")).hexdigest()


def load_raw_reviews(reviews_dir: Path) -> list[dict[str, Any]]:
    """Load every JSONL record under the raw reviews tree."""
    records: list[dict[str, Any]] = []
    for path in sorted(reviews_dir.rglob("*.jsonl")):
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSON in {path}:{line_number}") from exc
                records.append(record)
    return records


def clean_records(
    records: list[dict[str, Any]],
    product_map: dict[tuple[str, str], str],
) -> tuple[list[dict[str, Any]], Counter[str]]:
    """Filter, remap, and deduplicate reviews. Drop reasons are counted for the report."""
    kept: list[dict[str, Any]] = []
    drops: Counter[str] = Counter()
    seen_ids: set[tuple[str, str]] = set()
    seen_hashes: set[str] = set()

    for record in records:
        product_id = remap_product_id(record, product_map)
        cleaned = normalise_text(record.get("text"))
        reason = drop_reason(cleaned)
        if reason:
            drops[reason] += 1
            continue

        identity = (str(record.get("platform", "")), str(record.get("review_id", "")))
        if identity in seen_ids:
            drops["duplicate_id"] += 1
            continue
        digest = text_hash(cleaned)
        if digest in seen_hashes:
            drops["duplicate_text"] += 1
            continue

        seen_ids.add(identity)
        seen_hashes.add(digest)
        kept.append(
            {
                "review_id": record.get("review_id"),
                "platform": record.get("platform"),
                "platform_app_id": record.get("platform_app_id"),
                "product_id": product_id,
                "text": record.get("text"),
                "rating": record.get("rating"),
                "timestamp": record.get("timestamp"),
                "app_version": record.get("app_version"),
                "helpful_count": record.get("helpful_count"),
                "text_clean": cleaned,
                "text_hash": digest,
                "language": detect_language(cleaned),
            }
        )
    return kept, drops


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    """Write cleaned records as UTF-8 JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def print_report(input_count: int, kept: list[dict[str, Any]], drops: Counter[str]) -> None:
    """Print a one-screen cleaning summary."""
    print(f"Input records : {input_count:,}")
    print(f"Kept          : {len(kept):,}")
    print("Dropped:")
    if not drops:
        print("  (none)")
    else:
        for reason, count in drops.most_common():
            print(f"  {reason:16} {count:,}")
    by_product: Counter[str] = Counter(str(row["product_id"]) for row in kept)
    by_language: Counter[str] = Counter(str(row["language"]) for row in kept)
    print("Kept by language:")
    for language, count in by_language.most_common():
        print(f"  {language:16} {count:,}")
    by_platform: Counter[str] = Counter(str(row["platform"]) for row in kept)
    print("Kept by platform:")
    for platform, count in by_platform.most_common():
        print(f"  {platform:16} {count:,}")
    dates = []
    for row in kept:
        timestamp = str(row.get("timestamp", ""))
        try:
            dates.append(datetime.fromisoformat(timestamp.replace("Z", "+00:00")).date())
        except ValueError:
            continue
    if dates:
        print(f"Date window   : {min(dates)} to {max(dates)}")
    print("Kept by product:")
    for product_id, count in by_product.most_common():
        print(f"  {product_id:24} {count:,}")


def parse_args() -> argparse.Namespace:
    """Parse cleaning options."""
    parser = argparse.ArgumentParser(description="Clean and deduplicate raw app-store reviews.")
    parser.add_argument("--reviews-dir", type=Path, default=DEFAULT_REVIEWS_DIR)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    """Load raw reviews, write the cleaned JSONL file, and print drop counts."""
    args = parse_args()
    if not args.reviews_dir.exists():
        print(f"Reviews directory not found: {args.reviews_dir}", file=sys.stderr)
        sys.exit(1)
    product_map = load_product_map(args.registry)
    raw = load_raw_reviews(args.reviews_dir)
    if not raw:
        print("No review records found.", file=sys.stderr)
        sys.exit(1)
    kept, drops = clean_records(raw, product_map)
    write_jsonl(args.output, kept)
    print_report(len(raw), kept, drops)
    print(f"Wrote {len(kept):,} records to {args.output}")


if __name__ == "__main__":
    main()
