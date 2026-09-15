"""Load the corpus once, then filter it in memory.

Fifty thousand rows is small enough to hold and scan directly, so there is no index, no
database and no build step - the tool reads the same JSONL the rest of the project writes
and starts in about a second. Filtering is a linear scan, which at this size costs a few
milliseconds and keeps every filter composable without a query planner.

Issue labels are joined in from whatever labelling runs exist. They cover a small fraction
of the corpus, and that fraction is reported rather than hidden: a filter that silently
searched 4% of the data while appearing to search all of it would be worse than no filter.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.explore import keywords
from src.prep.clean import detect_language, normalise_text

CORPUS = Path("data/interim/reviews_cleaned.jsonl")
REFRESH = Path("data/raw/refresh")
LABEL_SOURCES = (
    Path("spike/phase3_diag/diag_claude-opus-5.jsonl"),
    Path("spike/phase3_diag/hunt_results.jsonl"),
    Path("spike/phase3_diag/topup_results.jsonl"),
    Path("spike/phase3_diag/jazzcash_brief.jsonl"),
    Path("spike/phase3_diag/urdu_pass_worklist.jsonl"),
)
HUMAN_LABELS = (
    Path("spike/phase3_diag/adjudications.jsonl"),
    Path("spike/phase3_diag/adjudications_urdu.jsonl"),
)


@dataclass
class Review:
    """One review, with whatever is known about it."""

    id: str
    text: str
    platform: str
    product: str
    rating: int | None
    language: str
    date: str
    version: str
    helpful: int
    label: str | None = None
    label_source: str | None = None

    @property
    def year(self) -> str:
        return self.date[:4]

    @property
    def month(self) -> str:
        return self.date[:7]

    @property
    def words(self) -> int:
        return len(self.text.split())


@dataclass
class Filters:
    """A combination of filters. Empty collections mean "no restriction"."""

    platforms: set[str] = field(default_factory=set)
    products: set[str] = field(default_factory=set)
    ratings: set[int] = field(default_factory=set)
    languages: set[str] = field(default_factory=set)
    versions: set[str] = field(default_factory=set)
    years: set[str] = field(default_factory=set)
    labels: set[str] = field(default_factory=set)
    tags: set[str] = field(default_factory=set)
    search: str = ""
    labelled_only: bool = False
    min_words: int = 0

    def keeps(self, review: Review) -> bool:
        """Whether one review survives every active filter."""
        if self.platforms and review.platform not in self.platforms:
            return False
        if self.products and review.product not in self.products:
            return False
        if self.ratings and review.rating not in self.ratings:
            return False
        if self.languages and review.language not in self.languages:
            return False
        if self.versions and review.version not in self.versions:
            return False
        if self.years and review.year not in self.years:
            return False
        if self.labelled_only and not review.label:
            return False
        if self.labels and review.label not in self.labels:
            return False
        if self.min_words and review.words < self.min_words:
            return False
        # Every keyword group must match, so tags narrow rather than widen.
        if self.tags and not all(keywords.matches(t, review.text) for t in self.tags):
            return False
        if self.search and self.search.casefold() not in review.text.casefold():
            return False
        return True


def _rows(path: Path) -> Iterable[dict[str, Any]]:
    """Yield JSON objects from a JSONL file, skipping blanks."""
    if not path.exists():
        return
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def _load_labels() -> dict[str, tuple[str, str]]:
    """Join issue labels from every run, preferring a human judgement over a model's."""
    out: dict[str, tuple[str, str]] = {}
    for path in LABEL_SOURCES:
        for row in _rows(path):
            rid = str(row.get("review_id") or row.get("id") or "")
            label = None
            if isinstance(row.get("label"), dict):
                label = row["label"].get("intent")
            elif isinstance(row.get("labels"), dict):
                first = next(iter(row["labels"].values()), None)
                label = first.get("intent") if isinstance(first, dict) else None
            elif isinstance(row.get("models"), dict):
                label = next(iter(row["models"].values()), None)
            if rid and label:
                out.setdefault(rid, (str(label), "model"))

    # A person's judgement always wins over a model's, and says so.
    for path in HUMAN_LABELS:
        for row in _rows(path):
            rid = str(row.get("review_id") or row.get("item_id") or "")
            label = row.get("human_intent") or row.get("label")
            if rid and label and not row.get("skipped"):
                out[rid] = (str(label), "human")
    return out


@dataclass
class Corpus:
    """Every review in memory, with the filters applied on demand."""

    reviews: list[Review]

    def filter(self, filters: Filters) -> list[Review]:
        """Reviews surviving the filter, newest first."""
        kept = [r for r in self.reviews if filters.keeps(r)]
        kept.sort(key=lambda r: r.date, reverse=True)
        return kept

    def values(self, attribute: str) -> list[str]:
        """Distinct values for a field, for the interface's menus."""
        seen = {getattr(r, attribute) for r in self.reviews}
        return sorted(str(v) for v in seen if v)

    @property
    def labelled(self) -> int:
        return sum(1 for r in self.reviews if r.label)


def load_corpus(path: Path = CORPUS, *, include_refresh: bool = True) -> Corpus:
    """Read the cleaned corpus, add forward-collected reviews, and join labels."""
    labels = _load_labels()
    reviews: list[Review] = []
    seen: set[str] = set()

    def add(row: dict[str, Any], text_key: str) -> None:
        rid = str(row.get("review_id") or "")
        if not rid or rid in seen:
            return
        seen.add(rid)
        label, source = labels.get(rid, (None, None))
        reviews.append(
            Review(
                id=rid,
                text=str(row.get(text_key) or row.get("text") or ""),
                platform=str(row.get("platform") or ""),
                product=str(row.get("product_id") or ""),
                rating=row.get("rating"),
                language=str(row.get("language") or ""),
                date=str(row.get("timestamp") or ""),
                version=str(row.get("app_version") or ""),
                helpful=int(row.get("helpful_count") or 0),
                label=label,
                label_source=source,
            )
        )

    for row in _rows(path):
        add(row, "text_clean")

    # Forward-collected reviews have not been through cleaning, so they are held to the
    # same minimum the cleaner applies rather than let in on different terms.
    if include_refresh and REFRESH.exists():
        for day in sorted(REFRESH.iterdir()):
            if not day.is_dir():
                continue
            for shard in sorted(day.glob("*.jsonl")):
                for row in _rows(shard):
                    text = normalise_text(row.get("text"))
                    if len(text.split()) < 3:
                        continue
                    # Language is assigned during cleaning, which these rows have not
                    # been through. Detecting it here rather than leaving it blank keeps
                    # the language filter honest: an empty facet silently drops rows from
                    # every language-scoped count.
                    row = {**row, "text": text, "language": detect_language(text)}
                    add(row, "text")

    return Corpus(reviews=reviews)
