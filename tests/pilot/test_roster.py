"""Tests for the Phase 2.5 pilot model roster loader."""

from pathlib import Path

import pytest
import yaml
from src.pilot.roster import load_roster

VALID_ENTRY = {
    "id": "claude-haiku-4-5",
    "provider": "anthropic",
    "label": "Claude Haiku 4.5",
    "price_per_mtok_input": 1.0,
    "price_per_mtok_output": 5.0,
    "min_request_interval": 0.5,
}


def _write(tmp_path: Path, models: list[dict]) -> Path:
    path = tmp_path / "models.yaml"
    path.write_text(yaml.safe_dump({"version": 1, "models": models}), encoding="utf-8")
    return path


def test_loads_a_valid_roster(tmp_path: Path) -> None:
    models = load_roster(_write(tmp_path, [VALID_ENTRY]))
    assert len(models) == 1
    assert models[0].id == "claude-haiku-4-5"
    assert models[0].provider == "anthropic"
    assert models[0].effort is None


def test_effort_is_optional_and_preserved(tmp_path: Path) -> None:
    entry = VALID_ENTRY | {"id": "claude-opus-5", "effort": "low"}
    assert load_roster(_write(tmp_path, [entry]))[0].effort == "low"


def test_empty_roster_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="empty"):
        load_roster(_write(tmp_path, []))


def test_unsupported_provider_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsupported provider"):
        load_roster(_write(tmp_path, [VALID_ENTRY | {"provider": "acme"}]))


def test_duplicate_model_id_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Duplicate model id"):
        load_roster(_write(tmp_path, [VALID_ENTRY, VALID_ENTRY]))


def test_missing_required_field_is_rejected(tmp_path: Path) -> None:
    incomplete = {k: v for k, v in VALID_ENTRY.items() if k != "label"}
    with pytest.raises(ValueError, match="missing fields"):
        load_roster(_write(tmp_path, [incomplete]))


def test_spend_estimate_uses_configured_prices(tmp_path: Path) -> None:
    model = load_roster(_write(tmp_path, [VALID_ENTRY]))[0]
    # 1M input at $1 plus 1M output at $5.
    assert model.estimate_usd(1_000_000, 1_000_000) == pytest.approx(6.0)


def test_free_tier_model_estimates_zero_spend(tmp_path: Path) -> None:
    free = {
        "id": "gemini-2.5-flash",
        "provider": "google",
        "label": "Gemini 2.5 Flash",
        "price_per_mtok_input": 0.0,
        "price_per_mtok_output": 0.0,
    }
    assert load_roster(_write(tmp_path, [free]))[0].estimate_usd(500_000, 500_000) == 0.0


def test_repository_roster_is_valid() -> None:
    models = load_roster(Path("config/models.yaml"))
    assert models, "the committed pilot roster must not be empty"
    assert len({model.id for model in models}) == len(models)
