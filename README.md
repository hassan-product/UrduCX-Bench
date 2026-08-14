# UrduCX-Bench

UrduCX-Bench is an open benchmark for evaluating customer-service language models on Urdu,
Roman Urdu, and Urdu-English code-switched text in telecom and mobile-wallet settings.

## Status

The repository scaffold is complete. Data collection, benchmark construction, model evaluation,
and publication will be developed in documented phases. No benchmark results are available yet.

## Scope

UrduCX-Bench is designed to measure five capabilities:

- intent classification across billing, account, payments, safety, network, and product requests;
- robustness across Urdu script, Roman Urdu, English, and code-switched expressions;
- extraction of complaint facts such as amounts, dates, references, and service names;
- policy-grounded eligibility decisions with an emphasis on avoiding false authorization; and
- safe handling of injection attempts, impersonation, abuse, and out-of-scope requests.

This project evaluates text models. It does not provide a chatbot, train models, use proprietary
operator data, or evaluate speech in its first release.

## Development setup

UrduCX-Bench requires Python 3.11 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
pre-commit install
```

Copy `.env.example` to `.env` only when a later phase requires external services. Never commit
credentials.

Run the local checks with:

```bash
ruff check .
pytest
```

## Repository layout

- `config/`: app, taxonomy, model, and fictional policy configuration.
- `src/`: collection, preparation, labelling, benchmark, evaluation, and publishing modules.
- `data/release/`: distributable benchmark artifacts; raw and interim data remain local.
- `tests/`: focused tests for privacy-sensitive preparation and scoring behavior.
- `results/`: reproducible model evaluation outputs.
- `notebooks/`: reports and exploratory analysis.
- `leaderboard/`: source for the public leaderboard.

## Data and privacy

Raw reviews are not redistributed. Collection code must omit reviewer identity, enforce a maximum
request rate of one request per second, and support checkpointed retries. Personally identifying
information must be scrubbed and tested before any derived item is published. External dataset
licenses are recorded in `DATA_LICENSES.md` before use.

## Roadmap

Future releases may add speech evaluation, regional Pakistani languages, and multi-turn
conversations. Those tracks are outside the first release.

## Contributing

See `CONTRIBUTING.md` for development and data-handling requirements.

## License and citation

Source code is licensed under the Apache License 2.0. Released benchmark data will be licensed
under CC BY 4.0 unless a release manifest states otherwise. Citation metadata is available in
`CITATION.cff`.

```bibtex
@misc{urducxbench2026,
	author = {{UrduCX-Bench Contributors}},
	title = {UrduCX-Bench: Customer-Service Evaluation for Urdu and Roman Urdu},
	year = {2026},
	url = {https://github.com/hassan-product/UrduCX-Bench}
}
```
