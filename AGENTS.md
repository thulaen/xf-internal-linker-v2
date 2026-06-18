# Agent Instructions (Codex / OpenAI Codex / CI Agents / Gemini / Claude)

**ABSOLUTE — Fast session-start payload is the default for every agent.** At session start, run `python scripts/session_start_payload.py` as the single first startup command. Do not run `docker compose exec -T backend python manage.py refresh_session_start_payload` during normal chat startup. Do not read `audit/session_start_payload.jsonl` to reconstruct markers. Only run live startup commands when the user explicitly asks for live startup debugging.


## SESSION START — NON-NEGOTIABLE FIRST STEP

1. Open `AGENT-HANDOFF.md` and read the most recent entry before doing anything else.
2. Your **very first response** must begin with this line (fill in the brackets):
   `[HANDOFF READ: <date of last entry> by <agent name> — <one-sentence summary of what they did>]`
3. At session end (or when stopping mid-task), append a new entry using the template at the top of `AGENT-HANDOFF.md`.

Skipping step 1 or 2 is a protocol violation. The acknowledgement line in your first response is proof you read it — without it, assume this step was missed and do it now.

**ABSOLUTE — Cross-agent progress pulse (Claude / Codex / Gemini / Antigravity / every future agent).** Near the start of EVERY reply — not just commits, every chat turn — surface the current progress line so the user always sees how much current chat work is left and whether anything is stuck. Start a requested task with `python scripts/agent_progress.py --start-task "<short plain-English task>" --steps "Inspect|Change|Test|Report" --force`, update it while working with `python scripts/agent_progress.py --step "<step>" --status in_progress|done|blocked --force`, and finish it with `python scripts/agent_progress.py --finish-task --force` before the final reply. The command refreshes the shared file `audit/agent_progress_latest.txt`, self-throttles to a 10-minute cadence, and prints the `[PROGRESS ...]` block ONLY when at least 10 minutes have passed since the last shown line OR something is stalled, unless `--force` is used for an explicit task update. Include that printed block in your reply. If no active chat task exists, the progress line may show the current uncommitted-file count as repo context, but agents must not treat that count as task completion. If `agent_progress.py` cannot run in your environment, instead read and surface the contents of `audit/agent_progress_latest.txt`. A `Stuck? YES` line means a run has wedged — a quality/mutation container sitting at ~0% CPU, a mutation lock held too long, or the current chat task has been marked blocked; investigate and clear the problem before continuing, and never leave a stall unreported. The pulse is kept fresh while no agent is replying by the optional `XFLinker - Agent Progress` Scheduled Task — install it once with `scripts/install-agent-progress-task.ps1` (user-level, no admin). This rule makes the 10-minute pulse identical across every agent instead of something one agent types by hand.

**ABSOLUTE — Language ownership ruleset (updated 2026-06-18):**
- **Python** owns Django, orchestration, module APIs, models, migrations, admin/operator workflows, management commands, schedules, analytics ingestion, report generation, approved offline ML, GUI backend endpoints, and MCP registration. Python may train candidate ranking profiles offline.
- **Rust** owns production correctness and hot paths. That includes domain invariants, ranking validity, governance decisions, never-zero weights, movement budgets, score validation, search execution, reranking, normalization, missing-value policy, score breakdown validation, helper workers, optional GPU dispatch, artifact validation, and performance-sensitive compute. Rust must validate, activate, promote, roll back, and live-score ranking profiles.
- **TypeScript/Angular** owns the browser UI, interaction state, visual workflows, forms, dashboards, and user-facing controls.
- **PostgreSQL** owns durable relational storage. **ClickHouse, DuckDB, and Polars** own analytics or offline exploration only.
- **Java** is reserved for later JVM-specific needs such as enterprise integrations, JVM libraries, search/index tooling, streaming connectors, or long-running services. It must not replace Python orchestration, Rust correctness, or Angular UI without a concrete reason.
- **No other first-party language owns production behavior.** C, C++, Go, Haskell, and Lua are removed. Do NOT implement them — `.githooks/check-removed-languages.py` hard-blocks. See `docs/adr/0007-python-rust-two-language.md` and `docs/PYTHON-RUST-MIGRATION-PLAN.md`.

**ABSOLUTE — Tests are on Dell whenever the repo has a Dell-backed runner.** Do not run or summarize Windows-only tests as complete when a Dell path exists. Python quality and test work must use the repo-owned turbo/Dell runners when available; Rust tests, lint, formatting, builds, mutation, fuzzing, and benchmarks run through `scripts/dell-rust.sh` on the `dell` Docker context. A local or single-container run is only a diagnostic after the Dell/turbo path fails or when the agent records a plain-English blocker proving Dell is unavailable.

**ABSOLUTE — Bazel is the default quality entry point (added 2026-06-18).** Agents must start quality work through Bazel, using `python scripts/bazel_default.py test //tools/quality:all` for the default suite or `python scripts/bazel_default.py run //tools/quality:<target>` for a scoped target. Old public language quality paths are deleted. Do not bypass Bazel by calling lower-level test or lint helpers directly unless you are debugging a failed Bazel target and you say that plainly in chat.

---

## Trigger discipline and chat-notification protocol

After every commit attempt, every push attempt, and every turn, the agent must
report the outcome in chat. No silent operations. No improvised formats. Pick
exactly one template below and fill in the placeholders.

After commit + push success:
```
Commit succeeded: <sha7>
Pushed to: <branch>
Findings filed: <N> (<#a, #b, #c>) — or "none" if N=0
CI: triggered, https://github.com/<owner>/<repo>/actions/runs/<id>
Hard-floor checks: all passed
Status: ready for next change
```

After commit but no push because only "commit" was requested:
```
Commit succeeded: <sha7>
Pushed: not requested
Findings filed: <N> (<#a, #b, #c>) — or "none" if N=0
Hard-floor checks: all passed
Status: ready for push or next change
```

After commit blocked:
```
Commit blocked: <hook-name> <reason>
Findings filed: 1 (#<id> — commit_blocker)
Push: skipped (commit did not land)
Suggested next: <specific fix>
Status: working tree still dirty, no commit
```

After commit succeeded but push failed:
```
Commit succeeded: <sha7>
Push failed: <reason>
Findings filed: <N> (<#a, #b, #c>) — or "none" if N=0
Suggested next: <specific recovery>
Status: commit landed locally, push still needed
```

After an edit-only turn with no commit signal:
```
Files changed: <list>
Not committed yet (waiting for commit signal)
Findings preview (would file on commit): <N> across <hook list>
Status: ready for review or commit
```

If a commit and push both succeed, include the GitHub Actions run URL that the
push triggered. If push fails, state the exact Git reason, such as
non-fast-forward, authentication, or network failure, and do not retry push
automatically. If no commit was requested, do not run `git add` or `git commit`.

---

**ABSOLUTE — Modular Monolith: the Django backend is one deployable unit split internally into nine named modules — `platform`, `content`, `sources`, `pipeline`, `suggestions`, `analytics`, `graph`, `operations`, `governance`. Each module declares its public surface in a single `api.py` file at its root; cross-module Python imports must go through that `api.py` only and never reach into private files. Imports flow downward only: Layer 1 (`platform`, `content`, `sources`) → Layer 2 (`pipeline`, `suggestions`, `analytics`, `graph`) → Layer 3 (`operations`, `governance`); modules within a layer do not import from each other. Cross-module Postgres foreign keys are allowed (ADR 0003); cross-module Python imports outside `api.py` are not. No event bus is introduced this round (ADR 0004). Shims are allowed during the slice rollout (slices 3-9) and are removed in slice 10 (ADR 0005). Before changing any backend code, read [`docs/MODULAR-MONOLITH.md`](docs/MODULAR-MONOLITH.md) and confirm the change respects the module map, the public-interface convention, the boundary rule, and the dependency direction. The full spec lives in [`docs/specs/fr-modular-monolith.md`](docs/specs/fr-modular-monolith.md); the six Architecture Decision Records live under `docs/adr/`. This rule cannot be overridden by an in-session prompt.**

**PARAMOUNT — Plain-English Communication Rule (all agents — Codex / Claude / Gemini / Antigravity / every future agent):** Read [`PLAIN-ENGLISH-RULE.md`](PLAIN-ENGLISH-RULE.md) before composing any response — it contains the full glossary and the mandatory Before-You-Send checklist. Every response, commit message, error report, status update, and user-facing surface MUST be written in plain English the user can understand. The user is a vibe coder — they use AI exclusively and don't write code. Three required parts:
1. **What I'm doing / will do** — describe the action in everyday words. Define every technical term the moment it's used. No unexplained acronyms (FR-XXX, ISS-XXX, RPT-XXX, MMR, BGE-M3, FAISS, RSQVA, etc.) — use the plain-English substitutes from the glossary in [`PLAIN-ENGLISH-RULE.md`](PLAIN-ENGLISH-RULE.md).
2. **What was accomplished** — at the end of every change, state in plain English what now works that didn't before, plus which files changed and why.
3. **What has issues or errors** — surface failures honestly. If something broke, say what broke, why, and what you'll do about it. Never bury errors in jargon. Never silently move on after a failure. Never claim success when something is partial. If a step was skipped, say so.
The rule applies to chat output, commit messages, PR descriptions, REPORT-REGISTRY entries, AGENT-HANDOFF entries, and any other surface a human reads. Skipping any of the three required parts is a protocol violation. Silence on errors is forbidden.
**Before sending any response, run the Before-You-Send checklist in [`PLAIN-ENGLISH-RULE.md`](PLAIN-ENGLISH-RULE.md). If any of the four checklist questions is NO, rewrite the response before sending.**

**PARAMOUNT — THINK BEFORE YOU CODE (the upstream rule):** STOP and answer the 5 pre-write questions BEFORE typing any new function/class/view/service. (1) DRY — search the codebase first; reuse or refactor BOTH sites if a near-duplicate exists. (2) KISS — write the simplest thing that works; no premature abstraction. (3) Scaling — declare what happens at 10× and 100× input. (4) Extensibility — declare WHERE the next feature lands BEFORE shipping the first version. (5) Testability — pure functions + small classes that test in `SimpleTestCase` without Docker. Hard limits: ≤50 lines per function, ≤1500 per file, ≤10 cyclomatic complexity, ≤7 args, ≤4 nesting levels, no duplicated 6+ line blocks. **Leave every file in BETTER shape than you found it.** Read [`THINK-BEFORE-YOU-CODE.md`](THINK-BEFORE-YOU-CODE.md) before writing a single line — this is the upstream rule that prevents the messes the other paramount files clean up after.

**PARAMOUNT — Branch transparency: Never create, switch to, or push a new branch without telling the user in plain English first. Work done on a branch does not appear on `master` until merged. If the user did not ask for a branch, stay on `master`. Silence is forbidden.**
**PARAMOUNT — Subagent batch limits (added 2026-06-10, applies to Claude / Codex / Gemini / Antigravity / every future agent):** A subagent is a helper agent that an agent launches to work on a piece of the task in parallel. When fanning work out to subagents: **minimum 3 subagents per fan-out; maximum 5 subagents running in parallel at any time; pause and report to the user before starting the next batch.** The between-batch report is plain English and states what the finished batch accomplished or found and what the next batch will do. Launching a sixth parallel subagent, skipping the between-batch report, or running an unbounded fan-out is a protocol violation. This applies to every fan-out surface — direct subagent launches, workflow scripts, and any future orchestration tool: chunk parallel work into batches of at most 5 and report between batches.
**PARAMOUNT — Strict no-duplicates rule: No persistent storage may pile up duplicate artefacts. Read [`NO-DUPLICATES.md`](NO-DUPLICATES.md) before adding any new artefact table.**
**PARAMOUNT — Docker-managed Rust builds: Rust crates build through the Docker-managed maturin path. Do not require a host Rust toolchain and do not commit generated build output.**
**PARAMOUNT — Shared-library first: before creating any custom library, helper, wrapper, or hot-path module, search for existing shared code and reuse it. New hot-path code is a Rust crate under `rust/extensions/` exposed to Python via PyO3 — reuse an existing crate first.**
**ABSOLUTE — Claude/Codex BDD and TDD workflow:** Use behavior-driven description (`Given / When / Then`) when talking to the user, and use test-driven development when writing code. Before writing tests or code, read the prior resolved lessons for the area you are about to touch so you do not repeat a known trap. Write or update a focused test before or alongside the code, run it, fix the code, and rerun until it passes. Keep temporary failing tests, generated fixtures, coverage files, and profile dumps in ignored disposable paths; if a temporary test proves a real behaviour rule, turn it into a small permanent regression test.
**ABSOLUTE — Scoped self-review:** Before any summary, review only the task scope using real evidence from the diff, touched files, direct call sites, tests, and tool output. Do not invent findings or turn the review into a broad audit. Log every real bad practice you find with `manage.py log_self_review_issue`, fix in-scope issues without changing behaviour, and say plainly when nothing needed fixing.
**ABSOLUTE — Future-ready testing tools: new code is not complete unless the Docker-managed test, coverage, lint, mutation/fuzz, and benchmark tools can discover and check it. If a task adds a new language, folder, framework, runtime path, or build target, update the tool wiring in the same change. Host-only tools are forbidden.**
**PARAMOUNT — Hardware-aware defaults: Read [`HARDWARE-PROFILES.md`](HARDWARE-PROFILES.md).**
**PARAMOUNT — Disk-pressure circuit breaker: Read [`DISK-PRESSURE-RULES.md`](DISK-PRESSURE-RULES.md).**
**PARAMOUNT — Deep-linking catalog: Read [`DEEP-LINKING-CATALOG.md`](DEEP-LINKING-CATALOG.md).**
**PARAMOUNT — Plain-English helpers: Read [`PLAIN-ENGLISH-HELPER-RULE.md`](PLAIN-ENGLISH-HELPER-RULE.md).**
**PARAMOUNT — Citations on every default: Read [`CITATION-RULE.md`](CITATION-RULE.md).**
**PARAMOUNT — Tech-debt reduction is mandatory each session: read [`TECH-DEBT-MANDATE.md`](TECH-DEBT-MANDATE.md). The handoff entry MUST include a "Tech-debt delta" line; sessions without one fail the handoff protocol.**
**PARAMOUNT — Performance-safe defaults forbidden patterns: read [`PERFORMANCE-SAFE-DEFAULTS.md`](PERFORMANCE-SAFE-DEFAULTS.md). No unbounded loops, no unbounded table growth, no duplicate artefacts; hot paths belong in Rust.**
**ABSOLUTE — Native rewrite escalation is evidence-only: If profiling and benchmark proof show that a hot path cannot meet the performance target in Python, an agent may recommend a narrow rewrite in Rust only after normal fixes have been attempted or ruled out: algorithm changes, data structures, query or index fixes, caching, batching, concurrency, allocation cuts, serialization cuts, I/O cuts, and configuration tuning. Profile first and prove the ceiling before proposing the rewrite. Check first whether an existing Rust crate under `rust/extensions/` can be reused safely. New Rust hot-path code is preferred only when the boundary is narrow, stable, measurable, independently testable, observable, and versioned, and does not duplicate business rules or create circular dependencies. The faster proven Rust path becomes the default (Rust owns the hot paths and has no Python fallback). Broad rewrites are forbidden unless measured proof shows the wider architecture cannot meet the budget. A rewrite is not allowed for bottlenecks caused mainly by database latency, network I/O, external APIs, bad queries, missing indexes, queue delay, broken locking design, or weak caching.**
**PARAMOUNT — Glossary update rule: every time you introduce a new technical thing (feature, signal, setting, acronym, framework name, abbreviation), add a one-line plain-English explanation to the glossary in `PLAIN-ENGLISH-RULE.md` in the same change. Read [`GLOSSARY-RULE.md`](GLOSSARY-RULE.md).**
**Before any work, follow the Session Gate in `AI-CONTEXT.md` — it is the single source of truth for what to read, update, check, and log.**
**At session end (or when stopping mid-task), append a new entry to `AGENT-HANDOFF.md` using the template at the top of that file. See the SESSION START block at the top of this file for the mandatory read + acknowledgement steps.**
**ABSOLUTE — Commit Request Gate:** A commit request is a request to complete the session-type-scaled AutoIssue quota first (docs 0 / reconciliation 10 / infrastructure 20 / feature full, self-capping at the number of issues that actually exist). Do not ask the user whether to resolve them. Do not make a partial commit to avoid the blocker. Do not unstage `AGENT-HANDOFF.md` or `AI-CONTEXT.md` to bypass the database check. If the fixes are too large for the current turn, stop before committing and leave a clear status note.
**ABSOLUTE — Self-Written Code Quality Gate:** Any code an agent writes must be fixed until it meets the coding guidelines, coverage target, mutation-test rule, and required test commands. If a required check cannot run, fix the check environment or command until it runs. Do not ask the user whether to fix code you wrote. Do not commit code with failing tests, unmet coverage, skipped mutation tests, missing tools, broken containers, or known guideline violations. If the machine itself cannot support the check after repair attempts, stop before committing and leave a clear status note. Do not commit.
**ABSOLUTE — Turbo quality model is mandatory for every agent and every language check.** Turbo quality model means the repo's split-run verification path that sends eligible quality work to helper machines and gathers the results back into one report. The Dell helper machine exists and must be used whenever the repo-owned runner supports it. Its Docker context is `dell`, its backend quality image is `xf-linker-backend-quality:latest`, and the Python turbo runner currently assigns 100% of the quality load to Dell and 0% to Windows. The Mint helper still exists for observability and any runner whose config names it, but agents must not assume Mint is the only helper. Every agent — Codex, Claude, Gemini, Antigravity, and every future agent — MUST use the turbo path for Python and Rust quality work whenever a repo-owned turbo runner or shard planner exists. This applies to normal tests, coverage, lint or static checks, mutation tests, fuzz tests, benchmarks, and build verification. It is NOT mutation-only. A single-container, one-machine, or low-core run is allowed only as a small diagnostic after a turbo run has failed, or when the agent records a plain-English blocker that proves the relevant helper machine is unavailable. Do not call a half-sized scoped run "complete" when turbo was available. Handoff entries and final summaries must state `turbo=used` or `turbo=blocked:<plain reason>` for every quality command group. Source-backed Dell setup: `docs/specs/fr-dell-mutation-runner.md`.
**If the Report Registry shows an open or reopened finding in the area you are about to touch, tell the user in chat before writing code. Silence is forbidden.**
**ABSOLUTE — AutoIssue quota at commit, scaled by session type:** At normal chat startup, use the fast payload command at the top of this file. Do not run `print_open_issues` as a second startup command unless the user explicitly asks for live startup debugging or asks what remains open. The fast payload includes the compact `[REGISTRY READ: ...]` counts and picked issue IDs. At commit, `check-autoissue-quota.py` runs `manage.py verify_autoissue_quota`, which requires you to resolve a number of AutoIssues that scales with the session type — docs 0, reconciliation 10, infrastructure 20, feature full — and self-caps per source at the number of issues that are actually open (a source with nothing open is auto-satisfied). Fix the required issues before finishing whatever the user asked for. **Before writing the first line of code in any file**, run `python scripts/backend_manage.py search_resolved_issues --area <repo-relative-path> --force` for each directory you will touch (for example `--area backend/apps/audit`); it surfaces the prior `lessons_learned` for that area so you do not repeat a known trap. If you find any new bug, performance bottleneck, missing validation, or code smell during the session — even outside scope — log it as an `AutoIssue(source='agent')` and a registry entry in the same change; silently moving on is forbidden. When you resolve an issue, fill its `lessons_learned` with two parts before marking it resolved: (1) the trap (what is not obvious about this code area), (2) the fix shape (what worked). An empty `lessons_learned` on a resolved row loses the lesson for the next agent. When fixing: keep it simple, keep functions short, avoid duplication, and refactor for performance in the same change.**
**ABSOLUTE — Agent Guard retired (updated 2026-06-12).** The old `scripts/agent_guard.py` and watcher are removed because they enforced agent-process ceremony instead of proving working code. Keep the underlying engineering rules: write tests first, keep functions small, avoid duplicated code, run the real quality checks, and use task-completion quality-debt reporting for planning signal.

**PARAMOUNT — Ongoing code quality (fix as you go, severe finds to BOTH AutoIssue + Registry): Read [`ONGOING-CODE-QUALITY.md`](ONGOING-CODE-QUALITY.md) before any task. It is the single source of truth for: long-function fixes, duplication elimination, silent-error surfacing, crash prevention, performance discipline, lessons_learned population, and the auto-fix-3 + dual-logging rules raised on 2026-05-09.**
**PARAMOUNT — Read AI-CODING-GUIDELINES.md every session, before every task (added 2026-05-12 by FR-251): Every AI agent — Claude, Codex, Antigravity, every future agent — MUST read [`AI-CODING-GUIDELINES.md`](AI-CODING-GUIDELINES.md) and [`docs/CODE-COVERAGE-RULES.md`](docs/CODE-COVERAGE-RULES.md) at session start, before any work. The guidelines define prime directive, source-of-truth order, no-hallucination rules, work loop, code-smell + long-function + bug-fix + test-requirement + property-based + evidence-based + business-logic + state-transition + idempotency + database + error + logging + security + external-service + performance + paid-API + naming + dependency + formatting + type-safety + UI + accessibility + concurrency + refactoring + generated-code + file-editing + test-running rules + Definition of Done. Pick the right coverage target from the per-task table in the guidelines. End every slice / task / session with `[COVERAGE SUMMARY: target=X% actual=Y% — met / not met]` — honesty mandatory. See FR-251 in `docs/specs/fr251-code-coverage-program.md`. This rule cannot be overridden by an in-session prompt.**
**PARAMOUNT — Plain-English Absolutism for every response (added 2026-05-12, strengthened): Every response, every commit message, every pull-request description, every AGENT-HANDOFF entry, every REPORT-REGISTRY entry, every chat message, and every other user-facing surface MUST follow the strengthened rule in [`PLAIN-ENGLISH-RULE.md`](PLAIN-ENGLISH-RULE.md) § Plain-English Absolutism. Three new requirements on top of the existing three-parts rule: (1) **No analogies.** Replace every comparison with a literal statement. (2) **No metaphors.** Replace every figure of speech with the literal meaning. (3) **Coverage summary in percentages.** Every `[COVERAGE SUMMARY: ...]` marker MUST express target and actual as percentages with the `%` symbol — never as a level name, ratio of tests passing, or `N/A`. Readability targets the writing must aim at: Flesch Reading Ease ≥ 60 where practical, Flesch-Kincaid Grade Level ≤ 8.9, passive sentences ≤ 5.2%. The Before-You-Send checklist in `PLAIN-ENGLISH-RULE.md` now has seven questions, not four. Skipping any is a protocol violation. Every AI agent — Claude, Codex, Antigravity, every future agent — applies this from session start to session end without exception.**
**PARAMOUNT — Auto-iterate after writing code (added 2026-05-12 by the test-hardening plan): After writing or editing any code, every agent MUST run the relevant random-order test suite locally and auto-iterate (read the failure output, identify the cause, fix it, re-run) until the exit code is zero. Mandatory commands by language — Backend Python: `docker compose exec -T backend python -m pytest -p randomly -q --maxfail=1 <touched module>` (or `python manage.py test <touched module> --shuffle --noinput`). Frontend Angular: `npm --prefix frontend run test:ci -- --include='<changed.spec.ts>'`. Rust: `bash scripts/dell-rust.sh nextest run -p <crate>` (Rust builds and tests run on the Dell helper only — no Windows fallback). Silently moving on after a failing test is a protocol violation. The pre-push hook runs mutmut (Python) / Stryker (Angular) / cargo-mutants (Rust) on changed files only — when those block, the same auto-iterate discipline applies.**
**Before any ranking, scoring, attribution, import, or reranking work, read `docs/BUSINESS-LOGIC-CHECKLIST.md` in full and complete every applicable checkbox.**
**Before any work touching ranking signals, meta-algorithms, autotuners, or weight-preset keys, read `docs/RANKING-GATES.md` and satisfy Gate A (implementation — fires when CODE is about to be written) and Gate B (user-idea intake — fires the moment an idea is PROPOSED). Every checkbox must pass or have an explicit written justification. Skipping either gate is a policy violation. Applies to Claude, Codex, Gemini, Antigravity, and every future agent.**
**Before any Python backend work, read `backend/PYTHON-RULES.md` first.**

This file applies to every AI agent that works on this repository.
Read all sections before making any changes to frontend styles.
**Before any frontend styling work, also read `frontend/FRONTEND-RULES.md`.**
**Before any frontend work, also read `frontend/DESIGN-PATTERNS.md` — the authoritative GA4 design language reference (extracted 2026-04-20). Card anatomy, co-location rules, button sizing, spacing tokens, and the 11 anti-patterns that contaminate layouts.**

---

## Code Quality Mandate — All AI Agents

These rules apply to every AI agent working in this repo (Claude, Codex, Gemini, etc.).
Goal: keep the codebase fast, organised, and stable as it grows — without introducing surprise changes.

### Do this automatically (no approval needed)
- **Clean up code you are already touching.** If a function you are modifying is messy, overly long, or duplicates logic nearby, tidy it as part of the same task. Do not leave it worse than you found it.
- **Fix bugs you encounter in the area you are working in**, even if they were not part of the original request. Note what you fixed in your response.
- **Prefer reuse over invention.** Before writing new logic, search for an existing function, utility, or component that already does the job. Extend it rather than duplicate it.
- **Handle unexpected errors.** Every function that touches external data (API calls, file I/O, DB queries) must include error handling. Never let an exception silently swallow a failure.

### Flag and ask first (do NOT do automatically)
- **Large refactors** — if fixing the task properly requires restructuring a file, module, or service beyond what you are already touching, stop and explain the situation in plain English before writing code. Get approval first.
- **Confusing or conflicting requirements** — if the request contradicts existing logic, another rule, or the architecture, pause and flag the conflict before writing code.
- **Risky logic** — if a change could affect data integrity, scoring, ranking, attribution, or imports, flag it explicitly and wait for confirmation.
- **A clearly better approach exists** — if you see a significantly better way to build what was asked, describe it and ask whether to proceed with the original plan or the better one.

### Performance is correctness
- **Slow hot-path code is a bug.** Treat it with the same urgency as incorrect output.
- **Rust owns the performance hot paths.** Rust crates under `rust/extensions/` (exposed to Python via PyO3) are authoritative for hot-path compute and have no Python fallback. See `backend/PYTHON-RULES.md` §19.
- **File performance findings in the Report Registry** (`docs/reports/REPORT-REGISTRY.md`). If you discover a hot-path function running >2× slower than expected, file it as MEDIUM. >5× is HIGH. Incorrect results from an optimisation is CRITICAL.
- **No feature is "done" if its hot path has no benchmark coverage.** Every hot-path function needs benchmarks at 3 input sizes before merge.
- **Poor performance in the Report Registry must be resolved** before the affected area is declared Phase-complete.
- **The compose stack is prod-only (applies to Claude, Codex, Gemini, any agent).** `docker-compose.yml` is the single canonical compose file; every `docker compose up` boots the production Angular bundle (`xf-linker-frontend-prod:latest`) + Django production settings. Do not add a dev-frontend service, do not recreate override/prod compose files, do not run the Angular dev server inside docker. Unit/integration test runs (`ng test`, `pytest`) are exempt — they use their own test settings and bypass the stack. Any performance claim must state the commit and that it came from the prod stack. Full rationale: `docs/PERFORMANCE.md` §13.

### Rust Session Gate — Mandatory
- **No Rust feature is "done" without test coverage.** Every Rust crate under `rust/extensions/` must have tests covering the happy path and the primary failure mode.
- **Hot-path benchmarks are non-negotiable.** Every new or modified Rust hot path must have a Criterion benchmark under `rust/extensions/<crate>/benches/`; Python hot paths use pytest-benchmark under `backend/benchmarks/`.

### Ongoing Code Quality Rules — Claude · Codex · Antigravity · Every Agent

These rules apply continuously — not just when asked. Every session, every file touched, every task.

- **Fix minor bugs and refactor for performance as you go.** While working on a task, if you spot a nearby bug or a slow code path, fix it in the same commit. Note what you fixed.
- **Surface silent errors — never let them pass.** If code catches an exception and does nothing (or just logs it and carries on), that is a silent error. Replace it with a specific exception type, a real log entry, and — where appropriate — a re-raise. Silent failures are bugs.
- **Prevent crashes.** Guard against None/null, out-of-bounds access, missing keys, and unvalidated external data at every system boundary. Internal code may trust itself; external data never can.
- **Eliminate code duplication.** If you see the same block of logic in two or more places, extract it into one shared function before adding a third copy. Six or more duplicated lines is the hard limit — extract immediately.
- **Don't defer.** Address all issues you find in the area you are working in. Do not leave a comment saying "TODO: fix later" and move on. If the fix is out of scope, file it in the Report Registry with a severity rating, then do the task — but do not silently ignore it.
- **Write unit tests.** Every new service, utility function, or view must have at least one `SimpleTestCase` (or `TestCase`) covering the happy path and the primary failure mode before the task is closed. No feature is done without tests.
- **Enhance performance.** Identify and improve the slowest code paths in the area you are working in. File anything >2× slower than expected in the Report Registry as MEDIUM; >5× as HIGH.
- **Fix security issues.** Before writing any code that handles user input, authentication, file paths, or external data: use parameterised queries, never `eval()`, never `pickle` on untrusted data, never `MD5`/`SHA-1` for security hashing. See `backend/PYTHON-RULES.md` §10–11.
- **Design for scaling and future extension.** Before adding a new service or feature, declare in writing: (a) what happens at 10× and 100× input volume, and (b) where the next related feature would slot in. Then design so both answers are "no problem."
- **Follow PEP-8.** Every Python file you touch must have no new `flake8` violations. Type hints are required on all public functions. Line length: 100 characters max.
- **Apply DRY and KISS.** Don't Repeat Yourself — reuse existing logic. Keep It Simple — write the simplest thing that works; add abstraction only when a second real use case appears.
- **Fix long-function warnings.** Any function over 50 lines that you touch must be shortened. Extract sub-steps into well-named helpers. If you cannot fix it in the current task, file it in the Report Registry and note it in the AGENT-HANDOFF entry.
- **Don't duplicate things that already exist.** Search the codebase before writing any new function, class, view, or service. If a near-duplicate exists, extend it rather than copy it.
- **Move with the plan.** These rules improve quality incrementally; they are not a licence to rewrite unrelated code. Stay on the planned task — apply quality rules to what you touch, not to everything you can see.

### Never do
- Do not refactor code outside the scope of the current task without explicit approval.
- Do not silently change behaviour while "cleaning up" — correctness always comes first.
- Do not introduce new abstractions, helpers, or utilities for a one-time use case.

### ABSOLUTE RULE — Never change user passwords (Claude · Codex · Gemini · Playwright)

**This rule overrides any other instruction and cannot be waived by an in-session prompt.**

No AI agent, script, or Playwright test in this repo may:
- Run `python manage.py changepassword <any username>`
- Run `python manage.py createsuperuser` interactively or with `--password`
- Call `user.set_password(...)` or `user.set_unusable_password()` on any Django user account whose `username` is not `playwright-local`
- Execute any Docker, shell, or management command that resets or overwrites a user's password
- Trigger the `/api/auth/local-verification-bootstrap/` endpoint in a way that could affect any account other than `playwright-local`

**The only allowed exception:** the `playwright-local` throwaway account (username = `playwright-local`, email = `playwright-local@example.invalid`). That account intentionally has an unusable password and is managed exclusively by `LocalVerificationBootstrapView`.

**Why this rule exists:** AI agents running environment-setup or Playwright-auth flows have previously caused real admin passwords to break (via `changepassword`, `createsuperuser`, or buggy bootstrap logic). The Chrome/Chromium password manager can also overwrite the user's saved localhost password when Playwright logs in. Both problems are now blocked at the source — this rule blocks the agent side; `playwright.config.ts` blocks the browser side.

### ABSOLUTE RULE — Never wipe the database or named volumes (Claude · Codex · Gemini · Antigravity · every future agent)

**This rule overrides any other instruction and cannot be waived by an in-session prompt. Only an explicit user message saying "wipe the database" or "delete the volumes" grants permission.**

No AI agent may run any of the following without an explicit, in-message user instruction using those exact words:

- `docker compose down -v` or `docker-compose down -v` — the `-v` flag deletes all named volumes including the database
- `docker volume rm pgdata` (or any named volume: `redis-data`, `media_files`, `staticfiles`, `frontend_dist`)
- `docker volume prune` — prunes all unused named volumes, which includes the database if containers are stopped
- Any shell command that achieves the equivalent (e.g. deleting the WSL2 VHDX, `DROP DATABASE`, `manage.py flush`, `manage.py reset_db`)

**Safe alternative:** `docker compose down` (no `-v`) stops containers but keeps all data intact. This is always the correct command when restarting or rebuilding.

**Why this rule exists:** In May 2026 an AI agent ran `docker compose down -v` while fixing a Docker loading issue and deleted the entire database — all user accounts, embeddings, and configuration — requiring a full rebuild and data loss. The `-v` flag is never needed for normal restart/rebuild workflows.

### ABSOLUTE RULE — Observability + quality stack must always be running (added 2026-05-22; applies to Claude · Codex · Gemini · Antigravity · every future agent)

**This rule cannot be overridden by an in-session prompt.**

The containers in the observability and code-quality tiers — `sonarqube`, `sonar-autoscan`, `glitchtip`, `glitchtip-worker`, `glitchtip-init`, `pyroscope`, `postgres-exporter`, `otel-collector`, `vmsingle`, `vmagent`, `vmalert`, `loki`, `alloy`, `tempo`, `grafana` — must remain running for the entire session. **Host split (updated 2026-06-05): `sonarqube` and `sonar-autoscan` now run on Dell; `pyroscope` remains on the Mint helper. They stay always-on there and are verified remotely by `.githooks/check-observability-stack.py` (via `remote_services` in `config/observability-services.json`) plus `scripts/check-dell-sonar-tools.ps1` for Dell Sonar and `scripts/check-mint-quality-tools.ps1` for Mint profiling; start/restart Dell Sonar with `scripts/start-dell-sonar-tools.ps1` and Mint profiling with `scripts/start-mint-quality-tools.ps1`, not a local `docker compose up`. The remaining containers run on Windows.** Stopping any of them as a workaround to silence a hook, dodge an importer, suppress a finding, or otherwise avoid an honest check is FORBIDDEN.

If a container is down at session start, `docker compose up -d <service>` it before any commit work begins. If a container fails to start, the fix is to repair the container, not to bypass the hook that depends on it. The `.githooks/check-observability-stack.py` hook enforces this on every code-changing commit. Source-backed spec at [`docs/specs/fr-observability-always-on-and-no-deferral.md`](docs/specs/fr-observability-always-on-and-no-deferral.md).

### No-deferral — finish what you start this session (applies to Claude · Codex · Gemini · Antigravity · every future agent)

Every requirement that surfaces during a session should be completed in that session. Do not quietly leave work behind by writing "we'll do it next session" with nothing to back it. The only acceptable forms of "future work" are: a genuinely-deferred item filed in the paper trail via `manage.py defer_work`, or a closed AutoIssue with two-part `Trap:`/`Fix shape:` lessons recording what was learned. In committed code, the tokens `TODO`, `FIXME`, `XXX`, `HACK` are acceptable only when the same comment line links a real tracked row, for example `(paper-trail #<N>)` or `(AutoIssue #<N>)`.

### Comments & Documentation — All Languages

Applies to every agent (Claude, Codex, Gemini) and every language in this repo (Python, Rust, TypeScript/Angular, SCSS, shell). Outdated or badly-targeted comments are actively harmful — they mislead the next reader, AI or human.

**The four rules.**

1. **Prefer self-documenting code.** Clear names and small functions replace most comments. **Every agent — Claude, Codex, Gemini, Antigravity, CI agents, and every future agent — MUST rename unclear code or split unclear logic before adding an explanatory comment.** Comments are allowed only for non-obvious reasons, risks, external constraints, fragile invariants, or citations. Comments that merely restate what the code already says are forbidden. If you are writing a comment longer than one line to explain a block of code, extract that block into a well-named function instead. Use descriptive names for variables, functions, classes, files, tests, and UI labels so the code reads clearly without extra explanation.

2. **Keep comments accurate — treat them as code.** When you change code, update or delete the comments next to it in the same edit. A comment that no longer matches the code below it is a bug. If a comment no longer describes what the code does or why, rewrite it or delete it — never leave it stale.

3. **Write for the right audience.**
   - **Inline comments** are for developers (or future you) actively modifying the code. They may reference technical context, warnings about fragile parts, or non-obvious invariants.
   - **API documentation / docstrings** are for developers *consuming* the code as a tool. They describe what the function does, what it returns, and what its contract is — not how the internals work.
   Do not mix the two. Do not put internal reasoning in an API docstring; do not put consumer-facing contract language in an inline comment.

4. **Focus on WHY, not WHAT.** The code already says *what* it does and *how*. Good comments explain *why*:
   - why this approach was chosen over a more obvious one
   - why this edge case needs special handling
   - why a specific constant value was picked (cite the source — benchmark, patent, measurement, spec section)
   - why a bug fix is shaped the way it is

   Do not translate code into English. A comment like `// increment the counter` above `counter += 1` is forbidden.

**Pre-finish comment check (mandatory before any commit).**

Before finishing any code task, scan every comment you added or touched and confirm:

1. **No WHAT-comments** that just translate code into English — delete them.
2. **No stale comments** next to code you changed — rewrite or delete them.
3. **Would a better name remove this comment?** If yes, rename the variable/function and delete the comment.
4. **Every remaining comment explains WHY**, not WHAT — if one doesn't, rewrite it.
5. **Could a smaller function remove this comment?** If yes, split the logic and delete the comment.

This check applies to every language. It mirrors the existing Pre-Commit Layout Check for frontend work.

---

## Design System - GA4 Visual Identity

This app is styled to match **Google Analytics 4 pixel-for-pixel** as of 2026-04-03.
Design uniformity is paramount. Do not drift from the design system.

### The Single Source of Truth

`frontend/src/styles/default-theme.scss`

All colours, spacing, shadows, fonts, and radius values are defined there as CSS custom properties (variables). Every component inherits from it. Read it before touching any `.scss` file.

---

## Hard Rules - Never Break These

### Colours
- **No hardcoded hex colours** in component `.scss` files. Use `var(--token-name)`.
- **No orange**. The primary color is GSC blue `#4285f4` (measured from live Google Search Console 2026-05-30; user correction supersedes the earlier `#0b57d0` and the legacy GA4 `#1a73e8`). It lives in `var(--color-primary)`.
- **No gradients** (`linear-gradient`, `radial-gradient`). GA4 uses flat colour only.

### Cards and Elevation
- Cards use `border: var(--card-border)` = `0.8px solid #dadce0` as the default style.
- **M3 Expressive tonal elevation is allowed.** Interactive cards (those the user clicks or drags) MAY use `var(--shadow-sm)` at rest and `var(--shadow-md)` on hover to communicate interactivity.
- Static informational cards (metrics, stat boxes) use `box-shadow: none` at rest — border only.
- Never use `box-shadow` values outside the token set (`--shadow-sm`, `--shadow-md`, `--shadow-hover`).

### Typography
- Font stack (Sans): `var(--font-family)` = `system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif, 'Apple Color Emoji', 'Segoe UI Emoji', 'Segoe UI Symbol'`
- Font stack (Mono): `var(--font-mono)` = `ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace`
- Do not import Google Fonts, Inter, or any external font.
- Base font size: `13px`.

### Navigation
- Nav item shape: `border-radius: 0 44px 44px 0` (pill-right). Do not change.
- Active state: `background: #e8f0fe`, `color: #1967d2`. No `::before` left bar.

---

## Token Priority Order

When writing styles, prefer in this order:

1. Semantic tokens: `var(--color-primary)`, `var(--color-border)`, `var(--card-border)`, `var(--color-text-secondary)`
2. Component palette tokens: `var(--color-blue-50)`, `var(--color-bg-faint)`, `var(--color-success-light)`
3. Raw hex: **only** for values that genuinely have no token equivalent - and add a comment explaining why

---

## Files That Need Care

| File | Risk | Rule |
|---|---|---|
| `frontend/src/styles/default-theme.scss` | CRITICAL | Changing a token here changes every component. Audit usages before editing. |
| `frontend/src/styles.scss` | HIGH | Global Angular Material overrides. Changes affect all pages. |
| `frontend/src/app/app.component.scss` | HIGH | Shell layout, toolbar, sidebar. Structural changes break navigation. |
| Any `*.component.scss` | MEDIUM | Must use tokens only. No hardcoded hex, no shadows on cards, no gradients. |

---

## What Is Allowed

- Adding new CSS variables to `default-theme.scss` (at the bottom, with a clear comment)
- Using existing tokens in new component styles
- Adding new component SCSS using the token system
- Adjusting layout (grid columns, gap, padding) as long as colours/shadows/typography tokens are unchanged

## What Requires Human Review

- Any edit to `default-theme.scss` that changes an existing token value
- Any new `box-shadow` on a card element
- Any new font import
- Any `linear-gradient` or `radial-gradient`
- Changing the nav item `border-radius`

---

## Material Design 3 (M3) Expressive — Mandatory

This app uses **Angular Material v20 with Material Design 3 (M3) Expressive**.

- **Use M3 APIs only**: Use `mat.define-theme` (M3) + `mat.theme($theme)` applied to `html {}`. Do NOT use `mat.m2-define-palette`, `mat.m2-define-light-theme`, `mat.all-component-themes`, or any `m2-` prefixed API.
- **Fully embrace M3 Expressive component states**: pronounced hover states, spring-motion transitions, expressive focus rings, and tonal surface elevation are all intentional and desired. Do NOT suppress or flatten them.
- Smooth transitions and motion are encouraged. Use `transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1)` as the standard easing across interactive elements.
- The primary brand colour (GSC blue `#4285f4`, corrected 2026-05-30; was `#0b57d0` / GA4 `#1a73e8`) is pinned via `--mat-sys-primary: var(--color-primary)` in `default-theme.scss`. Do not remove that override.
- New components must derive from M3 system tokens (`--mat-sys-primary`, `--mat-sys-surface`, `--mat-sys-on-surface`, etc.), not legacy M2/MDC private tokens.

---

## Spacing, Breathing Room & Edge Clearance — Mandatory for All Agents

The UI must feel **spacious but not cluttered**. Every agent must follow these rules on every new or modified view.

### Never-Touch Rules
- **Nothing touches an edge.** No button, chip, text, icon, or card may be flush against a page edge, card border, or container wall. Minimum clearance: `16px` from any container edge.
- **No element collisions.** Text, icons, and buttons must never overlap or be too close to read comfortably. Use `gap` on flex/grid layouts instead of `margin-right` on children.
- **No collapsed spacing.** If a component has zero `padding` or `margin`, add a comment explaining exactly why — otherwise it is a bug.
- **Filter bars and chip lists.** The first chip in any `mat-chip-listbox` must never be flush against the left container border. Minimum `padding-left: 4px` must exist on the listbox.

### Spacing Tokens (use these — never hardcode pixel values inside components)
| Context | Token | Value |
|---|---|---|
| Page outer padding | `--spacing-page` | `48px 64px` |
| Card inner padding | `--spacing-card` | `24px` |
| Section gap (grid of cards) | `--spacing-md` | `24px` |
| Inline gap (buttons, chips, icons) | `--spacing-sm` | `12px` |
| Form field bottom margin | `--spacing-field` | `16px` |

Add tokens to `_theme-vars.scss` if they do not already exist.

### Layout Rules
- Use `gap` on flex/grid, not `margin-right` on individual children.
- All page-level content lives inside `.page-content` which provides `48px 64px` outer padding. **Do NOT add extra outer padding inside a routed component** — you will double-pad.
- Paginator, chip rows, and action rows must never be clipped by an overflow container.

---

## Layout Precision Rules — Mandatory for All Agents

These rules were derived from real screenshots of layout bugs. Every agent MUST check for all four before submitting any frontend change.

### Rule A — Filter Bars & Chip Lists: Always Padded
- The first chip in any filter bar or `mat-chip-listbox` MUST have at least `16px` left-padding clearance from the container wall. Never flush-left.
- Apply `padding-left: var(--space-md)` (16px) on the `mat-chip-listbox` host or its wrapping container.

### Rule B — Form Fields: Centred Within Their Card
- Form fields inside a card section MUST NEVER be flush against the card edge. The container must have `padding: var(--spacing-card)` (24px) on all sides.
- Sparse forms (fewer than 3 fields in a wide card section) MUST be horizontally AND vertically centred within the available space. Use `align-items: center; justify-content: center` on the wrapping flex container.

### Rule C — Action Buttons: Edge Clearance + Input Alignment
- No button may be flush against any container wall. Minimum `16px` clearance (`var(--space-md)`) on all sides.
- Buttons in the same row as input fields MUST share the same vertical baseline — use `align-items: center` on the flex row.
- "Create"-style inline buttons next to form groups are a common failure point. Always verify they align with and have clearance from adjacent inputs.

### Rule D — Compound Label Separators
- When two pieces of metadata appear on the same line (e.g., node name + post count, import mode + description), they MUST be separated by a visible separator.
- Allowed separators: ` • ` (bullet — preferred for secondary metadata), ` — ` (em-dash — for ranges/classifications), `: ` (colon-space — for label–value pairs).
- Never concatenate two strings with only whitespace — they will visually merge into one word when font weights differ.
- ✅ `Forum Node • 0 posts` &nbsp;&nbsp; ✅ `Full import: Body text, sentences, embeddings`
- ❌ `Forum Node0 posts` &nbsp;&nbsp; ❌ `Full importBody text, sentences`

### Pre-Commit Layout Check
Before finishing any frontend task, visually confirm:
1. No chip, text, button, or input is flush against a container edge.
2. Filter bars have visible left-padding before the first chip.
3. Inline button rows are baseline-aligned with adjacent form fields.
4. All compound labels use ` • `, ` — `, or `: ` as separators.

---

## Design Uniformity — Mandatory for All Agents


Every screen must look like it belongs to the **same application**. No custom one-off styles are allowed.

### Component Standardisation
- **Inputs**: Always use `mat-form-field` with `appearance="outline"`. Never use a raw `<input>` styled locally.
- **Buttons**: Use only `mat-button`, `mat-stroked-button`, or `mat-flat-button color="primary"`. Do NOT introduce custom button classes with hardcoded sizes.
- **Error messages**: Always use `<mat-error>` inside a `mat-form-field`, or the global `.error-banner` utility class. Never use a raw `<div>` with inline colour styling.
- **Cards**: Always use `mat-card` with the global GA4 card system (flat, border-only). Never use a `<div>` with a `box-shadow` to simulate a card.
- **Chips/Status Badges**: Always use the `ga4-chip` mixin or `.status-chip.status-{state}` classes. Never invent a new badge pattern.

### Anti-Patterns — Never Do These
- ❌ Inline `style="..."` on any element.
- ❌ Component-level hardcoded pixel values for padding/margin — always use spacing tokens.
- ❌ Duplicating the same component pattern in more than one place — abstract to a global utility class.
- ❌ Any font-size below `11px` — it becomes unreadable.
- ❌ Content areas that scroll horizontally on a 1280px viewport.

---

## Global Architecture & Override Policy (Zero-Override Mandate)

Act as a strict frontend architect. To maintain absolute design uniformity, we follow a **"Zero Local Overrides"** policy.

1. **Forbidden `::ng-deep`**: Never use `::ng-deep` or `:host ::ng-deep`. If a library (Material, etc.) requires it, the override MUST be global, not component-specific.
2. **Global Themes Only**: Shift all structural overrides to `src/styles/themes/` (e.g., `_data-tables.scss`). 
3. **Utility Classes**: Create reusable utility classes (e.g., `.ga4-standard-field`) in these global files. Define padding, row heights, and standard colors there.
4. **Clean Components**: Component `.scss` files MUST stay nearly empty (layout-only). Apply global utility classes directly in the HTML templates.
5. **Architectural Stop-And-Think**: If you need a specific CSS selector to "force" a design, you MUST abstract it into a global utility class instead.
6. **Cleanup-on-Sight**: When modifying an existing component, you are REQUIRED to "evacuate" any local overrides or `::ng-deep` blocks into the global theme architecture.

---


## Docker Rules (also apply to this agent)

- Never add a `build:` block to a service that can reuse an existing image.
- `xf-linker-backend:latest` is shared by backend, celery-worker, and celery-beat.
- Never run `docker-compose down -v` - it deletes the database.

---

## Gemini Guard — .git/config Must Not Contain `worktreeConfig = true`

Applies to every agent (Claude, Codex, Gemini) and every tool that touches Git.

When `.git/config` contains the block below, **Gemini CLI and Gemini Antigravity silently stop generating code**. No error is thrown — the session just becomes unresponsive:

```
[extensions]
    worktreeConfig = true
```

Claude Code's `Agent(isolation: "worktree")` re-adds this block automatically whenever a worktree operation runs. This is the known cause.

### Automation is already in place

- `.githooks/post-checkout` and `.githooks/pre-commit` invoke `.githooks/_ensure-git-config-clean.sh` on every checkout, branch switch, worktree add, and commit attempt.
- `scripts/ensure-git-config-clean.ps1` is the PowerShell equivalent. It runs as the first step of `scripts/prune-verification-artifacts.ps1`.

### Rules

- **Never** re-add `[extensions] worktreeConfig = true` to `.git/config` under any circumstance.
- After running `Agent(isolation: "worktree")` or `git worktree add`, immediately run `scripts/ensure-git-config-clean.ps1` (or `.githooks/_ensure-git-config-clean.sh`). Do not rely solely on the checkout hook — worktree operations do not always trigger `post-checkout`.
- If Gemini stops responding mid-session, first check `.git/config` for that block and run the cleanup script. Do not debug Gemini itself first.

---

## Native Runtime Policy

- Before changing native Rust code, runtime ownership, or operator-facing runtime diagnostics, read `docs/NATIVE_RUNTIME_POLICY.md`.
- Treat Rust as the default speed path for hot ranking and pipeline loops; Rust is authoritative and has no Python fallback.
- Do not create a second native-runtime issue surface. Reuse the existing diagnostics system for Rust and Python runtime visibility.

---

## CI and Testing - Mandatory for All Agents

To prevent breaking the build on GitHub, every AI agent MUST verify their changes locally before pushing.

1. **Local Git Hooks**: This repository uses a mandatory pre-push hook.
   - Run `git config core.hooksPath .githooks` once to enable it.
2. **Manual Verification**: If the hook is bypassed or unavailable, you MUST run these commands and ensure they pass:
   - **Backend**: `cd backend && python manage.py test`
   - **Frontend**: `cd frontend && npm run test:ci && npm run build:prod`
3. **Never `--no-verify`**: Under no circumstances should an agent use `--no-verify` to bypass the pre-push checks.
4. **Angular Peer Deps**: If you encounter peer dependency errors in the frontend, ensure `frontend/.npmrc` contains `legacy-peer-deps=true`.

## Automatic Migration And Safe Artifact Prune

This is the canonical migration/prune policy for all AI agents in this repo, including Codex, Claude, Gemini, CI agents, and future tools. Do not duplicate the full policy in other instruction files; they should point back here.

### Mandatory backend-session migration flow

For every backend-related session (backend bugs, Django models, migrations, settings, runtime, APIs, management commands):

1. Run `docker compose exec backend python manage.py showmigrations`
2. If any migration is unapplied, run `docker compose exec backend python manage.py migrate --noinput`
3. Run `docker compose exec backend python manage.py makemigrations --check --dry-run`
4. If Django models or migration files changed during the session, run `docker compose exec backend python manage.py migrate --noinput` again
5. Before finishing, re-run `docker compose exec backend python manage.py showmigrations`
6. Before finishing, re-run `docker compose exec backend python manage.py makemigrations --check --dry-run`

Agents must not mark backend work complete while migrations are pending.

If Docker or the backend container is unavailable, agents must stop and record a clear blocker instead of guessing migration state.

### Mandatory safe artifact prune

After verification or at the end of the session, agents must run the approved cleanup command:

- `powershell -ExecutionPolicy Bypass -File scripts\\prune-verification-artifacts.ps1`

Safe prune means disposable caches and build artifacts only. The script covers frontend build/cache output, backend test/lint caches, native extension build folders, .NET `bin`/`obj`, and all four safe Docker categories in one call via `docker system prune -f`: **stopped containers, unused networks, dangling images, and build cache**. It also runs the Gemini `.git/config` guard first, so Gemini sessions can recover automatically.

### Mandatory VHDX compaction at session end

After `docker compose down` at session end, agents must also run:

- `powershell -ExecutionPolicy Bypass -File docker_compact_vhd.ps1`

This compacts the Windows virtual disk file (VHDX) so Windows actually reclaims the space that `docker system prune -f` freed. Docker's virtual disk never shrinks on its own. The compact script auto-skips if any container is still running, so it is always safe to call. Without this step, Windows continues to show the old (larger) disk usage even though Docker has cleaned up internally.

`scripts/prune-verification-artifacts.ps1` already invokes this script at the end, so running the prune script after `docker compose down` is sufficient.

### Forbidden cleanup

- Never run `docker-compose down -v`
- Never prune named Docker volumes: `pgdata`, `redis-data`, `media_files`, `staticfiles` — **embeddings live in `pgdata`**
- Never prune database volumes
- Never prune Redis/runtime data
- Never prune embeddings
- Never prune `media/`
- Never prune checked-in files

`docker system prune -f` never touches named volumes, so all of the above are automatically protected by the standard prune command.

Reuse the existing repo cleanup script and Docker prune policy above. Do not invent competing cleanup commands or duplicate this policy elsewhere.

---

## Vibe-Coding Pre-Push Rules — 28 Automated Checks

These rules run automatically via `scripts/lint-all.ps1` (steps 8-32) and `scripts/verify.ps1` (rule 26). They catch bugs AI agents commonly introduce. **Zero disk footprint, zero installs, self-pruning.** All agents (Claude, Gemini, Codex) must follow them.

### AI Agent Behavior
| # | Rule | Scope | What it catches |
|---|------|-------|-----------------|
| 1 | Debug artifact purge | TS, Rust | `console.log`, `dbg!`, `println!`, `debugger;` |
| 2 | Placeholder/stub blocker | All (diff) | `TODO`, `FIXME`, `HACK`, `NotImplementedError` |
| 3 | Diff-scope enforcement | Repo | >8 files outside primary directory = blocked |

### Code Quality
| # | Rule | Scope | What it catches |
|---|------|-------|-----------------|
| 4 | Function length (80 lines) | All (diff) | Monolithic functions |
| 5 | File length (500/400 lines) | All (diff) | God files |
| 6 | Cyclomatic complexity (C901 ≤ 15) | Python | Nested if/elif/else chains |
| 7 | Magic number detector | Python (diff) | Unnamed 3+ digit literals |
| 8 | Duplicate code blocks | All (diff) | Identical 6-line blocks across files |
| 9 | Merge conflict markers | All | `<<<<<<<` / `>>>>>>>` left in code |

### Error Handling
| # | Rule | Scope | What it catches |
|---|------|-------|-----------------|
| 10 | Empty catch/except | All | `catch {}`, `except: pass` |
| 11 | Missing HTTP error handling | Angular (diff) | `HttpClient` calls without `catchError` |
| 12 | Logger f-string detector | Python (diff) | `logger.info(f"...")` — bypasses lazy eval |

### Security
| # | Rule | Scope | What it catches |
|---|------|-------|-----------------|
| 13 | Hardcoded secrets | TS, Rust | API keys, passwords, connection strings |
| 14 | Angular XSS safety | HTML/TS | `bypassSecurityTrust*` in components |
| 16 | ReDoS detector | All | Nested regex quantifiers `(a+)+` |

### Performance
| # | Rule | Scope | What it catches |
|---|------|-------|-----------------|
| 17 | Resource leak detector | Python | `open()` without `with`, `requests.get` without timeout |
| 18 | N+1 query detector | Python (diff) | ORM queries inside `for` loops |
| 20 | Dangerous imports | Python (diff) | `from X import *`, `datetime.now()`, unbounded `@cache`, `eval()` |

### Repo Hygiene
| # | Rule | Scope | What it catches |
|---|------|-------|-----------------|
| 21 | Binary/large file blocker | Repo | `.pyc`, `.dll`, `.env`, files >2MB |
| 22 | Dockerfile layer check | Docker | `COPY . .` before dependency install |
| 23 | Lock file consistency | Repo | `package.json` changed without `package-lock.json` |

### Design System
| # | Rule | Scope | What it catches |
|---|------|-------|-----------------|
| 24 | Hardcoded style detector | SCSS | Hex colors, gradients, `font-family` in components |
| 25 | Unused SCSS classes | SCSS/HTML (diff) | Classes in `.scss` not referenced in `.html` |

### Test Coverage
| # | Rule | Scope | What it catches |
|---|------|-------|-----------------|
| 26 | Test existence check | Python | New source files without corresponding test files |

**"(diff)" = only checks files changed in this push.** Existing violations in untouched files are not flagged, but as files are modified they must be cleaned up.

---

## UX and Smart Navigation - Mandatory for All Agents

Everything in this app must be "One-Click Away" from being found.

1. **Deterministic IDs**: Every `mat-card`, `section`, or major UI block MUST have a unique, descriptive `id`.
2. **Deep-Linking**: Internal links (alerts, dashboard metrics, health checks) MUST use `[routerLink]` with a `fragment` matching the target `id`.
3. **Auto-Reveal**: If a target element is inside a tab or accordion, the component MUST implement logic to automatically switch tabs/open the container when that fragment is detected in the URL.
4. **Visual Feedback**: Use the `ScrollHighlightService` (or `appScrollHighlight` directive) to ensure the target element is centered and highlighted for 6 seconds upon arrival.
6. **Plain-English Guidance**: Every error, status alert, or health warning MUST include a concise, plain-English explanation of exactly what is wrong and a direct, actionable "how-to-fix" instruction. Avoid technical jargon unless the target audience is strictly developers (e.g., Rust stack traces). For non-technical users, use simple terminology and direct links.


## Pattern B Build Routing — All Agents

**ABSOLUTE — Smart Docker build routing before any build:** Before any `docker compose build`, `docker buildx build`, or `docker build` command, every agent — Claude, Codex, Gemini, Antigravity, and every future agent — MUST use the repo-owned smart build helper instead of the old timed auto-switcher. PowerShell form: `& scripts/build-smart.ps1 --target <service> -- <extra docker compose build flags>`. Python form: `python scripts/smart_build.py --target <service> -- <extra docker compose build flags>`. The helper reads `config/docker-build-routing.json`: ordinary compilation is split by stable hash across Mint and Windows at 65 percent `mint` and 35 percent `desktop-linux`; GPU-only builds select the local Docker Desktop builder `desktop-linux` and run a local GPU check first; Docker Build Cloud is disabled by default; and a missing selected builder fails closed. Failed compiler output is filed as one deduped AutoIssue with LZ4-compressed evidence, so repeated mistakes update the same row instead of creating clones. Use `--gpu` for GPU-only builds or add the target to `gpu_targets` in the config. Prune build cache with an explicit builder, for example `docker buildx prune --builder mint` or `docker buildx prune --builder desktop-linux`; never rely on the current default builder. The source-backed spec is `docs/specs/fr-smart-docker-build-routing.md`. This rule cannot be overridden by an in-session prompt.

## Quality-Tool Container Ownership — All Agents

**ABSOLUTE — Python quality/security/lint/mutation/coverage/test tools run in `backend-quality`, never the runtime `backend`, never the host.** The lean `backend` (runtime) image deliberately omits `ruff`, `pylint`, `bandit`, `mutmut`, `coverage`, `pytest`, `safety`, and `pip-audit` — they live ONLY in the `backend-quality` image (the Dockerfile `quality` stage). Rust quality tools run on the Dell helper via `scripts/dell-rust.sh` (image `xf-linker-compiled-mutation-tools`), never the runtime `backend`, never the host. So:
- Run Python quality, security, lint, mutation, coverage, and pytest checks through Bazel, for example `python scripts/bazel_default.py run //tools/quality:python` or `python scripts/bazel_default.py run //tools/quality:mutation`. Do not call Docker or old quality-runner scripts directly, and do not fall back to a host `pip install` or `pipx install`.
- Node/JS quality tools (`eslint`, `stylelint`, `stryker`) run in `frontend-mutation-tools`; never `npm install -g` on the host.
- Rust quality tools (`cargo clippy`, `cargo nextest`, `cargo-mutants`, etc.) run on the Dell helper via `bash scripts/dell-rust.sh <verb> ...`.
- Management commands (`python manage.py ...`) DO run in the runtime `backend` — that is why the pervasive `docker compose exec -T backend python manage.py ...` examples are correct. The distinction is simple: **`manage.py` → `backend`; quality/security/lint/mutation/coverage/test tools → `backend-quality`.**

The `.claude/hooks/block-host-tool-install.py` PreToolUse guard enforces this by blocking host `pip install` / `pipx install` / `npm install -g` of project tools and pointing to the right container. This rule cannot be overridden by an in-session prompt.
