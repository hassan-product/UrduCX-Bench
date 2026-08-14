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
| 1 — Data collection | **In progress** | App resolution and scraper job complete; full collection pending approval |
| 2 — Cleaning & language detection | Not started | Blocked on Phase 1 |
| 3 — Sampling & auto-labelling | Not started | Blocked on Phase 2 |
| 4 — Human verification | Not started | Blocked on Phase 3 |
| 5 — Benchmark task building | Not started | Blocked on Phase 4 |
| 6 — Scoring harness | Not started | Blocked on Phase 5 |
| 7 — Publication | Not started | Blocked on Phase 6 |
| 8 — Distribution | Not started | Human-led, not agent work |

**Environment:** Phase 0 was developed in a cloud/web dev container. Phase 1 development
continues locally on macOS in a Python 3.13 virtual environment.

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

- Added and pinned `google-play-scraper==1.2.7`.
- Added `src/collect/resolve_apps.py` with deterministic package-ID and official-developer
  checks. Resolved and human-confirmed SIMOSA, JazzCash, Easypaisa, Zong, and Ufone.
- Added `src/collect/scrape_reviews.py` with a strict seven-field non-identifying schema,
  a minimum one-second request interval, exponential-backoff retries, atomic page files,
  and JSON continuation-token checkpoints for crash-safe resume.
- Added `src/collect/render_review_preview.py` for local browser inspection of raw page
  files. The renderer rejects records outside the approved seven-field schema.
- Collected one local 20-review SIMOSA sample to verify the live API and browser preview.
  The sample, checkpoint, and generated HTML remain under ignored `data/raw/` paths.
- Added focused collection tests. Full repository validation passes with 12 tests.
- Stopped before the full 40,000–60,000 review collection run, pending human approval of
  the scraper sample as required by the one-job-at-a-time workflow.

---

## 4. Key decisions and their reasoning

1. **`PROJECT_CONTEXT.md` stays local and untracked.** It contains agent-facing working
   instructions ("you are helping a solo builder..."). It is listed in `.gitignore` so it
   is never committed or pushed. This keeps the public repo free of AI-authoring traces
   while still letting any AI assistant read it locally each session.
2. **No AI-tool references anywhere in tracked files.** No mentions of Copilot, Claude,
   Codex, Cursor, or "AI-generated" in commit messages, code comments, or docs. Common
   AI-tool local-state directories (`.claude/`, `.codex/`, `.cursor/`, `.copilot/`,
   `.continue/`, `.windsurf/`, `.aider*`) are added to `.gitignore` as a precaution, in
   case any of those tools are used locally later and drop config/cache folders into
   the repo.
3. **Code license = Apache-2.0; dataset license (once released) = CC BY 4.0** — per
   `PROJECT_CONTEXT.md` Section 12, to maximise adoption.
4. **Config files left empty rather than guessed.** `apps.yaml`, `models.yaml`,
   `taxonomy.yaml`, and `policy_docs/` require human judgment calls (Section 6 of the
   brief explicitly says "the human owns all judgment decisions"). Phase 0 intentionally
   does not pre-populate these with invented values.
5. **Phase-gate discipline.** Per the brief's working rule #2, each phase stops and
   reports against its acceptance criteria; the next phase does not start without human
   confirmation. Phase 1 has **not** been started yet — only planned.

---

## 5. Issues / bugs encountered and how they were resolved

### Issue 1 — First commit attempt blocked by pre-commit hooks
- **What happened:** Running `git commit` for the first time triggered `pre-commit`
  hooks. `ruff-format` reformatted 9 files and `end-of-file-fixer` fixed missing
  trailing newlines on ~20 files. Both hooks exited non-zero because they *modified*
  files, which aborts the commit by design (pre-commit's standard "fix and re-stage"
  pattern).
- **Impact:** Commit did not go through on the first attempt. No data loss, no broken
  state — this is expected, intentional pre-commit behaviour, not a real bug.
- **Resolution:** Ran `git add -A` again to re-stage the auto-fixed files, then re-ran
  `git commit` with the same message. Second attempt passed all 8 hooks cleanly and
  committed successfully as `78733bc`.
- **Lesson for future sessions:** Always expect a first-commit-attempt failure to be
  normal when pre-commit hooks reformat files. Re-stage and recommit rather than
  investigating it as a bug.

### Issue 2 — Ignoring AI-tool traces without leaving a trace of *why*
- **What happened:** Initially considered listing AI-tool directory names in the
  tracked `.gitignore` for clarity, but this would itself embed AI-tool references in
  a file that ships to GitHub — contradicting the "no trace" requirement.
  Note: as currently committed, `.gitignore` *does* list `.claude/`, `.codex/`, `.cursor/`,
  etc. by name (see the file directly) as a pragmatic tradeoff — tool directory names
  are configuration housekeeping, not authorship claims, so this was judged acceptable.
  `PROJECT_CONTEXT.md` itself (the clearest authorship trace) is excluded from git
  entirely rather than merely ignored-and-explained.
- **Impact:** None — resolved before any push happened.
- **Resolution:** Kept ignore rules for tool directories in the tracked `.gitignore`
  (they are just folder-name housekeeping, common in many public open-source repos),
  but ensured no narrative/commentary about *why* (i.e. no comments like
  "excluding Copilot/Claude artifacts") appears anywhere in tracked files.

No other bugs encountered so far. This section will grow as Phases 1+ produce real
code that can fail (scraping errors, rate-limit handling, PII-scrubber edge cases, etc.).

---

## 6. Work pending / next steps

**Immediate next action: continue Phase 1 only after human approval of the local scraper
sample.** The remaining build order is:

1. Run full collection, targeting 40k–60k reviews across at least four confirmed apps
  with at least 24 months of coverage.
2. Stop and present the collection output locally for human review.
3. Add and run `src/collect/validate_raw.py` for coverage and quality reporting.
4. Commit code only; raw data never leaves the local machine or enters git.
- **Acceptance target for Phase 1:** ≥40,000 reviews, ≥4 apps, ≥24 months span,
  validation report printed, no PII fields in stored schema.

**Open questions still needing the human's decision (from `PROJECT_CONTEXT.md` Section 17):**
1. Accept the 24-intent taxonomy as-is, or revise after reading a 200-review sample?
2. App scope resolved for Phase 1: SIMOSA, JazzCash, Easypaisa, Zong, and Ufone.
3. Publish both dev/test splits, or hold out test? (brief recommends publishing both)
4. Final model roster for the leaderboard.
5. Single-annotator gold set acceptable for v1? (brief recommends yes, documented in
   `LIMITATIONS.md`)

---

## 7. Environment / how to resume locally

Repo: `hassan-product/UrduCX-Bench`, branch `main`. Latest pushed commit at last update:
see Section 9 below.

```bash
git clone https://github.com/hassan-product/UrduCX-Bench.git
cd UrduCX-Bench
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
pre-commit install
ruff check . && pytest      # should pass / exit 0 with no tests yet
cp .env.example .env        # fill in real keys only when Phase 3/6 needs them
```

`PROJECT_CONTEXT.md` is not in git (by design). If starting on a new machine, copy it
over manually from wherever it was last saved before continuing.

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
| 2026-08-14 | *(pending this commit)* | Created `PROGRESS_LOG.md` as project memory file |
| 2026-08-14 | *(pending)* | Added Phase 1 app resolution, scraper, tests, and local preview |
