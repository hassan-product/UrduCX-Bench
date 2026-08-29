"""Blind adjudication and scoring for classification evaluation.

Built for a study of Urdu and Roman-Urdu customer complaints, but the tooling is
domain-agnostic: it takes a JSONL of items with optional model predictions, collects
human judgements under a protocol designed to keep them independent, and scores the
models against them.

Distinct from `src.eval`, which the project plan reserves for the model-running harness
(provider adapters, prompt templates, per-task scoring). This package is about the
human side: what the correct answer was, and how confidently that can be claimed.

The protocol matters more than the code. Three properties are enforced rather than
suggested, because each one, left to discipline, quietly stops holding:

  blind by default   Model predictions are withheld from the item payload entirely, not
                     hidden in the interface. Being shown two candidate labels and asked
                     which is better produces a preference survey, not a gold label.
  controls           Items where the models already agree are mixed in and made
                     indistinguishable, so the record can show the annotator was not
                     simply siding with a preferred model - and so the case where every
                     model is confidently wrong together stays visible.
  regimes stay apart Judgements record whether they were blind and which label version
                     they were made under, so two protocols are never silently pooled.
"""

from src.adjudicate.items import Item, Judgement, load_items, load_judgements
from src.adjudicate.worklist import build_worklist

__all__ = ["Item", "Judgement", "build_worklist", "load_items", "load_judgements"]
