"""Tests for deterministic, human-gated Google Play app resolution."""

from pathlib import Path
from typing import Any

import yaml
from src.collect.resolve_apps import choose_result, resolve_targets, write_config


def test_choose_result_prefers_expected_package_id() -> None:
    target = {
        "name": "SIMOSA",
        "query": "SIMOSA",
        "expected_app_id": "com.jazz.jazzworld",
    }
    results = [
        {"appId": "example.simosa", "title": "SIMOSA"},
        {"appId": "com.jazz.jazzworld", "title": "Jazz World"},
    ]

    assert choose_result(target, results)["appId"] == "com.jazz.jazzworld"


def test_resolve_targets_uses_verified_id_when_store_omits_it() -> None:
    target = {
        "name": "Easypaisa",
        "query": "Easypaisa",
        "expected_app_id": "pk.com.telenor.phoenix",
        "expected_developer": "Easypaisa Bank Limited",
    }

    apps = resolve_targets(
        (target,),
        search_fn=lambda *args, **kwargs: [
            {
                "appId": None,
                "title": "easypaisa - a digital bank",
                "developer": "Easypaisa Bank Limited",
            }
        ],
    )

    assert apps[0]["app_id"] == "pk.com.telenor.phoenix"
    assert apps[0]["confirmed"] is False


def test_choose_result_avoids_conflicting_variant_from_same_developer() -> None:
    target = {
        "name": "JazzCash",
        "query": "JazzCash",
        "expected_app_id": "com.techlogix.mobilinkcustomer",
        "expected_developer": "JazzCash",
    }
    results = [
        {
            "appId": None,
            "title": "JazzCash - Your Mobile Account",
            "developer": "JazzCash",
        },
        {
            "appId": "com.ibm.jazzcashmerchant",
            "title": "JazzCash Business",
            "developer": "JazzCash",
        },
    ]

    assert choose_result(target, results)["title"] == "JazzCash - Your Mobile Account"


def test_resolve_targets_keeps_results_unconfirmed() -> None:
    def fake_search(query: str, **kwargs: Any) -> list[dict[str, Any]]:
        assert kwargs == {"lang": "en", "country": "pk", "n_hits": 10}
        return [
            {
                "appId": "pk.example.easypaisa",
                "title": query,
                "developer": "Example Developer",
            }
        ]

    apps = resolve_targets(
        ({"name": "Easypaisa", "query": "Easypaisa"},), search_fn=fake_search
    )

    assert apps == [
        {
            "name": "Easypaisa",
            "app_id": "pk.example.easypaisa",
            "store_title": "Easypaisa",
            "developer": "Example Developer",
            "query": "Easypaisa",
            "confirmed": False,
        }
    ]


def test_write_config_preserves_human_review_gate(tmp_path: Path) -> None:
    output_path = tmp_path / "apps.yaml"
    apps = [{"name": "Ufone", "app_id": "pk.example.ufone", "confirmed": False}]

    write_config(apps, output_path)

    assert yaml.safe_load(output_path.read_text(encoding="utf-8")) == {"apps": apps}