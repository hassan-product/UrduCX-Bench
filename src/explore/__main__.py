"""Command line entry point: `python -m src.explore`.

Loads the corpus and serves it locally. No arguments are required: the defaults point at
the paths the rest of the project already writes to.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from src.explore.corpus import CORPUS, load_corpus
from src.explore.server import Session, serve


def main() -> None:
    """Parse arguments and serve."""
    parser = argparse.ArgumentParser(prog="python -m src.explore", description=__doc__)
    parser.add_argument("--corpus", type=Path, default=CORPUS, help="cleaned JSONL")
    parser.add_argument("--port", type=int, default=8800)
    parser.add_argument(
        "--no-refresh",
        action="store_true",
        help="exclude forward-collected reviews under data/raw/refresh",
    )
    args = parser.parse_args()

    corpus = load_corpus(args.corpus, include_refresh=not args.no_refresh)
    serve(Session(corpus=corpus), port=args.port)


if __name__ == "__main__":
    main()
