"""Tests for the dual-platform source-registry approval page."""

from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from src.collect.render_source_registry import flatten_registry, load_registry, render_registry

ROOT = Path(__file__).parents[2]
REGISTRY_PATH = ROOT / "config/source_registry.yaml"


def test_current_registry_has_dual_platform_core_and_distinct_jazz_products() -> None:
    registry = load_registry(REGISTRY_PATH)
    products = {product["product_id"]: product for product in registry["products"]}

    core_products = [
        product for product in registry["products"] if product["inclusion_tier"] == "core"
    ]
    assert len(core_products) == 11
    assert all(
        {listing["platform"] for listing in product["listings"]}
        == {"google_play", "apple_app_store"}
        for product in core_products
    )
    simosa_ids = {listing["platform_app_id"] for listing in products["simosa"]["listings"]}
    jazzcash_ids = {
        listing["platform_app_id"] for listing in products["jazzcash"]["listings"]
    }
    assert simosa_ids.isdisjoint(jazzcash_ids)


def test_registry_rejects_duplicate_platform_identity(tmp_path: Path) -> None:
    registry = load_registry(REGISTRY_PATH)
    invalid_registry = deepcopy(registry)
    duplicate = invalid_registry["products"][0]["listings"][0]
    invalid_registry["products"][1]["listings"][0]["platform_app_id"] = duplicate[
        "platform_app_id"
    ]
    config_path = tmp_path / "registry.yaml"
    config_path.write_text(yaml.safe_dump(invalid_registry), encoding="utf-8")

    with pytest.raises(ValueError, match="Duplicate platform identity"):
        load_registry(config_path)


def test_render_registry_contains_filters_and_escapes_embedded_data() -> None:
    registry = load_registry(REGISTRY_PATH)
    registry["products"][0]["display_name"] = "<script>alert(1)</script>"

    html = render_registry(registry)

    assert "Pakistan telecom & fintech source registry" in html
    assert 'id="platform-filter"' in html
    assert "<script>alert(1)</script>" not in html
    assert "\\u003cscript>" in html
    assert len(flatten_registry(registry)) == 33