"""Render a local browser preview of the cleaned Phase 2 review set.

The full cleaned file is too large to drop into one HTML page. This samples evenly across
products so a human can check remapped IDs, dropped short text, and remaining review quality.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from src.collect.render_source_registry import load_registry
from src.collect.scrape_reviews import atomic_write_text
from src.prep.clean import CLEAN_FIELDS

DEFAULT_INPUT = Path("data/interim/reviews_cleaned.jsonl")
DEFAULT_REGISTRY = Path("config/source_registry.yaml")
DEFAULT_OUTPUT = Path("data/interim/clean_preview/index.html")
DEFAULT_PER_SLICE = 250


def load_cleaned(path: Path) -> list[dict[str, Any]]:
    """Load cleaned JSONL and reject records outside the Phase 2 schema."""
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            if tuple(record) != CLEAN_FIELDS:
                raise ValueError(
                    f"Unexpected schema in {path}:{line_number}; "
                    f"expected {', '.join(CLEAN_FIELDS)}"
                )
            records.append(record)
    if not records:
        raise ValueError(f"No cleaned reviews found in {path}")
    return records


def load_brand_map(registry_path: Path) -> dict[str, str]:
    """Map each registry product_id to its brand_group."""
    registry = load_registry(registry_path)
    return {
        str(product["product_id"]): str(product["brand_group"]) for product in registry["products"]
    }


def attach_brand(records: list[dict[str, Any]], brand_map: dict[str, str]) -> list[dict[str, Any]]:
    """Copy brand_group onto each review for browser filters. Does not mutate inputs."""
    labelled = []
    for record in records:
        product_id = str(record["product_id"])
        labelled.append({**record, "brand_group": brand_map.get(product_id, "Unknown")})
    return labelled


def sample_evenly(records: list[dict[str, Any]], per_slice: int) -> list[dict[str, Any]]:
    """Keep the first N reviews per (product_id, platform) so Apple is not drowned out."""
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        key = (str(record["product_id"]), str(record["platform"]))
        if len(grouped[key]) < per_slice:
            grouped[key].append(record)
    sampled: list[dict[str, Any]] = []
    for key in sorted(grouped):
        sampled.extend(grouped[key])
    return sampled


def render_preview(records: list[dict[str, Any]], total_cleaned: int) -> str:
    """Return a self-contained HTML table with platform, brand, and product filters."""
    encoded = json.dumps(records, ensure_ascii=False).replace("<", "\\u003c")
    brands = sorted({str(row.get("brand_group", "Unknown")) for row in records})
    brand_options = "".join(f'<option value="{name}">{name}</option>' for name in brands)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>UrduCX Cleaned Reviews</title>
  <style>
    :root {{
      --ink: #17201b; --muted: #657168; --paper: #f4f1e8; --surface: #fffef9;
      --line: #d9d5c9; --accent: #006b58; --accent-soft: #dcefe9;
      --warning: #a04428; --apple: #20231f; --google: #176b45;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; color: var(--ink); background: var(--paper);
      font-family: "Avenir Next", Avenir, "Noto Sans", sans-serif;
    }}
    header {{ border-bottom: 1px solid var(--line); background: var(--surface); }}
    .inner {{ width: min(1480px, calc(100% - 32px)); margin: 0 auto; }}
    header .inner {{ padding: 30px 0 24px; }}
    .eyebrow {{ margin: 0 0 7px; color: var(--accent); font-size: 12px; font-weight: 800; }}
    h1 {{ margin: 0; font-family: Georgia, serif; font-size: 32px; font-weight: 600; }}
    .lede {{ max-width: 820px; margin: 10px 0 0; color: var(--muted); line-height: 1.5; }}
    .metrics {{ display: flex; flex-wrap: wrap; gap: 28px; margin-top: 20px; }}
    .metric strong {{ display: block; font-size: 22px; }}
    .metric span {{ color: var(--muted); font-size: 12px; }}
    main {{ padding: 22px 0 48px; }}
    .controls {{
      display: grid; grid-template-columns: 220px 260px 220px 1fr; gap: 16px; margin-bottom: 16px;
    }}
    .field {{ color: var(--muted); font-size: 11px; font-weight: 700; text-transform: uppercase; }}
    select {{
      display: block; width: 100%; height: 38px; margin-top: 5px; padding: 0 9px;
      border: 1px solid var(--line); border-radius: 4px; color: var(--ink);
      background: var(--surface); font: inherit;
    }}
    .dropdown {{ position: relative; margin-top: 5px; }}
    .dropdown-toggle {{
      display: flex; align-items: center; justify-content: space-between; width: 100%;
      height: 38px; padding: 0 10px; border: 1px solid var(--line); border-radius: 4px;
      background: var(--surface); color: var(--ink); font: inherit; cursor: pointer;
    }}
    .dropdown-toggle::after {{ content: "▾"; color: var(--muted); margin-left: 8px; }}
    .dropdown-toggle[aria-expanded="true"]::after {{ content: "▴"; }}
    .dropdown-panel {{
      position: absolute; z-index: 10; top: calc(100% + 4px); left: 0; width: max(100%, 420px);
      padding: 10px 12px; border: 1px solid var(--line); border-radius: 4px;
      background: var(--surface); box-shadow: 0 8px 20px rgba(23, 32, 27, 0.12);
    }}
    .product-actions {{ display: flex; gap: 8px; margin-bottom: 8px; }}
    .product-actions button, .rating-filters button {{
      height: 30px; padding: 0 10px; border: 1px solid var(--line); border-radius: 4px;
      background: var(--surface); color: var(--ink); font: inherit; cursor: pointer;
    }}
    .product-grid {{
      display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 6px 12px;
      max-height: 220px; overflow-y: auto;
    }}
    .check {{
      display: flex; align-items: center; gap: 8px; color: var(--ink);
      font-size: 13px; font-weight: 500; text-transform: none; cursor: pointer;
    }}
    .rating-row {{
      display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between;
      gap: 12px; margin-bottom: 10px;
    }}
    .rating-filters {{ display: flex; flex-wrap: wrap; gap: 6px; }}
    button[aria-pressed="true"] {{
      border-color: var(--accent); color: var(--accent); background: var(--accent-soft);
      font-weight: 700;
    }}
    .result-line {{ margin: 0; color: var(--muted); font-size: 12px; }}
    .table-wrap {{ overflow-x: auto; border: 1px solid var(--line); background: var(--surface); }}
    table {{ width: 100%; min-width: 980px; border-collapse: collapse; table-layout: fixed; }}
    th {{
      padding: 10px; color: var(--muted); background: #ece9df; font-size: 10px;
      text-align: left; text-transform: uppercase;
    }}
    td {{
      padding: 12px 10px; border-top: 1px solid var(--line);
      vertical-align: top; font-size: 13px;
    }}
    tbody tr:hover {{ background: #f7fbf8; }}
    .rating {{ width: 72px; font-weight: 800; color: var(--warning); }}
    .review {{
      font-family: "Noto Nastaliq Urdu", Georgia, serif; font-size: 15px; line-height: 1.65;
    }}
    .app {{ width: 200px; overflow-wrap: anywhere; }}
    .platform {{ width: 130px; }}
    .date {{ width: 170px; color: var(--muted); }}
    .platform-badge {{
      display: inline-block; padding: 4px 6px; border-radius: 3px;
      font-size: 10px; font-weight: 800;
    }}
    .google_play {{ color: var(--google); background: #dff0e7; }}
    .apple_app_store {{ color: var(--apple); background: #e7e8e5; }}
    .empty {{ padding: 36px; color: var(--muted); text-align: center; }}
    @media (max-width: 850px) {{
      .inner {{ width: min(100% - 20px, 1480px); }}
      .controls {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header><div class="inner">
    <p class="eyebrow">PHASE 2 · CLEANED SAMPLE</p>
    <h1>Cleaned review inspection</h1>
    <p class="lede">Apple and Google stay separate. Tick one or more products, or pick a
      brand group such as Jazz. This page is a sample, not the full 54k cleaned file.</p>
    <div class="metrics">
      <div class="metric"><strong id="visible-count">0</strong><span>visible now</span></div>
      <div class="metric"><strong>{total_cleaned:,}</strong><span>kept after cleaning</span></div>
      <div class="metric"><strong id="product-count">0</strong><span>products in sample</span></div>
    </div>
  </div></header>
  <main class="inner">
    <div class="controls">
      <label class="field">Platform
        <select id="platform">
          <option value="all">All platforms</option>
          <option value="google_play">Google Play only</option>
          <option value="apple_app_store">Apple App Store only</option>
        </select>
      </label>
      <label class="field">Brand group
        <select id="brand">
          <option value="all">All brands</option>
          {brand_options}
        </select>
      </label>
      <label class="field">Language
        <select id="language">
          <option value="all">All languages</option>
          <option value="english">English</option>
          <option value="roman_urdu">Roman Urdu</option>
          <option value="urdu_script">Urdu script</option>
          <option value="code_switched">Code-switched</option>
        </select>
      </label>
      <div class="field">Products
        <div class="dropdown" id="product-dropdown">
          <button
            type="button"
            id="product-toggle"
            class="dropdown-toggle"
            aria-haspopup="true"
            aria-expanded="false"
          >All products</button>
          <div class="dropdown-panel" id="product-panel" hidden>
            <div class="product-actions">
              <button type="button" id="select-all">Select all</button>
              <button type="button" id="clear-all">Clear</button>
            </div>
            <div class="product-grid" id="product-grid"></div>
          </div>
        </div>
      </div>
    </div>
    <div class="rating-row">
      <div class="rating-filters" aria-label="Filter by rating">
        <button type="button" data-rating="all" aria-pressed="true">All ratings</button>
        <button type="button" data-rating="1">1★</button>
        <button type="button" data-rating="2">2★</button>
        <button type="button" data-rating="3">3★</button>
        <button type="button" data-rating="4">4★</button>
        <button type="button" data-rating="5">5★</button>
      </div>
      <p class="result-line">Showing a sample of up to {DEFAULT_PER_SLICE}
        reviews per product × platform.</p>
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr>
          <th class="rating">Rating</th>
          <th class="review">Cleaned text</th>
          <th class="platform">Platform</th>
          <th class="app">Product / App ID</th>
          <th class="date">Timestamp</th>
        </tr></thead>
        <tbody id="reviews"></tbody>
      </table>
      <div class="empty" id="empty" hidden>No reviews match these filters.</div>
    </div>
  </main>
  <script>
    const reviews = {encoded};
    const body = document.querySelector("#reviews");
    const empty = document.querySelector("#empty");
    const visibleCount = document.querySelector("#visible-count");
    const platformSelect = document.querySelector("#platform");
    const brandSelect = document.querySelector("#brand");
    const languageSelect = document.querySelector("#language");
    const productDropdown = document.querySelector("#product-dropdown");
    const productToggle = document.querySelector("#product-toggle");
    const productPanel = document.querySelector("#product-panel");
    const productGrid = document.querySelector("#product-grid");
    const products = [...new Set(reviews.map(r => r.product_id))].sort();
    document.querySelector("#product-count").textContent = products.length;
    let rating = "all";

    function visibleProductsForBrand() {{
      const brand = brandSelect.value;
      return products.filter(product =>
        brand === "all" || reviews.some(r => r.product_id === product && r.brand_group === brand)
      );
    }}

    function selectedProducts() {{
      return [...productGrid.querySelectorAll("input:checked")].map(box => box.value);
    }}

    function updateToggleLabel() {{
      const visibleProducts = visibleProductsForBrand();
      const picked = selectedProducts();
      if (picked.length === 0) {{
        productToggle.textContent = "No products selected";
      }} else if (picked.length === visibleProducts.length) {{
        productToggle.textContent = "All products";
      }} else {{
        const suffix = picked.length === 1 ? "" : "s";
        productToggle.textContent = `${{picked.length}} product${{suffix}} selected`;
      }}
    }}

    function renderProductBoxes() {{
      const visibleProducts = visibleProductsForBrand();
      productGrid.replaceChildren(...visibleProducts.map(product => {{
        const label = document.createElement("label");
        label.className = "check";
        const box = document.createElement("input");
        box.type = "checkbox";
        box.value = product;
        box.checked = true;
        box.addEventListener("change", () => {{ updateToggleLabel(); show(); }});
        label.append(box, document.createTextNode(product));
        return label;
      }}));
      updateToggleLabel();
    }}

    function openProductPanel(open) {{
      productPanel.hidden = !open;
      productToggle.setAttribute("aria-expanded", String(open));
    }}

    productToggle.addEventListener("click", () => openProductPanel(productPanel.hidden));
    document.addEventListener("click", event => {{
      if (!productDropdown.contains(event.target)) openProductPanel(false);
    }});

    function cell(className, value) {{
      const element = document.createElement("td");
      element.className = className;
      element.textContent = value ?? "—";
      if (className === "review") element.dir = "auto";
      return element;
    }}

    function platformBadge(platform) {{
      const element = document.createElement("td");
      element.className = "platform";
      const badge = document.createElement("span");
      badge.className = `platform-badge ${{platform}}`;
      badge.textContent = platform === "google_play" ? "Google Play" : "Apple App Store";
      element.append(badge);
      return element;
    }}

    function show() {{
      const platform = platformSelect.value;
      const brand = brandSelect.value;
      const language = languageSelect.value;
      const picked = selectedProducts();
      const visible = reviews.filter(r =>
        (platform === "all" || r.platform === platform) &&
        (brand === "all" || r.brand_group === brand) &&
        (language === "all" || r.language === language) &&
        picked.includes(r.product_id) &&
        (rating === "all" || String(r.rating) === rating)
      );
      body.replaceChildren(...visible.map(review => {{
        const row = document.createElement("tr");
        row.append(
          cell("rating", `${{review.rating}} ★`),
          cell("review", review.text_clean),
          platformBadge(review.platform),
          cell("app", `${{review.product_id}} / ${{review.platform_app_id}}`),
          cell("date", review.timestamp),
        );
        return row;
      }}));
      visibleCount.textContent = visible.length;
      empty.hidden = visible.length !== 0;
    }}

    function setAll(checked) {{
      productGrid.querySelectorAll("input").forEach(box => {{ box.checked = checked; }});
      updateToggleLabel();
      show();
    }}

    platformSelect.addEventListener("change", show);
    languageSelect.addEventListener("change", show);
    brandSelect.addEventListener("change", () => {{ renderProductBoxes(); show(); }});
    document.querySelector("#select-all").addEventListener("click", () => setAll(true));
    document.querySelector("#clear-all").addEventListener("click", () => setAll(false));
    document.querySelectorAll("[data-rating]").forEach(button => {{
      button.addEventListener("click", () => {{
        document.querySelectorAll("[data-rating]").forEach(item =>
          item.setAttribute("aria-pressed", "false")
        );
        button.setAttribute("aria-pressed", "true");
        rating = button.dataset.rating;
        show();
      }});
    }});
    renderProductBoxes();
    show();
  </script>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    """Parse preview paths and sample size."""
    parser = argparse.ArgumentParser(description="Render a local cleaned-review preview.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--per-slice", type=int, default=DEFAULT_PER_SLICE)
    return parser.parse_args()


def main() -> None:
    """Sample the cleaned JSONL and write a self-contained HTML page."""
    args = parse_args()
    records = attach_brand(load_cleaned(args.input), load_brand_map(args.registry))
    sampled = sample_evenly(records, args.per_slice)
    atomic_write_text(args.output, render_preview(sampled, len(records)))
    print(
        f"Wrote browser preview for {len(sampled)} of {len(records)} cleaned reviews "
        f"to {args.output}"
    )


if __name__ == "__main__":
    main()
