"""Render collected review pages for local human inspection.

This preview keeps the raw sample local while making the exact stored schema, text, ratings, and
timestamps easy to inspect in a browser before a larger collection run is approved.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.collect.scrape_reviews import REVIEW_FIELDS, atomic_write_text

DEFAULT_INPUT_DIR = Path("data/raw/sample")
DEFAULT_OUTPUT = Path("data/raw/sample_preview/index.html")


def load_reviews(input_dir: Path) -> list[dict[str, Any]]:
    """Load page files and reject records outside the privacy-safe raw schema."""
    reviews = []
    for page_path in sorted(input_dir.glob("*/page_*.jsonl")):
        for line_number, line in enumerate(
            page_path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            review = json.loads(line)
            if tuple(review) != REVIEW_FIELDS:
                raise ValueError(
                    f"Unexpected schema in {page_path}:{line_number}; "
                    f"expected {', '.join(REVIEW_FIELDS)}"
                )
            reviews.append(review)
    if not reviews:
        raise ValueError(f"No review pages found under {input_dir}")
    return reviews


def render_preview(reviews: list[dict[str, Any]]) -> str:
    """Return a self-contained HTML review table without external assets."""
    encoded_reviews = json.dumps(reviews, ensure_ascii=False).replace("<", "\\u003c")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>UrduCX Review Sample</title>
  <style>
    :root {{
      --ink: #17201b;
      --muted: #657168;
      --paper: #f4f1e8;
      --surface: #fffef9;
      --line: #d9d5c9;
      --accent: #006b58;
      --accent-soft: #dcefe9;
      --warning: #a04428;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background:
        linear-gradient(rgba(23, 32, 27, 0.035) 1px, transparent 1px),
        var(--paper);
      background-size: 100% 28px;
      font-family: "Avenir Next", Avenir, "Noto Sans", sans-serif;
    }}
    header {{
      border-bottom: 1px solid var(--line);
      background: rgba(255, 254, 249, 0.94);
    }}
    .header-inner, main {{ width: min(1440px, calc(100% - 32px)); margin: 0 auto; }}
    .header-inner {{ padding: 28px 0 22px; }}
    .eyebrow {{
      margin: 0 0 7px;
      color: var(--accent);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0;
      text-transform: uppercase;
    }}
    h1 {{ margin: 0; font-family: Georgia, serif; font-size: 30px; font-weight: 600; }}
    .meta {{ display: flex; gap: 22px; margin-top: 16px; color: var(--muted); font-size: 13px; }}
    .meta strong {{ color: var(--ink); font-size: 18px; }}
    main {{ padding: 20px 0 44px; }}
    .toolbar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 12px 0;
    }}
    .filters {{ display: flex; flex-wrap: wrap; gap: 6px; }}
    button {{
      min-width: 42px;
      height: 34px;
      border: 1px solid var(--line);
      border-radius: 5px;
      color: var(--ink);
      background: var(--surface);
      font: inherit;
      cursor: pointer;
    }}
    button[aria-pressed="true"] {{
      border-color: var(--accent);
      color: var(--accent);
      background: var(--accent-soft);
      font-weight: 700;
    }}
    .schema {{ color: var(--muted); font-family: ui-monospace, monospace; font-size: 11px; }}
    .table-wrap {{ overflow-x: auto; border: 1px solid var(--line); background: var(--surface); }}
    table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
    th {{
      padding: 10px 12px;
      color: var(--muted);
      background: #ece9df;
      font-size: 11px;
      text-align: left;
      text-transform: uppercase;
    }}
    td {{
      padding: 13px 12px;
      border-top: 1px solid var(--line);
      vertical-align: top;
      font-size: 13px;
    }}
    tbody tr:hover {{ background: #f7fbf8; }}
    .rating {{ width: 72px; font-weight: 800; color: var(--warning); }}
    .review {{
      width: auto;
      font-family: "Noto Nastaliq Urdu", Georgia, serif;
      font-size: 15px;
      line-height: 1.65;
    }}
    .app {{ width: 190px; overflow-wrap: anywhere; }}
    .date {{ width: 170px; color: var(--muted); }}
    .version, .thumbs {{ width: 90px; color: var(--muted); }}
    .empty {{ padding: 40px; color: var(--muted); text-align: center; }}
    @media (max-width: 760px) {{
      .header-inner, main {{ width: min(100% - 20px, 1440px); }}
      .toolbar {{ align-items: flex-start; flex-direction: column; }}
      .schema {{ overflow-wrap: anywhere; }}
      .app {{ width: 140px; }}
      .review {{ min-width: 340px; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="header-inner">
      <p class="eyebrow">Phase 1 · Local sample</p>
      <h1>Collected review inspection</h1>
      <div class="meta">
        <span><strong id="visible-count">0</strong><br>visible reviews</span>
        <span><strong id="app-count">0</strong><br>apps represented</span>
      </div>
    </div>
  </header>
  <main>
    <div class="toolbar">
      <div class="filters" aria-label="Filter by rating">
        <button type="button" data-rating="all" aria-pressed="true">All</button>
        <button type="button" data-rating="1" aria-pressed="false">1★</button>
        <button type="button" data-rating="2" aria-pressed="false">2★</button>
        <button type="button" data-rating="3" aria-pressed="false">3★</button>
        <button type="button" data-rating="4" aria-pressed="false">4★</button>
        <button type="button" data-rating="5" aria-pressed="false">5★</button>
      </div>
      <div class="schema">7 fields · no reviewer name · no avatar · no user identifier</div>
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr>
          <th class="rating">Rating</th>
          <th class="review">Review text</th>
          <th class="app">App ID</th>
          <th class="date">Timestamp</th>
          <th class="version">Version</th>
          <th class="thumbs">Helpful</th>
        </tr></thead>
        <tbody id="reviews"></tbody>
      </table>
      <div class="empty" id="empty" hidden>No reviews match this rating.</div>
    </div>
  </main>
  <script>
    const reviews = {encoded_reviews};
    const body = document.querySelector("#reviews");
    const empty = document.querySelector("#empty");
    const visibleCount = document.querySelector("#visible-count");
    document.querySelector("#app-count").textContent = new Set(reviews.map(r => r.app_id)).size;

    function cell(className, value) {{
      const element = document.createElement("td");
      element.className = className;
      element.textContent = value ?? "—";
      if (className === "review") element.dir = "auto";
      return element;
    }}

    function show(rating) {{
      const visible = rating === "all" ? reviews : reviews.filter(r => String(r.rating) === rating);
      body.replaceChildren(...visible.map(review => {{
        const row = document.createElement("tr");
        row.append(
          cell("rating", `${{review.rating}} ★`),
          cell("review", review.text),
          cell("app", review.app_id),
          cell("date", review.timestamp),
          cell("version", review.app_version),
          cell("thumbs", review.thumbs_up_count),
        );
        return row;
      }}));
      visibleCount.textContent = visible.length;
      empty.hidden = visible.length !== 0;
    }}

    document.querySelectorAll("[data-rating]").forEach(button => {{
      button.addEventListener("click", () => {{
        document.querySelectorAll("[data-rating]").forEach(item =>
          item.setAttribute("aria-pressed", "false")
        );
        button.setAttribute("aria-pressed", "true");
        show(button.dataset.rating);
      }});
    }});
    show("all");
  </script>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    """Parse preview paths."""
    parser = argparse.ArgumentParser(description="Render a local review sample as HTML.")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    """Load strict raw pages and write a self-contained browser preview."""
    args = parse_args()
    reviews = load_reviews(args.input_dir)
    atomic_write_text(args.output, render_preview(reviews))
    print(f"Wrote browser preview for {len(reviews)} reviews to {args.output}")


if __name__ == "__main__":
    main()