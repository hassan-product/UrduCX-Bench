"""Generate and validate the human-authored Phase 2.5 script-gap pilot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.label.taxonomy import load_taxonomy

LANGUAGE_FORMS = ("urdu_script", "roman_urdu", "code_switched", "english")
COMPLAINT_COUNT = 20
DEFAULT_TEMPLATE = Path("spike/phase2_5/complaints.json")
DEFAULT_TAXONOMY = Path("config/taxonomy.yaml")

REQUIRED_SCENARIO_GROUPS = {
    "unauthorized deduction/VAS": {"unauthorized_vas_deduction"},
    "failed transfer with deduction": {"transfer_failed_money_deducted"},
    "OTP/login failure": {"otp_not_received", "login_failure"},
    "KYC/account block": {"kyc_verification_stuck", "account_blocked_frozen"},
    "network/service complaint": {
        "network_coverage_complaint",
        "data_speed_complaint",
        "service_outage_report",
    },
}


def build_template() -> dict[str, Any]:
    """Return 20 empty complaint slots without generating human-owned content."""
    return {
        "schema_version": 1,
        "complaints": [
            {
                "complaint_id": f"pilot-{index:02d}",
                "gold_intent": "",
                "variants": {
                    language: {"text": "", "fact_span": ""} for language in LANGUAGE_FORMS
                },
            }
            for index in range(1, COMPLAINT_COUNT + 1)
        ],
    }


def validate_pilot(payload: dict[str, Any], *, valid_intents: set[str]) -> None:
    """Reject incomplete, inconsistent, or out-of-taxonomy pilot authoring."""
    if payload.get("schema_version") != 1:
        raise ValueError("schema_version must be 1")

    complaints = payload.get("complaints")
    if not isinstance(complaints, list) or len(complaints) != COMPLAINT_COUNT:
        raise ValueError(f"Pilot must contain exactly {COMPLAINT_COUNT} complaints")

    seen_ids: set[str] = set()
    observed_intents: set[str] = set()
    for complaint in complaints:
        complaint_id = str(complaint.get("complaint_id", "")).strip()
        if not complaint_id or complaint_id in seen_ids:
            raise ValueError(f"Missing or duplicate complaint_id: {complaint_id!r}")
        seen_ids.add(complaint_id)

        gold_intent = str(complaint.get("gold_intent", "")).strip()
        if gold_intent not in valid_intents:
            raise ValueError(f"{complaint_id}: invalid gold_intent {gold_intent!r}")
        observed_intents.add(gold_intent)

        variants = complaint.get("variants")
        if not isinstance(variants, dict) or set(variants) != set(LANGUAGE_FORMS):
            raise ValueError(
                f"{complaint_id}: variants must be exactly {', '.join(LANGUAGE_FORMS)}"
            )
        for language in LANGUAGE_FORMS:
            variant = variants[language]
            if not isinstance(variant, dict):
                raise ValueError(f"{complaint_id}/{language}: variant must be an object")
            text = str(variant.get("text", "")).strip()
            fact_span = str(variant.get("fact_span", "")).strip()
            if not text:
                raise ValueError(f"{complaint_id}/{language}: text is required")
            if not fact_span or fact_span not in text:
                raise ValueError(f"{complaint_id}/{language}: fact_span must occur exactly in text")

    missing_groups = [
        name
        for name, intents in REQUIRED_SCENARIO_GROUPS.items()
        if observed_intents.isdisjoint(intents)
    ]
    if missing_groups:
        raise ValueError(f"Pilot is missing required scenario groups: {', '.join(missing_groups)}")


def load_payload(path: Path) -> dict[str, Any]:
    """Load one pilot authoring document."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Pilot document must be a JSON object")
    return payload


def write_template(path: Path, *, force: bool = False) -> None:
    """Write the blank private template without overwriting human work by default."""
    if path.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite existing pilot file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(build_template(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    """Parse template-generation and validation options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "validate"))
    parser.add_argument("--path", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Create a blank pilot or validate completed human authoring."""
    args = parse_args()
    if args.command == "init":
        write_template(args.path, force=args.force)
        print(f"Wrote {COMPLAINT_COUNT}-complaint authoring template to {args.path}")
        return

    taxonomy = load_taxonomy(args.taxonomy)
    validate_pilot(
        load_payload(args.path),
        valid_intents={intent.id for intent in taxonomy.intents},
    )
    print(f"Validated {COMPLAINT_COUNT} complaints and {COMPLAINT_COUNT * 4} language variants")


if __name__ == "__main__":
    main()
