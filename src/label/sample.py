"""Draw a reproducible Phase 3 sample balanced across product, language, and rating."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from src.prep.clean import LANGUAGE_VALUES, write_jsonl
from src.prep.render_clean_preview import load_cleaned

STRATUM_FIELDS = ("product_id", "language", "rating")
DEFAULT_INPUT = Path("data/interim/reviews_cleaned.jsonl")
DEFAULT_OUTPUT = Path("data/interim/reviews_phase3_sample.jsonl")
DEFAULT_REPORT = Path("data/interim/reviews_phase3_sample_report.json")
DEFAULT_TARGET_SIZE = 9_000
DEFAULT_SEED = 20260817


def _stratum_key(record: dict[str, Any]) -> tuple[str, str, int]:
    """Return the joint balancing key for one cleaned review."""
    return (
        str(record["product_id"]),
        str(record["language"]),
        int(record["rating"]),
    )


def sample_records(
    records: list[dict[str, Any]],
    target_size: int,
    seed: int,
) -> list[dict[str, Any]]:
    """Sample without replacement by cycling through each populated joint stratum."""
    if target_size < 1 or target_size > len(records):
        raise ValueError(f"target_size must be between 1 and {len(records)}")

    grouped: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[_stratum_key(record)].append(record)

    generator = random.Random(seed)
    strata = sorted(grouped)
    generator.shuffle(strata)
    for group in grouped.values():
        generator.shuffle(group)

    positions = dict.fromkeys(strata, 0)
    sampled: list[dict[str, Any]] = []
    while len(sampled) < target_size:
        for stratum in strata:
            position = positions[stratum]
            group = grouped[stratum]
            if position >= len(group):
                continue
            sampled.append(group[position])
            positions[stratum] = position + 1
            if len(sampled) == target_size:
                break

    return sampled


def file_sha256(path: Path) -> str:
    """Hash a file so the sampled input and output can be reproduced exactly."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _counts(records: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts = Counter(str(record[field]) for record in records)
    return dict(sorted(counts.items()))


def build_report(
    source: list[dict[str, Any]],
    sampled: list[dict[str, Any]],
    *,
    target_size: int,
    seed: int,
    input_sha256: str,
    output_sha256: str,
) -> dict[str, Any]:
    """Build reproducibility metadata and marginal/joint coverage counts."""
    joint_counts = Counter(_stratum_key(record) for record in sampled)
    return {
        "target_size": target_size,
        "sample_size": len(sampled),
        "source_size": len(source),
        "seed": seed,
        "stratum_fields": list(STRATUM_FIELDS),
        "input_sha256": input_sha256,
        "output_sha256": output_sha256,
        "counts": {
            field: _counts(sampled, field) for field in ("product_id", "language", "rating")
        },
        "joint_strata": [
            {
                "product_id": product_id,
                "language": language,
                "rating": rating,
                "count": count,
            }
            for (product_id, language, rating), count in sorted(joint_counts.items())
        ],
    }


def parse_args() -> argparse.Namespace:
    """Parse Phase 3 sampling options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--target-size", type=int, default=DEFAULT_TARGET_SIZE)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    return parser.parse_args()


def main() -> None:
    """Load the frozen clean set, sample it, and write the audit report."""
    args = parse_args()
    source = load_cleaned(args.input)
    invalid_languages = sorted({str(row["language"]) for row in source} - set(LANGUAGE_VALUES))
    if invalid_languages:
        raise ValueError(f"Unexpected language values: {', '.join(invalid_languages)}")

    sampled = sample_records(source, target_size=args.target_size, seed=args.seed)
    write_jsonl(args.output, sampled)
    report = build_report(
        source,
        sampled,
        target_size=args.target_size,
        seed=args.seed,
        input_sha256=file_sha256(args.input),
        output_sha256=file_sha256(args.output),
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"Sampled {len(sampled):,} of {len(source):,} cleaned reviews")
    print(f"Balanced on: {', '.join(STRATUM_FIELDS)}")
    print(f"Seed: {args.seed}")
    print(f"Wrote sample: {args.output}")
    print(f"Wrote report: {args.report}")


if __name__ == "__main__":
    main()