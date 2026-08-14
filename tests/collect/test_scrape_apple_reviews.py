"""Tests for privacy-safe, resumable Apple review collection."""

import json
from pathlib import Path
from typing import Any

from src.collect.scrape_apple_reviews import (
    RequestPacer,
    apple_reviews_url,
    collect_listing,
    fetch_page,
    serialize_apple_review,
)


def listing() -> dict[str, Any]:
    return {
        "product_id": "simosa",
        "display_name": "SIMOSA",
        "platform_app_id": "1441912305",
    }


def entry(review_id: str = "review-1") -> dict[str, Any]:
    return {
        "id": {"label": review_id},
        "author": {"name": {"label": "must not survive"}},
        "content": {"label": "Balance kat gaya"},
        "im:rating": {"label": "1"},
        "updated": {"label": "2026-08-04T21:30:22-07:00"},
        "im:version": {"label": "3.3.3"},
        "im:voteCount": {"label": "4"},
    }


def test_serialize_apple_review_keeps_shared_non_identifying_schema() -> None:
    result = serialize_apple_review(entry(), listing())

    assert result == {
        "review_id": "review-1",
        "platform": "apple_app_store",
        "platform_app_id": "1441912305",
        "product_id": "simosa",
        "text": "Balance kat gaya",
        "rating": 1,
        "timestamp": "2026-08-04T21:30:22-07:00",
        "app_version": "3.3.3",
        "helpful_count": 4,
    }
    assert "author" not in result


def test_apple_reviews_url_targets_pakistan_storefront() -> None:
    assert apple_reviews_url("1441912305", 2) == (
        "https://itunes.apple.com/pk/rss/customerreviews/"
        "page=2/id=1441912305/sortBy=mostRecent/json"
    )


def test_fetch_page_retries_with_exponential_backoff() -> None:
    attempts = 0
    sleeps: list[float] = []

    def flaky_fetch(url: str) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise OSError("temporary")
        return {"feed": {"entry": [entry()]}}

    result = fetch_page(
        listing(),
        1,
        pacer=RequestPacer(1.0, sleep_fn=lambda _: None, clock_fn=lambda: 0.0),
        fetch_json_fn=flaky_fetch,
        backoff_seconds=2.0,
        sleep_fn=sleeps.append,
    )

    assert len(result) == 1
    assert attempts == 3
    assert sleeps == [2.0, 4.0]


def test_collect_listing_writes_page_then_checkpoint(tmp_path: Path) -> None:
    def fake_fetch(url: str) -> dict[str, Any]:
        assert "page=1/id=1441912305" in url
        return {"feed": {"entry": [entry()]}}

    checkpoint = collect_listing(
        listing(),
        output_dir=tmp_path / "reviews",
        checkpoint_dir=tmp_path / "checkpoints",
        max_pages=1,
        pacer=RequestPacer(1.0, sleep_fn=lambda _: None, clock_fn=lambda: 0.0),
        fetch_json_fn=fake_fetch,
    )

    page_path = tmp_path / "reviews/apple_app_store/simosa/1441912305/page_000001.jsonl"
    assert json.loads(page_path.read_text(encoding="utf-8"))["product_id"] == "simosa"
    assert checkpoint["reviews_collected"] == 1
    assert checkpoint["next_page"] == 2
    assert checkpoint["complete"] is True