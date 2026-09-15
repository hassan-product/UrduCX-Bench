"""Resolve target app names to reviewable Google Play package IDs.

This script prevents guessed package IDs from entering collection configuration. It searches the
Pakistan storefront, records only non-user app metadata, and leaves every result pending explicit
human confirmation before review collection can begin.
"""

from __future__ import annotations

import argparse
import re
from collections.abc import Callable, Sequence
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import yaml
from google_play_scraper import search

DEFAULT_OUTPUT = Path("config/apps.yaml")
DEFAULT_TARGETS = (
    {
        "name": "SIMOSA",
        "query": "SIMOSA",
        "expected_app_id": "com.jazz.jazzworld",
        "expected_developer": "Jazz Digital Pakistan",
    },
    {
        "name": "JazzCash",
        "query": "JazzCash",
        "expected_app_id": "com.techlogix.mobilinkcustomer",
        "expected_developer": "JazzCash",
    },
    {
        "name": "Easypaisa",
        "query": "Easypaisa",
        "expected_app_id": "pk.com.telenor.phoenix",
        "expected_developer": "Easypaisa Bank Limited",
    },
    {
        "name": "Zong",
        "query": "Zong Pakistan",
        "expected_app_id": "com.zong.customercare",
        "expected_developer": "CMPak - Zong",
    },
    {
        "name": "Ufone",
        "query": "Ufone Pakistan",
        "expected_app_id": "com.ufoneselfcare",
        "expected_developer": "Pak Telecom Mobile Limited",
    },
)

SearchResult = dict[str, Any]
SearchFunction = Callable[..., list[SearchResult]]


def normalize_title(value: str) -> str:
    """Return a comparison form that ignores punctuation, whitespace, and case."""
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def choose_result(target: dict[str, str], results: Sequence[SearchResult]) -> SearchResult:
    """Choose an expected package ID or the closest title match from search results."""
    expected_app_id = target.get("expected_app_id")
    if expected_app_id:
        exact_match = next(
            (result for result in results if result.get("appId") == expected_app_id), None
        )
        if exact_match is not None:
            return exact_match

    if not results:
        raise ValueError(f"No Google Play results found for {target['name']!r}")

    expected_developer = normalize_title(target.get("expected_developer", ""))
    eligible_results = [
        result
        for result in results
        if not expected_developer
        or normalize_title(str(result.get("developer", ""))) == expected_developer
    ]
    if not eligible_results:
        raise ValueError(f"No official-developer result found for {target['name']!r}")

    target_title = normalize_title(target["name"])
    match = max(
        eligible_results,
        key=lambda result: (
            result.get("appId") is None,
            SequenceMatcher(
                None, target_title, normalize_title(str(result.get("title", "")))
            ).ratio(),
        ),
    )
    if expected_app_id and match.get("appId") not in (None, expected_app_id):
        raise ValueError(
            f"Google Play returned conflicting package ID for {target['name']!r}: "
            f"{match['appId']!r}"
        )
    return match


def resolve_targets(
    targets: Sequence[dict[str, str]] = DEFAULT_TARGETS,
    *,
    search_fn: SearchFunction = search,
) -> list[dict[str, Any]]:
    """Search the Pakistan store and return app records awaiting human confirmation."""
    resolved = []
    for target in targets:
        results = search_fn(target["query"], lang="en", country="pk", n_hits=10)
        match = choose_result(target, results)
        resolved.append(
            {
                "name": target["name"],
                "app_id": match.get("appId") or target.get("expected_app_id"),
                "store_title": match.get("title"),
                "developer": match.get("developer"),
                "query": target["query"],
                "confirmed": False,
            }
        )
    return resolved


def write_config(apps: Sequence[dict[str, Any]], output_path: Path) -> None:
    """Write resolved apps to YAML without marking any result as confirmed."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as config_file:
        yaml.safe_dump(
            {"apps": list(apps)},
            config_file,
            sort_keys=False,
            allow_unicode=True,
        )


def parse_args() -> argparse.Namespace:
    """Parse command-line options."""
    parser = argparse.ArgumentParser(
        description="Resolve Phase 1 target apps from the Pakistan Google Play storefront."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    """Resolve the default targets and write a human-reviewable app config."""
    args = parse_args()
    apps = resolve_targets()
    write_config(apps, args.output)
    print(f"Wrote {len(apps)} unconfirmed app records to {args.output}")
    print("Review each package ID and set confirmed: true before scraping reviews.")


if __name__ == "__main__":
    main()
