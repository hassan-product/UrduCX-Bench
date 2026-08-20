"""Tests for the private Phase 2.5 human-authoring contract."""

import pytest
from src.pilot.authoring import (
    COMPLAINT_COUNT,
    LANGUAGE_FORMS,
    build_template,
    validate_pilot,
    write_template,
)

VALID_INTENTS = {
    "unauthorized_vas_deduction",
    "transfer_failed_money_deducted",
    "otp_not_received",
    "account_blocked_frozen",
    "service_outage_report",
    "information_request",
}
REQUIRED_INTENTS = (
    "unauthorized_vas_deduction",
    "transfer_failed_money_deducted",
    "otp_not_received",
    "account_blocked_frozen",
    "service_outage_report",
)


def _complete_payload() -> dict:
    payload = build_template()
    for index, complaint in enumerate(payload["complaints"]):
        complaint["gold_intent"] = (
            REQUIRED_INTENTS[index] if index < len(REQUIRED_INTENTS) else "information_request"
        )
        for language in LANGUAGE_FORMS:
            fact = f"REF-{index:02d}"
            complaint["variants"][language] = {
                "text": f"Human-authored {language} complaint with {fact}",
                "fact_span": fact,
            }
    return payload


def test_template_has_twenty_blank_slots_and_four_language_forms() -> None:
    payload = build_template()

    assert len(payload["complaints"]) == COMPLAINT_COUNT
    assert all(
        set(complaint["variants"]) == set(LANGUAGE_FORMS)
        for complaint in payload["complaints"]
    )
    assert all(not complaint["gold_intent"] for complaint in payload["complaints"])


def test_validate_pilot_accepts_complete_human_authored_payload() -> None:
    validate_pilot(_complete_payload(), valid_intents=VALID_INTENTS)


@pytest.mark.parametrize("language", LANGUAGE_FORMS)
def test_validate_pilot_rejects_missing_or_unanchored_fact(language: str) -> None:
    payload = _complete_payload()
    payload["complaints"][0]["variants"][language]["fact_span"] = "not in text"

    with pytest.raises(ValueError, match="fact_span must occur exactly in text"):
        validate_pilot(payload, valid_intents=VALID_INTENTS)


def test_validate_pilot_rejects_unknown_intent() -> None:
    payload = _complete_payload()
    payload["complaints"][0]["gold_intent"] = "unknown"

    with pytest.raises(ValueError, match="invalid gold_intent"):
        validate_pilot(payload, valid_intents=VALID_INTENTS)


def test_validate_pilot_rejects_missing_required_scenario_group() -> None:
    payload = _complete_payload()
    for complaint in payload["complaints"]:
        if complaint["gold_intent"] == "service_outage_report":
            complaint["gold_intent"] = "information_request"

    with pytest.raises(ValueError, match="network/service complaint"):
        validate_pilot(payload, valid_intents=VALID_INTENTS)


def test_write_template_does_not_overwrite_human_work(tmp_path) -> None:
    path = tmp_path / "complaints.json"
    write_template(path)
    original = path.read_text(encoding="utf-8")

    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        write_template(path)

    assert path.read_text(encoding="utf-8") == original