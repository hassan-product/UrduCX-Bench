"""Collect reviews posted since the last run, so the corpus grows forward.

`scrape_reviews.py` walks *backwards* into an app's history and stops for good once its
checkpoint is marked complete, so re-running it never picks up anything new. This module
solves the opposite problem: start at the newest review and stop as soon as it is clearly
back in already-collected territory.

That matters because app stores serve only a recent window. The corpus is 71.6% 2026 and
holds 7 reviews from 2015 — history cannot be back-filled, by anyone. A longitudinal
series can only be built forward from today, which makes it the one asset here that a
later entrant cannot catch up on.

Phase 1 checkpoints are never read or written; a refresh cannot corrupt the original
collection. New reviews land in dated files under `data/raw/refresh/<date>/`.

Run it monthly. The first run collected 5,851 reviews covering ten days, so a month is
comfortably inside the store's window while keeping the request count small:

    0 3 1 * *  cd /path/to/UrduCX-Bench && .venv/bin/python -m src.collect.refresh_reviews \
                 >> data/raw/refresh/cron.log 2>&1

Re-running the same day is safe - already-collected ids are skipped, so a repeat costs
one page per app and writes nothing.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.collect.scrape_reviews import (
    DEFAULT_APPS_CONFIG,
    DEFAULT_OUTPUT_DIR,
    RequestPacer,
    ReviewsFunction,
    atomic_write_text,
    fetch_page,
    load_apps,
    serialize_review,
)

DEFAULT_REFRESH_DIR = Path("data/raw/refresh")
DEFAULT_PAGE_SIZE = 200
DEFAULT_STOP_AFTER_SEEN = 100
DEFAULT_MAX_PAGES = 25
REQUEST_INTERVAL = 1.0


def known_review_ids(app_id: str, reviews_dir: Path, refresh_dir: Path) -> set[str]:
    """Every review id already on disk for this app, across original and refresh runs."""
    known: set[str] = set()
    sources = [reviews_dir / app_id]
    if refresh_dir.exists():
        sources.extend(day / f"{app_id}.jsonl" for day in refresh_dir.iterdir() if day.is_dir())

    for source in sources:
        paths = sorted(source.glob("*.jsonl")) if source.is_dir() else [source]
        for path in paths:
            if not path.exists():
                continue
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        known.add(str(json.loads(line)["review_id"]))
                    except (json.JSONDecodeError, KeyError):
                        continue
    return known


def refresh_app(
    app: dict[str, Any],
    *,
    reviews_dir: Path,
    refresh_dir: Path,
    pacer: RequestPacer,
    reviews_fn: ReviewsFunction,
    page_size: int = DEFAULT_PAGE_SIZE,
    stop_after_seen: int = DEFAULT_STOP_AFTER_SEEN,
    max_pages: int = DEFAULT_MAX_PAGES,
    run_date: str | None = None,
) -> dict[str, Any]:
    """Walk newest-first until `stop_after_seen` consecutive reviews are already held.

    A plain "stop at the first familiar review" rule is too eager: the store reorders
    near-simultaneous posts, so one known id can sit above several genuinely new ones.
    Requiring a run of them makes the stop robust without reading the whole history.
    """
    app_id = str(app["app_id"])
    product_id = str(app.get("product_id", app["name"]).casefold().replace(" ", "_"))
    known = known_review_ids(app_id, reviews_dir, refresh_dir)

    fresh: list[dict[str, Any]] = []
    consecutive_seen = 0
    token = None
    pages = 0
    reason = "max_pages"

    while pages < max_pages:
        raw, token = fetch_page(
            app_id,
            count=page_size,
            continuation_token=token,
            pacer=pacer,
            reviews_fn=reviews_fn,
        )
        pages += 1
        if not raw:
            reason = "store_exhausted"
            break

        for review in raw:
            record = serialize_review(review, app_id, product_id)
            if str(record["review_id"]) in known:
                consecutive_seen += 1
                continue
            consecutive_seen = 0
            known.add(str(record["review_id"]))
            fresh.append(record)

        if consecutive_seen >= stop_after_seen:
            reason = "caught_up"
            break
        if token is None:
            reason = "store_exhausted"
            break

    date = run_date or datetime.now(UTC).strftime("%Y-%m-%d")
    written = 0
    if fresh:
        out = refresh_dir / date / f"{app_id}.jsonl"
        content = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in fresh)
        atomic_write_text(out, content)
        written = len(fresh)

    return {
        "app_id": app_id,
        "app_name": app["name"],
        "new_reviews": written,
        "pages_fetched": pages,
        "stop_reason": reason,
        "date": date,
    }


def parse_args() -> argparse.Namespace:
    """Parse refresh options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_APPS_CONFIG)
    parser.add_argument("--app", action="append", dest="apps", help="App name; repeat for more")
    parser.add_argument("--reviews-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--refresh-dir", type=Path, default=DEFAULT_REFRESH_DIR)
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE)
    parser.add_argument("--stop-after-seen", type=int, default=DEFAULT_STOP_AFTER_SEEN)
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    parser.add_argument("--interval", type=float, default=REQUEST_INTERVAL)
    return parser.parse_args()


def main() -> None:
    """Refresh every configured app and print a one-line summary each."""
    from google_play_scraper import reviews as reviews_fn

    args = parse_args()
    apps = load_apps(args.config, set(args.apps) if args.apps else None)
    pacer = RequestPacer(args.interval)

    total = 0
    started = time.monotonic()
    for app in apps:
        summary = refresh_app(
            app,
            reviews_dir=args.reviews_dir,
            refresh_dir=args.refresh_dir,
            pacer=pacer,
            reviews_fn=reviews_fn,
            page_size=args.page_size,
            stop_after_seen=args.stop_after_seen,
            max_pages=args.max_pages,
        )
        total += summary["new_reviews"]
        print(
            f"{summary['app_name']:24s} +{summary['new_reviews']:5d} new "
            f"({summary['pages_fetched']} pages, {summary['stop_reason']})"
        )

    print(f"\n{total:,} new reviews in {time.monotonic() - started:.0f}s")
    if total:
        print(f"Written under {args.refresh_dir}/<date>/ — run `validate_raw` before merging.")


if __name__ == "__main__":
    main()
