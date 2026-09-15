"""Tests for the evaluation harness.

Weighted toward the protocol rather than the plumbing: the properties that make a gold
label trustworthy are the ones that fail silently when they regress. A blind pass that
quietly stops being blind still produces a full file of judgements.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from src.adjudicate.items import (
    Item,
    Judgement,
    load_items,
    load_judgements,
    write_judgements,
)
from src.adjudicate.labels import load_labels
from src.adjudicate.power import (
    minimum_detectable_effect,
    permutation_test,
    required_n,
    spread,
)
from src.adjudicate.scoring import (
    accuracy,
    by_group,
    cohens_kappa,
    joint_error,
    reweighted_accuracy,
    usable,
    wilson,
)
from src.adjudicate.server import Session
from src.adjudicate.worklist import build_worklist, progress


def _item(identifier: str, **predictions: str) -> Item:
    return Item(id=identifier, text=f"text {identifier}", predictions=predictions)


# --- the blind protocol -----------------------------------------------------


def test_predictions_are_absent_from_a_blind_payload_not_merely_hidden() -> None:
    item = _item("a", model_x="p", model_y="q")

    blind = item.public(reveal_predictions=False)

    assert "predictions" not in blind, "a value present in the payload is discoverable"
    assert item.public(reveal_predictions=True)["predictions"] == {
        "model_x": "p",
        "model_y": "q",
    }


def test_a_judgement_records_the_regime_it_was_made_under(tmp_path: Path) -> None:
    labels = load_labels(Path("config/taxonomy.yaml"))
    session = Session(
        items=[_item("a", m="x")],
        labels=labels,
        output=tmp_path / "out.jsonl",
        blind=False,
    )

    judgement = session.record({"item_id": "a", "label": "login_failure"})

    assert judgement.blind is False
    assert judgement.label_version == labels.version


def test_a_secondary_identical_to_the_primary_is_discarded(tmp_path: Path) -> None:
    session = Session(
        items=[_item("a")],
        labels=load_labels(Path("config/taxonomy.yaml")),
        output=tmp_path / "out.jsonl",
    )

    judgement = session.record(
        {"item_id": "a", "label": "login_failure", "secondary": "login_failure"}
    )

    assert judgement.secondary is None, "naming the same label twice is not a second issue"


# --- controls ---------------------------------------------------------------


def test_an_item_is_a_control_only_when_several_models_concur() -> None:
    assert _item("a", x="same", y="same").is_control
    assert not _item("b", x="one", y="other").is_control
    assert not _item("c", x="lonely").is_control, "one model cannot agree with itself"


def test_joint_error_counts_only_where_every_model_was_wrong_together() -> None:
    pairs = [
        (_item("a", x="p", y="p"), Judgement(item_id="a", label="q")),
        (_item("b", x="p", y="p"), Judgement(item_id="b", label="p")),
        (_item("c", x="p", y="q"), Judgement(item_id="c", label="z")),
    ]

    wrong, controls = joint_error(pairs)

    assert (wrong, controls) == (1, 2), "the disagreement is not a control"


# --- skipped items ----------------------------------------------------------


def test_a_skipped_item_is_not_scored_as_a_model_error() -> None:
    items = [_item("a", m="p"), _item("b", m="p")]
    judgements = {
        "a": Judgement(item_id="a", label="p"),
        "b": Judgement(item_id="b", label=None, skipped=True),
    }

    hits, total = accuracy(usable(items, judgements), "m")

    assert (hits, total) == (1, 1), "an unanswered item is not a wrong answer"


def test_unblind_judgements_are_excluded_unless_requested() -> None:
    items = [_item("a", m="p"), _item("b", m="p")]
    judgements = {
        "a": Judgement(item_id="a", label="p"),
        "b": Judgement(item_id="b", label="p", blind=False),
    }

    assert len(usable(items, judgements)) == 1
    assert len(usable(items, judgements, include_unblind=True)) == 2


# --- reweighting ------------------------------------------------------------


def test_reweighting_lifts_accuracy_measured_on_an_enriched_sample() -> None:
    agree = [
        (_item(f"a{n}", x="p", y="p"), Judgement(item_id=f"a{n}", label="p")) for n in range(10)
    ]
    disagree = [
        (_item(f"d{n}", x="p", y="q"), Judgement(item_id=f"d{n}", label="z")) for n in range(10)
    ]
    pairs = agree + disagree

    raw = accuracy(pairs, "x")
    corrected = reweighted_accuracy(pairs, "x", population_agreement_rate=0.8)

    assert raw == (10, 20)
    assert corrected == pytest.approx(0.8), "80% of the population sits in the easy stratum"


# --- worklist ---------------------------------------------------------------


def test_controls_mode_offers_only_items_the_models_already_agree_on() -> None:
    items = [_item("a", x="p", y="p"), _item("b", x="p", y="q")]

    worklist = build_worklist(items, {}, mode="controls")

    assert [i.id for i in worklist] == ["a"]


def test_revisit_reopens_only_judgements_made_under_an_older_label_set() -> None:
    items = [_item("a"), _item("b")]
    judgements = {
        "a": Judgement(item_id="a", label="x", label_version=2),
        "b": Judgement(item_id="b", label="x", label_version=3),
    }

    worklist = build_worklist(items, judgements, mode="revisit", label_version=3)

    assert [i.id for i in worklist] == ["a"]


def test_progress_counts_against_this_pass_not_every_judgement_ever_made() -> None:
    items = [_item("a"), _item("b")]
    judgements = {f"other{n}": Judgement(item_id=f"other{n}", label="x") for n in range(50)}
    judgements["a"] = Judgement(item_id="a", label="x")

    assert progress(items, judgements, "all", 0) == (1, 2)


# --- persistence ------------------------------------------------------------


def test_rejudging_replaces_the_record_rather_than_appending(tmp_path: Path) -> None:
    path = tmp_path / "out.jsonl"
    session = Session(
        items=[_item("a")],
        labels=load_labels(Path("config/taxonomy.yaml")),
        output=path,
    )

    session.record({"item_id": "a", "label": "login_failure"})
    session.record({"item_id": "a", "label": "otp_not_received"})

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1, "two records for one item would be counted twice"
    assert rows[0]["label"] == "otp_not_received"


def test_items_load_from_the_field_names_a_review_corpus_uses(tmp_path: Path) -> None:
    path = tmp_path / "items.jsonl"
    path.write_text(
        json.dumps(
            {
                "review_id": "r1",
                "text_scrubbed": "paisay kat gaye",
                "language": "roman_urdu",
                "models": {"m": {"intent": "transfer_failed"}},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    item = load_items(path)[0]

    assert item.id == "r1"
    assert item.text == "paisay kat gaye"
    assert item.predictions == {"m": "transfer_failed"}
    assert item.meta["language"] == "roman_urdu"


def test_judgements_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "j.jsonl"
    original = {"a": Judgement(item_id="a", label="x", flags={"reason:vague": True})}

    write_judgements(path, original)

    assert load_judgements(path)["a"].flags == {"reason:vague": True}


# --- labels -----------------------------------------------------------------


def test_label_sets_load_from_either_schema(tmp_path: Path) -> None:
    path = tmp_path / "labels.yaml"
    path.write_text(
        "version: 4\nlabels:\n  - id: alpha\n    group: g\n    definition: d\n",
        encoding="utf-8",
    )

    label_set = load_labels(path)

    assert label_set.version == 4
    assert label_set.ids == ["alpha"]
    assert load_labels(Path("config/taxonomy.yaml")).ids, "the study's own scheme loads"


def test_duplicate_label_ids_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "labels.yaml"
    path.write_text("labels:\n  - id: a\n  - id: a\n", encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate"):
        load_labels(path)


# --- statistics -------------------------------------------------------------


def test_wilson_stays_inside_the_unit_interval_at_the_extremes() -> None:
    low, high = wilson(0, 5)
    assert low == pytest.approx(0.0, abs=1e-12) and 0 < high < 1

    low, high = wilson(5, 5)
    assert 0 < low < 1 and high == pytest.approx(1.0, abs=1e-12)


def test_kappa_discounts_agreement_that_chance_would_produce() -> None:
    assert cohens_kappa([("a", "a"), ("b", "b")] * 5) == pytest.approx(1.0)
    assert cohens_kappa([("a", "a"), ("a", "b"), ("b", "a"), ("b", "b")]) == pytest.approx(0.0)


def test_the_permutation_test_finds_a_real_effect_and_ignores_noise() -> None:
    obvious = [("a", False)] * 50 + [("b", True)] * 50
    _, p_real = permutation_test(obvious, rounds=1000, seed=1)
    assert p_real < 0.01

    flat = [("a", n % 2 == 0) for n in range(50)] + [("b", n % 2 == 0) for n in range(50)]
    _, p_null = permutation_test(flat, rounds=1000, seed=1)
    assert p_null > 0.05


def test_detectable_effect_shrinks_as_the_sample_grows() -> None:
    small = minimum_detectable_effect(0.6, 50)
    large = minimum_detectable_effect(0.6, 400)

    assert small > large
    assert required_n(0.6, small) == pytest.approx(50, abs=2)


def test_spread_is_zero_when_every_group_performs_identically() -> None:
    assert spread([("a", True), ("a", False), ("b", True), ("b", False)]) == 0.0


def test_by_group_splits_on_a_metadata_field() -> None:
    pairs = [
        (
            Item(id="a", text="t", meta={"lang": "ur"}, predictions={"m": "p"}),
            Judgement(item_id="a", label="p"),
        ),
        (
            Item(id="b", text="t", meta={"lang": "en"}, predictions={"m": "p"}),
            Judgement(item_id="b", label="q"),
        ),
    ]

    cells = by_group(pairs, "m", "lang")

    assert cells == {"ur": (1, 1), "en": (0, 1)}


# --- switching pass without restarting --------------------------------------


def _session(tmp_path: Path, items: list[Item], **kwargs: object) -> Session:
    return Session(
        items=items,
        labels=load_labels(Path("config/taxonomy.yaml")),
        output=tmp_path / "out.jsonl",
        **kwargs,
    )


def test_switching_pass_rebuilds_the_worklist(tmp_path: Path) -> None:
    items = [_item("a", x="p", y="p"), _item("b", x="p", y="q")]
    session = _session(tmp_path, items)
    assert len(session.worklist) == 2

    session.set_pass("controls", None)

    assert [i.id for i in session.worklist] == ["a"], "controls are the agreed items"


def test_blindness_can_be_turned_off_mid_session_and_is_recorded(tmp_path: Path) -> None:
    session = _session(tmp_path, [_item("a", m="p")])

    session.set_pass(None, False)
    judgement = session.record({"item_id": "a", "label": "login_failure"})

    assert session.blind is False
    assert judgement.blind is False, "the regime must travel with the judgement"


def test_an_unknown_mode_is_ignored_rather_than_emptying_the_worklist(tmp_path: Path) -> None:
    session = _session(tmp_path, [_item("a"), _item("b")])

    session.set_pass("nonsense", None)

    assert session.mode == "all"
    assert len(session.worklist) == 2


def test_counts_report_every_pass_so_the_interface_can_offer_them(tmp_path: Path) -> None:
    items = [_item("a", x="p", y="p"), _item("b", x="p", y="q")]
    session = _session(tmp_path, items)

    counts = session.counts()

    assert counts["all"] == 2
    assert counts["controls"] == 1
    assert counts["recheck"] == 0, "nothing judged yet, so nothing to re-check"


def test_the_score_report_excludes_skipped_and_unblind_judgements(tmp_path: Path) -> None:
    items = [_item(k, x="p", y="p") for k in "abc"]
    session = _session(tmp_path, items)
    session.record({"item_id": "a", "label": "p"})
    session.record({"item_id": "b", "skipped": True})
    session.set_pass(None, False)
    session.record({"item_id": "c", "label": "p"})

    report = session.score(by=None)

    assert report["judged"] == 3
    assert report["scored"] == 1
    assert report["excluded"] == 2


def test_the_score_report_offers_only_fields_present_in_the_data(tmp_path: Path) -> None:
    items = [
        Item(id="a", text="t", meta={"language": "urdu"}, predictions={"m": "p"}),
        Item(id="b", text="t", meta={"language": "english"}, predictions={"m": "q"}),
    ]
    session = _session(tmp_path, items)
    session.record({"item_id": "a", "label": "p"})
    session.record({"item_id": "b", "label": "p"})

    report = session.score(by="language", rounds=200)

    assert report["fields"] == ["language"]
    assert report["groups"], "a two-group split should produce a breakdown"
    assert "mde" in report["groups"][0], "a null needs its detectable effect reported"
