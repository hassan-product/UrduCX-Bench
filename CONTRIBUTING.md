# Contributing

Thank you for helping improve UrduCX-Bench. Contributions should keep the benchmark reproducible,
privacy-preserving, and useful across model providers.

## Development workflow

1. Create a focused branch from `main`.
2. Set up the environment using the instructions in `README.md`.
3. Add or update tests for behavioral changes.
4. Run `ruff check .` and `pytest` before opening a pull request.
5. Explain the motivation, behavior change, and validation in the pull request description.

Keep changes within one build phase where practical. Do not include paid evaluations in continuous
integration.

## Data contributions

Do not commit raw app-store reviews, credentials, reviewer identities, phone numbers, national ID
numbers, account details, email addresses, or other personally identifying information. Derived
benchmark items must pass the project's scrubbing and validation checks before review.

Record the source, intended use, and license of every external dataset in `DATA_LICENSES.md`.
Content without clear redistribution rights cannot be included in a release.

Policy-reasoning items must use fictional operators and original policy text. Reports should state
measurements neutrally and must not make legal claims about named companies.

## Benchmark changes

Changes to labels, scoring, prompts, splits, or released items affect comparability. Include a
rationale, migration note, and tests, and propose a version change when existing scores may shift.

## Reporting sensitive issues

Do not open a public issue containing leaked credentials or personal data. Contact the repository
maintainer privately through the security contact listed on the repository profile.
