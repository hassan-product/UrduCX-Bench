"""Serve the corpus explorer on localhost.

Bound to 127.0.0.1 and makes no outbound connections. The corpus is public review text,
but reading it and republishing it are different acts, and the tool keeps the second one
a deliberate choice rather than a side effect of opening a browser.

Export writes a JSONL in the shape the adjudication harness reads, so a filtered slice
becomes a judging queue without an intermediate step. That is the loop worth closing:
find the reviews worth looking at, then look at them properly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from src.explore import aggregate, keywords
from src.explore.corpus import Corpus, Filters, Review
from src.explore.page import PAGE

PAGE_SIZE = 40


def _ints(values: list[str]) -> set[int]:
    """Parse repeated query values into ints, ignoring anything unparseable."""
    out = set()
    for value in values:
        for part in value.split(","):
            if part.strip().isdigit():
                out.add(int(part))
    return out


def _strs(values: list[str]) -> set[str]:
    """Parse repeated query values into a set of strings."""
    return {p.strip() for v in values for p in v.split(",") if p.strip()}


def filters_from_query(query: dict[str, list[str]]) -> Filters:
    """Build a filter set from the URL query."""
    return Filters(
        platforms=_strs(query.get("platform", [])),
        products=_strs(query.get("product", [])),
        ratings=_ints(query.get("rating", [])),
        languages=_strs(query.get("language", [])),
        versions=_strs(query.get("version", [])),
        years=_strs(query.get("year", [])),
        labels=_strs(query.get("label", [])),
        tags=_strs(query.get("tag", [])),
        search=(query.get("q", [""])[0] or "").strip(),
        labelled_only=query.get("labelled", ["0"])[0] == "1",
        min_words=int(query.get("minwords", ["0"])[0] or 0),
    )


def review_json(review: Review) -> dict[str, Any]:
    """One review as the interface shows it."""
    return {
        "id": review.id,
        "text": review.text,
        "product": review.product,
        "platform": review.platform,
        "rating": review.rating,
        "language": review.language,
        "date": review.date[:10],
        "version": review.version,
        "label": review.label,
        "label_source": review.label_source,
    }


def export_rows(reviews: list[Review]) -> str:
    """A filtered slice in the shape the adjudication harness reads."""
    return "".join(
        json.dumps(
            {
                "id": r.id,
                "text": r.text,
                "meta": {
                    "product": r.product,
                    "platform": r.platform,
                    "language": r.language,
                    "rating": r.rating,
                    "version": r.version,
                    "date": r.date[:10],
                },
            },
            ensure_ascii=False,
        )
        + "\n"
        for r in reviews
    )


@dataclass
class Session:
    """The loaded corpus, shared by every request."""

    corpus: Corpus

    def report(self, filters: Filters, page: int) -> dict[str, Any]:
        """Everything the interface needs for one filter state."""
        kept = self.corpus.filter(filters)
        start = page * PAGE_SIZE
        return {
            "summary": aggregate.summary(kept, len(self.corpus.reviews)),
            "byProduct": aggregate.breakdown(kept, "product"),
            "byLanguage": aggregate.breakdown(kept, "language"),
            "byPlatform": aggregate.breakdown(kept, "platform"),
            "byYear": aggregate.breakdown(kept, "year", limit=15),
            "releases": aggregate.releases(kept)[:40],
            "trend": aggregate.trend(kept),
            "labelMix": aggregate.label_mix(kept),
            "reviews": [review_json(r) for r in kept[start : start + PAGE_SIZE]],
            "page": page,
            "pages": max(1, -(-len(kept) // PAGE_SIZE)),
        }


class Handler(BaseHTTPRequestHandler):
    """Routes for the explorer."""

    session: Session

    def log_message(self, *_args: Any) -> None:
        """Silence per-request logging."""
        return

    def _send(self, code: int, body: bytes, content_type: str, filename: str = "") -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        """Serve the page, the facet menus, a filtered report, or an export."""
        parsed = urlparse(self.path)
        route = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)
        corpus = self.session.corpus

        if route == "/":
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        elif route == "/facets":
            body = {
                "total": len(corpus.reviews),
                "labelled": corpus.labelled,
                "platforms": corpus.values("platform"),
                "products": corpus.values("product"),
                "languages": corpus.values("language"),
                "years": corpus.values("year"),
                "labels": sorted({r.label for r in corpus.reviews if r.label}),
                "tags": keywords.describe(),
            }
            self._send(
                200,
                json.dumps(body, ensure_ascii=False).encode("utf-8"),
                "application/json; charset=utf-8",
            )
        elif route == "/report":
            page = int(query.get("page", ["0"])[0] or 0)
            report = self.session.report(filters_from_query(query), page)
            self._send(
                200,
                json.dumps(report, ensure_ascii=False).encode("utf-8"),
                "application/json; charset=utf-8",
            )
        elif route == "/export":
            kept = corpus.filter(filters_from_query(query))
            self._send(
                200,
                export_rows(kept).encode("utf-8"),
                "application/x-ndjson; charset=utf-8",
                filename=f"slice_{len(kept)}.jsonl",
            )
        else:
            self._send(404, b"not found", "text/plain")


def serve(session: Session, port: int = 8800) -> None:
    """Run until interrupted."""
    Handler.session = session
    total = len(session.corpus.reviews)
    print(f"corpus  {total:,} reviews, {session.corpus.labelled:,} with an issue label")
    print(f"        {len(session.corpus.values('product'))} apps, "
          f"{len(session.corpus.values('version'))} app versions")
    print(f"\n  open  http://127.0.0.1:{port}\n\nCtrl-C to stop. Nothing leaves this machine.")
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
