"""Validate collected raw reviews: counts, date coverage, quality, and script distribution."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_REVIEWS_DIR = Path("data/raw/reviews")

# Arabic Unicode block (covers Urdu Nastaliq script)
_ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]")


def _classify_script(text: str) -> str:
    has_arabic = bool(_ARABIC_RE.search(text))
    has_latin = bool(re.search(r"[a-zA-Z]", text))
    if has_arabic and has_latin:
        return "mixed"
    if has_arabic:
        return "urdu_script"
    return "latin"


class _Stats:
    def __init__(self) -> None:
        self.count = 0
        self.seen_ids: set[str] = set()
        self.empty = 0
        self.ratings: dict[int, int] = defaultdict(int)
        self.timestamps: list[str] = []
        self.scripts: dict[str, int] = defaultdict(int)

    def add(self, record: dict) -> None:  # type: ignore[type-arg]
        self.count += 1
        rid = record.get("review_id")
        if rid:
            self.seen_ids.add(str(rid))
        text = (record.get("text") or "").strip()
        if not text:
            self.empty += 1
        rating = record.get("rating")
        if isinstance(rating, (int, float)):
            self.ratings[int(rating)] += 1
        ts = record.get("timestamp")
        if ts:
            self.timestamps.append(str(ts))
        self.scripts[_classify_script(text) if text else "empty"] += 1


def _load(reviews_dir: Path) -> dict[tuple[str, str], _Stats]:
    stats: dict[tuple[str, str], _Stats] = defaultdict(_Stats)
    for path in sorted(reviews_dir.rglob("*.jsonl")):
        with path.open(encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    rec = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                key = (rec.get("platform", "unknown"), rec.get("product_id", "unknown"))
                stats[key].add(rec)
    return stats


def _pct(n: int, total: int) -> str:
    return f"{100 * n / total:.1f}%" if total else "—"


def _date_range(s: _Stats) -> tuple[str, str]:
    if not s.timestamps:
        return "—", "—"
    return min(s.timestamps)[:10], max(s.timestamps)[:10]


def _print_report(all_stats: dict[tuple[str, str], _Stats]) -> None:
    rows = sorted(all_stats.items())
    platform_totals: dict[str, int] = defaultdict(int)
    grand = grand_dups = grand_empty = 0

    for (platform, _product_id), s in rows:
        dups = s.count - len(s.seen_ids)
        platform_totals[platform] += s.count
        grand += s.count
        grand_dups += dups
        grand_empty += s.empty

    W = 76
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    print("=" * W)
    print("UrduCX-Bench — Raw Data Validation Report")
    print(f"Generated: {now}")
    print("=" * W)
    print(f"\nTotal records: {grand:,}")
    for plat, n in sorted(platform_totals.items()):
        print(f"  {plat:30s}  {n:8,}")
    print(f"\nDuplicates : {grand_dups:,}  ({_pct(grand_dups, grand)})")
    print(f"Empty text : {grand_empty:,}  ({_pct(grand_empty, grand)})")

    sep = "─" * W

    # ── counts + date coverage ────────────────────────────────────────────────
    print(f"\n{sep}")
    print("Counts and date coverage")
    print(sep)
    cols = f"{'Product':22}  {'Platform':16}  {'Records':>8}  {'Dup':>5}  {'Empty':>5}"
    print(f"{cols}  {'Oldest':10}  {'Newest':10}")
    print(sep)
    for (platform, product_id), s in rows:
        dups = s.count - len(s.seen_ids)
        d_min, d_max = _date_range(s)
        print(
            f"{product_id:22}  {platform:16}  {s.count:8,}  "
            f"{dups:5,}  {s.empty:5,}  {d_min:10}  {d_max:10}"
        )

    # ── rating distribution ───────────────────────────────────────────────────
    print(f"\n{sep}")
    print("Rating distribution  (% of records with non-null rating)")
    print(sep)
    rcols = f"{'Product':22}  {'Platform':16}  {'★1':>6}  {'★2':>6}  {'★3':>6}"
    print(f"{rcols}  {'★4':>6}  {'★5':>6}")
    print(sep)
    for (platform, product_id), s in rows:
        total_r = sum(s.ratings.values())

        def rp(star: int, _r: dict = s.ratings, _t: int = total_r) -> str:
            return f"{100 * _r.get(star, 0) / _t:.0f}%" if _t else "—"

        print(
            f"{product_id:22}  {platform:16}  "
            f"{rp(1):>6}  {rp(2):>6}  {rp(3):>6}  {rp(4):>6}  {rp(5):>6}"
        )

    # ── script distribution ───────────────────────────────────────────────────
    print(f"\n{sep}")
    print("Script distribution  (% of records by text character set)")
    print(sep)
    scols = f"{'Product':22}  {'Platform':16}  {'urdu_script':>12}  {'mixed':>8}"
    print(f"{scols}  {'latin':>8}  {'empty':>8}")
    print(sep)
    for (platform, product_id), s in rows:
        sc = s.scripts
        print(
            f"{product_id:22}  {platform:16}  "
            f"{_pct(sc.get('urdu_script', 0), s.count):>12}  "
            f"{_pct(sc.get('mixed', 0), s.count):>8}  "
            f"{_pct(sc.get('latin', 0), s.count):>8}  "
            f"{_pct(sc.get('empty', 0), s.count):>8}"
        )

    print(f"\n{'=' * W}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate collected raw review files.")
    parser.add_argument("--reviews-dir", type=Path, default=DEFAULT_REVIEWS_DIR)
    args = parser.parse_args()

    if not args.reviews_dir.exists():
        print(f"Reviews directory not found: {args.reviews_dir}", file=sys.stderr)
        sys.exit(1)

    all_stats = _load(args.reviews_dir)
    if not all_stats:
        print("No review records found.", file=sys.stderr)
        sys.exit(1)

    _print_report(all_stats)


if __name__ == "__main__":
    main()
