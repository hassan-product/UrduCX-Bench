"""Tests for the corpus explorer.

Weighted toward the two claims the tool makes about itself: that filters narrow rather
than widen, and that what it exports is what the adjudication harness reads. The second
is the whole point of the tool - a filtered slice that cannot be judged is a browsing toy.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from src.adjudicate.items import load_items
from src.explore import keywords
from src.explore.aggregate import breakdown, label_mix, releases, summary, trend, wilson
from src.explore.corpus import Corpus, Filters, Review
from src.explore.server import Session, export_rows, filters_from_query


def _review(rid: str, **kwargs: object) -> Review:
    base = {
        "text": "the app deducted my money",
        "platform": "google_play",
        "product": "wallet_a",
        "rating": 1,
        "language": "english",
        "date": "2026-05-04T10:00:00",
        "version": "1.0",
        "helpful": 0,
    }
    base.update(kwargs)
    return Review(id=rid, **base)  # type: ignore[arg-type]


# --- filters narrow ---------------------------------------------------------


def test_filters_combine_as_and_not_or() -> None:
    corpus = Corpus([
        _review("a", product="wallet_a", rating=1),
        _review("b", product="wallet_b", rating=1),
        _review("c", product="wallet_a", rating=5),
    ])

    kept = corpus.filter(Filters(products={"wallet_a"}, ratings={1}))

    assert [r.id for r in kept] == ["a"], "each filter must narrow the previous result"


def test_several_keyword_tags_narrow_rather_than_widen() -> None:
    corpus = Corpus([
        _review("both", text="paisay kat gaye aur helpline jawab nahi deti"),
        _review("one", text="paisay kat gaye"),
    ])

    kept = corpus.filter(Filters(tags={"money_lost", "support"}))

    assert [r.id for r in kept] == ["both"]


def test_search_matches_urdu_script() -> None:
    corpus = Corpus([
        _review("ur", text="میرا بیلنس کٹ گیا"),
        _review("en", text="my balance was deducted"),
    ])

    assert [r.id for r in corpus.filter(Filters(search="بیلنس"))] == ["ur"]


def test_labelled_only_excludes_unlabelled_rows() -> None:
    corpus = Corpus([_review("a", label="login_failure"), _review("b")])

    assert [r.id for r in corpus.filter(Filters(labelled_only=True))] == ["a"]


# --- keyword groups ---------------------------------------------------------


@pytest.mark.parametrize(
    ("tag", "text"),
    [
        ("money_lost", "میرے پیسے کٹ گئے"),
        ("money_lost", "paisay kat gaye"),
        ("otp", "او ٹی پی نہیں آیا"),
        ("support", "helpline jawab nahi deti"),
        ("card", "debit card never arrived"),
    ],
)
def test_keyword_groups_match_across_scripts(tag: str, text: str) -> None:
    assert keywords.matches(tag, text), f"{tag} should match {text!r}"


def test_an_unknown_tag_matches_nothing_rather_than_everything() -> None:
    assert not keywords.matches("no_such_tag", "any text at all")


# --- aggregates -------------------------------------------------------------


def test_a_thin_version_is_dropped_rather_than_ranked_first() -> None:
    reviews = [_review(f"bad{n}", version="9.9", rating=1) for n in range(5)]
    reviews += [_review(f"ok{n}", version="1.0", rating=1 if n < 20 else 5)
                for n in range(60)]

    rows = releases(reviews, minimum=40)

    assert [r["version"] for r in rows] == ["1.0"], (
        "a 100%-negative version with five reviews is noise, not the worst release"
    )


def test_release_table_reports_the_interval_not_just_the_share() -> None:
    reviews = [_review(f"r{n}", version="2.0", rating=1 if n < 30 else 5)
               for n in range(60)]

    row = releases(reviews, minimum=40)[0]

    assert row["bad_pct"] == 50.0
    assert row["low"] < 50.0 < row["high"], "a share without its interval invites over-reading"


def test_summary_reports_share_of_the_whole_corpus() -> None:
    reviews = [_review("a"), _review("b")]

    assert summary(reviews, corpus_size=200)["share"] == 1.0


def test_summary_of_nothing_does_not_divide_by_zero() -> None:
    assert summary([], corpus_size=100)["total"] == 0


def test_trend_is_ordered_oldest_first() -> None:
    reviews = [
        _review("new", date="2026-06-01T00:00:00"),
        _review("old", date="2026-01-01T00:00:00"),
    ]

    assert [t["month"] for t in trend(reviews)] == ["2026-01", "2026-06"]


def test_label_mix_reports_how_many_were_judged_by_a_person() -> None:
    reviews = [
        _review("a", label="login_failure", label_source="human"),
        _review("b", label="login_failure", label_source="model"),
        _review("c"),
    ]

    mix = label_mix(reviews)

    assert mix[0]["of_labelled"] == 2, "unlabelled rows are not a denominator"
    assert mix[0]["human"] == 1


def test_breakdown_counts_negative_share_per_value() -> None:
    reviews = [_review("a", product="x", rating=1), _review("b", product="x", rating=5)]

    row = breakdown(reviews, "product")[0]

    assert (row["total"], row["bad"], row["bad_pct"]) == (2, 1, 50.0)


def test_wilson_widens_as_the_sample_thins() -> None:
    thin_low, thin_high = wilson(3, 5)
    thick_low, thick_high = wilson(300, 500)

    assert (thin_high - thin_low) > (thick_high - thick_low)


# --- the export contract ----------------------------------------------------


def test_an_exported_slice_loads_in_the_adjudication_harness(tmp_path: Path) -> None:
    reviews = [_review("r1", text="paisay kat gaye", language="roman_urdu")]
    path = tmp_path / "slice.jsonl"
    path.write_text(export_rows(reviews), encoding="utf-8")

    items = load_items(path)

    assert len(items) == 1
    assert items[0].id == "r1"
    assert items[0].text == "paisay kat gaye"
    assert items[0].meta["language"] == "roman_urdu"


def test_export_carries_no_predictions_so_judging_starts_blind(tmp_path: Path) -> None:
    path = tmp_path / "slice.jsonl"
    path.write_text(export_rows([_review("r1", label="login_failure")]), encoding="utf-8")

    row = json.loads(path.read_text(encoding="utf-8"))

    assert "predictions" not in row
    assert "label" not in row, "carrying an existing label would anchor the judgement"


# --- query parsing ----------------------------------------------------------


def test_query_parsing_accepts_repeated_and_comma_joined_values() -> None:
    filters = filters_from_query(
        {"product": ["a", "b,c"], "rating": ["1,2"], "q": ["  paisay "], "labelled": ["1"]}
    )

    assert filters.products == {"a", "b", "c"}
    assert filters.ratings == {1, 2}
    assert filters.search == "paisay"
    assert filters.labelled_only is True


def test_unparseable_ratings_are_ignored_not_crashed_on() -> None:
    assert filters_from_query({"rating": ["1,banana,3"]}).ratings == {1, 3}


def test_report_pages_without_running_off_the_end() -> None:
    session = Session(corpus=Corpus([_review(str(n)) for n in range(10)]))

    report = session.report(Filters(), page=99)

    assert report["reviews"] == []
    assert report["pages"] >= 1
