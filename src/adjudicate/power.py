"""Test a subgroup difference, and state what the design could have detected.

A null result is unreadable without its power. "No difference between groups" and
"this study could not have found one" produce identical tables, and the distinction is
the entire claim. Reporting the minimum detectable effect alongside the p-value turns
"we found nothing" into "nothing larger than N exists here", which is a real finding.

The test is a permutation test rather than chi-square: it assumes nothing about the
distribution and stays valid at the cell sizes this kind of study actually reaches.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict

Z_ALPHA = 1.959964  # two-sided 5%
Z_BETA = 0.841621  # 80% power


def spread(outcomes: list[tuple[str, bool]]) -> float:
    """Largest minus smallest per-group success rate."""
    cells: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for group, correct in outcomes:
        cells[group][1] += 1
        cells[group][0] += correct
    rates = [hits / total for hits, total in cells.values() if total]
    return max(rates) - min(rates) if len(rates) > 1 else 0.0


def permutation_test(
    outcomes: list[tuple[str, bool]], *, rounds: int = 20000, seed: int = 0
) -> tuple[float, float]:
    """Observed spread, and the share of label shuffles that match or exceed it.

    Shuffling the group labels breaks any real association while preserving both the
    group sizes and the overall success rate, so the shuffled distribution is exactly
    what chance alone produces for this dataset.
    """
    observed = spread(outcomes)
    groups = [group for group, _ in outcomes]
    results = [correct for _, correct in outcomes]
    rng = random.Random(seed)
    at_least = 0
    for _ in range(rounds):
        rng.shuffle(groups)
        if spread(list(zip(groups, results, strict=True))) >= observed:
            at_least += 1
    return observed, at_least / rounds


def minimum_detectable_effect(baseline: float, n_per_group: int) -> float:
    """Smallest two-group difference detectable at 80% power, two-sided 5%."""
    if n_per_group <= 0:
        return 1.0
    return (Z_ALPHA + Z_BETA) * math.sqrt(2 * baseline * (1 - baseline) / n_per_group)


def required_n(baseline: float, effect: float) -> int:
    """Group size needed to detect a difference of `effect` at 80% power."""
    if effect <= 0:
        return 0
    return math.ceil(2 * baseline * (1 - baseline) * ((Z_ALPHA + Z_BETA) / effect) ** 2)
