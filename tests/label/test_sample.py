"""Tests for Phase 3 stratified review sampling."""

from collections import Counter

import pytest
from src.label.sample import build_report, sample_records


def make_records(stratum_sizes: dict[tuple[str, str, int], int]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for (product_id, language, rating), size in stratum_sizes.items():
        for index in range(size):
            records.append(
                {
                    "review_id": f"{product_id}-{language}-{rating}-{index}",
                    "product_id": product_id,
                    "language": language,
                    "rating": rating,
                }
            )
    return records


def stratum_counts(records: list[dict[str, object]]) -> Counter[tuple[object, ...]]:
    return Counter(
        (record["product_id"], record["language"], record["rating"]) for record in records
    )


def test_sample_records_balances_populated_joint_strata() -> None:
    records = make_records(
        {
            ("easypaisa", "english", 1): 5,
            ("easypaisa", "roman_urdu", 5): 5,
            ("jazzcash", "english", 5): 5,
            ("jazzcash", "roman_urdu", 1): 5,
        }
    )

    sampled = sample_records(records, target_size=12, seed=42)

    assert len(sampled) == 12
    assert set(stratum_counts(sampled).values()) == {3}
    assert len({record["review_id"] for record in sampled}) == 12


def test_sample_records_redistributes_quota_from_sparse_strata() -> None:
    records = make_records(
        {
            ("easypaisa", "urdu_script", 1): 1,
            ("easypaisa", "english", 1): 5,
            ("jazzcash", "roman_urdu", 5): 5,
        }
    )

    sampled = sample_records(records, target_size=7, seed=42)

    assert sorted(stratum_counts(sampled).values()) == [1, 3, 3]


def test_sample_records_is_reproducible_and_seeded() -> None:
    records = make_records({("simosa", "english", 1): 20})

    first = sample_records(records, target_size=5, seed=7)
    repeated = sample_records(records, target_size=5, seed=7)
    changed = sample_records(records, target_size=5, seed=8)

    assert first == repeated
    assert first != changed


def test_build_report_records_reproducibility_and_coverage() -> None:
    records = make_records(
        {
            ("easypaisa", "english", 1): 2,
            ("jazzcash", "roman_urdu", 5): 2,
        }
    )
    sampled = sample_records(records, target_size=2, seed=7)

    report = build_report(
        records,
        sampled,
        target_size=2,
        seed=7,
        input_sha256="input-hash",
        output_sha256="output-hash",
    )

    assert report["sample_size"] == 2
    assert report["source_size"] == 4
    assert report["seed"] == 7
    assert report["input_sha256"] == "input-hash"
    assert report["output_sha256"] == "output-hash"
    assert report["counts"]["product_id"] == {"easypaisa": 1, "jazzcash": 1}
    assert len(report["joint_strata"]) == 2


@pytest.mark.parametrize("target_size", [0, -1, 4])
def test_sample_records_rejects_invalid_target_size(target_size: int) -> None:
    records = make_records({("simosa", "english", 1): 3})

    with pytest.raises(ValueError, match="target_size"):
        sample_records(records, target_size=target_size, seed=42)