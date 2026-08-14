"""Tests for the cross-platform review availability census."""

import json
from pathlib import Path

from src.collect.render_availability_census import (
    build_census,
    render_census,
    summarize_records,
)


def test_summarize_records_reports_observed_window_and_ratings() -> None:
    summary = summarize_records(
        [
            {"timestamp": "2024-01-01T00:00:00+00:00", "rating": 1, "text": "secret"},
            {"timestamp": "2026-01-01T00:00:00+00:00", "rating": 5, "text": "private"},
        ]
    )

    assert summary["observed_reviews"] == 2
    assert summary["earliest_observed"].startswith("2024-01-01")
    assert summary["latest_observed"].startswith("2026-01-01")
    assert summary["rating_distribution"] == {"1": 1, "2": 0, "3": 0, "4": 0, "5": 1}
    assert "text" not in summary


def test_build_census_keeps_google_totals_distinct_from_apple_access(tmp_path: Path) -> None:
    registry = {
        "products": [
            {
                "product_id": "example",
                "display_name": "Example",
                "brand_group": "Example",
                "vertical": "consumer_wallet",
                "audience": "consumer",
                "inclusion_tier": "core",
                "listings": [
                    {
                        "platform": platform,
                        "platform_app_id": app_id,
                        "bundle_id": app_id,
                        "store_title": "Example",
                        "developer": "Example",
                        "store_url": url,
                        "confirmed": True,
                    }
                    for platform, app_id, url in (
                        ("google_play", "pk.example", "https://play.google.com/store/apps/details?id=pk.example"),
                        ("apple_app_store", "123", "https://apps.apple.com/pk/app/example/id123"),
                    )
                ],
            }
        ]
    }
    for platform, app_id in (("google_play", "pk.example"), ("apple_app_store", "123")):
        page = tmp_path / platform / "example" / app_id / "page_000001.jsonl"
        page.parent.mkdir(parents=True)
        page.write_text(json.dumps({"timestamp": "2026-01-01T00:00:00Z", "rating": 5}) + "\n")

    census = build_census(registry, tmp_path, {"pk.example": {"reviews": 1000, "ratings": 2000}})

    google, apple = census["listings"]
    assert google["store_reported_reviews"] == 1000
    assert apple["store_reported_reviews"] is None
    assert apple["observed_reviews"] == 1


def test_render_census_escapes_embedded_listing_data() -> None:
    census = {
        "generated_at": "2026-08-15T00:00:00+05:00",
        "listings": [
            {
                "product_id": "example",
                "display_name": "<script>alert(1)</script>",
                "vertical": "consumer_wallet",
                "inclusion_tier": "core",
                "platform": "google_play",
                "platform_app_id": "pk.example",
                "store_reported_reviews": 1,
                "observed_reviews": 1,
                "earliest_observed": None,
                "latest_observed": None,
                "rating_distribution": {str(key): 0 for key in range(1, 6)},
                "access_note": "sample",
            }
        ],
    }

    html = render_census(census)

    assert "Review supply before quota selection" in html
    assert "google-total" in html
    assert "apple-total" in html
    assert "<script>alert(1)</script>" not in html
    assert "\\u003cscript>" in html