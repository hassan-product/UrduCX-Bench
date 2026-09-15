"""Collect a bounded Google sample and store-reported availability metadata.

This census intentionally writes one recent page per approved listing, not the full corpus. It
measures product/rating/date coverage cheaply before final collection quotas are chosen.
"""

from __future__ import annotations

import argparse
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from google_play_scraper import Sort, app, reviews

from src.collect.render_source_registry import flatten_registry, load_registry
from src.collect.scrape_reviews import (
    MIN_REQUEST_INTERVAL,
    RequestPacer,
    serialize_review,
    write_checkpoint,
    write_page,
)

DEFAULT_REGISTRY = Path("config/source_registry.yaml")
DEFAULT_OUTPUT_DIR = Path("data/raw/reviews")
DEFAULT_METADATA = Path("data/raw/availability_census/google_metadata.json")
GOOGLE_CENSUS_PAGE_SIZE = 200

AppFunction = Callable[..., dict[str, Any]]
ReviewsFunction = Callable[..., tuple[list[dict[str, Any]], Any]]


def load_google_listings(config_path: Path) -> list[dict[str, Any]]:
    """Load all confirmed Google listings from the canonical registry."""
    return [
        row
        for row in flatten_registry(load_registry(config_path))
        if row["platform"] == "google_play" and row["confirmed"]
    ]


def with_retries(
    operation: Callable[[], Any],
    *,
    pacer: RequestPacer,
    max_retries: int = 4,
    backoff_seconds: float = 2.0,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> Any:
    """Run one paced store operation with exponential-backoff retries."""
    for attempt in range(max_retries + 1):
        pacer.wait()
        try:
            return operation()
        except Exception:
            if attempt == max_retries:
                raise
            sleep_fn(backoff_seconds * (2**attempt))
    raise RuntimeError("Unreachable retry state")


def collect_listing_sample(
    listing: dict[str, Any],
    *,
    output_dir: Path,
    pacer: RequestPacer,
    app_fn: AppFunction = app,
    reviews_fn: ReviewsFunction = reviews,
) -> dict[str, Any]:
    """Persist one recent Google page and return non-user aggregate store metadata."""
    platform_app_id = str(listing["platform_app_id"])
    product_id = str(listing["product_id"])
    metadata = with_retries(lambda: app_fn(platform_app_id, lang="en", country="pk"), pacer=pacer)
    raw_reviews, _ = with_retries(
        lambda: reviews_fn(
            platform_app_id,
            lang="en",
            country="pk",
            sort=Sort.NEWEST,
            count=GOOGLE_CENSUS_PAGE_SIZE,
        ),
        pacer=pacer,
    )
    page = [serialize_review(review, platform_app_id, product_id) for review in raw_reviews]
    page_path = output_dir / "google_play" / product_id / platform_app_id / "page_000001.jsonl"
    write_page(page_path, page)
    print(f"{listing['display_name']} / Google: sampled {len(page)} recent reviews")
    return {
        "reviews": metadata.get("reviews"),
        "ratings": metadata.get("ratings"),
        "score": metadata.get("score"),
        "sampled_reviews": len(page),
    }


def parse_args() -> argparse.Namespace:
    """Parse Google census options."""
    parser = argparse.ArgumentParser(description="Collect the bounded Google availability census.")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--request-interval", type=float, default=MIN_REQUEST_INTERVAL)
    return parser.parse_args()


def main() -> None:
    """Collect one recent page and aggregate metadata for every approved Google listing."""
    args = parse_args()
    pacer = RequestPacer(args.request_interval)
    metadata = {
        str(listing["platform_app_id"]): collect_listing_sample(
            listing, output_dir=args.output_dir, pacer=pacer
        )
        for listing in load_google_listings(args.registry)
    }
    write_checkpoint(args.metadata, metadata)
    print(f"Wrote Google availability metadata for {len(metadata)} listings to {args.metadata}")


if __name__ == "__main__":
    main()
