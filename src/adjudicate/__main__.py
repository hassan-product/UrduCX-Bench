"""Command line entry point: `python -m src.adjudicate`.

Two subcommands. `judge` collects human labels; `score` reports what they say about the
models. They are separate because the first needs a person and the second does not, and
running the second repeatedly while the first is still in progress is the normal way to
work.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from src.adjudicate.demo import build as build_demo
from src.adjudicate.items import load_items, load_judgements
from src.adjudicate.labels import load_labels
from src.adjudicate.power import minimum_detectable_effect, permutation_test, required_n
from src.adjudicate.scoring import (
    accuracy,
    by_group,
    cohens_kappa,
    joint_error,
    usable,
    wilson,
)
from src.adjudicate.server import Session, serve


def _rate(label: str, hits: int, total: int, width: int = 26) -> str:
    """One rate row with its interval."""
    if total == 0:
        return f"  {label:<{width}}       no data"
    low, high = wilson(hits, total)
    return (
        f"  {label:<{width}} {hits:4d}/{total:<4d} {hits / total * 100:5.1f}%"
        f"  [{low * 100:4.1f},{high * 100:5.1f}]"
    )


def judge(args: argparse.Namespace) -> None:
    """Open the application: judging and results, with the pass selectable inside it."""
    if args.demo:
        # Real evaluation data is customer text and does not travel, so a demo needs
        # something invented to open. Everything downstream behaves identically.
        directory = Path(args.demo)
        args.items, args.labels, args.out = build_demo(directory)
        print(f"demo dataset written to {directory}\n")
    serve(
        Session(
            items=load_items(args.items),
            labels=load_labels(args.labels),
            output=args.out,
            mode=args.mode,
            blind=not args.show_predictions,
            seed=args.seed,
            limit=args.limit,
            title=args.items.name,
        ),
        port=args.port,
    )


def score(args: argparse.Namespace) -> None:
    """Report accuracy, agreement, joint error, and subgroup power."""
    items = load_items(args.items)
    judgements = load_judgements(args.gold)
    pairs = usable(items, judgements, include_unblind=args.include_unblind)

    excluded = len(judgements) - len(pairs)
    print(f"{len(items)} items, {len(judgements)} judged, {len(pairs)} scored")
    if excluded:
        print(f"  ({excluded} excluded: skipped, or judged with predictions visible)")

    models = sorted({m for i, _ in pairs for m in i.predictions})
    if not models:
        print("\nNo model predictions in this dataset - nothing to score against.")
        return

    print("\nACCURACY AGAINST HUMAN JUDGEMENT")
    for model in models:
        hits, total = accuracy(pairs, model)
        print(_rate(model, hits, total))

    wrong, controls = joint_error(pairs)
    if controls:
        print("\nWHERE EVERY MODEL AGREED WITH THE OTHERS")
        print(_rate("all agreed and all wrong", wrong, controls))
        print("  Inter-model agreement cannot surface this case; only human labels can.")

    if len(models) > 1:
        print("\nINTER-MODEL AGREEMENT")
        first, second = models[0], models[1]
        both = [
            (i.predictions[first], i.predictions[second])
            for i, _ in pairs
            if i.predictions.get(first) and i.predictions.get(second)
        ]
        same = sum(1 for a, b in both if a == b)
        print(_rate(f"{first} vs {second}", same, len(both)))
        print(f"  Cohen's kappa {cohens_kappa(both):.3f}")

    if args.by:
        for model in models:
            cells = by_group(pairs, model, args.by)
            if len(cells) < 2:
                continue
            print(f"\nBY {args.by.upper()} — {model}")
            for group, (hits, total) in sorted(cells.items()):
                print(_rate(group, hits, total))
            outcomes = [
                (str(i.meta.get(args.by)), i.predictions[model] == j.label)
                for i, j in pairs
                if i.predictions.get(model)
            ]
            observed, p = permutation_test(outcomes, rounds=args.rounds, seed=args.seed)
            smallest = min(total for _, total in cells.values())
            hits_all, total_all = accuracy(pairs, model)
            baseline = hits_all / total_all if total_all else 0.5
            mde = minimum_detectable_effect(baseline, smallest)
            verdict = "significant" if p < 0.05 else "no significant difference"
            print(f"    spread {observed * 100:.1f} pts, p = {p:.3f} — {verdict}")
            print(
                f"    this design could detect {mde * 100:.0f} pts at 80% power"
                f" (n={smallest} in the smallest group)"
            )
            if mde > observed:
                need = required_n(baseline, observed)
                print(
                    f"    a difference this size would need n={need} per group to confirm;"
                    " read the null as a bound, not a zero"
                )


def main() -> None:
    """Parse arguments and dispatch."""
    parser = argparse.ArgumentParser(prog="python -m src.adjudicate", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    j = sub.add_parser("judge", help="open the app: judge items and view results")
    j.add_argument("--items", type=Path, help="JSONL of items")
    j.add_argument("--labels", type=Path, help="YAML label set")
    j.add_argument("--out", type=Path, help="JSONL to write judgements to")
    j.add_argument(
        "--demo",
        nargs="?",
        const="demo_data",
        default=None,
        metavar="DIR",
        help="generate a synthetic dataset and open it; needs no data of your own",
    )
    j.add_argument(
        "--mode",
        choices=("all", "controls", "recheck", "revisit"),
        default="all",
        help="pass to open on; switchable in the interface",
    )
    j.add_argument("--limit", type=int, default=None)
    j.add_argument("--seed", type=int, default=0)
    j.add_argument("--port", type=int, default=8790)
    j.add_argument(
        "--show-predictions",
        action="store_true",
        help="show model answers before judging; records blind=false on every item",
    )
    j.set_defaults(func=judge)

    s = sub.add_parser("score", help="score models against the human labels")
    s.add_argument("--items", type=Path, required=True)
    s.add_argument("--gold", type=Path, required=True)
    s.add_argument("--by", default=None, help="metadata field to split on, e.g. language")
    s.add_argument("--rounds", type=int, default=20000)
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--include-unblind", action="store_true")
    s.set_defaults(func=score)

    args = parser.parse_args()
    if getattr(args, "demo", None) is None and args.command == "judge":
        missing = [n for n in ("items", "labels", "out") if getattr(args, n) is None]
        if missing:
            parser.error(f"judge needs --{', --'.join(missing)}, or --demo to generate a dataset")
    args.func(args)


if __name__ == "__main__":
    main()
