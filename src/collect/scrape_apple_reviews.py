"""Collect public Apple App Store reviews without retaining reviewer identity.

Apple exposes at most ten 50-review RSS pages per storefront listing. This collector preserves that
publicly accessible window with the same pacing, retry, atomic-write, and resume guarantees as the
Google collector.
"""

from __future__ import annotations

import argparse
import json
import ssl
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

import certifi

from src.collect.render_source_registry import flatten_registry, load_registry
from src.collect.review_schema import review_record
from src.collect.scrape_reviews import (
    MIN_REQUEST_INTERVAL,
    RequestPacer,
    write_checkpoint,
    write_page,
)

DEFAULT_REGISTRY = Path("config/source_registry.yaml")
DEFAULT_OUTPUT_DIR = Path("data/raw/reviews")
DEFAULT_CHECKPOINT_DIR = Path("data/raw/checkpoints")
APPLE_MAX_PAGES = 10
APPLE_PAGE_SIZE = 50

FetchJsonFunction = Callable[[str], dict[str, Any]]


def load_apple_listings(
    config_path: Path, selected_products: set[str] | None = None
) -> list[dict[str, Any]]:
    """Load confirmed Apple listings, refusing unknown product selections."""
    rows = [
        row
        for row in flatten_registry(load_registry(config_path))
        if row["platform"] == "apple_app_store" and row["confirmed"]
    ]
    if selected_products is None:
        return rows
    selected = [row for row in rows if row["product_id"] in selected_products]
    missing = selected_products - {str(row["product_id"]) for row in selected}
    if missing:
        raise ValueError(f"Unknown or unconfirmed Apple product(s): {', '.join(sorted(missing))}")
    return selected


def apple_reviews_url(platform_app_id: str, page_number: int) -> str:
    """Return the Pakistan storefront RSS URL for one Apple review page."""
    return (
        "https://itunes.apple.com/pk/rss/customerreviews/"
        f"page={page_number}/id={platform_app_id}/sortBy=mostRecent/json"
    )


def fetch_json(url: str) -> dict[str, Any]:
    """Fetch JSON using a pinned, certificate-validated CA bundle."""
    context = ssl.create_default_context(cafile=certifi.where())
    request = urllib.request.Request(url, headers={"User-Agent": "UrduCX-Bench/0.0.0"})
    with urllib.request.urlopen(request, context=context, timeout=30) as response:
        return json.load(response)


def label(entry: dict[str, Any], key: str) -> Any:
    """Read an Apple RSS label field without retaining nested author metadata."""
    value = entry.get(key)
    return value.get("label") if isinstance(value, dict) else None


def integer_label(entry: dict[str, Any], key: str) -> int | None:
    """Parse an integer Apple RSS label when present."""
    value = label(entry, key)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def serialize_apple_review(entry: dict[str, Any], listing: dict[str, Any]) -> dict[str, Any]:
    """Map an Apple RSS entry to the shared non-identifying raw schema."""
    return review_record(
        review_id=label(entry, "id"),
        platform="apple_app_store",
        platform_app_id=str(listing["platform_app_id"]),
        product_id=str(listing["product_id"]),
        text=label(entry, "content"),
        rating=integer_label(entry, "im:rating"),
        timestamp=label(entry, "updated"),
        app_version=label(entry, "im:version"),
        helpful_count=integer_label(entry, "im:voteCount"),
    )


def extract_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Return review entries from an Apple RSS payload."""
    entries = payload.get("feed", {}).get("entry", [])
    return entries if isinstance(entries, list) else []


def fetch_page(
    listing: dict[str, Any],
    page_number: int,
    *,
    pacer: RequestPacer,
    fetch_json_fn: FetchJsonFunction = fetch_json,
    max_retries: int = 4,
    backoff_seconds: float = 2.0,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> list[dict[str, Any]]:
    """Fetch one Apple page with pacing and exponential-backoff retries."""
    url = apple_reviews_url(str(listing["platform_app_id"]), page_number)
    for attempt in range(max_retries + 1):
        pacer.wait()
        try:
            return extract_entries(fetch_json_fn(url))
        except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError):
            if attempt == max_retries:
                raise
            sleep_fn(backoff_seconds * (2**attempt))
    raise RuntimeError("Unreachable retry state")


def collect_listing(
    listing: dict[str, Any],
    *,
    output_dir: Path,
    checkpoint_dir: Path,
    max_pages: int,
    pacer: RequestPacer,
    fetch_json_fn: FetchJsonFunction = fetch_json,
) -> dict[str, Any]:
    """Resume one Apple listing and checkpoint after each atomic page file."""
    platform_app_id = str(listing["platform_app_id"])
    product_id = str(listing["product_id"])
    checkpoint_path = checkpoint_dir / "apple_app_store" / f"{platform_app_id}.json"
    checkpoint: dict[str, Any] = {
        "platform": "apple_app_store",
        "platform_app_id": platform_app_id,
        "product_id": product_id,
        "next_page": 1,
        "reviews_collected": 0,
        "complete": False,
    }
    if checkpoint_path.exists():
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    if checkpoint["complete"]:
        return checkpoint

    pages_this_run = 0
    while checkpoint["next_page"] <= APPLE_MAX_PAGES and pages_this_run < max_pages:
        page_number = int(checkpoint["next_page"])
        entries = fetch_page(
            listing,
            page_number,
            pacer=pacer,
            fetch_json_fn=fetch_json_fn,
        )
        page = [serialize_apple_review(entry, listing) for entry in entries]
        page_path = (
            output_dir
            / "apple_app_store"
            / product_id
            / platform_app_id
            / f"page_{page_number:06d}.jsonl"
        )
        write_page(page_path, page)
        checkpoint["next_page"] = page_number + 1
        checkpoint["reviews_collected"] += len(page)
        checkpoint["complete"] = len(entries) < APPLE_PAGE_SIZE or page_number == APPLE_MAX_PAGES
        write_checkpoint(checkpoint_path, checkpoint)
        pages_this_run += 1
        print(
            f"{listing['display_name']} / Apple: wrote {len(page)} reviews "
            f"({checkpoint['reviews_collected']} accessible)"
        )
        if checkpoint["complete"]:
            break
    return checkpoint


def parse_args() -> argparse.Namespace:
    """Parse Apple collection options."""
    parser = argparse.ArgumentParser(description="Collect approved Apple App Store reviews.")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--product", action="append", dest="products")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--checkpoint-dir", type=Path, default=DEFAULT_CHECKPOINT_DIR)
    parser.add_argument("--max-pages-per-listing", type=int, default=APPLE_MAX_PAGES)
    parser.add_argument("--request-interval", type=float, default=MIN_REQUEST_INTERVAL)
    return parser.parse_args()


def main() -> None:
    """Collect approved Apple listings sequentially under one global request pacer."""
    args = parse_args()
    max_pages = min(max(args.max_pages_per_listing, 1), APPLE_MAX_PAGES)
    listings = load_apple_listings(args.registry, set(args.products) if args.products else None)
    pacer = RequestPacer(args.request_interval)
    for listing in listings:
        collect_listing(
            listing,
            output_dir=args.output_dir,
            checkpoint_dir=args.checkpoint_dir,
            max_pages=max_pages,
            pacer=pacer,
        )


if __name__ == "__main__":
    main()
