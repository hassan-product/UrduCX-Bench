"""Score models against human judgements.

Three corrections are applied by default, because each one, omitted, moves a headline
number by more than the effects being measured:

  skipped items are excluded   An unanswered item is not a wrong answer. Left in the
                               denominator it is scored as a model failure, and if
                               skips fall unevenly across subgroups it manufactures a
                               difference between them.
  regimes are not pooled       Judgements made with predictions visible are excluded
                               unless asked for, and reported separately when included.
  enrichment is reweighted     A set drawn to over-represent disagreements measures
                               accuracy far below the truth. Reweighting to the
                               population rate is the difference between 38% and 61%.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict

from src.adjudicate.items import Item, Judgement


def wilson(hits: int, total: int, z: float = 1.959964) -> tuple[float, float]:
    """Wilson score interval - honest at small cell sizes, unlike a normal approximation."""
    if total == 0:
        return (0.0, 0.0)
    proportion = hits / total
    denominator = 1 + z * z / total
    centre = (proportion + z * z / (2 * total)) / denominator
    margin = (
        z
        / denominator
        * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total))
    )
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def cohens_kappa(pairs: list[tuple[str, str]]) -> float:
    """Agreement corrected for what chance alone would produce."""
    if not pairs:
        return float("nan")
    total = len(pairs)
    observed = sum(1 for a, b in pairs if a == b) / total
    first, second = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    expected = sum(
        first[label] / total * second[label] / total
        for label in set(first) | set(second)
    )
    return (observed - expected) / (1 - expected) if expected < 1 else float("nan")


def usable(
    items: list[Item],
    judgements: dict[str, Judgement],
    *,
    include_unblind: bool = False,
) -> list[tuple[Item, Judgement]]:
    """Item/judgement pairs eligible for scoring, with the exclusions applied."""
    pairs = []
    for item in items:
        judgement = judgements.get(item.id)
        if judgement is None or not judgement.usable:
            continue
        if not judgement.blind and not include_unblind:
            continue
        pairs.append((item, judgement))
    return pairs


def accuracy(pairs: list[tuple[Item, Judgement]], model: str) -> tuple[int, int]:
    """Hits and total for one model over the scored pairs."""
    answered = [(i, j) for i, j in pairs if i.predictions.get(model)]
    hits = sum(1 for i, j in answered if i.predictions[model] == j.label)
    return hits, len(answered)


def by_group(
    pairs: list[tuple[Item, Judgement]], model: str, key: str
) -> dict[str, tuple[int, int]]:
    """Accuracy split by a metadata field, e.g. language or product."""
    cells: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for item, judgement in pairs:
        if not item.predictions.get(model):
            continue
        cell = cells[str(item.meta.get(key))]
        cell[1] += 1
        cell[0] += item.predictions[model] == judgement.label
    return {group: (hits, total) for group, (hits, total) in cells.items()}


def joint_error(pairs: list[tuple[Item, Judgement]]) -> tuple[int, int]:
    """How often every model agreed with the others and all were wrong.

    This is the number inter-model agreement cannot reach. Where models concur they
    look confident, and a pipeline that treats concurrence as truth adopts these
    errors without ever surfacing them.
    """
    controls = [(i, j) for i, j in pairs if i.is_control]
    wrong = sum(
        1 for i, j in controls if next(iter(i.predictions.values())) != j.label
    )
    return wrong, len(controls)


def reweighted_accuracy(
    pairs: list[tuple[Item, Judgement]], model: str, population_agreement_rate: float
) -> float | None:
    """Accuracy corrected for over-sampling of disagreements.

    Judging mostly hard cases is the right way to study disagreement and the wrong way
    to measure accuracy. Weighting each stratum by its share of the population undoes
    the distortion; without it the reported figure is far below the truth.
    """
    agree = [(i, j) for i, j in pairs if i.is_control]
    disagree = [(i, j) for i, j in pairs if not i.is_control and i.predictions]
    if not agree or not disagree:
        return None
    agree_hits, _ = accuracy(agree, model)
    disagree_hits, _ = accuracy(disagree, model)
    return (
        population_agreement_rate * (agree_hits / len(agree))
        + (1 - population_agreement_rate) * (disagree_hits / len(disagree))
    )
