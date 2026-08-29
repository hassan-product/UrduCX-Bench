# PROGRESS_LOG.md — UrduCX-Bench Project Memory

> **Purpose:** This is the project's persistent brain. Read this file first in any new
> session (alongside the local-only `PROJECT_CONTEXT_V2.md`, which holds the active build
> plan) to resume work with full context — no re-explaining required.
>
> **Update protocol:** This file is updated, committed, and pushed at the end of each
> working session (`wrap`). See "Session update protocol" at the bottom.

---

## 1. Project one-liner

UrduCX-Bench is an open benchmark measuring how well AI models handle real
customer-service conversations in Urdu, Roman Urdu, and Urdu-English code-switched
text, in the telecom/mobile-wallet domain. Solo builder, part-time, budget under $150.

The active spec lives in `PROJECT_CONTEXT_V2.md` (local-only, git-ignored — never
committed or pushed). It supersedes the original `PROJECT_CONTEXT.md` from 2026-08-18
onward.

---

## 2. Current status at a glance

| Phase | Status | Summary |
|---|---|---|
| 0 — Repo & environment setup | **Done** | Scaffold committed and pushed |
| 1 — Data collection | **Done** | 17 products collected; ~107.8k unique reviews; validator printed; human reviewed localhost previews |
| 2 — Cleaning, language & PII | **Done** | 54,519 cleaned; hardened typed PII matching supports three numeral systems; 9,000-item derived scrubbed file and human audit completed without overwriting source layers |
| 2.5 — Script-gap pilot | **Done** | 4 models, 320 classifications, $0.75. Script-gap hypothesis **not supported**; a taxonomy defect caused 61% of v1 errors; taxonomy raised to v2. The apparent consistency effect largely dissolved under v2, which is itself the finding: underspecified labels manufacture apparent script effects |
| 3 — Sampling & auto-labelling | **Diagnostic done; full run pending** | 500-item diagnostic across two models; starved-intent hunt and top-up over all 54,519 reviews; taxonomy raised to **v3 (26 intents)** after human adjudication exposed two missing categories, with both models re-labelled against it. The 9,000-item run remains deferred until the labelling is validated |
| 4 — Human verification | **Done** | 125 gold labels decomposing the agreement gap, plus 204 blind gold labels from a length-matched Urdu pass that settles the founding hypothesis. Remaining passes (50 controls, 50 blind re-check) are optional hardening, not blockers |
| 5 — Benchmark task building | Not started | Blocked on Phase 4 |
| 6 — Scoring harness | Not started | Blocked on Phase 5 |
| 7 — Publication | Not started | Blocked on Phase 6 |
| 8 — Distribution | Not started | Outreach and launch; not an engineering phase |

**Environment:** Phase 0 was developed in a cloud/web dev container. Phase 1 development
continues locally on macOS in a Python 3.13 virtual environment (`.venv/`). The project
uses `google-play-scraper==1.2.7` for Google Play and the public Apple iTunes RSS API
with `certifi==2026.7.22` for verified TLS. All raw data stays local and is git-ignored.

---

## 3. Work completed in detail (Phase 0)

- Initialised full directory skeleton per `PROJECT_CONTEXT.md` Section 10: `config/`,
  `data/{raw,interim,release}`, `src/{collect,prep,label,bench,eval/{adapters,prompts},publish}`,
  `results/`, `notebooks/`, `leaderboard/`, `tests/`.
- Added root docs: `README.md`, `LICENSE` (Apache-2.0 for code), `CONTRIBUTING.md`,
  `LIMITATIONS.md`, `DATA_LICENSES.md`, `CITATION.cff`, `REPORT.md` (placeholder).
- Added `pyproject.toml` (Python ≥3.11, `ruff` config, `pytest` config) and
  `requirements.txt` pinned to exact versions (`python-dotenv==1.2.2`, `PyYAML==6.0.3`
  at time of writing — Phase 0 only needs config/env loading; task-specific libraries
  like `google-play-scraper`, `pandas`, `datasets` etc. are added when their phase starts).
- Added `.pre-commit-config.yaml` (ruff check, ruff format, large-file check, merge-conflict
  check, YAML check, end-of-file fixer, mixed-line-ending check, trailing-whitespace check).
- Added `.github/workflows/ci.yml` — runs `ruff check` + `pytest` on every push. Deliberately
  does **not** run any paid evaluation step in CI.
- Added `.env.example` listing required secret variable names only (`OPENAI_API_KEY`,
  `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `HF_TOKEN`) with empty values. Real `.env` is
  git-ignored and was never created in this environment (no keys used yet).
- Placeholder config files created as empty/neutral scaffolds, deliberately **not**
  pre-filled with judgment calls that belong to the maintainer: `config/apps.yaml`,
  `config/models.yaml`, `config/taxonomy.yaml`, `config/policy_docs/README.md`.
- Created a local Python 3.12 virtual environment (`.venv/`, git-ignored), installed
  pinned dependencies, confirmed `ruff check` passes clean and `pytest` collects 0 tests
  and exits 0 (Phase 0's exact acceptance criterion).
- Set up `.gitignore` to exclude: secrets (`.env`), raw/interim data, caches
  (`outputs/cache/`, `.ruff_cache/`, `.pytest_cache/`), virtual environments, and editor
  metadata. Machine-specific local tooling state is excluded via `.git/info/exclude`
  instead, so it leaves no trace in the tracked repository (see decision log below).
- Committed (`chore: initialise repository scaffold`, commit `78733bc`) and pushed to
  `origin/main` on GitHub (`hassan-product/UrduCX-Bench`).

### Phase 1 progress

#### Job 1 — App resolution (complete)

- Added and pinned `google-play-scraper==1.2.7`.
- Added `src/collect/resolve_apps.py`. It searches the Pakistan Google Play storefront
  and resolves package IDs deterministically: it first attempts an exact match on the
  expected package ID, then falls back to developer-constrained title ranking. Any result
  with a conflicting non-null package ID raises rather than being silently written.
- **Why this design:** Google's search API sometimes returns the first result with
  `appId: null`, particularly for official flagship apps that dominate their own search
  query. The resolver accepts a null ID from the expected official result (recovering the
  known ID from config) while rejecting a *different* non-null ID from a competing app
  that shares the developer name.
- Resolved and human-confirmed five initial apps: SIMOSA, JazzCash, Easypaisa, My Zong,
  UPTCL/Ufone. Written to `config/apps.yaml` with `confirmed: true`.
- Added 5 focused resolver tests. Full suite passed (12 tests).

#### Job 2 — Google Play scraper (complete)

- Added `src/collect/scrape_reviews.py`. Key design choices:
  - **Rate limit:** minimum 1 second between requests, enforced by `RequestPacer`.
    The pacer is injected as a dependency so tests can stub it without any real sleep.
  - **Retry:** exponential backoff (2, 4, 8, 16 seconds) up to 4 attempts per page.
  - **Atomicity:** each page is written to a `.tmp` file, flushed, `fsync`-ed, then
    `os.replace()`-ed to its final path. The checkpoint is only updated *after* the page
    file exists. A crash between those two writes leaves the page but not the checkpoint,
    so the next run safely re-fetches and overwrites the same page rather than skipping it.
  - **Privacy:** stores exactly seven fields — `review_id`, `app_id`, `text`, `rating`,
    `timestamp`, `app_version`, `thumbs_up_count`. `userName`, `userImage`, and all
    other user-identifying fields are never written.
  - **Continuation tokens:** the pinned library returns `sort` as an integer in live
    tokens, not as a `Sort` enum member. The serializer handles both forms; a regression
    test covers the live integer shape discovered during the first real collection run.
- Added `src/collect/render_review_preview.py` for local browser inspection. The renderer
  validates that every record uses exactly the stored schema before building the HTML.
- Collected a 20-review SIMOSA sample to verify live API behaviour and browser preview.
  Discovered and fixed the integer token shape bug before full collection.
- Added 7 focused scraper and preview tests. All passed (12 tests total).
- Committed as `9f473af`.

#### Job 3 — Dual-platform source registry (complete)

**Decision to include Apple App Store:**
- The original Phase 1 spec only required Google Play, but restricting to one platform
  introduces selection bias: iPhone users may have different complaint patterns,
  income-related usage, and service expectations.
- Adding Apple as a separately labelled slice (not pooled with Google data) enables
  platform-comparison analysis without distorting the corpus.

**Why "Jazz" required explicit disambiguation:**
- The Jazz brand encompasses at least eight distinct applications on both stores:
  SIMOSA, JazzCash, Jazz Business World, JazzCash Business, JazzCash Retailer, DOST,
  ROX, FikrFree, and Tamasha. These products have different package identities, separate
  developer names in some cases, and completely different user populations (consumer,
  merchant, enterprise, agent, entertainment).
- The strategy adopted: every review is permanently joined to its exact platform identity
  (`platform_app_id`) and a canonical `product_id` defined in the source registry. A
  JazzCash review can never be counted as a SIMOSA review simply because both reference
  "Jazz" in their store titles or share a parent company.
- Apple track IDs were independently verified through the public Apple Search API
  (`itunes.apple.com/search`). SIMOSA is track `1441912305` and JazzCash is
  `1224617688` — different numeric IDs, different bundle IDs, different app categories —
  confirmed by cross-referencing search cross-results and direct store page responses.

**Registry structure (`config/source_registry.yaml`):**
- 17 products (11 core, 6 adjacent), 33 platform listings.
- Each product records: `product_id`, `display_name`, `brand_group`, `vertical`,
  `audience`, `inclusion_tier`, and a list of platform listings.
- Each listing records: `platform`, `platform_app_id`, `bundle_id`, `store_title`,
  `developer`, `store_url`, `confirmed`.
- Schema validation enforces: unique `(platform, platform_app_id)` pairs across the
  entire registry; store URLs must match their declared platform host; core products must
  have listings on both platforms before the validator passes.
- JazzCash Retailer is the single Google-only product — no Apple Pakistan listing exists.

**Core vs adjacent distinction:**
- **Core (11 products):** SIMOSA, My Zong, UPTCL/Ufone, My Telenor, JazzCash, Easypaisa,
  UPaisa, DOST/Mobilink Bank, SadaPay, NayaPay, Zindigi. These cover the primary
  telecom self-care, consumer wallet, and digital banking verticals that are central to
  the benchmark's problem statement.
- **Adjacent (6 products):** ROX (youth telecom), Jazz Business World (enterprise),
  JazzCash Business (merchant wallet), JazzCash Retailer (agent), FikrFree (insurance),
  Tamasha (entertainment). Included to broaden language register and complaint-type
  diversity, but not counted toward the core acceptance criteria.

**Human approval gate:**
- The registry browser (`data/raw/source_registry_preview/index.html`) exposes all 33
  listings with Platform, Tier, Vertical, Brand, and Status filters plus direct
  clickable store links for manual verification. The maintainer confirmed all 33 listings.
- Committed as part of `33ea30a`.

#### Job 4 — Shared schema and Apple collector (complete)

- Added `src/collect/review_schema.py` defining the canonical nine-field schema:
  `review_id`, `platform`, `platform_app_id`, `product_id`, `text`, `rating`,
  `timestamp`, `app_version`, `helpful_count`. The `platform`, `platform_app_id`, and
  `product_id` fields added to the original seven-field Google schema allow every stored
  record to be unambiguously joined back to one registry listing without re-reading
  any config at query time.
- Migrated `scrape_reviews.py` to emit the shared schema; `REVIEW_FIELDS` is re-exported
  for backward compatibility with the preview renderer.
- Added `src/collect/scrape_apple_reviews.py`. Key differences from the Google collector:
  - Uses the public Apple iTunes RSS API (`itunes.apple.com/pk/rss/customerreviews/…`),
    which requires no authentication but caps access at 10 pages × 50 reviews = 500
    reviews per listing per storefront.
  - HTTP requests use `certifi`'s pinned CA bundle (`certifi==2026.7.22`) to work around
    the macOS Python 3.13 system certificate-chain issue that blocks standard HTTPS in
    this environment. `curl` was confirmed to work; the Apple collector uses the same
    verified TLS approach.
  - Page completeness is detected by `len(entries) < 50` (short page means last page)
    or `page_number == 10` (hard API ceiling). Both conditions set `complete: true` in
    the checkpoint.
  - Same atomic write + checkpoint-after-page guarantee as the Google collector.
  - Reviewer identity: Apple RSS entries include an `author` dict with a `name` label.
    The serializer reads only `id`, `content`, `im:rating`, `updated`, `im:version`, and
    `im:voteCount` — the author field is never referenced and thus never stored.
- Ran Apple collection for all 16 approved Apple listings. Result: 5,483 reviews,
  9 listings at the 500-review ceiling, 0 duplicate review IDs. This collection is
  complete — Apple's public access window is fully exhausted.
- Added 4 focused Apple collector tests. Suite now 24 tests.

#### Job 5 — Cross-platform availability census (complete)

- Added `src/collect/collect_google_census.py`. It collects one 200-review recent page
  plus aggregate store metadata (`reviews`, `ratings`, `score`) per approved Google
  listing, writing results to `data/raw/availability_census/google_metadata.json`.
  Purpose: measure observable supply before committing to full collection quotas.
- Added `src/collect/render_availability_census.py`. It builds a census JSON from
  persisted page files and Google metadata, then renders a self-contained HTML report
  with Platform and Tier filters, per-listing supply, observed date windows, and rating
  distributions. The census intentionally separates Google store-reported totals from
  Apple publicly accessible counts — combining them into one "total" would be misleading
  because the two measures have different precision and meaning.
- Ran the bounded census: 3,400 Google reviews sampled (200 per listing) + 5,483 Apple
  already complete = 8,883 observed records. Zero duplicate IDs. All 8,883 records
  verified to use the exact nine-field schema with no reviewer identity keys.
- **What the census revealed (and why it changed the quota plan):**
  - Google lifetime totals vary from 436 (Jazz Business World) to 533,896 (Easypaisa),
    a 1,200× range. Equal per-product quotas are therefore both infeasible for low-volume
    products and wasteful for high-volume ones.
  - DOST, FikrFree, and Jazz Business World have total supply below any reasonable
    per-product floor. They will contribute all available reviews rather than a target quota.
  - Apple accessible supply varies from 11 (Jazz Business World) to 500 at the ceiling.
    Apple already contributes what it can; there is no further Apple collection to run.
- Census UI redesigned in the same session to match the source registry visual design
  system (same CSS variables, badge components, label+select controls, structured table
  header), so both localhost pages share a consistent inspection experience.

#### Job 6 — Collection quotas (confirmed)

**Why the original 40,000–60,000 target was revised:**
- The original spec was written for 5 primary products. With 17 products and 2 platforms,
  a 50,000-review corpus averages fewer than 3,000 per product — too shallow for the
  stratified labeling sample that Phase 3 requires (8,000–10,000 records balanced across
  product, language class, rating, and date).
- At 100,000 Google reviews, high-volume products are capped individually (6,000–12,000
  each) and low-volume products contribute their full available supply.

**Confirmed per-product Google quotas (`config/collection_quotas.yaml`):**

| Product | Google quota | Rationale |
|---|---:|---|
| Easypaisa | 12,000 | Largest supply (533k); highest consumer complaint volume |
| SIMOSA, My Telenor, JazzCash, My Zong | 10,000 each | Core products, strong supply (223k–311k) |
| UPTCL / Ufone | 8,000 | Core product, 115k available |
| Tamasha, SadaPay, NayaPay, Zindigi | 6,000 each | Good supply; diverse verticals |
| UPaisa, JazzCash Business | 5,000 each | Moderate supply |
| ROX | 4,000 | Adjacent; 6.4k available |
| JazzCash Retailer | 2,000 | Agent-facing app; ~2k available |
| DOST | 1,229 | Full supply; constrained |
| FikrFree | 590 | Full supply; constrained |
| Jazz Business World | 436 | Full supply; constrained |
| **Total** | **~102,255** | |

**Combined target: ~107,500 reviews** (102k Google + 5,483 Apple already collected).

**Why 100k is within budget:**
- Google Play scraping has no API cost; the only constraint is time and the 1 req/sec
  rate limit. At 200 reviews per request, 100k requires ~500 requests ≈ 8–9 minutes of
  wall-clock time.
- Phase 3 auto-labeling samples only 8,000–10,000 records; the raw corpus beyond that is
  not labeled and does not increase LLM cost. More raw material improves stratification
  quality without increasing the labeling budget.

#### Job 7 — Quota-aware Google scraper and full 17-product collection (complete)

- Updated `src/collect/scrape_reviews.py` to read `config/collection_quotas.yaml` via
  `load_quotas()`. Each app now stops after the first page that reaches its per-product
  `max_reviews` cap. Hitting quota does **not** set `complete: true`, so a later quota
  raise can resume from the stored continuation token.
- Added `--quotas` CLI flag (default `config/collection_quotas.yaml`). Missing quota
  file returns an empty map so older single-app runs still work.
- Expanded `config/apps.yaml` from 5 to all 17 registry products, with explicit
  `product_id` fields matching `source_registry.yaml`. Renamed display names `Zong` →
  `My Zong` and `Ufone` → `UPTCL / Ufone` so new pages write the canonical IDs.
- First sandboxed collection run returned empty pages (network blocked). Cleaned the
  zero-review checkpoints and re-ran unsandboxed.
- Full Google collection result (checkpoints, local-only):

  | Product | Collected | Stop reason |
  |---|---:|---|
  | Easypaisa | 12,000 | quota |
  | SIMOSA, JazzCash, My Telenor, My Zong | 10,000 each | quota |
  | UPTCL / Ufone | 8,000 | quota |
  | NayaPay, SadaPay, Tamasha, Zindigi | 6,000 each | quota |
  | JazzCash Business, UPaisa | 5,000 each | quota |
  | ROX | 4,000 | quota |
  | JazzCash Retailer | 1,968 | store exhausted |
  | DOST | 1,273 | quota (last short page) |
  | FikrFree | 600 | quota (last short page) |
  | Jazz Business World | 445 | quota (last short page) |
  | **Google total** | **102,286** | |
  | + Apple already complete | 5,483 | |
  | **Combined unique after Phase 2 dedup (expected)** | **~107,780** | |

- Combined target was ~107,500. Validator later scanned 111,169 raw records including
  the earlier 200-review census pages; ~2,989 of those are census/scraper overlaps.

#### Job 8 — Raw validator and human review (complete)

- Added `src/collect/validate_raw.py`. It walks every `*.jsonl` under
  `data/raw/reviews/` and prints: totals by platform, per-product counts, date window,
  duplicate rate, empty-text rate, rating mix, and a coarse script mix (Arabic block vs
  Latin vs mixed). Roman Urdu is still counted as Latin here; Phase 2 language detection
  will split English from Roman Urdu.
- Validation snapshot (2026-08-16):
  - 111,169 raw records (Google 105,686 including census pages; Apple 5,483).
  - Empty text: 0.
  - Duplicates: 2,989 (2.7%), almost all census page vs later quota scrape of the same
    newest reviews. Phase 2 will drop these on `(platform, review_id)`.
  - Product-id split on two apps: older pages used `zong` / `ufone` from the pre-rename
    `apps.yaml` names; census pages used `my_zong` / `uptcl`. `platform_app_id` is still
    the correct join key. Phase 2 remaps both to the registry IDs.
  - Date span: 2015 (Tamasha Apple) through 2026-08-15. Quota-capped Google apps are
    newest-first by design, so their observed window is recent months only.
  - Script: ~98–100% Latin (includes Roman Urdu); 0–2.5% Urdu script. Expected.
- Localhost previews refreshed for human review:
  - Registry: `http://127.0.0.1:8766`
  - Census: `http://127.0.0.1:8767`
  - Review sample: `http://127.0.0.1:8765` (16,045 reviews: first five pages × 17 apps).
    The full 107k corpus stays on disk; a 107k-row HTML page would freeze the browser.
- Code committed and pushed as `9cfae77`. Raw review files were not committed.
- Suite: 28 tests, `ruff check` clean.

#### Job 9 — Cleaned review preview and product filter UX (in progress)

- Added `src/prep/clean.py` with the canonical cleaned-review field contract used by
  Phase 2 preview code. The preview rejects records whose keys do not exactly match the
  cleaned schema, so a raw record cannot silently appear as cleaned data.
- Added `src/prep/render_clean_preview.py`. It loads cleaned JSONL, attaches the registry
  `brand_group` without mutating source records, samples up to `--per-slice` records per
  `(product_id, platform)`, and renders a self-contained local HTML inspection page.
  Sampling is deliberately per product and platform so the larger Google slices do not
  drown out Apple or smaller products in a browser review window.
- The preview keeps Platform, Brand group, and Rating filters separate. Product identity
  continues to use canonical `product_id`; brand filtering is only a convenience view and
  does not merge distinct Jazz applications.
- Product-filter UI went through three decisions based on the maintainer's requested behavior:
  1. The initial checkbox grid was insufficient because it permanently occupied the page.
  2. A native multi-select listbox supported multiple values but was not a dropdown with
     checkboxes and therefore did not match the requested interaction.
  3. The final control is a closed-by-default dropdown button. Opening it reveals a
     checkbox panel with `Select all` and `Clear`; the panel closes on outside click, and
     the button label reports `All products`, `No products selected`, or the number of
     selected products. This preserves multi-product filtering while keeping the page
     compact.
- Selection semantics are explicit: all products start selected; toggling one checkbox
  updates the result table and button label; brand changes rebuild only the visible product
  options; clicking outside closes the panel without changing selection.
- Added focused tests in `tests/prep/test_render_clean_preview.py` for raw-schema rejection,
  per-slice sampling, brand attachment, escaped review text, and the dropdown/checkbox
  markup. The live localhost page was regenerated and manually exercised: opening the
  dropdown exposed product checkboxes, unchecking `jazzcash` changed the selection count,
  and clicking outside closed the panel.
- Verification on 2026-08-16: `ruff check src/prep/render_clean_preview.py
  tests/prep/test_render_clean_preview.py` passed; `pytest
  tests/prep/test_render_clean_preview.py -q` passed with 4 tests. The preview rendered
  7,131 sampled records from 54,519 cleaned records.
- The generated preview remains local/interim output and is not intended to become the
  benchmark release dataset. Raw and interim data remain git-ignored; the preview source
  and tests are the tracked deliverables.

#### Job 10 — Phase 2 cleaning and first language labels (in progress)

- Ran `src/prep/clean.py` against the complete local raw corpus: 111,169 input records
  became 54,519 kept records. Drops were 49,923 `too_short`, 3,462 duplicate text,
  1,820 duplicate IDs, and 1,445 emoji-only records.
- Added a deterministic `language` field to the cleaned schema. The classifier first
  checks Unicode script, labels Arabic-only text `urdu_script`, mixed Arabic and Latin
  text `code_switched`, and uses a small explicit Roman Urdu marker vocabulary for
  Latin-only text; remaining Latin text is `english`.
- Current distribution: 47,930 `english`, 5,559 `roman_urdu`, 798 `urdu_script`, and
  232 `code_switched`. A manual sample from every bucket looked coherent, but this
  heuristic is an initial engineering label, not a human-verified gold annotation.
- Added focused tests for all four categories and for propagation of `language` onto
  cleaned records. The generated JSONL passed the strict preview schema and the full
  suite passed with 39 tests.
- Next decision point: inspect a larger stratified language sample and decide whether
  to refine the Roman Urdu vocabulary or add a lightweight language library before
  freezing the Phase 2 labels.

#### Job 11 — Language audit and Phase 2 validation slice (in progress)

- Audited a reproducible 25-item sample from each language bucket plus product-level
  distributions. English, Roman Urdu, Urdu script, and code-switched examples were
  coherent; mixed examples contained both scripts as expected. The initial marker-based
  Roman Urdu heuristic was retained rather than adding a heavyweight dependency before
  human review.
- Added a Language filter to the cleaned-review preview. Platform, Brand group, Language,
  Product, and Rating can now be inspected independently; the product dropdown still
  opens a checkbox panel for multi-selection.
- Extended the cleaner report with platform totals and the observed calendar date window.
  The final run reports 49,555 Google Play reviews and 4,964 Apple App Store reviews,
  spanning 2015-03-31 through 2026-08-15.
- Fixed a report-only timezone bug exposed by the full run: Google timestamps can be
  offset-naive while Apple timestamps are offset-aware. The report now compares normalized
  calendar dates without changing stored source timestamps.
- Full validation after the fix: `ruff check .`, `pytest -q` with 39 passing tests,
  `python src/prep/clean.py`, and `python src/prep/render_clean_preview.py` all passed.
- Phase 2 is not yet frozen: the labels are engineering heuristics and still need a human
  stratified review before Phase 3 sampling and auto-labelling begins.

#### Job 12 — Commit pending Phase 2 language-detection work (housekeeping)

- Discovered that the language-detection code described in Job 10/11 above (deterministic
  Unicode + Roman Urdu marker classifier in `clean.py`, plus the platform/date-window
  reporting) had been written and tested in an earlier session but was **never committed
  to git** — it sat as an uncommitted working-tree change while the log text describing
  it was already committed. Verified the code still passes the full suite (51 tests) and
  `ruff check .` before including it in this session's commit, so Phase 2's language
  detection is now actually in version control, not just described.

#### Job 13 — Phase 3 Step 1: stratified sampling (`src/label/sample.py`)

- Wrote `sample_records()`: deterministic, seeded round-robin sampling across every
  populated joint stratum of `(product_id, language, rating)`. Sparse strata (e.g. the
  798 `urdu_script` or 232 `code_switched` records) are never starved — once a stratum is
  exhausted, its remaining quota is redistributed across the other populated strata
  automatically, rather than sampling proportionally and losing rare classes.
- Added `build_report()` and a CLI (`python -m src.label.sample`) that write a
  reproducibility manifest: seed, SHA-256 of both the input and output files, marginal
  counts per `product_id`/`language`/`rating`, and the full joint-stratum breakdown.
- TDD: wrote 7 focused tests first (balanced sampling, redistribution from sparse strata,
  seeded reproducibility, rejection of invalid `target_size`, report content), confirmed
  they failed before `sample.py` existed, then implemented until green.
- Ran against the real 54,519-record cleaned corpus: sampled exactly 9,000 records,
  seed `20260817`. All 17 products and all 4 language classes are represented; every
  scarce `urdu_script`/`code_switched` record in a given product/rating cell was kept
  rather than down-sampled. Wrote `data/interim/reviews_phase3_sample.jsonl` and
  `data/interim/reviews_phase3_sample_report.json` (both git-ignored, matching the
  project's raw/interim-data convention).
- Rendered the sample through the existing `render_clean_preview` CLI
  (`data/interim/phase3_sample_preview/index.html`) and verified it in a real browser via
  an automated page snapshot: title, all four filter controls, and 8,271 rendered rows
  (the existing per-product/platform slice cap, not a data-loss bug) all confirmed present.
- Human raised a concern that 9,000 records "lost" the 54,519-record corpus; clarified
  that the full cleaned file is untouched on disk and remains the permanent source —
  the 9,000-item file is a separate, additional sample used only for auto-labelling.
  Human approved proceeding on that basis.

#### Job 14 — Phase 3 Step 2: human-authored taxonomy (`config/taxonomy.yaml`, `src/label/taxonomy.py`)

- Per `PROJECT_CONTEXT.md` Section 6 and build-plan step 23, taxonomy definitions are a
  **human-judgment gate** — `config/taxonomy.yaml` was not auto-filled; all 24 intents
  were authored by hand.
- Walked through all 6 families (Billing & Charges, Access & Account, Money Movement,
  Fraud & Safety, Network & Service, Product & Navigation) one family per batch. For each
  of the 24 intents, drafted a 1-line definition, 2 positive examples, 1 negative example,
  and an explicit `negative_rationale` — the reasoning for why the negative example is a
  boundary trap against a specific, named sibling intent (e.g. why
  `balance_disappeared_unexplained` is not `unauthorized_vas_deduction` when a cause is
  named). Human reviewed and approved every batch before the next was drafted.
- Encoded the approved content into `config/taxonomy.yaml` (`version: 1`, 24 intents,
  4 languages, 4 severities).
- Wrote `src/label/taxonomy.py` (`load_taxonomy()`): validates required fields, rejects
  duplicate intent IDs, and enforces exactly 2 positive examples per intent.
- TDD: 5 focused tests written first and confirmed failing (`ModuleNotFoundError`)
  before `taxonomy.py` existed, then implemented until green — confirmed 24 unique
  intent IDs, all 6 families present, every intent has a non-empty definition/examples/
  rationale, and malformed configs (duplicate ID, wrong example count) raise `ValueError`.
- Full suite after this step: 51 tests passing, `ruff check .` clean.

#### Job 15 — Phase 2 gap: PII scrubber (`src/prep/scrub_pii.py`)

- Closed the blocking gap identified in Issue 10: build-plan step 19 never existed in the
  repo, even though Phase 3 sampling and taxonomy work had already proceeded past it.
- Wrote `scrub_text()`: applies email, CNIC (dashed `\d{5}-\d{7}-\d` and plain 13-digit),
  Pakistani mobile (`03XX...` / `+923XX...`, with or without dashes/spaces), landline
  (`0XX-XXXXXXX`, separator required to avoid false positives on short numbers), and a
  generic 9+-digit account/reference-number pattern, applied most-specific-first so a
  span already replaced by a placeholder cannot also match a looser later pattern.
- Wrote `scrub_records()`: redacts each record's `text_clean` field into a new
  `text_scrubbed` field without mutating any other field, and returns aggregate
  redaction counts by type for reporting.
- Added a CLI (`python -m src.prep.scrub_pii`) that reads
  `data/interim/reviews_phase3_sample.jsonl`, writes
  `data/interim/reviews_phase3_sample_scrubbed.jsonl`, and prints a redaction-count report.
  `auto_label.py` should read the scrubbed file's `text_scrubbed` field, never `text` or
  `text_clean`, when calling the LLM.
- TDD: 16 tests written covering the ≥10-realistic-case acceptance bar from the original
  Phase 2 spec — email, dashed/plain CNIC, mobile with/without country code and
  separators, landline, generic account numbers, a mixed Urdu-script sentence with an
  embedded phone number, multi-PII-per-string counting, and negative cases (`10/10`
  rating, a 4-digit rupee amount) that must survive untouched so short numbers are never
  over-redacted.
- Full suite after this step: 67 tests passing, `ruff check .` clean.
- **Not yet done:** running the scrubber against the real 9,000-item local sample. This
  dev container has no `data/` contents (raw/interim data is git-ignored and only exists
  on the maintainer's local machine where Phase 1–3 were actually run). The maintainer needs to
  pull this commit locally and run `python -m src.prep.scrub_pii` there before
  `auto_label.py` can be built and exercised against real text.
- Human pulled this commit locally, ran `pytest tests/prep/test_scrub_pii.py -q`, and
  confirmed all 16 tests pass on their machine, closing out the "never actually run
  locally" risk for the scrubber code itself (the real 9,000-item sample still needs to
  be scrubbed before labelling).

#### Job 16 — Phase 3 Step 3: auto-labelling pipeline (`src/label/auto_label.py`)

- Added the official `anthropic` SDK (`anthropic==0.122.0`) to `requirements.txt`,
  installed via the same `certifi`-backed `--trusted-host`/`--cert` workaround documented
  in Issue 5 for this macOS Python 3.13 environment.
- Wrote `build_system_prompt()`: renders every taxonomy intent id + definition plus the
  allowed `language` and `severity` values into one instruction prompt, so the prompt
  always mirrors whatever `config/taxonomy.yaml` currently contains rather than
  duplicating intent text in code.
- Wrote `parse_label_response()`: parses the model's JSON reply and requires all five
  fields (`intent`, `language`, `severity`, `confidence`, `rationale`); a response missing
  any field raises rather than silently writing a partial label.
- Wrote `call_model()`: takes an injected `create_fn` (so tests never make a real network
  call) and an injected `sleep_fn`, retrying up to 5 attempts with the same exponential
  backoff shape (2, 4, 8, 16 seconds) used by the Phase 1 scraper on `RateLimitError`/
  `APIStatusError`, then raising if every attempt fails.
- Wrote a content-hash cache (`content_hash()`, `load_cached_label()`,
  `write_cached_label()`): every label response is keyed by the SHA-256 of
  `text_scrubbed` and written atomically (`.tmp` then `replace()`, matching the Phase 1
  scraper's atomic-write convention). `label_records()` checks the cache before ever
  calling the model, so an interrupted run resumes for free and a full re-run of an
  already-labelled sample costs ~$0 — this satisfies the Phase 3 cache-hit acceptance bar
  ahead of the real run.
- Wrote `label_records()`: reuses a `RequestPacer` (same shape as the Phase 1 scraper's)
  to pace live calls, merges each label onto its source record as `label_intent`,
  `label_language`, `label_severity`, `label_confidence`, `label_rationale` (prefixed so
  the LLM's own language guess never collides with Phase 2's deterministic `language`
  field), and returns running spend counters (`input_tokens`, `output_tokens`,
  `cache_hits`, `live_calls`).
- Wrote `estimate_spend_usd()` and `print_report()` using the $1/$5 per-MTok input/output
  pricing already recorded in decision 17, so a run prints cache hits, live calls, token
  totals, and an estimated dollar cost without needing to check Anthropic's dashboard.
- CLI (`python -m src.label.auto_label`) loads `.env` for `ANTHROPIC_API_KEY`, refuses to
  run without it, reads the scrubbed sample's `text_scrubbed` field (never `text` or
  `text_clean`), and supports `--limit` for a small paid smoke-test run before labelling
  the full 9,000 items.
- TDD: 12 focused tests using fake `create_fn`/`sleep_fn` stubs and real
  `httpx.Response`-backed `RateLimitError` instances — cache hit/miss paths, retry then
  succeed, retry exhaustion raises, cache roundtrip, spend accounting, and `--limit`
  truncation. No test calls the real Anthropic API.
- Full suite after this step: 79 tests passing, `ruff check .` clean.
- **Not yet done:** an actual paid labelling run. V2 now requires PII hardening, the
  Phase 2.5 pilot decision, an extended output schema, and versioned cache identity
  before any small paid smoke test or full run. The maintainer-owned API key remains local.

#### Job 17 — V2 project-plan amendment and revised gates (decision complete)

- Human reviewed a proposed mid-Phase-3 amendment against the original project plan and
  approved a smaller, corrected V2 direction. The consolidated active plan was written
  to `/Users/chaudry/Downloads/PROJECT_CONTEXT_V2.md`; it is deliberately outside this
  repository and must never be committed or pushed.
- **Data preservation is now explicit:** the 111,169 scanned raw records (including known
  census overlap), ~107,780 expected unique reviews, 54,519 cleaned records, and separate
  9,000-item sample are independent layers. No new cleaning, scrubbing, labelling, or
  benchmark script may overwrite or delete an earlier layer. New work writes derived
  files/fields only; original text and numeral forms remain local.
- **PII hardening is the immediate engineering priority:** the initial scrubber is useful
  but its generic 9+-digit account rule can destroy transaction references needed for T3,
  and coverage must include Pakistani phone/CNIC/IBAN forms written with ASCII,
  Urdu-Indic, or Arabic-Indic numerals. Matching will use a separate normalized field;
  amounts, dates, references, prices, and data quantities must survive. Acceptance now
  tests both PII removal and collateral damage, followed by a 50-record manual check
  stratified across the four language classes.
- **Phase 2.5 is inserted before the paid Phase 3 run:** the maintainer will write 20 realistic
  complaints with four human-written variants each (Urdu script, naturally messy Roman
  Urdu, code-switched, English) and assign the correct fine intent. A small cached model
  run will test whether the proposed script-gap headline is promising. The 80-item pilot
  is a private go/no-go signal and public preview only, never a publishable benchmark
  result or release-data source.
- **All 24 human-authored taxonomy definitions remain authoritative.** The proposed
  forced collapse to 14 was declined. Optional broader reporting groups may be computed
  later without overwriting fine labels. `refund_requested` and `vas_related` will be
  collected as orthogonal booleans while the existing fine intents remain intact.
- **No external annotator is available for v1.** The original solo-verification path is
  retained: the maintainer verifies at least 1,000 items and blindly relabels 200 after at
  least 48 hours. Report human-vs-AI and human-vs-self agreement and disclose the
  single-annotator limitation prominently; do not claim inter-annotator agreement.
- **The first paid label pass must collect the richer schema:** primary/secondary intent,
  multi-intent flag, language, severity, refund/VAS flags, entity-presence hints, T2 seed
  quality, Roman-Urdu orthographic variance, confidence, and one-sentence rationale.
  Values must be strictly validated. Cache identity must include text, exact model,
  prompt version, taxonomy version, and schema version so the existing five-field cache
  cannot be mistaken for a new response.
- **Later evaluation gains practical controls:** majority-class, TF-IDF/logistic-regression,
  and translate-then-classify baselines; bootstrap 95% confidence intervals (resampling
  whole complaint groups for T2); and a 20-item per-model cost pilot before the full
  Phase 6 run. The $120 project stop-and-report rule remains.
- The original product goal and USP are unchanged: an open, reproducible exam for real
  Pakistani telecom/wallet customer-service risk across Urdu script, natural Roman Urdu,
  English, and code-switching. The amendment strengthens privacy, evidence quality, and
  the chance of a clear public finding; it does not turn the project into a chatbot,
  discard the corpus, or predetermine the headline.
- The closest reviewed public resources cover Roman-Urdu sentiment, hate/offensive
  speech, embeddings, or general language tasks. They are relevant comparisons but do
  not replace the planned combination of customer-service intent, entity extraction,
  fictional-policy reasoning, safety, script consistency, and a public model leaderboard.
- Job 16 remains valid engineering groundwork, but is **not the final paid-run contract**.
  It has caching, retries, pacing, spend tracking, and 12 focused tests; its output schema,
  cache key, and validation must be revised only after Phases 2 and 2.5 pass. No Anthropic
  key/account was provided or used and no real provider request has been made.

#### Job 18 — Phase 2 hardened PII gate (complete)

- Replaced destructive broad digit-run redaction with prioritized typed matching for email,
  Pakistani phone, CNIC/legacy NIC, PK IBAN, context-supported account numbers, and explicit
  self-identification phrases. Matching uses a same-length ASCII-digit view supporting ASCII,
  Urdu-Indic, and Arabic-Indic numerals while replacements apply only to the original span.
- Added must-survive coverage for amounts, dates, transaction/reference IDs, package prices,
  ticket/meter/order numbers, and data quantities. Raw, cleaned, and sampled files remain
  unchanged; the scrubber wrote a separate 9,000-record derived file.
- Corrected an initially weak audit design. The final local page separates 24 synthetic positive
  challenges (six PII types across all four language forms) from 50 real records selected for
  PII-like risk cues and collateral-damage inspection. Synthetic challenges never enter the
  corpus or any release artifact.
- Human accepted the scrubber behavior. The reviewed real Urdu-script records contained no
  observed phone, account, CNIC, or similar private values, so they could not provide positive
  real-data examples. This absence is recorded rather than overstated: multilingual positive
  capability is supported by isolated tests/challenges, while real-data review supports the
  residual-exposure and no-collateral-damage checks. Pattern-based residual risk remains in
  `LIMITATIONS.md`.
- Verification: `ruff check .` clean and 102 tests passing at the Phase 2 closeout.

#### Job 19 — Phase 2.5 human-authoring contract (in progress)

- Added an ignored `spike/` workspace that cannot enter `data/release/`, plus a generator for
  `spike/phase2_5/complaints.json`. It creates 20 blank slots and never generates human-owned
  complaint text.
- Added strict validation requiring exactly four variants per complaint, a taxonomy-valid gold
  intent, an exact fact span in every variant, unique IDs, and coverage of the five V2 scenario
  groups. Existing human work is never overwritten unless `--force` is explicit.
- Added a reproducible private Word workbook with 20 distinct high-value case guides, official
  definitions, two complete approved example complaints per case, scenario briefs, boundary
  reminders, and blank fields for all four human-written variants. Its appendix lists all 24 valid
  taxonomy labels. The workbook is generated under ignored `spike/` and cannot enter release data.
- The private blank JSON template and Word workbook now exist locally. The maintainer will complete
  the workbook separately and share it when ready; the next engineering step is to transfer that
  human-authored content into the private JSON schema, validate all 80 variants, and present any
  semantic or structural issues for approval. No pilot model call has occurred.
- Verification: `ruff check .` clean, 112 tests passing, and the CLI correctly rejects the blank
  template as incomplete.

#### Job 20 — Phase 2.5 workbook transfer and correction (complete)

- The maintainer returned the completed workbook with all 20 cases and all 80 variants written by
  hand. No variant was machine-written, so the pilot's Roman Urdu arm — the condition the pilot
  actually measures — carries authentic human orthographic variance (`badger` for `baghair`,
  `oending`, `tupees`, `bajwood`/`bawjood`, `duphear`/`dupehar`).
- Transferred the workbook into `spike/phase2_5/complaints.json` via a re-runnable extractor that
  reads the `.docx` directly, so the transfer can be reproduced from source rather than retyped.
  Working from a PDF rendering was rejected: RTL text is visually reordered by extraction and
  would have silently corrupted the Urdu.
- Audit before transfer found 76 of 80 `fact_span` values failing the exact-substring rule. The
  maintainer had written summaries (`Rs 200, 1 mah` where the text says `200 rs`) or keyword lists
  (`UPAISA, 10000, 6PM`). All 80 spans were replaced with exact contiguous substrings of their own
  variant text; no complaint text was altered to make a span fit. This matters beyond the pilot —
  T3 needs gold spans as literal character offsets.
- Three semantic defects were found and fixed with explicit maintainer approval. The important one
  was Case 15: Urdu, Roman Urdu, and code-switched all described a caller *posing* as Jazz staff,
  but the English read `Someone from Jazz called me`, which would have flipped the gold label and
  silently penalised the English arm. Also fixed Case 01 (code-switched said one week where the
  other three said one month) and Case 10 (English dropped `TXN 512`).
- Four stray keyboard-layout artifacts were removed — a single Urdu letter glued to the start of a
  Roman Urdu or English variant. Every change is recorded in `spike/phase2_5/CHANGE_LOG.md`.
- Verification: strict validator green on 20 complaints and 80 variants; the hardened PII scrubber
  flags 0 of 80; 20 distinct valid taxonomy intents; all five required V2 scenario groups covered.
  `ruff check .` clean, 112 tests passing. Pilot data stays under ignored `spike/`.
- Recorded but not fixed: English variants run shorter than the other three forms (median 16 words
  versus 19.5), worst at Cases 11 and 15. This is a covariate that could resemble a language
  effect and belongs in the pilot report rather than in re-authored text.

#### Job 21 — Phase 2.5 pilot roster and runner (complete)

- Chose the roster after checking what the maintainer could actually reach: three Anthropic models
  spanning the price range plus one Google model for a second vendor. `config/models.yaml` records
  id, provider, local pricing, pacing, and optional effort/thinking settings per entry.
- Added `src/pilot/roster.py` (loads and validates the roster; rejects unknown providers, duplicate
  ids, missing fields) and `src/pilot/run_pilot.py` (fixed prompt, disk cache, retries, pacing,
  scoring, spend report). Added `google-genai==2.19.0` to `requirements.txt`.
- The classification prompt is rendered from `config/taxonomy.yaml` and is byte-identical for every
  model and every language form, so a score difference cannot come from how the question was asked.
- Cache identity is `provider | model | prompt version | taxonomy version | text`, closing the
  text-only weakness V2 Section 7 identified in `auto_label.py`. Verified in practice: re-running
  the three Claude models served 12 of 12 from cache at $0.00.
- 32 tests added (144 total), none touching the network; model replies are injected through fake
  create functions.
- Ran a 16-call smoke test before the 320-call run, per the V2 rule against unpiloted paid batches.
  It paid for itself immediately (see Issue 12).

#### Job 22 — First pilot run, corrected reporting, and findings (complete)

- Full run: 320 classifications across 20 complaints, 4 language forms, 4 models. Spend $0.7472.
- **The script-gap hypothesis was not supported.** Accuracy by language form was flat for all three
  Claude models; for Haiku, natural Roman Urdu was the *highest*-scoring form (90%) rather than the
  lowest. Every observed difference was 1-2 items out of 20, inside noise. This is not a ceiling
  artifact: Haiku scored 80-90% and had room to show a gap.
- **A taxonomy defect caused 61% of all errors.** `refund_request` and
  `transfer_failed_money_deducted` both fully matched Case 05, with no rule to separate them; all
  12 model answers (3 models x 4 forms) chose the failure over the request. A second pair,
  `account_compromised` -> `refund_request`, had the same cause. Root cause: `refund_request`
  describes a speech act while the other 23 intents describe failure types, so the two axes
  collide on any complaint that reports a problem and asks for money back.
- **A cross-language consistency effect was found instead.** Asking whether a model returns the
  *same* answer for the same complaint in all four forms: Haiku 14/20, Sonnet 18/20, Opus 20/20.
  Weaker models change their answer based on script alone while their average accuracy stays flat,
  so accuracy hides the effect entirely and only the four-form paired design exposes it.
- The effect is directional: of 9 deviations from a model's own majority answer, 7 came from Roman
  Urdu (4) and code-switched (3) versus 1 each from Urdu script and English. Consistent with the
  original hypothesis but far too few events to claim; recorded as a lead to test at scale.
- Confirmed the two findings are independent: Case 05 never flipped across language forms, so
  correcting its label cannot alter the consistency numbers.

#### Job 23 — Taxonomy v2 precedence rule and pilot hardening (in progress)

- Raised `config/taxonomy.yaml` to **version 2** with a failure-over-request precedence rule:
  when a complaint names a concrete failure, that failure is the intent and the money-back ask is
  recorded in the orthogonal `refund_requested` flag. `refund_request` as an intent is now reserved
  for a bare request with no identifiable failure behind it. Sharpened `refund_request`,
  `transfer_failed_money_deducted`, and `account_compromised`, and added a consent test to
  `unauthorized_vas_deduction` (a wrong amount on a subscribed service is overcharging, not an
  unauthorized charge). The version bump invalidates every cached reply by design.
- Widened the retry ladder from 5 attempts/30s to 6/62s and Gemini pacing from 6s to 8s after the
  free-tier quota dropped 43 calls (Issue 12). Added a test asserting total backoff outlasts a 40s
  quota pause.
- **Audit finding, not yet acted on:** the classification prompt sends only intent definitions
  (3,797 chars) while `taxonomy.yaml` holds 10,797 chars of human-authored guidance. The positive
  examples, negative examples, and negative rationales - written specifically to mark the boundary
  against each intent's most likely confusion - never reach the model. Including them is a strong
  candidate for the Phase 3 labelling run, where accuracy is what the spend buys. Deliberately not
  changed mid-run so the v1/v2 comparison stays clean.
- Audited the other 22 intents for the same defect. Fourteen carry no explicit boundary clause in
  their definition, but most produced zero errors; the residual confusions are one-offs that look
  like ordinary model error rather than definition defects. The refund overlap was the one
  structural problem.
- Verification: `ruff check .` clean, 147 tests passing. Confirmation re-run against taxonomy v2
  was still executing at the time of writing.

### Phase 3 progress — real-data diagnostic (2026-08-26/27)

Before this session no real review had ever been labelled. Eleven days of work, 147 tests, two
pilot runs and 320 classifications had all been against 20 hand-authored complaints. The
diagnostic closed that gap.

**Job 24 — pipeline repairs found before spending anything.** Three defects in
`src/label/auto_label.py` would each have corrupted a 9,000-item run:

- The prompt rendered `f"- {intent.id}: {intent.definition}"` and nothing else — 2,707 of the
  taxonomy's 10,797 characters. Every positive example, negative example and boundary rationale,
  the exact content whose sharpening fixed 61% of the v1 pilot errors, was omitted. Rendered
  prompt went from 3,797 to 15,080 characters once fixed.
- The disk cache was keyed on `sha256(text)` alone, so a two-model run would have served the
  first model's replies to the second. Now keyed on model, prompt version, taxonomy version and
  text, matching `src/pilot/run_pilot.py`.
- No prompt caching. The ~3.9k-token taxonomy prefix is identical on every call and was being
  billed in full each time. Adding `cache_control` saved roughly $15.80 on the diagnostic alone.

**Job 25 — the 500-item diagnostic.** `spike/phase3_diag/sample_500.py` drew 125 reviews per
language form, stratified within each on the regex severity proxy. Equal language strata rather
than corpus-proportional: the corpus is 88% English and a proportional draw yields ~6
code-switched items, which cannot show a language-specific failure. Labelled independently by
Claude Sonnet 5 and Claude Opus 5 — two models that tied at 95% in the Phase 2.5 pilot, so a
disagreement indicates an ambiguous item rather than a weaker model. 1,000 calls, 0 failed, 10
unparseable, $4.39.

Results on real complaints (rating 1–2, n=275):

| Measure | Value |
|---|---|
| Unclassifiable (reference labeller) | 13.1% |
| Unclassifiable (both models) | 6.9% |
| Multi-intent (genuine second intent) | 11.8% |
| Inter-model agreement | 74.9% |
| Cohen's kappa (all 490) | 0.758 |

A first reading put unclassifiable at 26.7–33.7%, which was an artifact: the 9,000-item sample
is rating-stratified and the taxonomy describes complaints, so praise has no matching intent.
Unclassifiable runs 63.5% at 5 stars and 13.1% at 1 star. The complaint-only figure is the real
one.

Agreement was flat across language forms — Urdu script 78.0%, Roman Urdu 75.0%, code-switched
85.4% (highest), English 79.8%; kappa 0.72–0.82 — replicating the Phase 2.5 negative result on
real data at n≈123 per cell instead of n=20.

**Job 26 — the regex severity proxy was measured, not assumed.** Against labelled
`financial_loss` it reached 70.2% precision and 71.3% recall, and its misses were not evenly
distributed: 17 in Urdu script and 11 code-switched against 1 in English. A Latin-token pattern
is close to blind on Urdu-script complaints. Every keyword-derived statistic produced earlier in
the project understates non-English harm.

**Job 27 — starved-intent hunt over all 54,519 reviews.** Three intents had zero support in the
diagnostic and nine more sat under ten. `spike/phase3_diag/hunt_starved.py` searched the full
corpus with multilingual patterns, scrubbed the candidates through the Phase 2 PII gate, and
labelled the 50 best matches per intent. `otp_not_received` returned 45/50 — abundant, and
missed by the sample rather than absent. `fake_payment_screenshot` returned 0/50. A follow-up
top-up (`topup_starved.py`) brought five viable intents to the ≥30 threshold:
`refund_request` 91, `scam_impersonation_report` 69, `account_compromised` 53,
`loan_repayment_dispute` 47, `bill_payment_not_reflected` 34.

**Job 28 — the authored-versus-real comparison, run under identical conditions.** The Phase 2.5
pilot used taxonomy v1 and the definitions-only prompt; the diagnostic used v2, the full prompt
and structured outputs, so comparing them directly invited an obvious objection.
`spike/phase3_diag/authored_vs_real.py` re-labelled all 80 authored variants under the
diagnostic's exact conditions:

| Set | Inter-model agreement |
|---|---|
| Authored complaints (n=80) | **100.0%** |
| Real complaints (n=275) | **74.9%** |
| Gap | **+25.1 points** |

Same two models, same taxonomy, same prompt, same metric; the only variable is authored versus
real. Both models scored 76/80 against the authored gold labels while agreeing with each other
on 80/80 — they make the same four errors, which points at gold-label disputes rather than model
noise.

**Job 29 — forward collection.** `src/collect/refresh_reviews.py`, six tests. First run
collected 5,782 new reviews across 17 apps in 61 seconds; verified all August 2026,
schema-valid, unique, no reviewer identity, 99.95% genuinely new.

**Job 30 — blind adjudication tool.** `spike/phase3_diag/adjudicate.py`, a local
`http.server` on 127.0.0.1 serving 100 disagreements plus 100 controls in shuffled order.
Model predictions are withheld from the item payload entirely and returned only after a
judgement is saved. Verified over the wire: `/next` returns only `review_id`, `text`,
`product_id`, `rating`, `language_detected`.

- Verification: `ruff check .` clean, 161 tests passing (was 147). Session spend ~$7.50 of $150.

### Phase 4 — the script-gap question, answered (2026-08-29/30)

The project was built to test whether models handle Urdu-script and Roman-Urdu complaints
worse than English. Two earlier attempts could not answer it: Phase 2.5 held content
constant across four scripts but had n=20, and the Phase 3 diagnostic enriched its sample
for model disagreement, which distorts accuracy and left per-language cells of 5-9 items.

**Job 31 — a design that could answer.** `spike/phase3_diag/urdu_pass.py` drew ~60 reviews
per language form, random within each language and **matched to the Urdu-script length
profile**, because Urdu-script complaints run a median 23 words against English's 14 and an
unmatched comparison would measure verbosity. 239 items, both models, blind human
adjudication.

**Job 32 — taxonomy v3.** Adjudication surfaced two categories the scheme lacked, both
measured before being added: `support_unresponsive` (6.0% of the corpus; two v2 intents push
this case away in their own negative examples and nothing took it in) and
`card_activation_failed` (1.9%; card complaints scattered across five unrelated intents).
Both models were re-labelled against v3 for $1.76 so annotator and model worked from the
same 26 options - without that, choosing a new intent would have scored as a model error
when the model was never offered the answer. A revisit pass, keyed on taxonomy version so
items leave the list as they are re-judged, cleared the earlier judgements made under v2.

**Result — the founding hypothesis is not supported.** Accuracy against 204 blind gold
labels, ~50 per language:

| Language | Sonnet 5 | Opus 5 |
|---|---|---|
| Urdu script | 62.0% | 64.0% |
| Roman Urdu | **68.6%** | **64.7%** |
| Code-switched | 63.6% | 56.4% |
| English | 60.4% | 54.2% |

English ranks last for both models, Roman Urdu first, spread 8-10 points, every interval
overlapping every other. Performance is uniform across script at 55-65%, independently
replicating the ~63% measured on a separate sample two days earlier.

**Two defects found and fixed on the way:**

- `max_tokens=300` truncated rationales mid-string on longer non-English reviews, surfacing
  as a JSON parse failure rather than a length error. It dropped 8 items, 4 of them Roman
  Urdu - the language then showing the weakest score. Urdu script and Roman Urdu tokenize
  less efficiently than English, so an identical budget silently favours English inputs.
  Raised to 700; zero failures on the re-run.
- 13 skipped reviews were counted in the denominator as model misses, unevenly distributed
  (6 Urdu script against 2 English), suppressing Urdu-script accuracy by ~6 points and
  manufacturing a gap in the direction of the hypothesis. Same defect as Issue 13. Both
  times the error flattered the prior.

- Verification: `ruff check .` clean, 161 tests passing.

### Phase 5 — the harness becomes a tool anyone can run (2026-08-30/09-01)

The tooling that produced the gold labels lived in the ignored `spike/` directory,
hard-coded to one dataset, untested, and runnable only by its author. It is the part of
this work most likely to be useful elsewhere, so it was lifted out.

**Job 33 — extraction.** `src/adjudicate/` — nine modules, domain-agnostic: a JSONL of
items, a YAML label set, a local server, and scoring. Validated by reproducing the study
exactly: same per-language accuracy for three models, same p-values, same 28-point
detectable-effect floor. A generic tool that gets different numbers from the specific one
is broken, so that check was the point of the exercise.

`src/eval/` was left alone. The project plan reserves it for the model-running harness
(`adapters/`, `prompts/`, `run_eval.py`, `score.py`), and an early draft of this work had
already overwritten its `__init__.py` before the collision was noticed.

**Job 34 — one application instead of three commands.** Pass selection and the blindness
setting became controls in the interface rather than flags typed at launch, and scoring
became a view rather than a separate command. Blindness in particular needed to be visible
state: a pass that quietly stops being blind still writes a full file of judgements.

**Job 35 — a null result reports its own power.** Subgroup analysis prints the minimum
detectable effect beside the p-value. "No difference" and "this could not have found one"
produce identical tables, and the distinction is the whole claim. On this study: a gap
larger than ~28 points would have shown up and did not; a smaller one is not excluded.

**Job 36 — `--demo`.** Real evaluation data is customer text and does not travel, so the
tool now generates a synthetic dataset and opens on it. The fake models disagree often
enough for the controls pass to mean something, and one group carries a real deficit so the
subgroup test has something to find, while the sample stays small enough that the power
line still says it cannot be certain.

**Job 37 — written for the reader, not the author.** Results now lead with a plain-English
verdict and demote the statistics beneath it. Column headers became *got right*, *score*,
*could really be*, *how sure*; the p-value became "chance produces a gap this big 7 times
out of 10"; the detectable-effect floor became a bordered caution panel; kappa gained a
word before its number. Every technical term carries a tooltip, and a glossary panel lists
them all at once. Label ids are shown in human form with the id kept in small type beside
them, because the id is what gets recorded but not what should be read first.

The reasoning is the same one that runs through the study: a figure nobody can interpret
is not evidence to the person being asked to act on it.

- Verification: `ruff check .` clean, 191 tests passing (161 before this phase).

---

## 4. Key decisions and their reasoning

0. **Budget stays at $150; the reduced $20 scope was considered and declined (2026-08-25).** A
  $20 cap would have ruled out the 9,000-item labelling run and forced the project down to a
  standalone consistency study. The maintainer chose to retain the full budget and the full
  five-task plan. Spend to date is $0.75, so money is not the binding constraint — maintainer
  time is.

0a. **`refund_request` loses to the underlying failure (taxonomy v2, 2026-08-25).** Asking for
  money back is a speech act, not a failure type, so it collided with every intent describing a
  concrete failure. Rather than delete the intent or relabel one case, the boundary was made
  explicit: the failure is the intent, `refund_requested` records the ask, and `refund_request`
  survives for bare requests. This also settles V2 open decision 5 in favour of collecting a
  secondary intent rather than forcing a single label. Chosen over three alternatives —
  relabelling Case 05 (leaves the rule broken), rewriting Case 05 (patches one case), and
  accepting both silently (hides the ambiguity from the labels).

0b. **The public headline is chosen from evidence, and the first candidate failed (2026-08-25).**
  The script-gap claim that motivated the project is not supported by its own pilot. Recording
  this plainly rather than reframing it protects the project's credibility; V2 Section 4 already
  required the headline to follow the results rather than the reverse.


1. **Project context stays local and untracked.** The active plan is now
  `PROJECT_CONTEXT_V2.md`; both it and the original `PROJECT_CONTEXT.md` are explicitly
  git-ignored. Working plans, budgets, and internal process notes are kept out of the
  public repository so it contains only the project itself.
2. **Tracked files describe the project, not the process used to build it.** Commit
   messages, code comments, and docs stay free of tooling, workflow, and authorship
   commentary. Machine-specific local tooling state is excluded through the per-clone
   `.git/info/exclude` file rather than the tracked `.gitignore`, so the ignore list
   itself carries no working-process trace either.
3. **Code license = Apache-2.0; dataset license (once released) = CC BY 4.0** — per
   `PROJECT_CONTEXT.md` Section 12, to maximise adoption.
4. **Config files left empty rather than guessed.** `apps.yaml`, `models.yaml`,
   `taxonomy.yaml`, and `policy_docs/` require human judgment calls, which the brief
   reserves for the maintainer.
5. **Phase-gate discipline with one-job-at-a-time human approval.** Per the brief's
   working rule #2, each phase stops and reports before the next begins. Within Phase 1,
   an additional one-job-at-a-time gate was adopted: each discrete deliverable is shown
   on localhost before proceeding to the next step.
6. **Package ID is the permanent source identity, never the brand name.** Google Play
   package IDs and Apple track IDs are stable identifiers that survive title and brand
   renames. Every stored review carries its exact `platform_app_id` and a canonical
   `product_id` from the registry, so "Jazz" products are never pooled by accident.
7. **Separate Google and Apple figures; never combine them into one total.** Google
   exposes a store-reported lifetime written-review count. Apple exposes only the latest
   500 reviews per listing via public RSS. These two measures have different precision
   and meaning; the census report and stored schema preserve the distinction.
8. **Review schema is append-only and privacy-defined.** The nine-field schema
   (`review_id`, `platform`, `platform_app_id`, `product_id`, `text`, `rating`,
   `timestamp`, `app_version`, `helpful_count`) is formally typed in `review_schema.py`
   and validated in every renderer. Adding a field requires updating that module and all
   tests. Removing a field breaks the schema check and fails the test suite.
9. **Low-volume products collect all available reviews; high-volume products are capped.**
   Forcing artificial equal quotas would either truncate small products to meaninglessness
   or bloat large products beyond what Phase 3 labeling can consume. The census revealed
   the actual supply distribution and informed the per-product caps in
   `config/collection_quotas.yaml`.
10. **Apple collection is already complete.** Apple's public access ceiling of 500 reviews
    per listing is reached by collecting all 10 RSS pages. There is no further Apple
    scraping to run; the 5,483 reviews collected are the complete publicly available set.
11. **Empty Google pages mean the store is exhausted, even if a continuation token is
    still present.** JazzCash Retailer returned empty pages with live tokens after 1,968
    real reviews. The collector now marks `complete: true` and stops instead of looping.
12. **Browser previews are inspection windows, not the corpus.** Full collection lives in
    `data/raw/reviews/` (git-ignored). Preview HTML is a sampled slice for human review.
13. **`product_id` written at scrape time follows `apps.yaml`.** Census used the registry;
    the first five-app quota run used display-name fallbacks (`zong`, `ufone`). Phase 2
    must remap via `platform_app_id`, not trust every stored `product_id` blindly.
14. **Product selection uses a dropdown with checkboxes.** A native multi-select listbox
  technically supports multiple values but does not provide the requested compact
  dropdown interaction or visible checkbox affordances. The custom control therefore
  keeps checkboxes inside an expandable panel, with explicit select-all, clear, outside
  click dismissal, and a summary label.
15. **Preview samples are bounded by product and platform.** Rendering the complete
  cleaned corpus in one HTML page would make human inspection slow and can freeze the
  browser. The preview intentionally samples each product/platform slice while showing
  the total cleaned count separately.
16. **Phase 3 sample size fixed at 9,000, not the full 54,519-record corpus.** The spec's
  floor is 8,000–10,000 balanced items; labelling the full corpus would multiply
  auto-labelling API cost roughly 6x for no benchmark benefit, since Phase 4 only
  human-verifies a subset regardless. The full cleaned file is retained untouched as the
  permanent source; the sample is an additional, separate file used only for labelling.
17. **Auto-labelling model: Claude Haiku 4.5, not Sonnet or Opus.** Chosen for cost
  (~$1/$5 per MTok input/output vs. ~$2/$10 for Sonnet 5 and ~$5/$25 for Opus 5) given
  the project's built-in Phase 4 kappa gate exists specifically to catch auto-label
  quality problems before they reach the gold set. If Phase 4 kappa comes back below the
  project's own 0.6 threshold, or specific intents show poor agreement, the plan is to
  selectively re-label only those flagged items with a stronger model — not the full
  9,000-item batch — rather than defaulting to a more expensive model upfront.
18. **API key is human-supplied and local-only.** The maintainer is using their own Anthropic
  Console credit. The credential goes into a local, git-ignored `.env` file per the
  existing `.env.example` convention; it is never shared or committed.
19. **`auto_label.py` injects the model call and the sleep function rather than taking an
  `Anthropic` client directly.** This mirrors the Phase 1 scraper's `RequestPacer`/
  `reviews_fn` injection pattern and means the full retry/backoff/cache logic has real
  unit test coverage without any test making a network call or sleeping for real.
20. **Label fields are written with a `label_` prefix.** The LLM's own `language` guess is
  stored as `label_language`, distinct from Phase 2's deterministic `language` field —
  the two can disagree, and comparing them is useful signal, so neither is allowed to
  silently overwrite the other.

21. **A 500-item diagnostic runs before the 9,000-item batch (2026-08-26).** The taxonomy, the
  most carefully built artifact in the project, had never been applied to a real review. Paying
  to label 9,000 items against an unvalidated schema risks discovering a structural defect after
  the spend rather than before it. The diagnostic cost $4.39 and found the pipeline defects in
  Issues 15–17 before any of them could scale.

22. **Two strong models, not a capability ladder (2026-08-26).** Sonnet 5 and Opus 5 tied at 95%
  in the Phase 2.5 pilot, so where they disagree on a real review the *item* is ambiguous rather
  than one model weaker. Haiku 4.5 was dropped for two reasons: at 86% its errors would have
  mixed model skill into the ambiguity signal, and its minimum cacheable prefix sits above this
  prompt's ~3.9k tokens, so it would have run uncached (Issue 17).

23. **Structured outputs with an enum-bound intent field (2026-08-27).** The response schema is
  generated from the taxonomy itself, so an invalid intent id is structurally impossible rather
  than merely unlikely, and the 1% of free-text replies that failed JSON parsing in the
  diagnostic cannot recur. `minimum`/`maximum` are unsupported on a `number` field, so the
  confidence bound is enforced in `parse_label_response` instead (Issue 19).

24. **The extended label schema is adopted, on evidence rather than plan (2026-08-27).** V2 left
  single-label versus multi-label open pending real multi-intent rates. The diagnostic measured
  11.8%, so a single-label release would discard a distinct second matter on roughly one review
  in eight. `intent_secondary` and `refund_requested` — both already named by the taxonomy v2
  precedence rule — are now required fields. This closes V2 open question 4.

25. **The labelling prompt carries examples, not just definitions (2026-08-26).** The boundary
  between two intents lives in the negative example and its rationale, not in the definition
  sentence. Sending definitions alone withheld 75% of the taxonomy's content from the model
  while the project reported results as though the taxonomy had been applied (Issue 15).

26. **Cache identity covers the whole request, not just the text (2026-08-26).** Keying on text
  alone let one model's reply serve another's and let a stale reply survive a prompt or taxonomy
  change. The pilot runner already had this right; the labeller did not (Issue 16).

27. **A 400 is never retried (2026-08-27).** `BadRequestError` subclasses `APIStatusError`, so a
  malformed request was being resent MAX_ATTEMPTS times. On a 9,000-item run with a schema
  mistake that is 45,000 wasted calls, and the retry loop hides the cause behind a generic
  failure message (Issue 18).

28. **`fake_payment_screenshot` is retained and marked out-of-channel, not merged or dropped
  (2026-08-27).** Two independent searches over all 54,519 reviews — keyword, then a scenario
  search requiring counterparty, payment-proof, forgery and non-receipt signals together —
  returned zero examples. The reason is channel, not taxonomy: in that scam the app behaved
  correctly and a counterparty deceived a merchant, so there is nothing to complain to the app
  about. Contrast `scam_impersonation_report`, well represented because the fraudster poses as
  the company. Merging would conflate counterparty fraud with company impersonation; dropping
  would lose a category any operator-side complaint system meets routinely. The generalisation —
  app-store reviews capture fraud only when the platform is blamed — is recorded in
  `LIMITATIONS.md` as a property of the collection channel, not of this corpus.

29. **No v3 precedence rule for `unauthorized_vas_deduction` (2026-08-27).** The hunt's confusion
  matrix appeared to show the intent swallowing fraud complaints, and it was initially recorded
  as a boundary defect of the same shape as the v1 `refund_request` collision. Reading the
  underlying reviews reversed that: all 23 items were genuinely unauthorized VAS charges, each
  naming a service. Pakistani reviewers write "scam", "fraud" and "unauthorized" to mean a
  provider charge they never consented to, so keyword retrieval on those words returns VAS
  complaints. The same hunt found 20 genuine `account_compromised` cases and labelled them
  correctly — the boundary discriminates. **A confusion matrix computed over keyword-retrieved
  candidates measures the retrieval, not the taxonomy** (Issue 20).

30. **Forward collection is a separate module, not a flag on the Phase 1 scraper (2026-08-26).**
  `scrape_reviews.py` walks backwards into history and returns early once a checkpoint is marked
  complete, so re-running it can never pick up new reviews. `refresh_reviews.py` solves the
  opposite problem and never reads or writes Phase 1 checkpoints, so a refresh cannot corrupt the
  original collection. It stops after 100 *consecutive* known ids rather than the first one,
  because the store reorders near-simultaneous posts and a lone familiar review can sit above
  genuinely new ones.

31. **Adjudication is blind, with controls (2026-08-27).** Showing an annotator two model answers
  and asking which is better produces a preference survey, not an independent judgement, and a
  reviewer would say so. Model predictions are withheld from the item payload entirely — not
  merely hidden in the page — and returned only after a judgement is saved. 100 agreement
  controls are shuffled in and indistinguishable, so the record can show the annotator was not
  siding with a preferred model. The worklist order is seeded and shuffled, which means a partial
  pass is still an unbiased sample.

32. **The public headline is the authored-versus-real gap, not the script-gap result
  (2026-08-27).** V2 left the Phase 2.5 headline open between consistency, T4 policy
  over-authorization, and harder complaints. The diagnostic supplies a stronger option than any
  of the three: identical models, taxonomy, prompt and metric produce 100% agreement on authored
  complaints and 74.9% on real ones. The script-gap finding remains, reframed as a methods
  caution — 490 items support a strong failure to detect a gap, not proof of absence — and the
  Phase 2.5 v1→v2 contrast supplies the companion claim that underspecified labels manufacture
  apparent script effects.

33. **Taxonomy raised to v3, and both models re-labelled against it (2026-08-30).** Human
  adjudication showed the 24-intent scheme had no home for two recurring complaint types.
  Adding them was not enough on its own: the models had labelled every item against 24
  options, so an annotator picking a 25th or 26th would have scored as a model error when
  the model was never offered the answer. Re-labelling all 239 items under v3 cost $1.76
  and put annotator and model on the same footing. The cache key already carried the
  taxonomy version, so the v2 labels behind the 125-item decomposition were untouched and
  that result remains a clean v2 measurement.

34. **The revisit list is keyed on taxonomy version, not on a fixed set (2026-08-30).**
  Judgements now record the taxonomy version they were made under, so an item appears on
  the revisit page only while it predates the current version, and leaves the moment it is
  re-judged. Both pages write the same file and saving replaces by review id, so two
  browser tabs stay consistent with no merge step. The selection rule was later widened
  from keyword matching to "a model itself chose one of the new intents", which is the
  stronger test - it catches every case where the annotator lacked an option the model had,
  without depending on a hand-written pattern, and it found six genuine gaps where keywords
  had found three.

35. **Length is matched, subject matter is not, and the difference is stated (2026-08-30).**
  Urdu-script complaints run a median 23 words against English's 14, so an unmatched
  language comparison would partly measure verbosity. Matching removes that. It does not
  remove the content confound - Urdu-script reviews skew toward UX complaints and English
  toward OTP - and no real-corpus design can, since language and subject matter are
  genuinely correlated in the population. Only a parallel corpus separates them, which is
  what Phase 2.5 was and why that design was right despite its sample size.

36. **The adjudication tooling was extracted rather than left in `spike/` (2026-08-31).**
  It is the reusable half of the project: the study's findings are specific to Pakistani
  complaints, but blind adjudication with controls, exclusion of skipped items, reweighting
  for enriched samples, and a power statement beside every null are not. Leaving it in an
  ignored directory meant it could not be shown, tested, or reused.

37. **The protocol is enforced in code, not documented in a README (2026-08-31).**
  Predictions are absent from the item payload rather than hidden in the interface;
  controls are shuffled in and indistinguishable; judgements carry the blindness regime
  and label-set version they were made under. Each of these, left to discipline, stops
  holding without producing any visible symptom - a pass that quietly stops being blind
  still writes a full file of judgements, and two protocols reported as one number is not
  a number.

38. **A null result carries its power or it is not reported (2026-09-01).**
  The script-gap finding was stated as "disproven" for three days before the minimum
  detectable effect was computed. At ~50 items per language the design could only have
  caught a gap of ~28 points; the observed spread was 11. The claim that survives is a
  bound - no large gap exists, and every point estimate runs opposite to the hypothesis -
  not a zero. The tool now prints this automatically so the omission cannot repeat.

39. **The interface is written for a reader who did not build it (2026-09-01).**
  `p = 0.711` and `kappa 0.576` are precise and useless to the person deciding whether to
  ship. Results now lead with the plain reading and keep every statistic beneath it, on the
  same principle that governs the paper: the finding is what someone can act on, and a
  number they cannot interpret is not a finding.

---

## 5. Issues and bugs encountered

### Issue 1 — First commit attempt blocked by pre-commit hooks (Phase 0)
- **What happened:** `ruff-format` and `end-of-file-fixer` modified files on the first
  commit attempt, aborting it by design. Re-staged and recommitted.
- **Lesson:** Always expect first-commit hook reformatting; re-stage and retry.

### Issue 2 — Local tooling state named in the tracked ignore file (Phase 0)
- **What happened:** Machine-specific editor and tooling directories were listed in the
  tracked `.gitignore`. Those entries are a local working-environment detail that does
  not belong in a public repository.
- **Resolution:** Moved them to `.git/info/exclude`, which is per-clone and never pushed.
  `.gitignore` now carries only project-level exclusions (secrets, data, caches,
  virtualenvs, editor metadata). Note the trade-off: `.git/info/exclude` does not travel
  with a fresh clone, so it must be recreated when setting up on another machine.

### Issue 3 — Google Play search API omits first-result `appId` (Phase 1)
- **What happened:** For dominant apps (SIMOSA, JazzCash, Easypaisa), the library
  returns `appId: null` on the top search result — not a missing listing, just an API
  quirk. A second-position result with a different ID (e.g., a merchant variant) may
  have a non-null ID.
- **Resolution:** The resolver accepts a null ID from the expected official listing and
  falls back to the configured expected ID. A conflicting *non-null* ID from a same-
  developer variant raises a `ValueError`, preventing silent selection of the wrong app.
  Covered by `test_choose_result_avoids_conflicting_variant_from_same_developer`.

### Issue 4 — Continuation token `sort` field is an integer, not a `Sort` enum (Phase 1)
- **What happened:** The first live SIMOSA collection run crashed at checkpoint-write
  because the token returned by the library stored `sort` as an integer (2) rather than
  the `Sort.NEWEST` enum member. The synthetic test token used `Sort.NEWEST` and missed
  this.
- **Resolution:** `serialize_token` now handles both forms with `isinstance(token.sort, Sort)`.
  `deserialize_token` stores the integer directly (no enum conversion). The regression
  test was updated to use `Sort.NEWEST.value` to match the live shape.

### Issue 5 — macOS Python 3.13 TLS certificate verification (Phase 1)
- **What happened:** Standard Python `urllib.request` fails to reach `pypi.org` and
  `itunes.apple.com` because macOS Python 3.13's system SSL trust store is not populated
  by default (`OSStatus -26276`).
- **Resolution:** Added `certifi==2026.7.22` as a project dependency. Apple requests in
  `scrape_apple_reviews.py` use `ssl.create_default_context(cafile=certifi.where())`.
  `pip install` for certifi itself was bootstrapped with `--trusted-host` flags.
  `curl` (which uses the macOS keychain) worked throughout and was used for the census
  probe and Apple search API calls.

### Issue 6 — YAML parse error from unquoted colons in store titles (Phase 1)
- **What happened:** `source_registry.yaml` entries such as
  `store_title: SadaPay: Money made simple` caused a YAML scanner error because `:` is
  special syntax inside plain scalars.
- **Resolution:** Quoted store titles that contain colons: `'SadaPay: Money made simple'`.
  `ruff check` and the YAML pre-commit hook now catch similar issues.

### Issue 7 — Sandbox blocked `git push` and `python -m http.server` (Phase 1)
- The sandboxed execution environment blocked localhost socket binding (ports 8765–8767)
  and Git's credential-helper IPC pipe. Resolved by running the preview servers and Git
  pushes outside the sandbox.

### Issue 8 — Sandboxed Google collection wrote empty pages (Phase 1)
- **What happened:** The first full Google run inside the sandbox printed
  `SIMOSA: wrote 0 reviews` on every page. HTTPS to Play was blocked, but the library
  returned empty lists instead of raising, so the collector treated them as valid pages.
- **Resolution:** Killed the run, deleted the zero-review checkpoints and page files,
  re-ran unsandboxed. Added the empty-page exhaustion guard in the same session so a
  later real empty page cannot loop forever.

### Issue 9 — Google API returns empty pages with live continuation tokens (Phase 1)
- **What happened:** JazzCash Retailer collected 1,968 real reviews, then kept returning
  empty pages with a non-null token. The collector looped until it was killed.
- **Resolution:** `collect_app` now treats an empty page as store exhaustion, writes
  `complete: true`, and stops. Covered by `test_collect_app_marks_complete_on_empty_page`.
  Corrupted Retailer files from the loop were deleted and the listing was re-collected.

### Issue 10 — Phase 2 PII scrubber was never built; prior work sat uncommitted (Phase 2/3)
- **What happened:** Build-plan step 19 (`src/prep/scrub_pii.py`, regex-redacting phone
  numbers, CNIC-shaped numbers, emails, and account numbers before anything leaves the
  local environment) does not exist anywhere in the repo, even though earlier log entries
  (Job 10/11) describe Phase 2 cleaning and language work as substantially complete.
  Separately, that same language-detection code existed only in the working tree and had
  never been committed to git.
- **Why it matters now:** Phase 3 auto-labelling sends raw review text to a third-party
  LLM API. The project's own privacy rule ("this must run before anything is published")
  is written for the release dataset, but the same reasoning applies to sending
  unredacted text to any external API — phone numbers, CNIC numbers, and emails should
  not leave the local machine unredacted.
- **Resolution status:** Closed in Job 18. Typed/anchored patterns replaced the broad
  account-number rule, three numeral systems and must-survive facts are tested, the local
  sample was written to a separate scrubbed derivative, and the corrected human audit was
  accepted. No external API call occurred. The previously-uncommitted language code was
  committed in Job 12.

### Issue 11 — Live API keys pasted into the tracked `.env.example` (Phase 2.5)

- **Symptom:** After being asked to add credentials, both the Anthropic and Google keys were
  entered into `.env.example` rather than `.env`. `.env.example` is tracked and pushed; it exists
  only to document variable names and must always hold empty values.
- **Exposure check before any edit:** the only commit touching that file is the Phase 0 scaffold
  (`78733bc`) and its stored version has every value empty; nothing was staged; no commit or push
  had occurred. The keys never left the local working tree.
- **Resolution:** values moved to `.env` (git-ignored, confirmed untracked), `.env.example`
  restored from git. The maintainer independently revoked and reissued both keys.
- **Residual risk:** a `git add -A` would have swept the file into a commit, and a push would have
  published two live keys. A pre-commit guard that rejects any non-empty value in `.env.example`
  is proposed but not yet implemented.

### Issue 12 — Retired Gemini model and an incompatible thinking setting (Phase 2.5)

- **Symptom:** all four Gemini calls in the first smoke test failed. The broad retry handler
  swallowed the cause; a direct call surfaced `404 NOT_FOUND: models/gemini-2.5-flash is no longer
  available to new users`, directing new accounts to `gemini-3.6-flash`.
- **Second failure on the replacement:** `gemini-3.6-flash` rejects `thinking_budget=0` with a 400,
  which the runner was sending unconditionally to keep reasoning tokens out of a single-label
  classification.
- **Resolution:** roster switched to `gemini-3.6-flash`; the zero thinking budget became an
  optional per-model `disable_thinking` flag rather than a hardcoded call parameter.
- **Lesson:** the 16-call smoke test caught both failures before the 320-call run, which is exactly
  what the V2 rule against unpiloted paid batches is for.

### Issue 13 — Failed calls were scored as wrong answers (Phase 2.5)

- **Symptom:** the first full run reported Gemini at 44% accuracy, far below the Claude models.
- **Cause:** 43 of its 80 calls never returned - the free-tier quota answers with a 429 and a ~40s
  retry hint, which the 30s backoff ladder could not outlast - and the report counted each
  unanswered call as an incorrect answer. Of the 37 it did answer, Gemini scored 95%.
- **Why it mattered:** a rate-limited run masqueraded as a poor-quality model. Left uncorrected it
  would have produced a false and publicly unfair comparison between two vendors.
- **Resolution:** accuracy is now computed over answered items only, with unanswered calls reported
  separately in a health column; backoff widened past the quota pause. Two tests pin the behaviour,
  including one asserting an unparseable *reply* still counts against accuracy while a failed
  *call* does not.

### Issue 14 — Repo-wide formatter run pulled unrelated files into the change set (Phase 2.5)

- **Symptom:** `ruff check --fix` and `ruff format` were run across the whole repository rather
  than the files being edited, modifying 26 unrelated modules and tests.
- **Assessment:** all changes were confirmed formatting-only (whitespace, line reflowing) with no
  behaviour change, but they did not belong in a feature commit and would have made review
  impossible.
- **Resolution:** all unrelated files reverted; the commit is scoped to the roster, runner, tests,
  taxonomy, and requirements. The repository remains not fully `ruff format`-clean, which is
  pre-existing and unchanged - `ruff check .` is the standard this project verifies against.

### Issue 15 — Labelling prompt sent a quarter of the taxonomy (Phase 3)
- **What happened:** `build_system_prompt` rendered `f"- {intent.id}: {intent.definition}"` and
  nothing more — 2,707 of the taxonomy's 10,797 characters. All positive examples, negative
  examples and boundary rationales were omitted, which is exactly the content whose sharpening
  resolved 61% of the Phase 2.5 v1 errors.
- **Why it mattered:** the project was reporting model behaviour "against the taxonomy" while
  withholding the part of the taxonomy that encodes every boundary.
- **Fix:** full rendering per intent; prompt grew 3,797 → 15,080 characters. Test added asserting
  every definition, both positive examples, the negative example and the rationale appear.

### Issue 16 — Cache key omitted model and prompt identity (Phase 3)
- **What happened:** `auto_label.py` keyed cached replies on `sha256(text)` alone.
- **Why it mattered:** a two-model run would silently serve the first model's replies to the
  second, and the comparison would look clean while being fabricated. A prompt or taxonomy change
  would also leave stale replies in place. `src/pilot/run_pilot.py` already had this right; the
  labeller had not been brought into line.
- **Fix:** `cache_key(text, model=..., taxonomy_version=...)` composing model, prompt version,
  taxonomy version and text. Test asserts all four dimensions separate keys.

### Issue 17 — Haiku 4.5 silently ran uncached (Phase 3)
- **What happened:** with `cache_control` set, Sonnet 5 reported a 5,113-token cache write then
  reads; Haiku 4.5 reported `cache_creation_input_tokens: 0` and `cache_read_input_tokens: 0` on
  every call, paying full price for the ~3.8k-token prefix each time.
- **Cause:** Haiku's minimum cacheable prefix sits above this prompt's length. No error is
  raised — caching simply does not happen.
- **Fix:** roster changed to Sonnet 5 + Opus 5, which also improved the diagnostic (Decision 22).
  Recorded because the failure is silent: only `usage.cache_read_input_tokens` reveals it.

### Issue 18 — Malformed requests were retried five times (Phase 3)
- **What happened:** a schema rejection (`400 invalid_request_error`) was resent MAX_ATTEMPTS
  times with backoff before surfacing as a generic "failed after 5 attempts".
- **Cause:** `BadRequestError` subclasses `APIStatusError`, which was in `RETRYABLE_ERRORS`.
- **Why it mattered:** a 400 fails identically every time. On the 9,000-item run one schema
  mistake would have become 45,000 calls, and the real error text stays buried.
- **Fix:** `is_retryable()` — rate limits and 5xx only. Test asserts a 400 fails on the first
  attempt.

### Issue 19 — Structured-output schema rejects numeric bounds (Phase 3)
- **What happened:** `{"type": "number", "minimum": 0, "maximum": 1}` returned
  `output_config.format.schema: For 'number' type, properties maximum, minimum are not supported`.
- **Fix:** bound removed from the schema and enforced in `parse_label_response` via
  `_bounded_confidence`. Surfaced only because of Issue 18 — the retry loop had been masking it.

### Issue 20 — A confusion matrix was misread as a taxonomy defect (Phase 3)
- **What happened:** the starved-intent hunt showed 23 candidates for
  `scam_impersonation_report` and `account_compromised` landing in
  `unauthorized_vas_deduction`. This was recorded, and reported to the maintainer, as a boundary
  defect of the same shape as the v1 `refund_request` collision, with a v3 precedence rule
  proposed.
- **What was actually true:** reading the reviews showed all 23 were genuine unauthorized VAS
  charges, each naming a service (Tamasha, EFU Life, CapCut, FikrFree). The hunt patterns searched
  for "scam", "fraud" and "unauthorized", which in this corpus are the ordinary words for a
  provider charge the user never consented to. The retrieval was wrong; the model was right.
- **Lesson:** a confusion matrix built over keyword-retrieved candidates measures the retrieval,
  not the taxonomy. The v1 collision was real because it was measured against gold labels; this
  was not. Inspect the text before calling a boundary broken. Recorded in `config/taxonomy.yaml`
  beside the intent so the mistake is not re-derived.

### Issue 21 — Top-up script discarded its own previous results (Phase 3)
- **What happened:** `topup_starved.py` opened its output with `"w"`, so a second run to close a
  five-example shortfall overwrote the 225 rows from the first run; the combined total fell from
  25 to 18.
- **Fix:** output now merges by `review_id` before writing. Candidate slicing also changed from a
  fixed `[50:50+n]` window to "everything below the offset, minus what has been labelled", so
  repeat runs advance down the ranking instead of redrawing the same candidates. A draw floor was
  added because retrieval yield decays down the ranking, so the rate observed in the first slice
  over-predicts. No spend cost — every reply was already cached.

### Issue 22 — A token budget that looks language-neutral is not (Phase 4)
- **What happened:** `max_tokens=300` truncated the model's reply mid-string on longer
  non-English reviews. It surfaced as `Unterminated string` from the JSON parser, not as a
  length error, so the cause was not obvious from the message.
- **Why it mattered:** it silently dropped 8 items, 4 of them Roman Urdu - the language
  then showing the weakest agreement. A sample thinned unevenly by language is exactly what
  a script-gap study cannot tolerate.
- **Root cause:** Urdu script and Roman Urdu tokenize less efficiently than English, so an
  identical budget buys fewer words. The default favoured English without appearing to.
- **Fix:** raised to 700 and re-ran; zero failures, all four languages restored to 59-60.

### Issue 23 — Skipped items scored as model errors (Phase 4)
- **What happened:** 13 reviews the annotator skipped sat in the accuracy denominator as
  automatic misses.
- **Why it mattered:** they were unevenly distributed - 6 Urdu script against 2 English -
  and suppressed Urdu-script accuracy by roughly 6 points, manufacturing a gap in the
  direction of the founding hypothesis. Urdu script moved 56.4% -> 62.0% once excluded.
- **Root cause:** the same confusion as Issue 13, where rate-limited calls were counted as
  wrong answers. An unanswered item is not a wrong answer. Both occurrences pushed the
  result toward the prior, which is the direction that gets believed rather than checked.
- **Fix:** skipped items excluded from the denominator and reported separately, matching
  the convention already used for unanswered API calls.

### Issue 24 — A quoting bug blanked the adjudication page (Phase 4)
- **What happened:** adding the v3 intent group emitted `showV3(''+v[0]+''` into the page.
  Two adjacent string literals with no operator is a hard parse error, so the entire
  `<script>` block failed and the page rendered a header and nothing else.
- **Root cause:** the page HTML lives inside a Python `"""` block, where `\'` collapses to
  `'` before reaching the browser. The working line directly above it used `\\'`.
- **Fix:** raw strings for the escape, and the descriptive text no longer travels through
  an HTML attribute at all - only an id is passed and the text is looked up in JS, so the
  class of bug cannot recur. `node --check` on the extracted script is now run before
  restarting the server; it identified the exact line immediately.

### Issue 25 — Inline event handlers broke the page twice (Phase 5)
- **What happened:** generated markup carried `onclick="fn('+id+')"`. The argument sits
  inside a quoted attribute, inside a quoted JS string, inside a Python triple-quoted
  string, where `\'` collapses to `'` before reaching the browser. Two adjacent string
  literals with no operator is a hard parse error, so the whole `<script>` failed and the
  page rendered a header and nothing else.
- **Why it recurred:** the first fix corrected the escaping on one line and recorded that
  the bug could not return. It returned three days later on a different line, because the
  escaping was the symptom and four levels of quoting was the cause.
- **Fix:** inline handlers taking string arguments are gone. Markup carries `data-*`
  attributes and two delegated listeners read them, so there is nothing left to escape.
  `node --check` now runs against the extracted script before every restart, and it
  identified the exact line both times in under a second.

### Issue 26 — `output_config.effort` is rejected by pre-4.6 models (Phase 5)
- **What happened:** every Claude Haiku 4.5 call returned `400 - This model does not
  support the effort parameter`, so the model was silently absent from a comparison built
  to include it.
- **Why it mattered:** the parameter was added for frontier models and tested only there.
  Haiku-class models are what production deploys for high-volume work, so the defect was
  invisible in testing and total under the conditions that matter.
- **Fix:** `supports_effort()` gates the parameter by model, with tests asserting it is
  sent to Opus and withheld from Haiku.

### Issue 27 — A table's min-width scrolled away its own labels (Phase 5)
- **What happened:** results tables carried `min-width: 560px` inside a scrolling
  container. On a narrower viewport the container scrolled horizontally and the name
  column left the screen, leaving columns of numbers identifying nothing.
- **Fix:** min-width removed; below 760px the estimate bar is dropped instead, being a
  second reading of numbers already present in the row. Tables with no natural first
  column gained a header rather than a blank cell.

---

## 6. Work pending / next steps

**Every measurement the paper needs is complete. What remains is writing.**

### What the evidence now supports

| Finding | Figure | Basis |
|---|---|---|
| Authored items overstate agreement | 100% vs 74.9% | identical models, taxonomy, prompt, metric |
| ...and overstate accuracy further | 95% vs ~63% | authored gold vs human gold |
| Agreement is not correctness | both wrong on 30.8% | 26 controls where the models agreed |
| Disagreements are two-thirds difficulty | 68.7% / 31.3% | 99 adjudicated disagreements |
| **No script gap** | 8-10 point spread, all overlapping | 204 blind gold labels, length-matched |
| Keyword severity fails by script | 17 Urdu misses to 1 English | proxy vs labelled `financial_loss` |
| Reviews capture fraud only when the platform is blamed | 0 of 54,519 | two independent searches |

### Ordered plan

1. **Draft the paper.** Outline at `paper/OUTLINE.md`. Sections 3 (Data) and 5 (Design)
  are pure description and need no further decisions.
2. **arXiv preprint** for the priority claim, then a venue. WNUT is the closest fit: the
  central result is that clean authored text overstates performance against noisy real
  text. LREC is the alternative if the release leads with the dataset.
3. **Label the full 9,000** (~$21 on Sonnet 5 with caching) for the dataset release. Not
  needed for the paper.
4. **Release** review ids and derived labels with a rehydration script, not review text.

### Optional hardening, in value order

- **50 more controls** (~30 min). The 30.8% joint-error figure rests on 26 items, interval
  [16.5, 50.0]. Another 50 roughly halves that range. Highest value per minute remaining.
- **Blind self re-check, 50 items** (~30 min, after a week's gap). No second annotator is
  available, so test-retest is the measurable substitute. A low score is publishable: it
  would bound what any annotator could reach. `--mode recheck`, then
  `python -m spike.phase3_diag.self_agreement`.
- **13 revisit items** (~5 min) at `--mode revisit`, clearing the last taxonomy-version
  asymmetry. Will not move the headline; 13 of 239.

### Standing, not blocking

- **Monthly forward collection.** `python -m src.collect.refresh_reviews`. Cron line is in
  the module docstring and deliberately **not installed**. First run took 5,782 reviews in
  61 seconds. App stores serve only a recent window, so this is the one asset a later
  entrant cannot back-fill.

### Open decisions

1. Whether to install the collection cron.
2. Naming apps: the findings need no app names, the dataset does. Recommend anonymising in
  the paper, shipping identifiers under a research licence, and taking Pakistani legal
  advice before either.
3. Whether the release ships the diagnostic subset, the 9,000-item run, or both.
4. Case 05's gold label (carried from Phase 2.5): under the v2 precedence rule its correct
  answer is `transfer_failed_money_deducted`, but it was authored to test `refund_request`.
  Relabel it, leaving no bare-refund case, or rewrite its text.

### Closed since the last entry

- ~~Script-gap hypothesis~~ **Answered (Job 31).** Not supported, at ~50 gold labels per
  language with length matched and sampling unenriched.
- ~~Whether the taxonomy needs new intents~~ **Answered (Job 32).** Two added as v3, both
  measured before being added; models re-labelled so the comparison stays fair.
- ~~Per-language accuracy from the 125-item set~~ **Abandoned and replaced.** Cells of 5-9
  items could not support it; the Urdu pass was built to answer it properly.

## 7. Environment / how to resume locally

Repo: `hassan-product/UrduCX-Bench`, branch `main`. Latest code commit is the most recent
session commit on `main`; run `git log -1 --oneline` after pulling.

```bash
git clone https://github.com/hassan-product/UrduCX-Bench.git
cd UrduCX-Bench
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
pre-commit install
ruff check . && pytest   # should pass — currently 161 tests
cp .env.example .env     # fill in real keys only when Phase 3/6 needs them
```

The active `PROJECT_CONTEXT_V2.md` is stored in the maintainer's Downloads folder and is not
in git by design. Copy it manually when resuming on another machine. Raw and interim
data are also local-only and git-ignored.

**Local browser preview servers (run manually when needed):**
```bash
# Review sample (local HTML slice; regenerate before serving — not the full 107k corpus)
python -m http.server 8765 --bind 127.0.0.1 --directory data/raw/sample_preview

# Source registry (17 products, 33 listings, all approved)
python -m http.server 8766 --bind 127.0.0.1 --directory data/raw/source_registry_preview

# Availability census (33 listings, Google totals + Apple accessible counts)
python -m http.server 8767 --bind 127.0.0.1 --directory data/raw/availability_census_preview
```

**Phase 4 adjudication (serves its own page; needs no separate http.server):**
```bash
python -m spike.phase3_diag.adjudicate   # then open http://127.0.0.1:8790
```
Judgements append to `spike/phase3_diag/adjudications.jsonl`. Re-running resumes rather than
restarts. Local-only and git-ignored, like the rest of `spike/`.

**Monthly forward collection (see Decision 30):**
```bash
python -m src.collect.refresh_reviews   # new reviews only; ~60s for all 17 apps
```

**To regenerate preview HTML from updated config or collected data:**
```bash
python -m src.collect.render_source_registry
python -m src.collect.render_availability_census \
  --google-metadata data/raw/availability_census/google_metadata.json
python -m src.collect.validate_raw
python src/prep/render_clean_preview.py
python -m http.server 8768 --bind 127.0.0.1 --directory data/interim/clean_preview
```

---

## 8. Session update protocol

At the end of each working session (**`wrap`**):

1. Update this file's "Current status", "Work completed", "Issues/bugs", and
   "Work pending" sections to reflect everything done in that session.
2. `git add PROGRESS_LOG.md`, commit with message `docs: update progress log`
   (or a more specific message if useful), and `git push`.
3. This routine is scoped narrowly: it covers only updating, committing, and pushing
   `PROGRESS_LOG.md`. It never extends to destructive or irreversible git operations
   (force-push, history rewrite, branch deletion, etc.), which are always a deliberate,
   separately considered step.

---

## 9. Change history

| Date | Commit | Summary |
|---|---|---|
| 2026-08-14 | `78733bc` | Phase 0 scaffold committed and pushed |
| 2026-08-14 | `157d08c` | Created `PROGRESS_LOG.md` as project memory file |
| 2026-08-14 | `9f473af` | Phase 1 Job 1–2: app resolver, Google scraper, review preview, tests |
| 2026-08-15 | `33ea30a` | Phase 1 Job 3–6: dual-platform registry, Apple collector, census, 100k quota config |
| 2026-08-16 | `9cfae77` | Phase 1 Job 7–8: quotas, 17-app collection, empty-page guard, `validate_raw` |
| 2026-08-16 | `cb7c09e` | Phase 2 preview: cleaned-schema contract, bounded review preview, dropdown-with-checkboxes product filter, focused tests |
| 2026-08-17 | `f476db5` | Phase 3 Steps 1–2: stratified sampler, human-authored 24-intent taxonomy, committed pending Phase 2 language-detection work |
| 2026-08-17 | `b51bf9b` | Phase 2 Job 15: PII scrubber (`src/prep/scrub_pii.py`), 16 tests; not yet run against real local data |
| 2026-08-18 | `9f7e5ce` | Phase 3 Job 16: initial auto-labelling pipeline (`src/label/auto_label.py`), `anthropic` dependency added, 12 tests; no paid/provider call |
| 2026-08-18 | `02285e1` | Job 17: adopt V2 gates and decisions; preserve all data layers, retain 24 intents, harden PII, insert Phase 2.5, extend label schema, use solo verification and later baselines/CIs |
| 2026-08-18 | `2d9af61` | Ignore local `PROJECT_CONTEXT_V2.md` (amended 2026-08-20 to strip a tooling attribution trailer from the message; history rewritten and force-pushed) |
| 2026-08-20 | `275bf36` | Repo hygiene audit: removed tooling attribution and working-process traces from `.gitignore`, `PROGRESS_LOG.md`, and one module docstring; local tooling ignores moved to `.git/info/exclude` |
| 2026-08-21 | `422d2f0` | Complete Phase 2 hardened PII gate; add corrected multilingual audit, private Phase 2.5 authoring schema/validator, and reproducible Word workbook generator; pause pending completed human workbook |
| 2026-08-23 | `dee6567` | Phase 2.5 Job 20: transfer the completed 20-case workbook into the private pilot JSON, correct all 80 fact spans, fix three approved semantic defects, and record the change log; data complete, roster and runner pending |
| 2026-08-25 | `d17992d` | Phase 2.5 Jobs 21–23: pilot roster and runner, 4-model 320-classification run for $0.75, corrected accuracy reporting, taxonomy v2 failure-over-request precedence rule, widened retry backoff; script-gap hypothesis not supported, consistency effect found |
| 2026-08-27 | `9cdc7d4` | Phase 3 Jobs 24–30: repaired three labelling-pipeline defects, ran the 500-item real-data diagnostic across two models, hunted and topped up the starved intents over all 54,519 reviews, re-measured the authored set under identical conditions (100% vs 74.9% inter-model agreement), added structured outputs and forward collection, and built the blind adjudication tool |
| 2026-08-30 | `2e92e81` | Phase 4 Jobs 31-32: length-matched Urdu pass, 204 blind gold labels, script-gap hypothesis answered and not supported; taxonomy raised to v3 with two measured intents and both models re-labelled; fixed a token budget that silently favoured English and skipped items scored as model errors; paper outline added |
