"""Generate a small synthetic dataset so the tool runs from a clean checkout.

Real evaluation data is customer text and does not travel. Without something to open,
the only way to show what the tool does is a screen recording of someone else's data,
which is worse than a working copy of a fake one.

The items here are invented support tickets. The point is not that they are realistic -
they are not - but that the interface, the passes, and every statistic behave exactly as
they do on real data, including the parts that only appear once numbers are thin.

Two properties are built into the fake predictions on purpose, because a demo where
everything agrees teaches the wrong lesson:

  the models disagree on roughly a fifth of items, which is what makes the controls pass
  and the joint-error figure mean anything;
  and one group is given a genuine deficit, so the subgroup test has something to find -
  while the sample stays small enough that the power line still says it cannot be sure.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

LABELS = {
    "billing": [
        ("charged_twice", "The customer was billed more than once for one purchase."),
        ("unexpected_fee", "A charge the customer says was never disclosed."),
        ("refund_not_received", "A refund was agreed but has not arrived."),
    ],
    "access": [
        ("cannot_sign_in", "Correct credentials are rejected at the login screen."),
        ("account_locked", "The provider has suspended or frozen the account."),
    ],
    "delivery": [
        ("never_arrived", "An order was paid for and never delivered."),
        ("wrong_item", "Something arrived, but not what was ordered."),
    ],
    "service": [
        ("no_response", "The provider never replied to a message or call."),
        ("rude_agent", "A staff member was hostile or dismissive."),
    ],
}

TEMPLATES = {
    "charged_twice": ["billed twice for order {n}", "two charges of {m} for one payment"],
    "unexpected_fee": ["a {m} fee nobody mentioned", "charged {m} extra with no warning"],
    "refund_not_received": ["refund promised {n} days ago, nothing yet"],
    "cannot_sign_in": ["password is right, it still says invalid", "cannot log in at all"],
    "account_locked": ["account frozen overnight, no explanation"],
    "never_arrived": ["order {n} paid for, never delivered"],
    "wrong_item": ["ordered one thing, received another entirely"],
    "no_response": ["messaged support {n} times, no reply"],
    "rude_agent": ["the agent was openly rude when I asked"],
}

REGIONS = ("north", "south", "east", "west")
SEED = 20260901


def write_labels(path: Path) -> None:
    """Write a label set in the format the tool reads."""
    lines = ["version: 1", "labels:"]
    for group, entries in LABELS.items():
        for label_id, definition in entries:
            other = next(i for i, _ in entries if i != label_id) if len(entries) > 1 else ""
            lines += [
                f"  - id: {label_id}",
                f"    group: {group}",
                f"    definition: {definition}",
                "    positive_examples:",
                f'      - "{TEMPLATES[label_id][0].format(n=3, m="$40")}"',
                f'      - "example of {label_id.replace("_", " ")}"',
                f'    negative_example: "a complaint that instead describes {other}"',
                "    negative_rationale: >-",
                f"      Names a different failure, so it belongs in {other}.",
            ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_items(path: Path, count: int = 120) -> None:
    """Write synthetic items with two models' predictions attached."""
    rng = random.Random(SEED)
    all_ids = [label_id for entries in LABELS.values() for label_id, _ in entries]

    rows = []
    for n in range(count):
        truth = rng.choice(all_ids)
        region = REGIONS[n % len(REGIONS)]
        text = rng.choice(TEMPLATES[truth]).format(n=rng.randint(2, 30), m=f"${rng.randint(5, 90)}")

        # One region is given a real deficit so the subgroup test has something to find.
        skill = 0.55 if region == "west" else 0.78
        first = truth if rng.random() < skill else rng.choice(all_ids)
        second = first if rng.random() < 0.8 else rng.choice(all_ids)

        rows.append(
            {
                "id": f"demo_{n:04d}",
                "text": text,
                "meta": {"region": region, "channel": "email" if n % 3 else "chat"},
                "predictions": {"model-alpha": first, "model-beta": second},
            }
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )


def build(directory: Path, count: int = 120) -> tuple[Path, Path, Path]:
    """Write a complete demo dataset; returns items, labels and output paths."""
    items, labels = directory / "demo_items.jsonl", directory / "demo_labels.yaml"
    write_items(items, count)
    write_labels(labels)
    return items, labels, directory / "demo_judgements.jsonl"
