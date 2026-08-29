"""Tests for loading and validating the Phase 3 human-authored taxonomy."""

from pathlib import Path

import pytest
from src.label.taxonomy import load_taxonomy

REGISTRY_PATH = Path("config/taxonomy.yaml")


def test_load_taxonomy_reads_current_config() -> None:
    taxonomy = load_taxonomy(REGISTRY_PATH)

    assert len(taxonomy.intents) == 26
    assert len({intent.id for intent in taxonomy.intents}) == 26
    assert taxonomy.languages == ["urdu_script", "roman_urdu", "english", "code_switched"]
    assert taxonomy.severities == [
        "financial_loss",
        "service_disruption",
        "friction",
        "informational",
    ]


def test_every_intent_has_definition_and_examples() -> None:
    taxonomy = load_taxonomy(REGISTRY_PATH)

    for intent in taxonomy.intents:
        assert intent.definition.strip()
        assert len(intent.positive_examples) == 2
        assert all(example.strip() for example in intent.positive_examples)
        assert intent.negative_example.strip()
        assert intent.negative_rationale.strip()


def test_every_intent_belongs_to_one_of_six_families() -> None:
    taxonomy = load_taxonomy(REGISTRY_PATH)

    families = {intent.family for intent in taxonomy.intents}
    assert families == {
        "billing_and_charges",
        "access_and_account",
        "money_movement",
        "fraud_and_safety",
        "network_and_service",
        "product_and_navigation",
    }


def test_load_taxonomy_rejects_duplicate_intent_ids(tmp_path: Path) -> None:
    path = tmp_path / "taxonomy.yaml"
    path.write_text(
        """
version: 1
intents:
  - id: dup
    family: billing_and_charges
    definition: one
    positive_examples: ["a", "b"]
    negative_example: "c"
    negative_rationale: "d"
  - id: dup
    family: billing_and_charges
    definition: one
    positive_examples: ["a", "b"]
    negative_example: "c"
    negative_rationale: "d"
languages: [english]
severities: [friction]
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Duplicate intent id"):
        load_taxonomy(path)


def test_load_taxonomy_rejects_wrong_example_count(tmp_path: Path) -> None:
    path = tmp_path / "taxonomy.yaml"
    path.write_text(
        """
version: 1
intents:
  - id: only_one_positive
    family: billing_and_charges
    definition: one
    positive_examples: ["a"]
    negative_example: "c"
    negative_rationale: "d"
languages: [english]
severities: [friction]
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="exactly 2 positive_examples"):
        load_taxonomy(path)
