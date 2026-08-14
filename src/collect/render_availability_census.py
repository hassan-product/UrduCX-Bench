"""Measure and render the accessible review supply before full collection.

Google exposes a store-reported written-review count but only a sampled date window here. Apple
exposes no lifetime total and caps public RSS access at 500 reviews, so those facts are reported
separately instead of being combined into a misleading availability number.
"""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from src.collect.render_source_registry import flatten_registry, load_registry
from src.collect.scrape_reviews import atomic_write_text

DEFAULT_REGISTRY = Path("config/source_registry.yaml")
DEFAULT_REVIEWS_DIR = Path("data/raw/reviews")
DEFAULT_CENSUS = Path("data/raw/availability_census/census.json")
DEFAULT_PREVIEW = Path("data/raw/availability_census_preview/index.html")


def parse_timestamp(value: Any) -> datetime | None:
    """Parse an ISO timestamp emitted by either collector."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize counts, observed dates, and rating distribution without review text."""
    timestamps = [
        parsed
        for record in records
        if (parsed := parse_timestamp(record.get("timestamp")))
    ]
    ratings = Counter(str(record.get("rating")) for record in records if record.get("rating"))
    return {
        "observed_reviews": len(records),
        "earliest_observed": min(timestamps).isoformat() if timestamps else None,
        "latest_observed": max(timestamps).isoformat() if timestamps else None,
        "rating_distribution": {str(rating): ratings.get(str(rating), 0) for rating in range(1, 6)},
    }


def read_listing_records(reviews_dir: Path, listing: dict[str, Any]) -> list[dict[str, Any]]:
    """Read all persisted pages for one platform listing."""
    base = (
        reviews_dir
        / str(listing["platform"])
        / str(listing["product_id"])
        / str(listing["platform_app_id"])
    )
    records = []
    for page_path in sorted(base.glob("page_*.jsonl")):
        records.extend(
            json.loads(line)
            for line in page_path.read_text(encoding="utf-8").splitlines()
            if line
        )
    return records


def build_census(
    registry: dict[str, Any],
    reviews_dir: Path,
    google_metadata: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Build listing-level and product-level availability facts from persisted samples."""
    rows = []
    for listing in flatten_registry(registry):
        records = read_listing_records(reviews_dir, listing)
        summary = summarize_records(records)
        metadata = google_metadata.get(str(listing["platform_app_id"]), {})
        rows.append(
            {
                "product_id": listing["product_id"],
                "display_name": listing["display_name"],
                "vertical": listing["vertical"],
                "inclusion_tier": listing["inclusion_tier"],
                "platform": listing["platform"],
                "platform_app_id": str(listing["platform_app_id"]),
                "store_reported_reviews": metadata.get("reviews"),
                "store_reported_ratings": metadata.get("ratings"),
                "access_note": (
                    "Up to 500 public RSS reviews"
                    if listing["platform"] == "apple_app_store"
                    else "Latest sample; lifetime total is store-reported"
                ),
                **summary,
            }
        )
    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "method": {
            "google_play": "Store metadata totals plus latest persisted sample",
            "apple_app_store": "All publicly accessible Pakistan RSS pages, capped at 500",
        },
        "listings": rows,
    }


def render_census(census: dict[str, Any]) -> str:
    """Return a self-contained availability report for quota review."""
    rows_json = json.dumps(census["listings"], ensure_ascii=False).replace("<", "\\u003c")
    generated_at = str(census["generated_at"])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>UrduCX Availability Census</title>
  <style>
    :root {{
      --ink: #17201b; --muted: #657168; --paper: #f4f1e8; --surface: #fffef9;
      --line: #d9d5c9; --accent: #006b58; --accent-soft: #dcefe9;
      --google: #176b45; --apple: #20231f;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; color: var(--ink); background: var(--paper);
      font-family: "Avenir Next", Avenir, "Noto Sans", sans-serif; }}
    header {{ border-bottom: 1px solid var(--line); background: var(--surface); }}
    .inner {{ width: min(1480px, calc(100% - 32px)); margin: 0 auto; }}
    header .inner {{ padding: 30px 0 24px; }}
    .eyebrow {{ margin: 0 0 7px; color: var(--accent); font-size: 12px; font-weight: 800; }}
    h1 {{ margin: 0; font-family: Georgia, serif; font-size: 32px; font-weight: 600; }}
    .lede {{ max-width: 900px; margin: 10px 0 0; color: var(--muted); line-height: 1.5; }}
    .metrics {{ display: flex; flex-wrap: wrap; gap: 28px; margin-top: 20px; }}
    .metric strong {{ display: block; font-size: 22px; }}
    .metric span {{ color: var(--muted); font-size: 12px; }}
    main {{ padding: 22px 0 48px; }}
    .method-note {{
      display: grid; grid-template-columns: 1fr 1fr; gap: 1px; margin-bottom: 20px;
      border: 1px solid var(--line); background: var(--line);
    }}
    .method-note div {{ padding: 14px; background: var(--surface); }}
    .method-note strong {{ display: block; margin-bottom: 4px; }}
    .method-note span {{ color: var(--muted); font-size: 12px; }}
    .controls {{ display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 12px; }}
    label {{ color: var(--muted); font-size: 11px; font-weight: 700; text-transform: uppercase; }}
    select {{
      display: block; width: 200px; height: 38px; margin-top: 5px; padding: 0 9px;
      border: 1px solid var(--line); border-radius: 4px;
      color: var(--ink); background: var(--surface); font: inherit;
    }}
    .result-line {{ margin: 0 0 9px; color: var(--muted); font-size: 12px; }}
    .table-wrap {{ overflow-x: auto; border: 1px solid var(--line); background: var(--surface); }}
    table {{ width: 100%; min-width: 1260px; border-collapse: collapse; table-layout: fixed; }}
    th {{
      padding: 10px 12px; color: var(--muted); background: #ece9df;
      font-size: 11px; text-align: left; text-transform: uppercase;
    }}
    td {{ padding: 12px; border-top: 1px solid var(--line); vertical-align: top; font-size: 13px; }}
    tbody tr:hover {{ background: #f7fbf8; }}
    .col-product {{ width: 150px; }} .col-tier {{ width: 80px; }}
    .col-vertical {{ width: 150px; }} .col-platform {{ width: 130px; }}
    .col-id {{ width: 190px; }} .col-store {{ width: 110px; }}
    .col-observed {{ width: 80px; }} .col-window {{ width: 250px; }}
    .col-ratings {{ width: 130px; }} .col-note {{ width: auto; }}
    .product-name {{ font-size: 14px; font-weight: 700; }}
    .tier-label {{ font-size: 10px; color: var(--muted); text-transform: uppercase; }}
    .platform-badge {{
      display: inline-block; padding: 4px 7px; border-radius: 3px;
      font-size: 11px; font-weight: 800;
    }}
    .google_play {{ color: var(--google); background: #dff0e7; }}
    .apple_app_store {{ color: var(--apple); background: #e7e8e5; }}
    code {{ font-size: 10px; overflow-wrap: anywhere; }}
    .ratings {{ font-family: ui-monospace, monospace; font-size: 11px; color: var(--muted); }}
    .note {{ color: var(--muted); font-size: 11px; }}
    @media (max-width: 760px) {{
      .inner {{ width: min(100% - 20px, 1480px); }}
      .method-note {{ grid-template-columns: 1fr; }}
      .controls {{ flex-direction: column; }}
    }}
  </style>
</head>
<body>
  <header><div class="inner">
    <p class="eyebrow">PHASE 1 · AVAILABILITY CENSUS</p>
    <h1>Review supply before quota selection</h1>
    <p class="lede">Observed coverage comes from persisted collector pages. Google lifetime
      totals are store-reported. Apple exposes only its latest 500 reviews per Pakistan listing.</p>
    <div class="metrics">
      <div class="metric"><strong id="products">0</strong><span>products</span></div>
      <div class="metric"><strong id="listings">0</strong><span>listings</span></div>
      <div class="metric"><strong id="google-total">0</strong><span>Google store-reported reviews</span></div>
      <div class="metric"><strong id="apple-total">0</strong><span>Apple reviews accessible</span></div>
      <div class="metric"><strong>{generated_at[:10]}</strong><span>census date</span></div>
    </div>
  </div></header>
  <main class="inner">
    <section class="method-note">
      <div>
        <strong>Google Play</strong>
        <span>Store-reported written-review total and a recent 200-review sample per listing.</span>
      </div>
      <div>
        <strong>Apple App Store</strong>
        <span>All reviews accessible through up to ten public 50-review RSS pages (max 500).</span>
      </div>
    </section>
    <div class="controls">
      <label>Platform<select id="platform">
        <option value="all">All platforms</option>
        <option value="google_play">Google Play</option>
        <option value="apple_app_store">Apple App Store</option>
      </select></label>
      <label>Tier<select id="tier">
        <option value="all">All tiers</option>
        <option value="core">Core</option>
        <option value="adjacent">Adjacent</option>
      </select></label>
    </div>
    <p class="result-line"><strong id="visible">0</strong> matching listings</p>
    <div class="table-wrap"><table>
      <thead><tr>
        <th class="col-product">Product</th>
        <th class="col-tier">Tier</th>
        <th class="col-vertical">Vertical</th>
        <th class="col-platform">Platform</th>
        <th class="col-id">Platform ID</th>
        <th class="col-store">Store-reported</th>
        <th class="col-observed">Observed</th>
        <th class="col-window">Observed date window</th>
        <th class="col-ratings">Ratings 1→5</th>
        <th class="col-note">Note</th>
      </tr></thead>
      <tbody id="body"></tbody>
    </table></div>
  </main>
  <script>
    const rows = {rows_json};
    const body = document.querySelector("#body");

    function cell(className) {{
      const td = document.createElement("td"); td.className = className; return td;
    }}

    function render() {{
      const platform = document.querySelector("#platform").value;
      const tier = document.querySelector("#tier").value;
      const visible = rows.filter(row =>
        (platform === "all" || row.platform === platform) &&
        (tier === "all" || row.inclusion_tier === tier)
      );
      body.replaceChildren(...visible.map(row => {{
        const tr = document.createElement("tr");

        const product = cell("col-product");
        const name = document.createElement("div"); name.className = "product-name"; name.textContent = row.display_name;
        const tier = document.createElement("div"); tier.className = "tier-label"; tier.textContent = row.inclusion_tier;
        product.append(name, tier);

        const platform = cell("col-platform");
        const badge = document.createElement("span");
        badge.className = `platform-badge ${{row.platform}}`;
        badge.textContent = row.platform === "google_play" ? "Google Play" : "Apple App Store";
        platform.append(badge);

        const id = cell("col-id");
        const code = document.createElement("code"); code.textContent = row.platform_app_id;
        id.append(code);

        const ratings = cell("col-ratings ratings");
        ratings.textContent = [1,2,3,4,5].map(k => row.rating_distribution[k]).join(" · ");

        const noteCell = cell("col-note note");
        noteCell.textContent = row.access_note;

        tr.append(
          product,
          Object.assign(cell("col-tier"), {{ textContent: row.inclusion_tier }}),
          Object.assign(cell("col-vertical"), {{ textContent: row.vertical.replaceAll("_", " ") }}),
          platform, id,
          Object.assign(cell("col-store"), {{ textContent: row.store_reported_reviews?.toLocaleString() ?? "—" }}),
          Object.assign(cell("col-observed"), {{ textContent: row.observed_reviews }}),
          Object.assign(cell("col-window"), {{
            textContent: row.earliest_observed
              ? `${{row.earliest_observed.slice(0,10)}} → ${{row.latest_observed.slice(0,10)}}`
              : "—"
          }}),
          ratings, noteCell,
        );
        return tr;
      }}));
      document.querySelector("#visible").textContent = visible.length;
    }}

    document.querySelectorAll("select").forEach(s => s.addEventListener("change", render));
    document.querySelector("#products").textContent = new Set(rows.map(r => r.product_id)).size;
    document.querySelector("#listings").textContent = rows.length;
    document.querySelector("#google-total").textContent =
      rows.filter(r => r.platform === "google_play")
          .reduce((t, r) => t + (r.store_reported_reviews ?? 0), 0).toLocaleString();
    document.querySelector("#apple-total").textContent =
      rows.filter(r => r.platform === "apple_app_store")
          .reduce((t, r) => t + r.observed_reviews, 0).toLocaleString();
    render();
  </script>
</body>
</html>"""


def parse_args() -> argparse.Namespace:
    """Parse census paths."""
    parser = argparse.ArgumentParser(description="Render a persisted availability census.")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--reviews-dir", type=Path, default=DEFAULT_REVIEWS_DIR)
    parser.add_argument("--google-metadata", type=Path, required=True)
    parser.add_argument("--census", type=Path, default=DEFAULT_CENSUS)
    parser.add_argument("--output", type=Path, default=DEFAULT_PREVIEW)
    return parser.parse_args()


def main() -> None:
    """Build census JSON from persisted pages and render its local report."""
    args = parse_args()
    registry = load_registry(args.registry)
    google_metadata = json.loads(args.google_metadata.read_text(encoding="utf-8"))
    census = build_census(registry, args.reviews_dir, google_metadata)
    atomic_write_text(args.census, json.dumps(census, ensure_ascii=False, indent=2) + "\n")
    atomic_write_text(args.output, render_census(census))
    print(f"Wrote availability census for {len(census['listings'])} listings to {args.output}")


if __name__ == "__main__":
    main()