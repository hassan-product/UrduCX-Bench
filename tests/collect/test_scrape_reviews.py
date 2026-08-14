"""Tests for privacy-safe, resumable review collection."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from google_play_scraper import Sort
from google_play_scraper.features.reviews import _ContinuationToken
from src.collect.scrape_reviews import (
    REVIEW_FIELDS,
    RequestPacer,
    collect_app,
    deserialize_token,
    fetch_page,
    load_apps,
    serialize_review,
    serialize_token,
)


def make_token(value: str = "next") -> _ContinuationToken:
    return _ContinuationToken(value, "en", "pk", Sort.NEWEST.value, 100, None, None)


def test_load_apps_requires_human_confirmation(tmp_path: Path) -> None:
    config_path = tmp_path / "apps.yaml"
    config_path.write_text(
        "apps:\n- name: SIMOSA\n  app_id: com.jazz.jazzworld\n  confirmed: false\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Human confirmation required for: SIMOSA"):
        load_apps(config_path)


def test_serialize_review_keeps_only_allowed_fields() -> None:
    raw_review = {
        "reviewId": "review-1",
        "userName": "must not survive",
        "userImage": "https://example.test/avatar.png",
        "content": "Balance kat gaya",
        "score": 1,
        "at": datetime(2026, 8, 14, 10, 30),
        "reviewCreatedVersion": "5.2.0",
        "thumbsUpCount": 7,
    }

    result = serialize_review(raw_review, "com.example.app")

    assert tuple(result) == REVIEW_FIELDS
    assert result["timestamp"] == "2026-08-14T10:30:00"
    assert "userName" not in result
    assert "userImage" not in result


def test_continuation_token_round_trip() -> None:
    restored = deserialize_token(serialize_token(make_token()))

    assert restored is not None
    assert restored.token == "next"
    assert restored.sort == Sort.NEWEST.value
    assert restored.country == "pk"


def test_collect_app_writes_page_before_resumable_checkpoint(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []

    def fake_reviews(app_id: str, **kwargs: Any) -> tuple[list[dict[str, Any]], _ContinuationToken]:
        calls.append({"app_id": app_id, **kwargs})
        return ([{"reviewId": "one", "content": "Theek nahin", "score": 1}], make_token())

    checkpoint = collect_app(
        {"name": "SIMOSA", "app_id": "com.jazz.jazzworld"},
        output_dir=tmp_path / "reviews",
        checkpoint_dir=tmp_path / "checkpoints",
        count=100,
        max_pages=1,
        pacer=RequestPacer(1.0, sleep_fn=lambda _: None, clock_fn=lambda: 0.0),
        reviews_fn=fake_reviews,
    )

    page_path = tmp_path / "reviews/com.jazz.jazzworld/page_000001.jsonl"
    assert json.loads(page_path.read_text(encoding="utf-8"))["review_id"] == "one"
    assert checkpoint["reviews_collected"] == 1
    assert checkpoint["next_page"] == 2
    assert checkpoint["complete"] is False
    assert calls[0]["continuation_token"] is None


def test_fetch_page_retries_with_exponential_backoff() -> None:
    attempts = 0
    sleeps: list[float] = []

    def flaky_reviews(*args: Any, **kwargs: Any) -> tuple[list[dict[str, Any]], None]:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ConnectionError("temporary")
        return [], None

    result = fetch_page(
        "com.example.app",
        count=10,
        continuation_token=None,
        pacer=RequestPacer(1.0, sleep_fn=lambda _: None, clock_fn=lambda: 0.0),
        reviews_fn=flaky_reviews,
        backoff_seconds=2.0,
        sleep_fn=sleeps.append,
    )

    assert result == ([], None)
    assert attempts == 3
    assert sleeps == [2.0, 4.0]