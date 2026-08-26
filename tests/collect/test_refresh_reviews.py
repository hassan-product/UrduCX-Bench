"""Tests for forward collection: pick up new reviews without re-walking history."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.collect.refresh_reviews import known_review_ids, refresh_app
from src.collect.scrape_reviews import RequestPacer

APP = {"app_id": "com.example.app", "name": "Example", "product_id": "example"}


def _pacer() -> RequestPacer:
    return RequestPacer(1.0, sleep_fn=lambda _seconds: None, clock_fn=lambda: 0.0)


def _store_review(review_id: str) -> dict[str, Any]:
    return {
        "reviewId": review_id,
        "content": f"review {review_id}",
        "score": 1,
        "at": "2026-08-26T00:00:00",
        "reviewCreatedVersion": "1.0",
        "thumbsUpCount": 0,
    }


def _write_page(path: Path, review_ids: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps({"review_id": rid}) + "\n" for rid in review_ids), encoding="utf-8"
    )


def _pages_fn(pages: list[list[dict[str, Any]]]):
    calls = {"n": 0}

    def reviews_fn(*_args: object, **_kwargs: object):
        index = calls["n"]
        calls["n"] += 1
        if index >= len(pages):
            return [], None
        token = None if index == len(pages) - 1 else object()
        return pages[index], token

    return reviews_fn


def test_known_ids_span_original_and_refresh_directories(tmp_path: Path) -> None:
    reviews_dir, refresh_dir = tmp_path / "reviews", tmp_path / "refresh"
    _write_page(reviews_dir / APP["app_id"] / "page_000001.jsonl", ["a", "b"])
    _write_page(refresh_dir / "2026-08-01" / f"{APP['app_id']}.jsonl", ["c"])

    assert known_review_ids(APP["app_id"], reviews_dir, refresh_dir) == {"a", "b", "c"}


def test_only_unseen_reviews_are_written(tmp_path: Path) -> None:
    reviews_dir, refresh_dir = tmp_path / "reviews", tmp_path / "refresh"
    _write_page(reviews_dir / APP["app_id"] / "page_000001.jsonl", ["old1", "old2"])

    reviews_fn = _pages_fn([[_store_review("new1"), _store_review("old1")]])
    summary = refresh_app(
        APP,
        reviews_dir=reviews_dir,
        refresh_dir=refresh_dir,
        pacer=_pacer(),
        reviews_fn=reviews_fn,
        stop_after_seen=1,
        run_date="2026-08-26",
    )

    assert summary["new_reviews"] == 1
    assert summary["stop_reason"] == "caught_up"
    written = (refresh_dir / "2026-08-26" / f"{APP['app_id']}.jsonl").read_text(encoding="utf-8")
    assert json.loads(written.strip())["review_id"] == "new1"


def test_one_familiar_review_among_new_ones_does_not_stop_the_walk(tmp_path: Path) -> None:
    """The store reorders near-simultaneous posts, so a lone known id is not 'caught up'."""
    reviews_dir, refresh_dir = tmp_path / "reviews", tmp_path / "refresh"
    _write_page(reviews_dir / APP["app_id"] / "page_000001.jsonl", ["seen"])

    page = [_store_review("n1"), _store_review("seen"), _store_review("n2")]
    summary = refresh_app(
        APP,
        reviews_dir=reviews_dir,
        refresh_dir=refresh_dir,
        pacer=_pacer(),
        reviews_fn=_pages_fn([page]),
        stop_after_seen=2,
        run_date="2026-08-26",
    )

    assert summary["new_reviews"] == 2, "the run of seen ids never reached the threshold"


def test_a_second_refresh_collects_nothing_new(tmp_path: Path) -> None:
    reviews_dir, refresh_dir = tmp_path / "reviews", tmp_path / "refresh"
    _write_page(reviews_dir / APP["app_id"] / "page_000001.jsonl", [])
    page = [_store_review("n1"), _store_review("n2")]

    kwargs = dict(
        reviews_dir=reviews_dir,
        refresh_dir=refresh_dir,
        pacer=_pacer(),
        stop_after_seen=2,
        run_date="2026-08-26",
    )
    first = refresh_app(APP, reviews_fn=_pages_fn([page]), **kwargs)
    second = refresh_app(APP, reviews_fn=_pages_fn([page]), **kwargs)

    assert first["new_reviews"] == 2
    assert second["new_reviews"] == 0, "already-written refresh output must count as known"


def test_refresh_never_touches_phase_one_checkpoints(tmp_path: Path) -> None:
    reviews_dir, refresh_dir = tmp_path / "reviews", tmp_path / "refresh"
    checkpoints = tmp_path / "checkpoints"
    checkpoints.mkdir()
    checkpoint = checkpoints / f"{APP['app_id']}.json"
    original = json.dumps({"complete": True, "reviews_collected": 10})
    checkpoint.write_text(original, encoding="utf-8")

    refresh_app(
        APP,
        reviews_dir=reviews_dir,
        refresh_dir=refresh_dir,
        pacer=_pacer(),
        reviews_fn=_pages_fn([[_store_review("n1")]]),
        stop_after_seen=1,
        run_date="2026-08-26",
    )

    assert checkpoint.read_text(encoding="utf-8") == original


def test_empty_store_page_ends_the_walk(tmp_path: Path) -> None:
    summary = refresh_app(
        APP,
        reviews_dir=tmp_path / "reviews",
        refresh_dir=tmp_path / "refresh",
        pacer=_pacer(),
        reviews_fn=_pages_fn([]),
        run_date="2026-08-26",
    )

    assert summary["new_reviews"] == 0
    assert summary["stop_reason"] == "store_exhausted"
