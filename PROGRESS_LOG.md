# PROGRESS_LOG.md — UrduCX-Bench Project Memory

> **Purpose:** This is the project's persistent brain. Read this file first in any new
> session (alongside `PROJECT_CONTEXT.md`, which holds the static build plan) to resume
> work with full context — no re-explaining required.
>
> **Update protocol:** This file is updated, committed, and pushed automatically whenever
> the human types `wrap` at the end of a working session, with no further confirmation
> requested for that specific action. See "Session update protocol" at the bottom.

---

## 1. Project one-liner

UrduCX-Bench is an open benchmark measuring how well AI models handle real
customer-service conversations in Urdu, Roman Urdu, and Urdu-English code-switched
text, in the telecom/mobile-wallet domain. Solo builder, part-time, budget under $150.

Full spec lives in `PROJECT_CONTEXT.md` (local-only, git-ignored — never pushed).

---

## 2. Current status at a glance

| Phase | Status | Summary |
|---|---|---|
| 0 — Repo & environment setup | **Done** | Scaffold committed and pushed |
| 1 — Data collection | **Done** | 17 products collected; ~107.8k unique reviews; validator printed; human reviewed localhost previews |
| 2 — Cleaning & language detection | **In progress** | Cleaned-schema helpers and a sampled browser preview are implemented; full language detection remains next |
| 3 — Sampling & auto-labelling | Not started | Blocked on Phase 2 |
| 4 — Human verification | Not started | Blocked on Phase 3 |
| 5 — Benchmark task building | Not started | Blocked on Phase 4 |
| 6 — Scoring harness | Not started | Blocked on Phase 5 |
| 7 — Publication | Not started | Blocked on Phase 6 |
| 8 — Distribution | Not started | Human-led, not agent work |

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
  pre-filled with judgment calls that belong to the human: `config/apps.yaml`,
  `config/models.yaml`, `config/taxonomy.yaml`, `config/policy_docs/README.md`.
- Created a local Python 3.12 virtual environment (`.venv/`, git-ignored), installed
  pinned dependencies, confirmed `ruff check` passes clean and `pytest` collects 0 tests
  and exits 0 (Phase 0's exact acceptance criterion).
- Set up `.gitignore` to exclude: secrets (`.env`), raw/interim data, caches
  (`outputs/cache/`, `.ruff_cache/`, `.pytest_cache/`), virtual environments, editor
  metadata, and **any AI-tool-specific local artifacts** (see decision log below).
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
  clickable store links for manual verification. The human confirmed all 33 listings.
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
- Product-filter UI went through three decisions based on the human's requested behavior:
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

---

## 4. Key decisions and their reasoning

1. **`PROJECT_CONTEXT.md` stays local and untracked.** It contains agent-facing working
   instructions ("you are helping a solo builder..."). It is listed in `.gitignore` so it
   is never committed or pushed. This keeps the public repo free of AI-authoring traces
   while still letting any AI assistant read it locally each session.
2. **No AI-tool references anywhere in tracked files.** No mentions of Copilot, Claude,
   Codex, Cursor, or "AI-generated" in commit messages, code comments, or docs. Common
   AI-tool local-state directories are added to `.gitignore` as a precaution.
3. **Code license = Apache-2.0; dataset license (once released) = CC BY 4.0** — per
   `PROJECT_CONTEXT.md` Section 12, to maximise adoption.
4. **Config files left empty rather than guessed.** `apps.yaml`, `models.yaml`,
   `taxonomy.yaml`, and `policy_docs/` require human judgment calls (the brief explicitly
   says "the human owns all judgment decisions").
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

---

## 5. Issues and bugs encountered

### Issue 1 — First commit attempt blocked by pre-commit hooks (Phase 0)
- **What happened:** `ruff-format` and `end-of-file-fixer` modified files on the first
  commit attempt, aborting it by design. Re-staged and recommitted.
- **Lesson:** Always expect first-commit hook reformatting; re-stage and retry.

### Issue 2 — AI-tool gitignore trace (Phase 0)
- Tool directory names (`.claude/` etc.) are listed in `.gitignore` as housekeeping;
  no authoring commentary appears in any tracked file.

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
- The VS Code Copilot sandbox blocked localhost socket binding (port 8765–8767) and Git's
  credential-helper IPC pipe. Resolved by retrying with `requestUnsandboxedExecution`
  for server commands and Git pushes.

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

---

## 6. Work pending / next steps

**Immediate next action: complete Phase 2 cleaning and language detection.**

The cleaned-preview inspection surface is in place. Raw data stays local. Next build order:

1. Deduplicate raw JSONL on `(platform, review_id)` — drop the ~2,989 census overlaps.
2. Normalise `product_id` via `platform_app_id` → registry map (`zong`→`my_zong`,
   `ufone`→`uptcl`, and any other display-name leftovers).
3. Detect language/script per review: `urdu_script`, `roman_urdu`, `english`, `mixed`.
   The validator's Arabic-block check is not enough; Roman Urdu is Latin script.
4. Write a single clean dataset to `data/interim/` (Parquet preferred).
5. Print a Phase 2 validation report (unique counts, date span, language mix).
6. Regenerate the cleaned preview from the completed clean dataset and review it in the
  dropdown-with-checkboxes UI.
7. Commit code only. Interim data stays git-ignored.

**Phase 1 acceptance criteria (from `PROJECT_CONTEXT.md`) — met:**
- ≥40,000 reviews across ≥4 apps spanning ≥24 months: ~107,780 unique across 17
  products, 2015–2026.
- Validation report printed (`python -m src.collect.validate_raw`).
- No PII fields in the stored schema.

**Open questions for later phases:**
1. Accept the 24-intent taxonomy as-is, or revise after reading a 200-review sample?
   (Deferred to Phase 3 — the human makes this call.)
2. Publish both dev/test splits, or hold out the test set? (Spec recommends publishing both.)
3. Final model roster for the leaderboard (Phase 6).
4. Single-annotator gold set acceptable for v1? (Spec recommends yes, documented in
   `LIMITATIONS.md`.)

---

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
ruff check . && pytest   # should pass — currently 28 tests
cp .env.example .env     # fill in real keys only when Phase 3/6 needs them
```

`PROJECT_CONTEXT.md` is not in git (by design). Copy it over manually if resuming on a
new machine. Raw data (`data/raw/`) is also local-only and git-ignored.

**Local browser preview servers (run manually when needed):**
```bash
# Review sample (local HTML slice; regenerate before serving — not the full 107k corpus)
python -m http.server 8765 --bind 127.0.0.1 --directory data/raw/sample_preview

# Source registry (17 products, 33 listings, all approved)
python -m http.server 8766 --bind 127.0.0.1 --directory data/raw/source_registry_preview

# Availability census (33 listings, Google totals + Apple accessible counts)
python -m http.server 8767 --bind 127.0.0.1 --directory data/raw/availability_census_preview
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

When the human types **`wrap`** in a chat session:

1. Update this file's "Current status", "Work completed", "Issues/bugs", and
   "Work pending" sections to reflect everything done in that session.
2. `git add PROGRESS_LOG.md`, commit with message `docs: update progress log`
   (or a more specific message if useful), and `git push` — **without asking for
   further confirmation**, since this is a standing instruction covering exactly this
   one file and this one action.
3. This standing permission is scoped narrowly: it covers only updating, committing,
   and pushing `PROGRESS_LOG.md`. It does not extend to other destructive or
   irreversible git operations (force-push, history rewrite, branch deletion, etc.),
   which still require explicit confirmation each time.

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
