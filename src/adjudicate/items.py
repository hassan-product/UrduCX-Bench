"""Item and judgement records, and the readers for their files.

An item is one thing to be judged: an id, the text, arbitrary metadata, and whatever
predictions already exist for it. Predictions are optional - a dataset with none is a
plain annotation job, and the same tooling handles it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Item:
    """One unit of work: text to be judged, plus whatever is known about it."""

    id: str
    text: str
    meta: dict[str, Any] = field(default_factory=dict)
    predictions: dict[str, str] = field(default_factory=dict)

    @property
    def models_agree(self) -> bool:
        """True when every model that answered gave the same label."""
        answered = {label for label in self.predictions.values() if label}
        return len(answered) == 1

    @property
    def is_control(self) -> bool:
        """A control is an item the models already agree on.

        Judging these is how joint error becomes visible. Where two models agree,
        inter-model agreement can never reveal that both are wrong; only a human can.
        """
        return len(self.predictions) > 1 and self.models_agree

    def public(self, *, reveal_predictions: bool) -> dict[str, Any]:
        """The payload sent to the browser.

        Predictions are omitted unless explicitly revealed. Omitted, not hidden: a value
        present in the response is discoverable whatever the interface does with it.
        """
        payload: dict[str, Any] = {"id": self.id, "text": self.text, "meta": self.meta}
        if reveal_predictions:
            payload["predictions"] = self.predictions
        return payload


@dataclass(frozen=True)
class Judgement:
    """One human decision, with the conditions under which it was made."""

    item_id: str
    label: str | None
    secondary: str | None = None
    flags: dict[str, bool] = field(default_factory=dict)
    notes: str = ""
    skipped: bool = False
    blind: bool = True
    label_version: int = 0
    predictions: dict[str, str] = field(default_factory=dict)

    @property
    def usable(self) -> bool:
        """Whether this judgement can be scored.

        A skipped item is an unanswered question, not a wrong answer. Counting it in a
        denominator scores the models as having failed on something nobody assessed.
        """
        return not self.skipped and bool(self.label)

    def to_dict(self) -> dict[str, Any]:
        """Serialise for the judgements file."""
        return {
            "item_id": self.item_id,
            "label": self.label,
            "secondary": self.secondary,
            "flags": self.flags,
            "notes": self.notes,
            "skipped": self.skipped,
            "blind": self.blind,
            "label_version": self.label_version,
            "predictions": self.predictions,
        }


def _rows(path: Path) -> list[dict[str, Any]]:
    """Read a JSONL file, ignoring blank lines."""
    if not path.exists():
        return []
    return [
        json.loads(line) for line in path.open(encoding="utf-8") if line.strip()
    ]


def load_items(path: Path) -> list[Item]:
    """Load items, accepting `id` or `review_id` and `text` or `text_scrubbed`."""
    items: list[Item] = []
    for row in _rows(path):
        identifier = row.get("id") or row.get("review_id")
        text = row.get("text") or row.get("text_scrubbed") or row.get("text_clean") or ""
        if not identifier:
            raise ValueError(f"item is missing an id: {row}")
        known = {"id", "review_id", "text", "text_scrubbed", "text_clean", "predictions",
                 "models", "meta"}
        meta = row.get("meta") or {k: v for k, v in row.items() if k not in known}
        raw = row.get("predictions") or row.get("models") or {}
        predictions = {
            model: (value.get("intent") if isinstance(value, dict) else value)
            for model, value in raw.items()
        }
        items.append(
            Item(
                id=str(identifier),
                text=str(text),
                meta=meta,
                predictions={m: v for m, v in predictions.items() if v},
            )
        )
    return items


def load_judgements(path: Path) -> dict[str, Judgement]:
    """Load judgements keyed by item id. Later records replace earlier ones."""
    out: dict[str, Judgement] = {}
    for row in _rows(path):
        item_id = str(row.get("item_id") or row.get("review_id"))
        out[item_id] = Judgement(
            item_id=item_id,
            label=row.get("label") or row.get("human_intent"),
            secondary=row.get("secondary") or row.get("human_intent_secondary"),
            flags=row.get("flags") or {},
            notes=row.get("notes", ""),
            skipped=bool(row.get("skipped")),
            blind=bool(row.get("blind", True)),
            label_version=int(row.get("label_version", row.get("taxonomy_version", 0))),
            predictions=row.get("predictions") or row.get("models") or {},
        )
    return out


def write_judgements(path: Path, judgements: dict[str, Judgement]) -> None:
    """Rewrite the judgements file.

    Replacing rather than appending is what makes re-judging safe: an item judged twice
    leaves one record, so no analysis can count it twice with contradictory answers.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(j.to_dict(), ensure_ascii=False) + "\n"
            for j in judgements.values()
        ),
        encoding="utf-8",
    )
