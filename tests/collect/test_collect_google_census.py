"""Tests for bounded Google availability collection."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from src.collect.collect_google_census import collect_listing_sample, with_retries
from src.collect.scrape_reviews import RequestPacer


def test_collect_listing_sample_writes_shared_schema_and_aggregate_metadata(
    tmp_path: Path,
) -> None:
    listing = {
        "display_name": "SIMOSA",
        "product_id": "simosa",
        "platform_app_id": "com.jazz.jazzworld",
    }

    def fake_app(app_id: str, **kwargs: Any) -> dict[str, Any]:
        assert kwargs == {"lang": "en", "country": "pk"}
        return {"reviews": 1000, "ratings": 2000, "score": 4.2, "description": "ignored"}

    def fake_reviews(app_id: str, **kwargs: Any) -> tuple[list[dict[str, Any]], None]:
        return [
            {
                "reviewId": "one",
                "content": "Balance kat gaya",
                "score": 1,
                "at": datetime(2026, 8, 15),
                "reviewCreatedVersion": "3.3.3",
                "thumbsUpCount": 4,
                "userName": "must not survive",
            }
        ], None

    metadata = collect_listing_sample(
        listing,
        output_dir=tmp_path,
        pacer=RequestPacer(1.0, sleep_fn=lambda _: None, clock_fn=lambda: 0.0),
        app_fn=fake_app,
        reviews_fn=fake_reviews,
    )

    page = tmp_path / "google_play/simosa/com.jazz.jazzworld/page_000001.jsonl"
    record = json.loads(page.read_text(encoding="utf-8"))
    assert record["platform"] == "google_play"
    assert record["product_id"] == "simosa"
    assert "userName" not in record
    assert metadata == {"reviews": 1000, "ratings": 2000, "score": 4.2, "sampled_reviews": 1}


def test_with_retries_backs_off() -> None:
    attempts = 0
    sleeps: list[float] = []

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ConnectionError("temporary")
        return "ok"

    result = with_retries(
        operation,
        pacer=RequestPacer(1.0, sleep_fn=lambda _: None, clock_fn=lambda: 0.0),
        backoff_seconds=2.0,
        sleep_fn=sleeps.append,
    )

    assert result == "ok"
    assert sleeps == [2.0, 4.0]