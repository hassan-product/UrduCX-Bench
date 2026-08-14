"""Render the candidate source registry for local human approval.

This Phase 1 gate makes product, platform, vertical, audience, and store identity visible before
collection so similarly branded applications cannot be silently pooled.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from src.collect.scrape_reviews import atomic_write_text

DEFAULT_CONFIG = Path("config/source_registry.yaml")
DEFAULT_OUTPUT = Path("data/raw/source_registry_preview/index.html")
PLATFORM_HOSTS = {
    "google_play": "play.google.com",
    "apple_app_store": "apps.apple.com",
}
PRODUCT_FIELDS = {
    "product_id",
    "display_name",
    "brand_group",
    "vertical",
    "audience",
    "inclusion_tier",
    "listings",
}
LISTING_FIELDS = {
    "platform",
    "platform_app_id",
    "bundle_id",
    "store_title",
    "developer",
    "store_url",
    "confirmed",
}


def load_registry(config_path: Path) -> dict[str, Any]:
    """Load and validate unique platform identities and core platform coverage."""
    registry = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    products = registry.get("products")
    if not isinstance(products, list) or not products:
        raise ValueError(f"No products found in {config_path}")

    product_ids: set[str] = set()
    listing_ids: set[tuple[str, str]] = set()
    for product in products:
        if set(product) != PRODUCT_FIELDS:
            raise ValueError(f"Unexpected product schema for {product.get('product_id')!r}")
        product_id = str(product["product_id"])
        if product_id in product_ids:
            raise ValueError(f"Duplicate product ID: {product_id}")
        product_ids.add(product_id)

        platforms = set()
        for listing in product["listings"]:
            if set(listing) != LISTING_FIELDS:
                raise ValueError(f"Unexpected listing schema for {product_id!r}")
            platform = str(listing["platform"])
            platform_app_id = str(listing["platform_app_id"])
            identity = (platform, platform_app_id)
            if identity in listing_ids:
                raise ValueError(f"Duplicate platform identity: {platform}/{platform_app_id}")
            listing_ids.add(identity)
            platforms.add(platform)

            expected_host = PLATFORM_HOSTS.get(platform)
            if expected_host is None:
                raise ValueError(f"Unknown platform for {product_id!r}: {platform!r}")
            parsed_url = urlparse(str(listing["store_url"]))
            if parsed_url.scheme != "https" or parsed_url.hostname != expected_host:
                raise ValueError(f"Store URL does not match {platform} for {product_id!r}")

        if product["inclusion_tier"] == "core" and platforms != set(PLATFORM_HOSTS):
            raise ValueError(f"Core product lacks both platforms: {product_id}")
    return registry


def flatten_registry(registry: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten product metadata onto each platform listing for browser filtering."""
    rows = []
    for product in registry["products"]:
        product_metadata = {key: value for key, value in product.items() if key != "listings"}
        for listing in product["listings"]:
            rows.append({**product_metadata, **listing})
    return rows


def render_registry(registry: dict[str, Any]) -> str:
    """Return a self-contained, filterable registry approval page."""
    rows_json = json.dumps(flatten_registry(registry), ensure_ascii=False).replace(
        "<", "\\u003c"
    )
    verified_at = str(registry.get("metadata_verified_at", "unknown"))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>UrduCX Source Registry</title>
  <style>
    :root {{
      --ink: #17201b; --muted: #657168; --paper: #f4f1e8; --surface: #fffef9;
      --line: #d9d5c9; --accent: #006b58; --accent-soft: #dcefe9;
      --pending: #9a4e1f; --pending-soft: #fae8d9; --apple: #20231f; --google: #176b45;
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
    .identity-note {{
      display: grid; grid-template-columns: 170px 1fr; gap: 18px; margin-bottom: 20px;
      padding: 15px 18px; border-left: 4px solid var(--accent); background: var(--surface);
    }}
    .identity-note strong {{ font-family: Georgia, serif; font-size: 17px; }}
    .identity-note p {{ margin: 0; color: var(--muted); line-height: 1.5; }}
    .controls {{
      display: grid; grid-template-columns: repeat(5, minmax(145px, 1fr)); gap: 10px;
      margin-bottom: 14px;
    }}
    label {{ color: var(--muted); font-size: 11px; font-weight: 700; text-transform: uppercase; }}
    select {{
      display: block; width: 100%; height: 38px; margin-top: 5px; padding: 0 9px;
      border: 1px solid var(--line); border-radius: 4px; color: var(--ink);
      background: var(--surface);
      font: inherit;
    }}
    .result-line {{ margin: 0 0 9px; color: var(--muted); font-size: 12px; }}
    .table-wrap {{ overflow-x: auto; border: 1px solid var(--line); background: var(--surface); }}
    table {{ width: 100%; min-width: 1240px; border-collapse: collapse; table-layout: fixed; }}
    th {{
      padding: 10px; color: var(--muted); background: #ece9df; font-size: 10px;
      text-align: left; text-transform: uppercase;
    }}
    td {{
      padding: 12px 10px; border-top: 1px solid var(--line);
      vertical-align: top; font-size: 12px;
    }}
    tbody tr:hover {{ background: #f7fbf8; }}
    .product {{ width: 150px; }} .vertical {{ width: 145px; }} .brand {{ width: 150px; }}
    .audience {{ width: 90px; }} .platform {{ width: 115px; }} .identity {{ width: 200px; }}
    .developer {{ width: 210px; }} .status {{ width: 90px; }} .store {{ width: 70px; }}
    .product strong {{ display: block; font-size: 14px; }}
    .tier {{ color: var(--muted); font-size: 10px; text-transform: uppercase; }}
    code {{ font-size: 10px; overflow-wrap: anywhere; }}
    .platform-badge, .status-badge {{
      display: inline-block; padding: 4px 6px; border-radius: 3px;
      font-size: 10px; font-weight: 800;
    }}
    .google_play {{ color: var(--google); background: #dff0e7; }}
    .apple_app_store {{ color: var(--apple); background: #e7e8e5; }}
    .approved {{ color: var(--accent); background: var(--accent-soft); }}
    .pending {{ color: var(--pending); background: var(--pending-soft); }}
    a {{ color: var(--accent); font-weight: 700; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .empty {{ padding: 36px; color: var(--muted); text-align: center; }}
    @media (max-width: 850px) {{
      .inner {{ width: min(100% - 20px, 1480px); }}
      .controls {{ grid-template-columns: 1fr 1fr; }}
      .identity-note {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header><div class="inner">
    <p class="eyebrow">PHASE 1 · SOURCE APPROVAL GATE</p>
    <h1>Pakistan telecom & fintech source registry</h1>
    <p class="lede">Every row is one store listing. Products are joined across stores by a
      canonical product ID, while package, track, and bundle IDs remain visible and separate.</p>
    <div class="metrics">
      <div class="metric"><strong id="product-count">0</strong><span>products</span></div>
      <div class="metric"><strong id="listing-count">0</strong><span>store listings</span></div>
      <div class="metric"><strong id="core-count">0</strong><span>core products</span></div>
      <div class="metric"><strong id="pending-count">0</strong><span>pending approval</span></div>
      <div class="metric"><strong>{verified_at}</strong><span>metadata checked</span></div>
    </div>
  </div></header>
  <main class="inner">
    <section class="identity-note">
      <strong>Jazz is a group, not an app</strong>
      <p>SIMOSA, JazzCash, DOST, ROX, FikrFree, Tamasha, and business products remain
        distinct. Reviews join through the exact platform identity shown below, never by a
        shared brand or developer name.</p>
    </section>
    <div class="controls">
      <label>Platform<select id="platform-filter"></select></label>
      <label>Tier<select id="tier-filter"></select></label>
      <label>Vertical<select id="vertical-filter"></select></label>
      <label>Brand<select id="brand-filter"></select></label>
      <label>Status<select id="status-filter"></select></label>
    </div>
    <p class="result-line"><strong id="visible-count">0</strong> matching listings</p>
    <div class="table-wrap">
      <table>
        <thead><tr><th class="product">Product</th><th class="vertical">Vertical</th>
          <th class="brand">Brand group</th><th class="audience">Audience</th>
          <th class="platform">Platform</th><th class="identity">Platform identity</th>
          <th>Store title</th><th class="developer">Developer / seller</th>
          <th class="status">Status</th><th class="store">Verify</th></tr></thead>
        <tbody id="registry"></tbody>
      </table>
      <div class="empty" id="empty" hidden>No listings match these filters.</div>
    </div>
  </main>
  <script>
    const rows = {rows_json};
    const labels = {{
      google_play: "Google Play", apple_app_store: "Apple App Store",
      telecom_self_care: "Telecom self-care", consumer_wallet: "Consumer wallet",
      digital_banking: "Digital banking", youth_telecom: "Youth telecom",
      enterprise_telecom: "Enterprise telecom", merchant_wallet: "Merchant wallet",
      retailer_wallet: "Retailer wallet", insurance: "Insurance", entertainment: "Entertainment"
    }};
    const filters = ["platform", "inclusion_tier", "vertical", "brand_group", "status"];
    rows.forEach(row => row.status = row.confirmed ? "approved" : "pending");

    function title(value) {{
      return labels[value] ?? value.replaceAll("_", " ").replace(
        /\\b\\w/g, letter => letter.toUpperCase()
      );
    }}
    function setupFilter(field) {{
      const filterId = field.replace("inclusion_tier", "tier").replace("brand_group", "brand");
      const element = document.querySelector(`#${{filterId}}-filter`);
      const values = [...new Set(rows.map(row => row[field]))].sort();
      element.append(
        new Option("All", "all"),
        ...values.map(value => new Option(title(value), value))
      );
      element.addEventListener("change", render);
    }}
    function cell(className, value) {{
      const element = document.createElement("td"); element.className = className;
      element.textContent = value ?? "—"; return element;
    }}
    function render() {{
      const visible = rows.filter(row => filters.every(field => {{
        const id = field.replace("inclusion_tier", "tier").replace("brand_group", "brand");
        const value = document.querySelector(`#${{id}}-filter`).value;
        return value === "all" || String(row[field]) === value;
      }}));
      document.querySelector("#registry").replaceChildren(...visible.map(row => {{
        const tr = document.createElement("tr");
        const product = cell("product", "");
        const strong = document.createElement("strong"); strong.textContent = row.display_name;
        const tier = document.createElement("span");
        tier.className = "tier"; tier.textContent = row.inclusion_tier;
        product.append(strong, tier);
        const platform = cell("platform", "");
        const platformBadge = document.createElement("span");
        platformBadge.className = `platform-badge ${{row.platform}}`;
        platformBadge.textContent = title(row.platform);
        platform.append(platformBadge);
        const identity = cell("identity", "");
        const idCode = document.createElement("code"); idCode.textContent = row.platform_app_id;
        const bundle = document.createElement("code");
        bundle.textContent = `bundle: ${{row.bundle_id}}`;
        identity.append(idCode, document.createElement("br"), bundle);
        const status = cell("status", "");
        const statusBadge = document.createElement("span");
        statusBadge.className = `status-badge ${{row.status}}`;
        statusBadge.textContent = title(row.status);
        status.append(statusBadge);
        const store = cell("store", "");
        const link = document.createElement("a"); link.href = row.store_url; link.target = "_blank";
        link.rel = "noopener"; link.textContent = "Open"; store.append(link);
        tr.append(product, cell("vertical", title(row.vertical)), cell("brand", row.brand_group),
          cell("audience", title(row.audience)), platform, identity, cell("", row.store_title),
          cell("developer", row.developer), status, store);
        return tr;
      }}));
      document.querySelector("#visible-count").textContent = visible.length;
      document.querySelector("#empty").hidden = visible.length !== 0;
    }}
    filters.forEach(setupFilter);
    document.querySelector("#product-count").textContent = new Set(
      rows.map(row => row.product_id)
    ).size;
    document.querySelector("#listing-count").textContent = rows.length;
    document.querySelector("#core-count").textContent = new Set(
      rows.filter(row => row.inclusion_tier === "core").map(row => row.product_id)
    ).size;
    document.querySelector("#pending-count").textContent = rows.filter(
      row => !row.confirmed
    ).length;
    render();
  </script>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    """Parse registry input and preview output paths."""
    parser = argparse.ArgumentParser(description="Render the Phase 1 source registry.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    """Validate the registry and write its self-contained approval page."""
    args = parse_args()
    registry = load_registry(args.config)
    atomic_write_text(args.output, render_registry(registry))
    rows = flatten_registry(registry)
    print(
      f"Wrote {len(rows)} listings across {len(registry['products'])} products "
      f"to {args.output}"
    )


if __name__ == "__main__":
    main()