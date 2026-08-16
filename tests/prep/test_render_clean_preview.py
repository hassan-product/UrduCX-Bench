"""Tests for the cleaned-review browser preview."""

import json
from pathlib import Path

import pytest
from src.prep.render_clean_preview import (
    attach_brand,
    load_cleaned,
    render_preview,
    sample_evenly,
)


def cleaned_record(**overrides: object) -> dict[str, object]:
    record = {
        "review_id": "review-1",
        "platform": "google_play",
        "platform_app_id": "com.example.app",
        "product_id": "example",
        "text": "Balance <b>kat</b> gaya hai",
        "rating": 1,
        "timestamp": "2026-08-14T10:30:00",
        "app_version": "5.2.0",
        "helpful_count": 7,
        "text_clean": "Balance kat gaya hai",
        "text_hash": "abc",
    }
    record.update(overrides)
    return record


def test_load_cleaned_rejects_raw_schema(tmp_path: Path) -> None:
    path = tmp_path / "reviews_cleaned.jsonl"
    raw = {k: v for k, v in cleaned_record().items() if k not in {"text_clean", "text_hash"}}
    path.write_text(json.dumps(raw) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Unexpected schema"):
        load_cleaned(path)


def test_sample_evenly_caps_each_product_platform_slice() -> None:
    records = [
        cleaned_record(review_id="a", product_id="simosa", platform="google_play"),
        cleaned_record(review_id="b", product_id="simosa", platform="google_play"),
        cleaned_record(review_id="c", product_id="simosa", platform="apple_app_store"),
        cleaned_record(review_id="d", product_id="easypaisa", platform="google_play"),
    ]
    sampled = sample_evenly(records, per_slice=1)
    assert [row["review_id"] for row in sampled] == ["d", "c", "a"]


def test_attach_brand_copies_registry_group() -> None:
    labelled = attach_brand(
        [cleaned_record(product_id="simosa")],
        {"simosa": "Jazz"},
    )
    assert labelled[0]["brand_group"] == "Jazz"


def test_render_preview_escapes_script_and_lists_filters() -> None:
    html = render_preview(
        [
            cleaned_record(
                text_clean="Balance <script>alert(1)</script> kat gaya",
                brand_group="Jazz",
            )
        ],
        total_cleaned=54519,
    )
    assert "Cleaned review inspection" in html
    assert "54,519" in html
    assert "Google Play only" in html
    assert 'value="Jazz"' in html
    assert 'id="product-toggle"' in html
    assert 'id="product-panel"' in html
    assert 'id="product-grid"' in html
    assert 'id="select-all"' in html
    assert "<script>alert(1)</script>" not in html
    assert "\\u003cscript>" in html
