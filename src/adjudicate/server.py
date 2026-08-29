"""Serve the adjudication interface on localhost.

Bound to 127.0.0.1 and nothing else. The material being judged is customer text; the
correct place for it is the machine already holding it, and a tool that makes the safe
choice the default one is more use than a warning in a README.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from src.adjudicate.items import Item, Judgement, load_judgements, write_judgements
from src.adjudicate.labels import LabelSet
from src.adjudicate.page import PAGE
from src.adjudicate.worklist import progress

NONE_LABEL = "__none__"
DEFAULT_REASONS = (
    ("praise", "positive, no complaint to categorise"),
    ("vague", "unhappy, but names nothing specific"),
    ("unreadable", "fragment or nonsense"),
    ("uncovered", "a real, specific issue no label covers"),
)


@dataclass
class Session:
    """Everything one adjudication pass needs to know about itself."""

    worklist: list[Item]
    labels: LabelSet
    output: Path
    mode: str = "all"
    blind: bool = True
    title: str = "items"
    reasons: tuple[tuple[str, str], ...] = DEFAULT_REASONS
    judgements: dict[str, Judgement] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Load any judgements already on disk so a restart resumes."""
        self.judgements = load_judgements(self.output)

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
        item = next((i for i in self.worklist if i.id == item_id), None)
        label = payload.get("label")
        if label == NONE_LABEL:
            label = NONE_LABEL
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


class Handler(BaseHTTPRequestHandler):
    """Routes for the interface. One session per process."""

    session: Session

    def log_message(self, *_args: Any) -> None:
        """Silence per-request logging; the terminal is for the operator."""
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

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        """Serve the page, its config, the next item, or an earlier one."""
        session = self.session
        route = self.path.split("?", 1)[0].rstrip("/") or "/"

        if route == "/":
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        elif route == "/config":
            self._json(
                {
                    "mode": session.mode,
                    "title": session.title,
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
                }
            )
        elif route == "/next":
            pending = session.pending()
            done, total = progress(
                session.worklist, session.judgements, session.mode, session.labels.version
            )
            item = (
                pending[0].public(reveal_predictions=not session.blind)
                if pending
                else None
            )
            self._json({"item": item, "done": done, "total": total})
        elif route == "/back":
            self._back()
        else:
            self._send(404, b"not found", "text/plain")

    def _back(self) -> None:
        """Re-serve an already-judged item so a decision can be revised."""
        steps = 1
        if "?" in self.path:
            for part in self.path.split("?", 1)[1].split("&"):
                if part.startswith("steps="):
                    steps = max(1, int(part.split("=", 1)[1] or 1))
        judged = list(self.session.judgements.values())
        if steps > len(judged):
            self._json({"item": None, "steps": len(judged)})
            return
        previous = judged[-steps]
        item = next(
            (i for i in self.session.worklist if i.id == previous.item_id), None
        )
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
        """Record one judgement and return the predictions, if this pass reveals them."""
        if self.path.rstrip("/") != "/save":
            self._send(404, b"not found", "text/plain")
            return
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")
        judgement = self.session.record(payload)
        # Suppressed in recheck: seeing the predictions again could cue the earlier
        # judgement, which is exactly what a blind retest has to avoid.
        show = self.session.mode != "recheck"
        self._json({"predictions": judgement.predictions if show else {}})


def serve(session: Session, port: int = 8790) -> None:
    """Run until interrupted. Progress is written after every judgement."""
    Handler.session = session
    done, total = progress(
        session.worklist, session.judgements, session.mode, session.labels.version
    )
    print(f"{session.mode}: {total} items, {done} already judged")
    print(f"  labels   v{session.labels.version}, {len(session.labels.labels)} of them")
    print(f"  blind    {'yes' if session.blind else 'NO — predictions shown before choosing'}")
    print(f"  writing  {session.output}")
    print(f"\n  open  http://127.0.0.1:{port}\n\nCtrl-C to stop; progress is saved.")
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
