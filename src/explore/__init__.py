"""Browse the review corpus locally: filter, aggregate, and export slices to judge.

Runs entirely on the machine holding the data and makes no network calls of any kind.
The corpus is public review text, but republishing it is a different act from reading it,
and the tool defaults to the version that keeps that choice open.

The dividing line this module holds to: every dimension here is either recorded on the
row or arithmetic over it. Issue types are shown only where a real label exists. Keyword
matches are offered as a way to find reviews, never as a way to classify them - the study
this corpus comes from measured that shortcut at 70% precision and seventeen times blinder
on Urdu script than on English, which makes it a search box and not a classifier.
"""

from src.explore.corpus import Corpus, Filters, load_corpus

__all__ = ["Corpus", "Filters", "load_corpus"]
