"""Choose which items go in front of the annotator, and in what order.

Selection is deliberately narrow. How items are drawn from a corpus - stratified,
matched, enriched - is the study's business and belongs upstream, in whatever produces
the items file. This module only decides which of those items still need a judgement,
and shuffles them so annotator drift cannot land on one subgroup.

That shuffle is not cosmetic. Standards move over a long session: people get faster,
stricter, more willing to reach for a catch-all. If a subgroup is judged in one block,
that drift lands entirely on it and is indistinguishable from a real effect.
"""

from __future__ import annotations

import random
from collections.abc import Callable

from src.adjudicate.items import Item, Judgement


def build_worklist(
    items: list[Item],
    judgements: dict[str, Judgement],
    *,
    mode: str = "all",
    limit: int | None = None,
    seed: int = 0,
    label_version: int = 0,
    needs_revisit: Callable[[Item, Judgement], bool] | None = None,
) -> list[Item]:
    """Return the items still to judge, shuffled.

    all       everything not yet judged
    controls  only items the models already agree on, not yet judged - these are what
              make joint model error visible, and inter-model agreement never can
    recheck   items already judged, served again for a blind test-retest. Where no
              second annotator is available, self-agreement is the measurable
              substitute: it cannot show whether one person is right, but it does show
              whether the task is stable or arbitrary.
    revisit   items judged under an older label version, so a change to the label set
              reopens exactly the judgements it could have altered and nothing else
    """
    rng = random.Random(seed)

    if mode == "recheck":
        pool = [i for i in items if i.id in judgements]
    elif mode == "revisit":
        pool = [
            i
            for i in items
            if (j := judgements.get(i.id))
            and j.label_version < label_version
            and (needs_revisit is None or needs_revisit(i, j))
        ]
    elif mode == "controls":
        pool = [i for i in items if i.is_control and i.id not in judgements]
    else:
        pool = [i for i in items if i.id not in judgements]

    rng.shuffle(pool)
    return pool[:limit] if limit else pool


def progress(worklist: list[Item], judgements: dict[str, Judgement], mode: str,
             label_version: int) -> tuple[int, int]:
    """Done and total for this pass.

    Counted against this worklist, never against every judgement ever made: a controls
    or revisit pass shares its output file with the main one, and counting the file
    would report progress far beyond the pass being run.
    """
    if mode == "revisit":
        done = sum(
            1
            for i in worklist
            if (j := judgements.get(i.id)) and j.label_version >= label_version
        )
    else:
        done = sum(1 for i in worklist if i.id in judgements)
    return done, len(worklist)
