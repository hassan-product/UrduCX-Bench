"""Tests for Phase 2/3 PII redaction, run before any text reaches an external API."""

import pytest
from src.prep.scrub_pii import load_jsonl, scrub_records, scrub_text, write_jsonl


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Contact me at ali.khan@example.com about this",
            "Contact me at <EMAIL> about this",
        ),
        (
            "My CNIC is 42101-1234567-1 for verification",
            "My CNIC is <CNIC> for verification",
        ),
        (
            "CNIC 4210112345671 sent to agent already",
            "CNIC <CNIC> sent to agent already",
        ),
        (
            "Call me on 03001234567 please",
            "Call me on <PHONE> please",
        ),
        (
            "Number is +923001234567 waiting for callback",
            "Number is <PHONE> waiting for callback",
        ),
        (
            "Try 0300-1234567 or 0300 1234567 both mine",
            "Try <PHONE> or <PHONE> both mine",
        ),
        (
            "Landline 021-1234567 also unreachable",
            "Landline <PHONE> also unreachable",
        ),
        (
            "Account number 123456789012 shows wrong balance",
            "Account number <ACCOUNT> shows wrong balance",
        ),
        (
            "Balance kat gaya, phone 03211234567 aur email ali@x.com dono",
            "Balance kat gaya, phone <PHONE> aur email <EMAIL> dono",
        ),
        (
            "بہت اچھا نہیں چل رہا 03001234567 پر رابطہ کریں",
            "بہت اچھا نہیں چل رہا <PHONE> پر رابطہ کریں",
        ),
        (
            "App bohat acha hai lekin balance nahi aya",
            "App bohat acha hai lekin balance nahi aya",
        ),
        (
            "Rating 10/10 and lost 5000 rupees today",
            "Rating 10/10 and lost 5000 rupees today",
        ),
    ],
)
def test_scrub_text_redacts_realistic_pii(text: str, expected: str) -> None:
    scrubbed, _ = scrub_text(text)
    assert scrubbed == expected


def test_scrub_text_counts_each_redaction_by_type() -> None:
    scrubbed, counts = scrub_text("Email ali@x.com or call 03001234567 or 03211234568")
    assert scrubbed == "Email <EMAIL> or call <PHONE> or <PHONE>"
    assert counts == {"email": 1, "phone": 2}


def test_scrub_text_no_pii_returns_empty_counts() -> None:
    scrubbed, counts = scrub_text("Network is slow in my area")
    assert scrubbed == "Network is slow in my area"
    assert counts == {}


def test_scrub_records_adds_text_scrubbed_and_preserves_other_fields() -> None:
    records = [
        {
            "review_id": "a",
            "product_id": "simosa",
            "text": "raw text unused here",
            "text_clean": "Call 03001234567 about balance",
        },
        {
            "review_id": "b",
            "product_id": "jazzcash",
            "text": "raw text unused here",
            "text_clean": "No PII in this one",
        },
    ]

    scrubbed, counts = scrub_records(records)

    assert scrubbed[0]["text_scrubbed"] == "Call <PHONE> about balance"
    assert scrubbed[0]["review_id"] == "a"
    assert scrubbed[0]["text_clean"] == "Call 03001234567 about balance"
    assert scrubbed[1]["text_scrubbed"] == "No PII in this one"
    assert counts == {"phone": 1}


def test_write_and_load_jsonl_roundtrip(tmp_path) -> None:
    path = tmp_path / "scrubbed.jsonl"
    records = [{"review_id": "a", "text_scrubbed": "hi"}]
    write_jsonl(path, records)
    assert load_jsonl(path) == records
