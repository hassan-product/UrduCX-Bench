"""Tests for the Phase 2.5 script-gap pilot runner.

No test performs a network call. Model replies are injected through fake create
functions so cache, retry, scoring, and reporting behaviour can be exercised offline.
"""

from pathlib import Path

import pytest
from src.label.taxonomy import Intent, Taxonomy
from src.pilot.roster import ModelSpec
from src.pilot.run_pilot import (
    MAX_ATTEMPTS,
    ModelReply,
    RunTotals,
    _percent,
    build_classification_prompt,
    cache_key,
    call_with_retry,
    load_cached,
    parse_intent,
    render_report,
    run_model,
    score,
    write_cached,
)

VALID_INTENTS = {"otp_not_received", "refund_request", "login_failure"}


def _taxonomy() -> Taxonomy:
    intents = [
        Intent(
            id=intent_id,
            family="test",
            definition=f"Definition for {intent_id}.",
            positive_examples=["a", "b"],
            negative_example="c",
            negative_rationale="d",
        )
        for intent_id in sorted(VALID_INTENTS)
    ]
    return Taxonomy(version=1, intents=intents, languages=[], severities=[])


def _model(**overrides) -> ModelSpec:
    defaults = {
        "id": "test-model",
        "provider": "anthropic",
        "label": "Test Model",
        "price_per_mtok_input": 1.0,
        "price_per_mtok_output": 5.0,
        "min_request_interval": 0.0,
        "effort": None,
        "disable_thinking": False,
    }
    return ModelSpec(**(defaults | overrides))


def _complaint(complaint_id: str, gold: str) -> dict:
    return {
        "complaint_id": complaint_id,
        "gold_intent": gold,
        "variants": {
            language: {"text": f"{complaint_id}-{language}", "fact_span": "x"}
            for language in ("urdu_script", "roman_urdu", "code_switched", "english")
        },
    }


# --- prompt ---------------------------------------------------------------


def test_prompt_lists_every_taxonomy_intent_and_demands_a_bare_id() -> None:
    prompt = build_classification_prompt(_taxonomy())
    for intent_id in VALID_INTENTS:
        assert intent_id in prompt
    assert "exactly one intent id" in prompt


# --- reply parsing --------------------------------------------------------


@pytest.mark.parametrize(
    "reply",
    ["otp_not_received", "  otp_not_received  ", "`otp_not_received`", "otp_not_received."],
)
def test_parses_a_bare_intent_id_despite_surrounding_punctuation(reply: str) -> None:
    assert parse_intent(reply, VALID_INTENTS) == "otp_not_received"


def test_parses_an_intent_id_wrapped_in_a_sentence() -> None:
    reply = "The best match is refund_request for this complaint."
    assert parse_intent(reply, VALID_INTENTS) == "refund_request"


def test_unknown_intent_returns_none() -> None:
    assert parse_intent("billing_problem", VALID_INTENTS) is None


def test_ambiguous_reply_naming_two_intents_returns_none() -> None:
    reply = "Could be refund_request or login_failure."
    assert parse_intent(reply, VALID_INTENTS) is None


def test_empty_reply_returns_none() -> None:
    assert parse_intent("", VALID_INTENTS) is None


# --- cache identity -------------------------------------------------------


def test_cache_key_is_stable_for_identical_inputs() -> None:
    model = _model()
    assert cache_key(model, "text", taxonomy_version=1) == cache_key(
        model, "text", taxonomy_version=1
    )


def test_cache_key_changes_with_text_model_and_taxonomy_version() -> None:
    base = cache_key(_model(), "text", taxonomy_version=1)
    assert cache_key(_model(), "other", taxonomy_version=1) != base
    assert cache_key(_model(id="another"), "text", taxonomy_version=1) != base
    assert cache_key(_model(), "text", taxonomy_version=2) != base


def test_cache_roundtrip_preserves_reply_and_token_counts(tmp_path: Path) -> None:
    reply = ModelReply(text="refund_request", input_tokens=11, output_tokens=3)
    write_cached(tmp_path, "abc", reply)
    assert load_cached(tmp_path, "abc") == reply


def test_cache_miss_returns_none(tmp_path: Path) -> None:
    assert load_cached(tmp_path, "missing") is None


# --- retry ----------------------------------------------------------------


def test_retries_a_transient_failure_then_succeeds() -> None:
    attempts = {"n": 0}

    def create(system: str, text: str) -> ModelReply:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("temporary")
        return ModelReply(text="refund_request", input_tokens=1, output_tokens=1)

    reply = call_with_retry(create, "sys", "text", sleep_fn=lambda _: None)
    assert reply.text == "refund_request"
    assert attempts["n"] == 3


def test_raises_after_exhausting_attempts() -> None:
    def always_fail(system: str, text: str) -> ModelReply:
        raise RuntimeError("down")

    with pytest.raises(RuntimeError, match=f"All {MAX_ATTEMPTS} attempts failed"):
        call_with_retry(always_fail, "sys", "text", sleep_fn=lambda _: None)


def test_backoff_outlasts_a_forty_second_quota_pause() -> None:
    """Google's free tier answers a quota 429 with a ~40s retry hint."""
    waits: list[float] = []

    def always_fail(system: str, text: str) -> ModelReply:
        raise RuntimeError("429 quota")

    with pytest.raises(RuntimeError):
        call_with_retry(always_fail, "sys", "text", sleep_fn=waits.append)
    assert sum(waits) > 40.0, f"total backoff {sum(waits)}s must outlast a 40s pause"


# --- run loop -------------------------------------------------------------


def test_scores_each_variant_against_its_gold_intent(tmp_path: Path) -> None:
    complaints = [_complaint("pilot-01", "refund_request")]
    totals = RunTotals()
    rows = run_model(
        _model(),
        complaints,
        system="sys",
        valid_intents=VALID_INTENTS,
        taxonomy_version=1,
        cache_dir=tmp_path,
        totals=totals,
        create_fn=lambda s, t: ModelReply("refund_request", 10, 2),
        sleep_fn=lambda _: None,
    )
    assert len(rows) == 4
    assert all(row["correct"] for row in rows)
    assert totals.live_calls == 4
    assert totals.spend_usd == pytest.approx(4 * (10 / 1e6 * 1.0 + 2 / 1e6 * 5.0))


def test_a_wrong_prediction_is_recorded_as_incorrect(tmp_path: Path) -> None:
    rows = run_model(
        _model(),
        [_complaint("pilot-01", "refund_request")],
        system="sys",
        valid_intents=VALID_INTENTS,
        taxonomy_version=1,
        cache_dir=tmp_path,
        totals=RunTotals(),
        create_fn=lambda s, t: ModelReply("login_failure", 10, 2),
        sleep_fn=lambda _: None,
    )
    assert not any(row["correct"] for row in rows)
    assert {row["predicted_intent"] for row in rows} == {"login_failure"}


def test_second_run_is_served_entirely_from_cache(tmp_path: Path) -> None:
    complaints = [_complaint("pilot-01", "refund_request")]
    kwargs = {
        "system": "sys",
        "valid_intents": VALID_INTENTS,
        "taxonomy_version": 1,
        "cache_dir": tmp_path,
        "sleep_fn": lambda _: None,
    }
    first = RunTotals()
    run_model(
        _model(),
        complaints,
        totals=first,
        create_fn=lambda s, t: ModelReply("refund_request", 10, 2),
        **kwargs,
    )
    assert first.live_calls == 4

    def must_not_be_called(system: str, text: str) -> ModelReply:
        raise AssertionError("cached run must not call the model")

    second = RunTotals()
    rows = run_model(_model(), complaints, totals=second, create_fn=must_not_be_called, **kwargs)
    assert second.live_calls == 0
    assert second.cache_hits == 4
    assert second.spend_usd == 0.0
    assert all(row["correct"] for row in rows)


def test_unparseable_reply_is_flagged_and_counts_as_incorrect(tmp_path: Path) -> None:
    rows = run_model(
        _model(),
        [_complaint("pilot-01", "refund_request")],
        system="sys",
        valid_intents=VALID_INTENTS,
        taxonomy_version=1,
        cache_dir=tmp_path,
        totals=RunTotals(),
        create_fn=lambda s, t: ModelReply("I am not sure", 10, 2),
        sleep_fn=lambda _: None,
    )
    assert all(row["status"] == "unparseable" for row in rows)
    assert not any(row["correct"] for row in rows)


def test_persistent_failure_is_recorded_without_aborting_the_run(tmp_path: Path) -> None:
    def always_fail(system: str, text: str) -> ModelReply:
        raise RuntimeError("down")

    totals = RunTotals()
    rows = run_model(
        _model(),
        [_complaint("pilot-01", "refund_request")],
        system="sys",
        valid_intents=VALID_INTENTS,
        taxonomy_version=1,
        cache_dir=tmp_path,
        totals=totals,
        create_fn=always_fail,
        sleep_fn=lambda _: None,
    )
    assert len(rows) == 4
    assert totals.errors == 4
    assert all(row["status"] == "error" for row in rows)


def test_limit_truncates_to_the_first_n_complaints(tmp_path: Path) -> None:
    complaints = [_complaint(f"pilot-{i:02d}", "refund_request") for i in range(1, 6)]
    rows = run_model(
        _model(),
        complaints,
        system="sys",
        valid_intents=VALID_INTENTS,
        taxonomy_version=1,
        cache_dir=tmp_path,
        totals=RunTotals(),
        create_fn=lambda s, t: ModelReply("refund_request", 1, 1),
        sleep_fn=lambda _: None,
        limit=2,
    )
    assert {row["complaint_id"] for row in rows} == {"pilot-01", "pilot-02"}


# --- scoring and reporting -------------------------------------------------


def test_score_aggregates_by_model_and_language() -> None:
    rows = [
        {"model": "m", "language": "roman_urdu", "correct": True, "status": "ok"},
        {"model": "m", "language": "roman_urdu", "correct": False, "status": "ok"},
        {"model": "m", "language": "english", "correct": True, "status": "ok"},
    ]
    table = score(rows)
    assert table["m"]["roman_urdu"] == {"correct": 1, "answered": 2, "errors": 0}
    assert table["m"]["english"] == {"correct": 1, "answered": 1, "errors": 0}


def test_unanswered_calls_are_excluded_from_accuracy_not_counted_as_wrong() -> None:
    """A rate-limited run must not masquerade as a low score."""
    rows = [
        {"model": "m", "language": "roman_urdu", "correct": True, "status": "ok"},
        {"model": "m", "language": "roman_urdu", "correct": False, "status": "error"},
        {"model": "m", "language": "roman_urdu", "correct": False, "status": "error"},
    ]
    cell = score(rows)["m"]["roman_urdu"]
    assert cell == {"correct": 1, "answered": 1, "errors": 2}
    # 1/1 answered correctly is 100%, not 1/3 = 33%.
    assert _percent(score(rows)["m"], "roman_urdu") == pytest.approx(100.0)


def test_unparseable_replies_still_count_against_accuracy() -> None:
    """Unlike a failed call, a real reply with no valid intent is a genuine miss."""
    rows = [
        {"model": "m", "language": "english", "correct": True, "status": "ok"},
        {"model": "m", "language": "english", "correct": False, "status": "unparseable"},
    ]
    assert score(rows)["m"]["english"] == {"correct": 1, "answered": 2, "errors": 0}


def test_report_shows_a_positive_gap_when_roman_urdu_lags() -> None:
    rows = [
        {"model": "test-model", "language": "roman_urdu", "correct": False, "status": "ok"},
        {"model": "test-model", "language": "english", "correct": True, "status": "ok"},
        {"model": "test-model", "language": "urdu_script", "correct": True, "status": "ok"},
        {"model": "test-model", "language": "code_switched", "correct": True, "status": "ok"},
    ]
    report = render_report(rows, [_model()], RunTotals())
    assert "+100 pts" in report
    assert "Gap against natural Roman Urdu" in report
