"""Serve the adjudication interface on localhost.

Bound to 127.0.0.1 and nothing else. The material being judged is usually customer text;
the right place for it is the machine already holding it, and a tool whose safe choice is
also its default gets used correctly more often than one with a warning in its README.

The session holds every item and rebuilds its worklist on demand, so switching between
passes - all, controls, re-check, revisit - is a control in the interface rather than a
restart with different flags.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from src.adjudicate.items import Item, Judgement, load_judgements, write_judgements
from src.adjudicate.labels import LabelSet
from src.adjudicate.page import PAGE
from src.adjudicate.power import minimum_detectable_effect, permutation_test, required_n
from src.adjudicate.scoring import (
    accuracy,
    by_group,
    cohens_kappa,
    joint_error,
    usable,
    wilson,
)
from src.adjudicate.worklist import build_worklist, progress

NONE_LABEL = "__none__"
MODES = ("all", "controls", "recheck", "revisit")
DEFAULT_REASONS = (
    ("praise", "positive, no complaint to categorise"),
    ("vague", "unhappy, but names nothing specific"),
    ("unreadable", "fragment or nonsense"),
    ("uncovered", "a real, specific issue no label covers"),
)


@dataclass
class Session:
    """One adjudication session: every item, and the state of the current pass."""

    items: list[Item]
    labels: LabelSet
    output: Path
    mode: str = "all"
    blind: bool = True
    seed: int = 0
    limit: int | None = None
    title: str = ""
    reasons: tuple[tuple[str, str], ...] = DEFAULT_REASONS
    judgements: dict[str, Judgement] = field(default_factory=dict)
    worklist: list[Item] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Load judgements already on disk, then build the first worklist."""
        self.judgements = load_judgements(self.output)
        self.rebuild()

    def rebuild(self) -> None:
        """Recompute the worklist for the current mode."""
        self.worklist = build_worklist(
            self.items,
            self.judgements,
            mode=self.mode,
            limit=self.limit,
            seed=self.seed,
            label_version=self.labels.version,
        )

    def set_pass(self, mode: str | None, blind: bool | None) -> None:
        """Switch pass without restarting. Blindness applies from the next judgement."""
        if mode in MODES and mode != self.mode:
            self.mode = mode
            self.rebuild()
        if blind is not None:
            self.blind = blind

    def counts(self) -> dict[str, int]:
        """How many items each mode currently has, for the interface's mode menu."""
        out = {}
        for mode in MODES:
            out[mode] = len(
                build_worklist(
                    self.items,
                    self.judgements,
                    mode=mode,
                    seed=self.seed,
                    label_version=self.labels.version,
                )
            )
        return out

    def pending(self) -> list[Item]:
        """Items still needing a judgement in this pass."""
        if self.mode == "revisit":
            return [
                i
                for i in self.worklist
                if (j := self.judgements.get(i.id)) is None
                or j.label_version < self.labels.version
            ]
        return [i for i in self.worklist if i.id not in self.judgements]

    def record(self, payload: dict[str, Any]) -> Judgement:
        """Store one judgement, replacing any earlier one for the same item."""
        item_id = str(payload["item_id"])
        item = next((i for i in self.items if i.id == item_id), None)
        label = payload.get("label")
        secondary = payload.get("secondary") or None
        if secondary == label:
            secondary = None  # not a separate second matter
        judgement = Judgement(
            item_id=item_id,
            label=label,
            secondary=secondary,
            flags=payload.get("flags") or {},
            notes=payload.get("notes", ""),
            skipped=bool(payload.get("skipped")),
            blind=self.blind,
            label_version=self.labels.version,
            predictions=item.predictions if item else {},
        )
        self.judgements[item_id] = judgement
        write_judgements(self.output, self.judgements)
        return judgement

    def score(self, by: str | None, rounds: int = 4000) -> dict[str, Any]:
        """Everything the results view shows, computed from the judgements on disk."""
        pairs = usable(self.items, self.judgements)
        excluded = len(self.judgements) - len(pairs)
        models = sorted({m for i, _ in pairs for m in i.predictions})

        report: dict[str, Any] = {
            "items": len(self.items),
            "judged": len(self.judgements),
            "scored": len(pairs),
            "excluded": excluded,
            "models": [],
            "joint": None,
            "agreement": None,
            "groups": [],
            "by": by,
            "fields": sorted(
                {k for i in self.items for k, v in i.meta.items() if isinstance(v, str)}
            ),
        }
        if not pairs or not models:
            return report

        for model in models:
            hits, total = accuracy(pairs, model)
            report["models"].append(
                {"model": model, "hits": hits, "total": total, **_band(hits, total)}
            )

        wrong, controls = joint_error(pairs)
        if controls:
            report["joint"] = {"wrong": wrong, "total": controls, **_band(wrong, controls)}

        if len(models) > 1:
            both = [
                (i.predictions[models[0]], i.predictions[models[1]])
                for i, _ in pairs
                if i.predictions.get(models[0]) and i.predictions.get(models[1])
            ]
            same = sum(1 for a, b in both if a == b)
            report["agreement"] = {
                "pair": f"{models[0]} vs {models[1]}",
                "hits": same,
                "total": len(both),
                "kappa": round(cohens_kappa(both), 3) if both else None,
                **_band(same, len(both)),
            }

        if by:
            for model in models:
                cells = by_group(pairs, model, by)
                if len(cells) < 2:
                    continue
                outcomes = [
                    (str(i.meta.get(by)), i.predictions[model] == j.label)
                    for i, j in pairs
                    if i.predictions.get(model)
                ]
                observed, p = permutation_test(outcomes, rounds=rounds, seed=self.seed)
                smallest = min(total for _, total in cells.values())
                hits, total = accuracy(pairs, model)
                baseline = hits / total if total else 0.5
                mde = minimum_detectable_effect(baseline, smallest)
                report["groups"].append(
                    {
                        "model": model,
                        "cells": [
                            {"group": g, "hits": h, "total": t, **_band(h, t)}
                            for g, (h, t) in sorted(cells.items())
                        ],
                        "spread": round(observed * 100, 1),
                        "p": round(p, 3),
                        "mde": round(mde * 100, 1),
                        "needed": required_n(baseline, observed) if observed else None,
                        "significant": p < 0.05,
                    }
                )
        return report


def _band(hits: int, total: int) -> dict[str, float]:
    """Percentage and Wilson interval, rounded for display."""
    if total == 0:
        return {"pct": 0.0, "low": 0.0, "high": 0.0}
    low, high = wilson(hits, total)
    return {
        "pct": round(hits / total * 100, 1),
        "low": round(low * 100, 1),
        "high": round(high * 100, 1),
    }


class Handler(BaseHTTPRequestHandler):
    """Routes for the interface. One session per process."""

    session: Session

    def log_message(self, *_args: Any) -> None:
        """Silence per-request logging; the terminal belongs to the operator."""
        return

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: dict[str, Any]) -> None:
        self._send(
            200,
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def _state(self) -> dict[str, Any]:
        session = self.session
        done, total = progress(
            session.worklist, session.judgements, session.mode, session.labels.version
        )
        return {
            "mode": session.mode,
            "blind": session.blind,
            "done": done,
            "total": total,
            "counts": session.counts(),
        }

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        """Serve the page, its config, state, the next item, or the score report."""
        session = self.session
        parsed = urlparse(self.path)
        route = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)

        if route == "/":
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        elif route == "/config":
            self._json(
                {
                    "title": session.title,
                    "output": str(session.output),
                    "labelVersion": session.labels.version,
                    "ids": session.labels.ids,
                    "groups": {
                        group: [label.id for label in labels]
                        for group, labels in session.labels.grouped().items()
                    },
                    "defs": {
                        label.id: {
                            "definition": label.definition,
                            "positive_examples": list(label.positive_examples),
                            "negative_example": label.negative_example,
                            "negative_rationale": label.negative_rationale,
                        }
                        for label in session.labels.labels
                    },
                    "flags": list(session.labels.flags),
                    "reasons": [list(r) for r in session.reasons],
                    "modes": list(MODES),
                    **self._state(),
                }
            )
        elif route == "/next":
            pending = session.pending()
            item = (
                pending[0].public(reveal_predictions=not session.blind)
                if pending
                else None
            )
            self._json({"item": item, **self._state()})
        elif route == "/back":
            self._back(query)
        elif route == "/score":
            by = (query.get("by") or [None])[0]
            self._json(session.score(by or None))
        else:
            self._send(404, b"not found", "text/plain")

    def _back(self, query: dict[str, list[str]]) -> None:
        """Re-serve an already-judged item so a decision can be revised."""
        steps = max(1, int((query.get("steps") or ["1"])[0] or 1))
        judged = list(self.session.judgements.values())
        if steps > len(judged):
            self._json({"item": None, "steps": len(judged)})
            return
        previous = judged[-steps]
        item = next((i for i in self.session.items if i.id == previous.item_id), None)
        self._json(
            {
                "item": item.public(reveal_predictions=not self.session.blind)
                if item
                else None,
                "previous": previous.to_dict(),
                "steps": steps,
            }
        )

    def do_POST(self) -> None:  # noqa: N802 - stdlib naming
        """Record a judgement, or switch pass."""
        route = urlparse(self.path).path.rstrip("/") or "/"
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")

        if route == "/save":
            judgement = self.session.record(payload)
            # Suppressed in recheck: seeing the predictions again could cue the earlier
            # judgement, which is exactly what a blind retest has to avoid.
            show = self.session.mode != "recheck"
            self._json(
                {
                    "predictions": judgement.predictions if show else {},
                    **self._state(),
                }
            )
        elif route == "/pass":
            self.session.set_pass(payload.get("mode"), payload.get("blind"))
            self._json(self._state())
        else:
            self._send(404, b"not found", "text/plain")


def serve(session: Session, port: int = 8790) -> None:
    """Run until interrupted. Progress is written after every judgement."""
    Handler.session = session
    counts = session.counts()
    print(f"{session.title or session.output.name}")
    print(f"  labels   v{session.labels.version}, {len(session.labels.labels)} of them")
    print(f"  writing  {session.output}")
    print("  passes   " + ", ".join(f"{m} {n}" for m, n in counts.items()))
    print(f"\n  open  http://127.0.0.1:{port}\n\nCtrl-C to stop; progress is saved.")
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
