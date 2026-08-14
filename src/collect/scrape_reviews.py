"""Collect public app reviews without retaining reviewer identity.

This Phase 1 collector turns approved app IDs into crash-safe page files. Each request is paced,
retried with exponential backoff, and checkpointed only after its page is atomically persisted.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from google_play_scraper import Sort, reviews
from google_play_scraper.features.reviews import _ContinuationToken

from src.collect.review_schema import REVIEW_FIELDS, review_record

__all__ = ["REVIEW_FIELDS"]

DEFAULT_APPS_CONFIG = Path("config/apps.yaml")
DEFAULT_OUTPUT_DIR = Path("data/raw/reviews")
DEFAULT_CHECKPOINT_DIR = Path("data/raw/checkpoints")
MIN_REQUEST_INTERVAL = 1.0
ReviewsFunction = Callable[..., tuple[list[dict[str, Any]], _ContinuationToken | None]]
SleepFunction = Callable[[float], None]
ClockFunction = Callable[[], float]


class RequestPacer:
    """Keep starts of consecutive store requests at least one interval apart."""

    def __init__(
        self,
        interval: float,
        *,
        sleep_fn: SleepFunction = time.sleep,
        clock_fn: ClockFunction = time.monotonic,
    ) -> None:
        if interval < MIN_REQUEST_INTERVAL:
            raise ValueError(f"Request interval must be at least {MIN_REQUEST_INTERVAL} second")
        self.interval = interval
        self.sleep_fn = sleep_fn
        self.clock_fn = clock_fn
        self.last_request_at: float | None = None

    def wait(self) -> None:
        """Wait until another request may start, then record its start time."""
        now = self.clock_fn()
        if self.last_request_at is not None:
            remaining = self.interval - (now - self.last_request_at)
            if remaining > 0:
                self.sleep_fn(remaining)
                now = self.clock_fn()
        self.last_request_at = now


def load_apps(config_path: Path, selected_names: set[str] | None = None) -> list[dict[str, Any]]:
    """Load approved apps, refusing unknown names or unconfirmed records."""
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    apps = payload.get("apps", [])
    if not isinstance(apps, list) or not apps:
        raise ValueError(f"No apps found in {config_path}")

    selected = [app for app in apps if selected_names is None or app.get("name") in selected_names]
    found_names = {str(app.get("name")) for app in selected}
    missing_names = (selected_names or set()) - found_names
    if missing_names:
        raise ValueError(f"Unknown app name(s): {', '.join(sorted(missing_names))}")
    if not selected:
        raise ValueError("No apps selected")

    unconfirmed = [
        str(app.get("name", app.get("app_id", "<unknown>")))
        for app in selected
        if not app.get("confirmed")
    ]
    if unconfirmed:
        raise ValueError(f"Human confirmation required for: {', '.join(unconfirmed)}")
    return selected


def serialize_review(
    review: dict[str, Any], platform_app_id: str, product_id: str
) -> dict[str, Any]:
    """Map a store review to the strict non-identifying raw schema."""
    timestamp = review.get("at")
    if isinstance(timestamp, datetime):
        timestamp = timestamp.isoformat()
    return review_record(
        review_id=review.get("reviewId"),
        platform="google_play",
        platform_app_id=platform_app_id,
        product_id=product_id,
        text=review.get("content"),
        rating=review.get("score"),
        timestamp=timestamp,
        app_version=review.get("reviewCreatedVersion"),
        helpful_count=review.get("thumbsUpCount"),
    )


def serialize_token(token: _ContinuationToken | None) -> dict[str, Any] | None:
    """Convert the pinned library's continuation token to portable JSON data."""
    if token is None:
        return None
    sort_value = token.sort.value if isinstance(token.sort, Sort) else token.sort
    return {
        "token": token.token,
        "lang": token.lang,
        "country": token.country,
        "sort": sort_value,
        "count": token.count,
        "filter_score_with": token.filter_score_with,
        "filter_device_with": token.filter_device_with,
    }


def deserialize_token(payload: dict[str, Any] | None) -> _ContinuationToken | None:
    """Rebuild a continuation token from a JSON checkpoint."""
    if payload is None:
        return None
    return _ContinuationToken(
        payload["token"],
        payload["lang"],
        payload["country"],
        payload["sort"],
        payload["count"],
        payload["filter_score_with"],
        payload["filter_device_with"],
    )


def atomic_write_text(path: Path, content: str) -> None:
    """Replace a text file atomically after flushing its complete contents."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    with temporary_path.open("w", encoding="utf-8") as output_file:
        output_file.write(content)
        output_file.flush()
        os.fsync(output_file.fileno())
    temporary_path.replace(path)


def write_page(path: Path, page: Sequence[dict[str, Any]]) -> None:
    """Atomically write one JSONL page."""
    content = "".join(json.dumps(review, ensure_ascii=False) + "\n" for review in page)
    atomic_write_text(path, content)


def write_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    """Atomically write collection progress after its corresponding page exists."""
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def fetch_page(
    app_id: str,
    *,
    count: int,
    continuation_token: _ContinuationToken | None,
    pacer: RequestPacer,
    reviews_fn: ReviewsFunction = reviews,
    max_retries: int = 4,
    backoff_seconds: float = 2.0,
    sleep_fn: SleepFunction = time.sleep,
) -> tuple[list[dict[str, Any]], _ContinuationToken | None]:
    """Fetch one page, retrying transient failures with exponential backoff."""
    for attempt in range(max_retries + 1):
        pacer.wait()
        try:
            return reviews_fn(
                app_id,
                lang="en",
                country="pk",
                sort=Sort.NEWEST,
                count=count,
                continuation_token=continuation_token,
            )
        except Exception:
            if attempt == max_retries:
                raise
            sleep_fn(backoff_seconds * (2**attempt))
    raise RuntimeError("Unreachable retry state")


def collect_app(
    app: dict[str, Any],
    *,
    output_dir: Path,
    checkpoint_dir: Path,
    count: int,
    max_pages: int | None,
    pacer: RequestPacer,
    reviews_fn: ReviewsFunction = reviews,
) -> dict[str, Any]:
    """Resume collection for one app and persist each fetched page before its checkpoint."""
    app_id = str(app["app_id"])
    checkpoint_path = checkpoint_dir / f"{app_id}.json"
    checkpoint: dict[str, Any] = {
        "app_id": app_id,
        "app_name": app["name"],
        "next_page": 1,
        "reviews_collected": 0,
        "continuation_token": None,
        "complete": False,
    }
    if checkpoint_path.exists():
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    if checkpoint["complete"]:
        return checkpoint

    pages_this_run = 0
    while max_pages is None or pages_this_run < max_pages:
        raw_reviews, next_token = fetch_page(
            app_id,
            count=count,
            continuation_token=deserialize_token(checkpoint["continuation_token"]),
            pacer=pacer,
            reviews_fn=reviews_fn,
        )
        product_id = str(app.get("product_id", app["name"]).casefold().replace(" ", "_"))
        page = [serialize_review(review, app_id, product_id) for review in raw_reviews]
        page_path = output_dir / app_id / f"page_{checkpoint['next_page']:06d}.jsonl"
        write_page(page_path, page)

        checkpoint["next_page"] += 1
        checkpoint["reviews_collected"] += len(page)
        checkpoint["continuation_token"] = serialize_token(next_token)
        checkpoint["complete"] = next_token is None
        write_checkpoint(checkpoint_path, checkpoint)
        pages_this_run += 1
        print(
            f"{app['name']}: wrote {len(page)} reviews "
            f"({checkpoint['reviews_collected']} total)"
        )
        if next_token is None:
            break
    return checkpoint


def parse_args() -> argparse.Namespace:
    """Parse collection options."""
    parser = argparse.ArgumentParser(description="Collect approved public Google Play reviews.")
    parser.add_argument("--config", type=Path, default=DEFAULT_APPS_CONFIG)
    parser.add_argument(
        "--app", action="append", dest="apps", help="App name; repeat to select more"
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--checkpoint-dir", type=Path, default=DEFAULT_CHECKPOINT_DIR)
    parser.add_argument("--count", type=int, default=100, choices=range(1, 201), metavar="1-200")
    parser.add_argument("--max-pages-per-app", type=int)
    parser.add_argument("--request-interval", type=float, default=MIN_REQUEST_INTERVAL)
    return parser.parse_args()


def main() -> None:
    """Collect selected apps sequentially so one global rate limit is enforced."""
    args = parse_args()
    apps = load_apps(args.config, set(args.apps) if args.apps else None)
    pacer = RequestPacer(args.request_interval)
    for app in apps:
        collect_app(
            app,
            output_dir=args.output_dir,
            checkpoint_dir=args.checkpoint_dir,
            count=args.count,
            max_pages=args.max_pages_per_app,
            pacer=pacer,
        )


if __name__ == "__main__":
    main()