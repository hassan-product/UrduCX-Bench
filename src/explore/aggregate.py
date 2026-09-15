"""Summarise a filtered slice.

Every figure here is a count or a share of counts. Nothing is inferred, modelled or
predicted, which is what makes this half of the tool trustworthy without a labelling run:
a rating and a version number are recorded facts, and the arithmetic over them carries no
error rate of its own.

The one statistical courtesy applied is a minimum sample size on the release table. A
version with nine reviews can show 100% bad and mean nothing, and a table that ranks it
first is worse than a table that omits it.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict

from src.explore.corpus import Review

MIN_VERSION_REVIEWS = 40


def wilson(hits: int, total: int, z: float = 1.959964) -> tuple[float, float]:
    """Wilson interval, so a thin cell reads as thin rather than as a finding."""
    if total == 0:
        return (0.0, 0.0)
    p = hits / total
    d = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / d
    margin = z / d * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def breakdown(reviews: list[Review], attribute: str, limit: int = 20) -> list[dict]:
    """Counts and negative-review share for one dimension."""
    totals: Counter = Counter()
    bad: Counter = Counter()
    for review in reviews:
        key = str(getattr(review, attribute) or "—")
        totals[key] += 1
        if (review.rating or 5) <= 2:
            bad[key] += 1
    out = []
    for key, total in totals.most_common(limit):
        low, high = wilson(bad[key], total)
        out.append(
            {
                "key": key,
                "total": total,
                "share": round(total / len(reviews) * 100, 1) if reviews else 0.0,
                "bad": bad[key],
                "bad_pct": round(bad[key] / total * 100, 1),
                "low": round(low * 100, 1),
                "high": round(high * 100, 1),
            }
        )
    return out


def releases(reviews: list[Review], minimum: int = MIN_VERSION_REVIEWS) -> list[dict]:
    """Negative-review share per app version, worst first.

    This is the corpus's most useful free signal: it answers whether a release made
    things worse, using only the rating and the version string, both of which every
    store records. Versions below the minimum are dropped rather than ranked - a
    hundred-percent-bad release with nine reviews is noise wearing a headline.
    """
    cells: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    for review in reviews:
        if not review.version:
            continue
        cell = cells[(review.product, review.version)]
        cell[1] += 1
        cell[0] += (review.rating or 5) <= 2

    rows = []
    for (product, version), (bad, total) in cells.items():
        if total < minimum:
            continue
        low, high = wilson(bad, total)
        rows.append(
            {
                "product": product,
                "version": version,
                "total": total,
                "bad": bad,
                "bad_pct": round(bad / total * 100, 1),
                "low": round(low * 100, 1),
                "high": round(high * 100, 1),
            }
        )
    rows.sort(key=lambda r: -r["bad_pct"])
    return rows


def trend(reviews: list[Review], months: int = 24) -> list[dict]:
    """Monthly volume and negative share, oldest first."""
    cells: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for review in reviews:
        if len(review.month) != 7:
            continue
        cell = cells[review.month]
        cell[1] += 1
        cell[0] += (review.rating or 5) <= 2
    ordered = sorted(cells.items())[-months:]
    return [
        {
            "month": month,
            "total": total,
            "bad": bad,
            "bad_pct": round(bad / total * 100, 1) if total else 0.0,
        }
        for month, (bad, total) in ordered
    ]


def summary(reviews: list[Review], corpus_size: int) -> dict:
    """Headline counts for whatever is currently filtered."""
    if not reviews:
        return {
            "total": 0,
            "share": 0.0,
            "bad_pct": 0.0,
            "labelled": 0,
            "median_words": 0,
            "languages": {},
            "span": "",
        }
    bad = sum(1 for r in reviews if (r.rating or 5) <= 2)
    labelled = sum(1 for r in reviews if r.label)
    lengths = sorted(r.words for r in reviews)
    dates = sorted(r.date[:7] for r in reviews if r.date)
    return {
        "total": len(reviews),
        "share": round(len(reviews) / corpus_size * 100, 1),
        "bad_pct": round(bad / len(reviews) * 100, 1),
        "labelled": labelled,
        "labelled_pct": round(labelled / len(reviews) * 100, 1),
        "median_words": lengths[len(lengths) // 2],
        "languages": dict(Counter(r.language for r in reviews).most_common()),
        "span": f"{dates[0]} to {dates[-1]}" if dates else "",
    }


def label_mix(reviews: list[Review], limit: int = 15) -> list[dict]:
    """Issue-type counts over the labelled subset only."""
    labelled = [r for r in reviews if r.label]
    if not labelled:
        return []
    counts = Counter(r.label for r in labelled)
    human = sum(1 for r in labelled if r.label_source == "human")
    return [
        {
            "label": label,
            "total": total,
            "share": round(total / len(labelled) * 100, 1),
            "of_labelled": len(labelled),
            "human": human,
        }
        for label, total in counts.most_common(limit)
    ]
