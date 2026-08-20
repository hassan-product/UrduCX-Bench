"""Tests for the real-data safety audit and synthetic PII challenge matrix."""

from src.prep.clean import LANGUAGE_VALUES
from src.prep.render_pii_audit import (
    build_challenge_records,
    render_audit,
    sample_audit_records,
)


def _records_per_language(count: int = 20) -> list[dict[str, str]]:
    records = []
    for language in LANGUAGE_VALUES:
        for index in range(count):
            clean = f"{language} text {index}"
            scrubbed = "<PHONE>" if index == 0 else clean
            records.append(
                {
                    "review_id": f"{language}-{index}",
                    "language": language,
                    "text_clean": clean,
                    "text_scrubbed": scrubbed,
                }
            )
    return records


def test_sample_audit_records_is_stratified_and_prioritizes_changes() -> None:
    selected = sample_audit_records(_records_per_language(), target_size=50, seed=7)

    assert len(selected) == 50
    assert all(
        sum(record["language"] == language for record in selected) >= 12
        for language in LANGUAGE_VALUES
    )
    assert all(
        any(
            record["language"] == language
            and record["text_clean"] != record["text_scrubbed"]
            for record in selected
        )
        for language in LANGUAGE_VALUES
    )
    assert selected == sample_audit_records(_records_per_language(), target_size=50, seed=7)


def test_sample_audit_records_prioritizes_unredacted_pii_cues() -> None:
    records = _records_per_language()
    for language in LANGUAGE_VALUES:
        candidate = next(
            record
            for record in records
            if record["review_id"] == f"{language}-19"
        )
        candidate["text_clean"] = "CNIC 42101 and account details are pending"
        candidate["text_scrubbed"] = candidate["text_clean"]

    selected = sample_audit_records(records, target_size=8, seed=7)

    assert all(
        any(record["review_id"] == f"{language}-19" for record in selected)
        for language in LANGUAGE_VALUES
    )


def test_render_audit_escapes_text_and_includes_review_controls() -> None:
    records = [
        {
            "language": "english",
            "text_clean": "Call <script>alert(1)</script>",
            "text_scrubbed": "Call <PHONE>",
        }
    ]

    page = render_audit(records, build_challenge_records(), seed=7)

    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "Call &lt;PHONE&gt;" in page
    assert "Real corpus safety audit" in page
    assert "Synthetic multilingual challenge matrix" in page
    assert "These challenge messages are not app-store reviews" in page
    assert "Expected PII removed" in page
    assert "Control fact preserved" in page
    assert "No visible residual PII" in page
    assert "No useful facts destroyed" in page
    assert "localStorage" in page


def test_challenge_matrix_covers_every_pii_type_in_every_language() -> None:
    records = build_challenge_records()

    assert len(records) == 24
    expected_pairs = {
        (language, pii_type)
        for language in LANGUAGE_VALUES
        for pii_type in ("phone", "account", "cnic", "iban", "email", "name")
    }
    assert {(record["language"], record["pii_type"]) for record in records} == expected_pairs
    assert all(record["text_clean"] != record["text_scrubbed"] for record in records)
    assert all(record["expected_placeholder"] in record["text_scrubbed"] for record in records)
    assert all(record["must_preserve"] in record["text_scrubbed"] for record in records)