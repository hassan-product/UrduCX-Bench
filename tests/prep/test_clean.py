"""Tests for Phase 2 text cleaning, product remapping, and deduplication."""

from pathlib import Path

from src.prep.clean import (
    clean_records,
    detect_language,
    drop_reason,
    load_product_map,
    normalise_text,
    remap_product_id,
    word_count,
)


def test_normalise_text_strips_markup_and_collapses_whitespace() -> None:
    raw = "  Balance <b>kat</b>   gaya\nphir se  "
    assert normalise_text(raw) == "Balance kat gaya phir se"


def test_drop_reason_rejects_empty_emoji_and_short_text() -> None:
    assert drop_reason("") == "empty"
    assert drop_reason("🔥🔥🔥") == "emoji_only"
    assert drop_reason("bohat acha") == "too_short"
    assert drop_reason("bohat acha nahi laga") is None
    assert drop_reason("بہت اچھا نہیں") is None


def test_word_count_counts_urdu_and_latin_tokens() -> None:
    assert word_count("JazzCash app hang") == 3
    assert word_count("بہت اچھا نہیں") == 3


def test_detect_language_handles_script_and_register() -> None:
    assert detect_language("بہت اچھا نہیں چل رہا") == "urdu_script"
    assert detect_language("app bohat acha hai lekin balance nahi aya") == "roman_urdu"
    assert detect_language("The application keeps crashing after login") == "english"
    assert detect_language("App بند ہو گیا hai") == "code_switched"


def test_remap_product_id_uses_registry_not_stored_name() -> None:
    product_map = {("google_play", "com.zong.customercare"): "my_zong"}
    record = {
        "platform": "google_play",
        "platform_app_id": "com.zong.customercare",
        "product_id": "zong",
    }
    assert remap_product_id(record, product_map) == "my_zong"


def test_clean_records_dedupes_id_then_normalised_text() -> None:
    product_map = {("google_play", "com.jazz.jazzworld"): "simosa"}
    records = [
        {
            "review_id": "a",
            "platform": "google_play",
            "platform_app_id": "com.jazz.jazzworld",
            "product_id": "simosa",
            "text": "App hang ho gaya hai",
            "rating": 1,
            "timestamp": "2026-01-01",
            "app_version": "1.0",
            "helpful_count": 0,
        },
        {
            "review_id": "a",
            "platform": "google_play",
            "platform_app_id": "com.jazz.jazzworld",
            "product_id": "simosa",
            "text": "App hang ho gaya hai",
            "rating": 1,
            "timestamp": "2026-01-01",
            "app_version": "1.0",
            "helpful_count": 0,
        },
        {
            "review_id": "b",
            "platform": "google_play",
            "platform_app_id": "com.jazz.jazzworld",
            "product_id": "simosa",
            "text": "  App   hang ho gaya hai ",
            "rating": 2,
            "timestamp": "2026-01-02",
            "app_version": "1.0",
            "helpful_count": 0,
        },
        {
            "review_id": "c",
            "platform": "google_play",
            "platform_app_id": "com.jazz.jazzworld",
            "product_id": "simosa",
            "text": "Balance check nahi ho raha",
            "rating": 1,
            "timestamp": "2026-01-03",
            "app_version": "1.0",
            "helpful_count": 0,
        },
    ]

    kept, drops = clean_records(records, product_map)

    assert [row["review_id"] for row in kept] == ["a", "c"]
    assert drops["duplicate_id"] == 1
    assert drops["duplicate_text"] == 1
    assert kept[0]["text_clean"] == "App hang ho gaya hai"
    assert "text_hash" in kept[0]
    assert kept[0]["language"] == "roman_urdu"


def test_load_product_map_reads_current_registry() -> None:
    mapping = load_product_map(Path("config/source_registry.yaml"))
    assert mapping[("google_play", "com.zong.customercare")] == "my_zong"
    assert mapping[("google_play", "com.ufoneselfcare")] == "uptcl"
