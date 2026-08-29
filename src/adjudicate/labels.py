"""The label set an annotator chooses from.

A label is more than an id. What makes a scheme usable is the boundary material: two
examples that belong, one that looks like it belongs and does not, and the reason why.
Those are what an annotator reads when two labels both seem to fit, and sending only
definitions to a model withholds the part that decides every hard case.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Label:
    """One category, with the material that marks its edges."""

    id: str
    group: str = ""
    definition: str = ""
    positive_examples: tuple[str, ...] = ()
    negative_example: str = ""
    negative_rationale: str = ""


@dataclass(frozen=True)
class LabelSet:
    """A versioned set of labels.

    The version is load-bearing: judgements record it, so changing the scheme reopens
    exactly the judgements it could have altered and leaves the rest alone.
    """

    version: int
    labels: tuple[Label, ...]
    flags: tuple[str, ...] = ()

    @property
    def ids(self) -> list[str]:
        """Label ids in declaration order."""
        return [label.id for label in self.labels]

    def grouped(self) -> dict[str, list[Label]]:
        """Labels by group, preserving declaration order."""
        out: dict[str, list[Label]] = {}
        for label in self.labels:
            out.setdefault(label.group or "labels", []).append(label)
        return out


def load_labels(path: Path) -> LabelSet:
    """Read a label set from YAML.

    Accepts `labels:` or `intents:`, and `group:` or `family:`, so a scheme written for
    one study loads without rewriting it.
    """
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw = payload.get("labels") or payload.get("intents") or []
    labels = []
    seen: set[str] = set()
    for entry in raw:
        identifier = str(entry.get("id", "")).strip()
        if not identifier:
            raise ValueError(f"label is missing an id: {entry}")
        if identifier in seen:
            raise ValueError(f"duplicate label id: {identifier}")
        seen.add(identifier)
        labels.append(
            Label(
                id=identifier,
                group=str(entry.get("group") or entry.get("family") or ""),
                definition=str(entry.get("definition", "")).strip(),
                positive_examples=tuple(entry.get("positive_examples") or ()),
                negative_example=str(entry.get("negative_example", "")),
                negative_rationale=str(entry.get("negative_rationale", "")).strip(),
            )
        )
    if not labels:
        raise ValueError(f"no labels found in {path}")
    return LabelSet(
        version=int(payload.get("version", 0)),
        labels=tuple(labels),
        flags=tuple(payload.get("flags") or ()),
    )
