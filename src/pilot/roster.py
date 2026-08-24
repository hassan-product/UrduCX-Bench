"""Load and validate the Phase 2.5 pilot model roster."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

SUPPORTED_PROVIDERS = ("anthropic", "google")
REQUIRED_FIELDS = ("id", "provider", "label")


@dataclass(frozen=True)
class ModelSpec:
    """One system under test, with its local pricing and pacing settings."""

    id: str
    provider: str
    label: str
    price_per_mtok_input: float
    price_per_mtok_output: float
    min_request_interval: float
    effort: str | None
    disable_thinking: bool

    def estimate_usd(self, input_tokens: int, output_tokens: int) -> float:
        """Estimate spend for this model from token counts."""
        return (
            input_tokens / 1_000_000 * self.price_per_mtok_input
            + output_tokens / 1_000_000 * self.price_per_mtok_output
        )


def load_roster(path: Path) -> list[ModelSpec]:
    """Parse the roster, raising on unknown providers or duplicate model ids."""
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw_models = payload.get("models") or []
    if not raw_models:
        raise ValueError(f"No models configured in {path}; the pilot roster is empty")

    seen: set[str] = set()
    models: list[ModelSpec] = []
    for raw in raw_models:
        missing = [field for field in REQUIRED_FIELDS if not raw.get(field)]
        if missing:
            raise ValueError(f"Model entry missing fields: {missing}")

        provider = str(raw["provider"])
        if provider not in SUPPORTED_PROVIDERS:
            raise ValueError(
                f"{raw['id']}: unsupported provider {provider!r}; "
                f"expected one of {', '.join(SUPPORTED_PROVIDERS)}"
            )

        model_id = str(raw["id"])
        if model_id in seen:
            raise ValueError(f"Duplicate model id in roster: {model_id}")
        seen.add(model_id)

        models.append(
            ModelSpec(
                id=model_id,
                provider=provider,
                label=str(raw["label"]),
                price_per_mtok_input=float(raw.get("price_per_mtok_input", 0.0)),
                price_per_mtok_output=float(raw.get("price_per_mtok_output", 0.0)),
                min_request_interval=float(raw.get("min_request_interval", 0.5)),
                effort=str(raw["effort"]) if raw.get("effort") else None,
                disable_thinking=bool(raw.get("disable_thinking", False)),
            )
        )
    return models
