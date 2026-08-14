"""Tests for the local raw-review browser preview."""

import json
from pathlib import Path

import pytest
from src.collect.render_review_preview import load_reviews, render_preview


def review_record() -> dict[str, object]:
    return {
        "review_id": "review-1",
        "platform": "google_play",
        "platform_app_id": "com.example.app",
        "product_id": "example",
        "text": "Balance <script>alert(1)</script> kat gaya",
        "rating": 1,
        "timestamp": "2026-08-14T10:30:00",
        "app_version": "5.2.0",
        "helpful_count": 7,
    }


def test_load_reviews_accepts_only_strict_schema(tmp_path: Path) -> None:
    page_dir = tmp_path / "com.example.app"
    page_dir.mkdir()
    record = {**review_record(), "userName": "must not survive"}
    (page_dir / "page_000001.jsonl").write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(ValueError, match="Unexpected schema"):
        load_reviews(tmp_path)


def test_render_preview_escapes_script_terminators() -> None:
    html = render_preview([review_record()])

    assert "Collected review inspection" in html
    assert "<script>alert(1)</script>" not in html
    assert "\\u003cscript>" in html