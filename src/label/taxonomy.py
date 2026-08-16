"""Load and validate the Phase 3 human-authored taxonomy config."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

REQUIRED_INTENT_FIELDS = (
    "id",
    "family",
    "definition",
    "positive_examples",
    "negative_example",
    "negative_rationale",
)


@dataclass(frozen=True)
class Intent:
    """One taxonomy intent with its human-authored definition and examples."""

    id: str
    family: str
    definition: str
    positive_examples: list[str]
    negative_example: str
    negative_rationale: str


@dataclass(frozen=True)
class Taxonomy:
    """The full taxonomy: intents plus the orthogonal language/severity labels."""

    version: int
    intents: list[Intent]
    languages: list[str]
    severities: list[str]


def load_taxonomy(path: Path) -> Taxonomy:
    """Parse and validate the taxonomy config, raising on any structural defect."""
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw_intents = payload.get("intents", [])

    intents: list[Intent] = []
    seen_ids: set[str] = set()
    for raw in raw_intents:
        missing = [field for field in REQUIRED_INTENT_FIELDS if not raw.get(field)]
        if missing:
            raise ValueError(f"Intent {raw.get('id', '<unknown>')} missing fields: {missing}")

        intent_id = str(raw["id"])
        if intent_id in seen_ids:
            raise ValueError(f"Duplicate intent id: {intent_id}")
        seen_ids.add(intent_id)

        positive_examples = list(raw["positive_examples"])
        if len(positive_examples) != 2:
            raise ValueError(f"Intent {intent_id} must have exactly 2 positive_examples")

        intents.append(
            Intent(
                id=intent_id,
                family=str(raw["family"]),
                definition=str(raw["definition"]),
                positive_examples=positive_examples,
                negative_example=str(raw["negative_example"]),
                negative_rationale=str(raw["negative_rationale"]),
            )
        )

    return Taxonomy(
        version=int(payload.get("version", 0)),
        intents=intents,
        languages=list(payload.get("languages", [])),
        severities=list(payload.get("severities", [])),
    )
