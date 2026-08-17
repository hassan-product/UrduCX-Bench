"""Tests for the Phase 3 auto-labelling pipeline (cached, resumable, spend-logged)."""

from __future__ import annotations

import json

import httpx
import pytest
from anthropic import RateLimitError
from src.label.auto_label import (
    RequestPacer,
    build_system_prompt,
    call_model,
    content_hash,
    estimate_spend_usd,
    label_records,
    load_cached_label,
    parse_label_response,
    write_cached_label,
)
from src.label.taxonomy import Intent, Taxonomy

VALID_LABEL_JSON = json.dumps(
    {
        "intent": "otp_not_received",
        "language": "roman_urdu",
        "severity": "friction",
        "confidence": 0.9,
        "rationale": "User reports the OTP never arrived after multiple attempts.",
    }
)


def _taxonomy() -> Taxonomy:
    return Taxonomy(
        version=1,
        intents=[
            Intent(
                id="otp_not_received",
                family="access_and_account",
                definition="User never received a login/verification OTP.",
                positive_examples=["a", "b"],
                negative_example="c",
                negative_rationale="d",
            ),
            Intent(
                id="login_failure",
                family="access_and_account",
                definition="User cannot log in despite correct credentials.",
                positive_examples=["e", "f"],
                negative_example="g",
                negative_rationale="h",
            ),
        ],
        languages=["urdu_script", "roman_urdu", "english", "code_switched"],
        severities=["financial_loss", "service_disruption", "friction", "informational"],
    )


class _FakeTextBlock:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _FakeUsage:
    def __init__(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _FakeResponse:
    def __init__(self, text: str, input_tokens: int = 120, output_tokens: int = 40) -> None:
        self.content = [_FakeTextBlock(text)]
        self.usage = _FakeUsage(input_tokens, output_tokens)


def _rate_limit_error() -> RateLimitError:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(429, request=request)
    return RateLimitError("rate limited", response=response, body=None)


def test_content_hash_is_deterministic_and_sensitive_to_text() -> None:
    assert content_hash("hello") == content_hash("hello")
    assert content_hash("hello") != content_hash("world")


def test_build_system_prompt_includes_all_intents_and_label_sets() -> None:
    prompt = build_system_prompt(_taxonomy())
    assert "otp_not_received" in prompt
    assert "login_failure" in prompt
    assert "roman_urdu" in prompt
    assert "friction" in prompt


def test_parse_label_response_returns_typed_fields() -> None:
    label = parse_label_response(VALID_LABEL_JSON)
    assert label == {
        "intent": "otp_not_received",
        "language": "roman_urdu",
        "severity": "friction",
        "confidence": 0.9,
        "rationale": "User reports the OTP never arrived after multiple attempts.",
    }


def test_parse_label_response_missing_field_raises() -> None:
    incomplete = json.dumps({"intent": "otp_not_received", "language": "roman_urdu"})
    with pytest.raises(ValueError, match="missing fields"):
        parse_label_response(incomplete)


def test_call_model_happy_path_returns_label_and_token_usage() -> None:
    def create_fn(**_kwargs: object) -> _FakeResponse:
        return _FakeResponse(VALID_LABEL_JSON)

    label, input_tokens, output_tokens = call_model(
        create_fn, model="claude-haiku-4-5", system_prompt="sys", review_text="Call 03001234567"
    )
    assert label["intent"] == "otp_not_received"
    assert input_tokens == 120
    assert output_tokens == 40


def test_call_model_retries_on_rate_limit_then_succeeds() -> None:
    calls = {"count": 0}
    sleeps: list[float] = []

    def create_fn(**_kwargs: object) -> _FakeResponse:
        calls["count"] += 1
        if calls["count"] < 3:
            raise _rate_limit_error()
        return _FakeResponse(VALID_LABEL_JSON)

    label, _, _ = call_model(
        create_fn,
        model="claude-haiku-4-5",
        system_prompt="sys",
        review_text="text",
        sleep_fn=sleeps.append,
    )
    assert label["intent"] == "otp_not_received"
    assert calls["count"] == 3
    assert len(sleeps) == 2  # slept before attempt 2 and attempt 3, no sleep needed


def test_call_model_raises_after_max_attempts() -> None:
    def create_fn(**_kwargs: object) -> _FakeResponse:
        raise _rate_limit_error()

    with pytest.raises(RuntimeError, match="failed after"):
        call_model(
            create_fn,
            model="claude-haiku-4-5",
            system_prompt="sys",
            review_text="text",
            sleep_fn=lambda _seconds: None,
        )


def test_cached_label_roundtrip(tmp_path) -> None:
    key = content_hash("some scrubbed text")
    payload = {
        "intent": "otp_not_received",
        "language": "roman_urdu",
        "severity": "friction",
        "confidence": 0.8,
        "rationale": "one sentence",
    }
    assert load_cached_label(tmp_path, key) is None
    write_cached_label(tmp_path, key, payload)
    assert load_cached_label(tmp_path, key) == payload


def test_label_records_uses_cache_and_skips_live_call(tmp_path) -> None:
    text = "Call 03001234567 about my OTP"
    key = content_hash(text)
    write_cached_label(
        tmp_path,
        key,
        {
            "intent": "otp_not_received",
            "language": "roman_urdu",
            "severity": "friction",
            "confidence": 0.85,
            "rationale": "cached rationale",
        },
    )

    def create_fn(**_kwargs: object) -> _FakeResponse:
        raise AssertionError("live call should not happen on a cache hit")

    labeled, spend = label_records(
        [{"review_id": "a", "text_scrubbed": text}],
        create_fn=create_fn,
        model="claude-haiku-4-5",
        taxonomy=_taxonomy(),
        cache_dir=tmp_path,
        pacer=RequestPacer(0.0, sleep_fn=lambda _seconds: None),
    )

    assert spend == {"input_tokens": 0, "output_tokens": 0, "cache_hits": 1, "live_calls": 0}
    assert labeled[0]["label_intent"] == "otp_not_received"
    assert labeled[0]["label_rationale"] == "cached rationale"
    assert labeled[0]["review_id"] == "a"


def test_label_records_calls_live_writes_cache_and_updates_spend(tmp_path) -> None:
    def create_fn(**_kwargs: object) -> _FakeResponse:
        return _FakeResponse(VALID_LABEL_JSON)

    labeled, spend = label_records(
        [{"review_id": "b", "text_scrubbed": "No PII here, app is slow"}],
        create_fn=create_fn,
        model="claude-haiku-4-5",
        taxonomy=_taxonomy(),
        cache_dir=tmp_path,
        pacer=RequestPacer(0.0, sleep_fn=lambda _seconds: None),
    )

    assert spend == {"input_tokens": 120, "output_tokens": 40, "cache_hits": 0, "live_calls": 1}
    assert labeled[0]["label_intent"] == "otp_not_received"
    key = content_hash("No PII here, app is slow")
    assert load_cached_label(tmp_path, key) is not None


def test_label_records_respects_limit(tmp_path) -> None:
    def create_fn(**_kwargs: object) -> _FakeResponse:
        return _FakeResponse(VALID_LABEL_JSON)

    records = [{"review_id": str(i), "text_scrubbed": f"text {i}"} for i in range(5)]
    labeled, spend = label_records(
        records,
        create_fn=create_fn,
        model="claude-haiku-4-5",
        taxonomy=_taxonomy(),
        cache_dir=tmp_path,
        pacer=RequestPacer(0.0, sleep_fn=lambda _seconds: None),
        limit=2,
    )

    assert len(labeled) == 2
    assert spend["live_calls"] == 2


def test_estimate_spend_usd_computes_expected_cost() -> None:
    spend = {"input_tokens": 1_000_000, "output_tokens": 500_000, "cache_hits": 0, "live_calls": 1}
    assert estimate_spend_usd(spend) == pytest.approx(1.0 + 2.5)
