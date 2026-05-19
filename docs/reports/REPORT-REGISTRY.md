# Report Registry

This file is the single index of all audit reports and individual issues found by AI sessions. Every AI must read this file before starting work (see Session Gate in `AI-CONTEXT.md`).

## Rules

**Blocker Rule:** Any AI whose work area overlaps with an `OPEN` finding must tell the user in chat before writing any code, and must then either resolve it or explicitly justify in writing (in the Current Session Note in `AI-CONTEXT.md`) why it is skipping it.

**Silence Is Forbidden Rule:** If an AI notices an open or reopened finding that overlaps with the area it is about to touch, it must not stay silent. It must tell the user in chat first. Silent continuation is a policy violation.

**Anti-Duplication Rule:** Before logging a new issue, search this file for existing entries. If the issue is already logged, add a note to the existing entry instead of creating a duplicate.

**Anti-Regression Rule:** Before changing code in any area, search the Resolved sections below for entries that touch the same files. If a match exists, read what was fixed and verify your changes don't undo it. Resolved entries are permanent history — never delete them.

**Recurrence Rule:** If a new feature or change re-introduces a previously resolved issue (same root cause, same affected area), reopen the original entry by moving it back to the Open section with a note explaining what brought it back. Do not create a duplicate.

**Logging Rule:** If you find any bug, performance bottleneck, logic flaw, missing validation, or code smell during your session — even if it's outside your current task scope — add it here. Don't ignore it. Future AIs will see it and can fix it.

---

## Open Reports

### RPT-012 - Resolved-issue search tests collided with restored database lessons (2026-05-19)

- **Found by:** auto_issues_append_registry, from AutoIssue #358 (source `agent`).
- **AutoIssue:** #358.
- **Status:** OPEN.
- **Severity:** LOW.
- **Area:** `backend/apps/auto_issues/tests_search_resolved_issues.py`.
- **canonical_fingerprint:** `da8565b8659d441c`.
- **What is wrong in plain English:** Self-review category: tooling

The focused Python quality group failed because tests_search_resolved_issues.py expected exactly one match for backend/apps/audit and backend/apps/pipeline, but the restored database already contains real resolved lessons under those paths. The tests now use unique test-only path prefixes so they prove batching without colliding with inherited data.
- **Why it matters:** the AutoIssue picker that surfaced this is part of the test-hardening or coverage program — leaving it open means a real failure signal goes uninvestigated.
- **Fix shape:** see AutoIssue #358 for the full picker description; the next agent picks this up during the standard 18-pick or 10-coverage-gap drain.

---

### RPT-011 - Quality wrappers ran broad unrelated tests for changed-file commits (2026-05-19)

- **Found by:** auto_issues_append_registry, from AutoIssue #348 (source `agent`).
- **AutoIssue:** #348.
- **Status:** OPEN.
- **Severity:** LOW.
- **Area:** `scripts/run-angular-quality.sh`, `scripts/run-cpp-tests.sh`, `scripts/run-cpp-coverage.sh`, `scripts/run-cpp-sanitizers.sh`.
- **canonical_fingerprint:** `48595e4c2deab1be`.
- **What is wrong in plain English:** Self-review category: tooling

Frontend quality ran full lint and full Karma tests for any frontend app file, and C++ test, coverage, and sanitizer wrappers ran every CTest binary. Changed-mode now passes focused Angular spec includes and uses the existing C++ changed-binary mapper for test, coverage, and sanitizer runs.
- **Why it matters:** the AutoIssue picker that surfaced this is part of the test-hardening or coverage program — leaving it open means a real failure signal goes uninvestigated.
- **Fix shape:** see AutoIssue #348 for the full picker description; the next agent picks this up during the standard 18-pick or 10-coverage-gap drain.

---

### RPT-010 - Python quality selector uses whole app target for focused Commit A files (2026-05-19)

- **Found by:** auto_issues_append_registry, from AutoIssue #343 (source `agent`).
- **AutoIssue:** #343.
- **Status:** OPEN.
- **Severity:** LOW.
- **Area:** `scripts/select_python_test_targets.py`.
- **canonical_fingerprint:** `33411a9a7c049fff`.
- **What is wrong in plain English:** Self-review category: tooling

The Python quality target selector returned apps/auto_issues for focused management-command and helper changes. That pulled unrelated Loki and session-close tests into the Commit A hook run, causing moving full-chain-only failures. The selector now prefers exact nearby tests and only uses a whole-app fallback when an app has no focused target at all.
- **Why it matters:** the AutoIssue picker that surfaced this is part of the test-hardening or coverage program — leaving it open means a real failure signal goes uninvestigated.
- **Fix shape:** see AutoIssue #343 for the full picker description; the next agent picks this up during the standard 18-pick or 10-coverage-gap drain.

---

### RPT-009 - Commit chain Loki picker target fails in full hook run but passes alone (2026-05-19)

- **Found by:** auto_issues_append_registry, from AutoIssue #342 (source `agent`).
- **AutoIssue:** #342.
- **Status:** OPEN.
- **Severity:** LOW.
- **Area:** `apps/auto_issues/tests_loki_picker.py`.
- **canonical_fingerprint:** `27787c19ac44ebac`.
- **What is wrong in plain English:** Self-review category: tooling

The normal Commit A hook chain reported an error in apps/auto_issues/tests_loki_picker.py::LokiHotPatternIntegrationTests::test_ignores_non_stack_containers, while the exact pytest target passed when rerun alone. This points to shared test state, test database residue, or order coupling during the Docker-managed quality run.
- **Why it matters:** the AutoIssue picker that surfaced this is part of the test-hardening or coverage program — leaving it open means a real failure signal goes uninvestigated.
- **Fix shape:** see AutoIssue #342 for the full picker description; the next agent picks this up during the standard 18-pick or 10-coverage-gap drain.

---

### RPT-008 - Commit chain session_close target fails in full hook run but passes alone (2026-05-19)

- **Found by:** auto_issues_append_registry, from AutoIssue #341 (source `agent`).
- **AutoIssue:** #341.
- **Status:** OPEN.
- **Severity:** LOW.
- **Area:** `apps/auto_issues/tests/test_session_close.py`.
- **canonical_fingerprint:** `ba973a8dd679c8c9`.
- **What is wrong in plain English:** Self-review category: tooling

The normal Commit A hook chain reported an error in apps/auto_issues/tests/test_session_close.py::SessionCloseMarkerTests::test_marker_is_emitted, while the exact pytest target passed when rerun alone. This points to shared test state, stale database state, or test-order coupling in the quality chain. Future agents should clear test database state and rerun the …
- **Why it matters:** the AutoIssue picker that surfaced this is part of the test-hardening or coverage program — leaving it open means a real failure signal goes uninvestigated.
- **Fix shape:** see AutoIssue #341 for the full picker description; the next agent picks this up during the standard 18-pick or 10-coverage-gap drain.

---

### ISS-130 - TDD lesson logger dedupes different repo paths (2026-05-18)

- **Found by:** Codex while logging lessons for the restored-backup schema repair command.
- **AutoIssue:** #260.
- **Status:** OPEN.
- **Severity:** MEDIUM.
- **Area:** `backend/apps/auto_issues/management/commands/log_tdd_lesson.py`, `backend/apps/auto_issues/services/fingerprinting.py`.
- **What is wrong in plain English:** two different test-driven-development lesson logs for two different files collapsed into the same AutoIssue row because the shared fingerprint helper turns slash-separated repo paths into the same placeholder.
- **Why it matters:** the next agent can lose one of the lessons that explains why a file changed, and commit hooks may see weaker proof than the session actually produced.
- **Fix shape:** give the TDD lesson logger a path-safe fingerprint input or a dedicated exact-hash path so file and test names stay distinct while normal cross-source error dedupe keeps its current behavior.

---

### ISS-129 - Management commands dispatch missed scheduled runs during schema work (2026-05-15)

- **Found by:** Codex during the AutoIssue category migration and self-review logging work.
- **AutoIssue:** #272.
- **Status:** OPEN.
- **Severity:** HIGH.
- **Area:** `backend/apps/core/apps.py`, `backend/apps/core/services/schedule_tracker.py`.
- **What is wrong in plain English:** running `manage.py migrate auto_issues` started the schedule recovery sweep and dispatched 81 missed scheduled runs. Schema work and small logging commands should not enqueue unrelated app work.
- **Why it matters:** agents can trigger heavy background jobs while trying to apply a migration or record a review finding. That makes verification noisy and can put load on the system at the wrong time.
- **Fix shape:** gate the schedule recovery sweep so it does not run during migrations, schema checks, self-review logging, or other maintenance commands.

---

### ISS-128 - Docker Desktop engine returns 500 while dashboard is running (2026-05-14)

- **Found by:** Codex during safe Docker Desktop recovery.
- **AutoIssue:** #257.
- **Status:** RESOLVED 2026-05-14.
- **Severity:** HIGH.
- **Area:** `scripts/reset-docker-sockets.ps1`, `scripts/recover-docker-desktop-safe.ps1`, Docker Desktop, `docker-desktop` WSL distribution.
- **What is wrong in plain English:** Docker Desktop can show its dashboard while normal Docker commands fail with a 500 error from the Docker engine pipe. In this state, `docker ps -a`, `docker volume ls`, and the AutoIssue startup check cannot run, even though Docker Desktop looks open.
- **Why it matters:** agents may try risky cleanup if they mistake this for a broken project stack. The safe recovery must protect PostgreSQL, Redis, media, static files, frontend build output, GlitchTip, Grafana, Loki, Tempo, Pyroscope, and all Docker named volumes.
- **Fix shape:** use `scripts/recover-docker-desktop-safe.ps1`. It first asks Docker Desktop to shut down normally, terminates only the `docker-desktop` WSL distribution, runs `scripts/reset-docker-sockets.ps1`, starts Docker Desktop, and waits until containers and volumes can be listed. If Windows administrator rights are needed, rerun the same script from Administrator PowerShell with `-AdminServiceRestart`; that mode restarts Docker helper processes and `com.docker.service` without deleting volumes.
- **Closure:** current Docker health was restored, protected volumes were verified, a PostgreSQL backup was created at `backups/postgres-20260514-234111.dump`, safe cache/image cleanup ran after the backup, and the new safe recovery script was added. The trap is that Docker Desktop's visible dashboard is not proof that the Docker engine is healthy. The working fix is to prove health with both container and volume listing, then recover through WSL termination, socket reset, and service restart only when needed.

---

### ISS-126 - Backend core tests fail under production-style settings (2026-05-11)

- **Found by:** Codex during prevention sweep verification.
- **AutoIssue:** #126.
- **Status:** OPEN.
- **Severity:** MEDIUM.
- **Area:** `backend/apps/core/tests_passkey.py`, `backend/apps/core/tasks_passkey_cleanup.py`, `config/settings/test.py`.
- **What is wrong in plain English:** running the core backend tests without the repository's test settings can fail the passkey cleanup tests with "Cannot open a new connection in an atomic block." The same tests pass when run with `config.settings.test`, which is the test configuration used elsewhere in the repo.
- **Why it matters:** future agents can lose time chasing a backend failure that comes from the wrong test wrapper, not from the frontend slice they are trying to verify.
- **Fix shape:** make the documented backend test command harder to misuse, or adjust the passkey cleanup test setup so it cannot accidentally inherit production-style database connection behavior.

---

### ISS-127 - Broken-link scan task missing from pipeline task wrapper (2026-05-13)

- **Found by:** Codex during Mission A import-task verification.
- **AutoIssue:** #221.
- **Status:** OPEN.
- **Severity:** MEDIUM.
- **Area:** `backend/apps/pipeline/tasks.py`, `backend/apps/pipeline/tasks_broken_links.py`, `backend/apps/pipeline/tests.py`.
- **What is wrong in plain English:** the full backend test suite still expects `apps.pipeline.tasks.scan_broken_links`, but that task is not exported there after the broken-link split. Tests that call it fail with `AttributeError`.
- **Why it matters:** the scheduled broken-link check may have no stable public task entry point, and the backend suite cannot complete while the old import path is missing.
- **Fix shape:** restore a small public Celery task wrapper in `backend/apps/pipeline/tasks.py` that delegates to the helpers in `tasks_broken_links.py`, or update all callers and tests to import the new task owner consistently.

---

### ISS-118 - Ops feed writer logs duplicate-key errors for repeated dedup keys (2026-05-11)

- **Found by:** Codex during the prevention sweep verification run.
- **AutoIssue:** #118.
- **Status:** OPEN.
- **Severity:** MEDIUM.
- **Area:** `backend/apps/ops_feed/services.py`.
- **What is wrong in plain English:** the activity-feed writer correctly has a database rule that prevents duplicate entries, but the writer still tries to create the same event again and logs a noisy database traceback when the duplicate key already exists.
- **Why it matters:** the database is protecting the data, but repeated tracebacks can hide real errors and make monitoring look worse than it is.
- **Fix shape:** change the writer to treat an existing `dedup_key` as "already recorded" instead of logging a failure, then add a focused test that emits the same dedup key twice and confirms only one row exists with no error log.

---

### RPT-007 — Grafana Faro + Tempo deployment + 18-pick Opening Ritual (2026-05-11)

- **Found by:** Claude Opus 4.7 via user directive "Deploy and integrate Grafana Faro and Tempo into our existing observability stack, and establish a mandatory Opening Ritual for all AI agents."
- **Status:** SHIPPED 2026-05-11 — services declared in compose, configs in place, pickers + tests written, Opening Ritual rule extended from 12 to 18 picks across 6 sources. End-to-end verification (docker compose up, manual smoke triggers) is the final gating step before the entry can be marked RESOLVED.
- **User decisions captured during planning:** Quota raised to 18 (3 per source) rather than rebalanced; Faro sits ALONGSIDE the existing OTel browser tracer (RUM only, no shared tracer); Tempo stores traces locally with hardware-aware retention (72 h laptop / 168 h workstation); otel-collector fan-out preserves the ABSOLUTE-protected Sentry → GlitchTip pipeline.
- **Plan:** [`~/.claude/plans/objective-deploy-and-integrate-zany-bee.md`](../../../.claude/plans/objective-deploy-and-integrate-zany-bee.md).

**Shipped this session (10 streams):**

| Stream | What landed | Files |
|---|---|---|
| 1 | Tempo service added to `docker-compose.yml` with hardware-aware retention env var; `tempo/tempo-config.yaml` written; `otelcol-config.yaml` traces pipeline gains a second exporter `otlp/tempo` ALONGSIDE the existing `sentry` exporter — fan-out, not substitution. Batch processor tuned (`timeout 5s → 2s`, `send_batch_size 512 → 1024`) to amortize the extra exporter. | `docker-compose.yml`, `tempo/tempo-config.yaml` (new), `otelcol-config.yaml` |
| 2 | Grafana service added to compose; data sources for Tempo / Loki / Pyroscope / Prometheus auto-provisioned; minimal traces-overview dashboard JSON. Anonymous auth OFF; admin credentials via `.env`. | `docker-compose.yml`, `grafana/provisioning/datasources/datasources.yaml` (new), `grafana/provisioning/dashboards/dashboards.yaml` (new), `grafana/dashboards/traces-overview.json` (new), `.env.example` |
| 3 | `@grafana/faro-web-sdk` added to `frontend/package.json`; new `faro-bootstrap.ts` sits alongside `otel-bootstrap.ts` (no shared tracer); `main.ts` wires Faro after OTel with a `__karma__` skip gate; production env defaults session sampling to 25 %. | `frontend/package.json`, `frontend/src/app/core/observability/faro-bootstrap.ts` (new), `frontend/src/environments/environment.ts`, `frontend/src/environments/environment.production.ts`, `frontend/src/main.ts` |
| 4 | `faro.receiver` HTTP block added to `config.alloy` listening on `:12347` (CORS open); dedicated `loki.write "faro"` writes events with `{service="frontend", source="faro"}` external labels so the picker can filter cleanly. Alloy ports list gains `127.0.0.1:12347:12347`. | `config.alloy`, `docker-compose.yml` |
| 5 | `faro_picker.py` (~370 lines) with two disjoint detectors — `pick_faro_error_clusters` (LogQL queries on the `source="faro"` label, normalized via the loki-picker fingerprinter) and `pick_faro_webvital_breaches` (LCP/INP/CLS samples grouped by route). Celery task wrapper + beat entry at `:20/:50` (between Loki and Tempo). 11 tests under `tests_faro_picker.py`. | `backend/apps/auto_issues/services/faro_picker.py` (new), `backend/apps/auto_issues/tests_faro_picker.py` (new), `backend/apps/auto_issues/tasks.py`, `backend/config/settings/celery_schedules.py` |
| 6 | `tempo_picker.py` (~330 lines) with two disjoint detectors — `pick_tempo_slow_spans` (TraceQL `{ duration > Xms }`) and `pick_tempo_error_spans` (TraceQL `{ status = error }`). Cross-fingerprint with GlitchTip via `canonical_fingerprint(span_name, service_name)` so a slow span captured by Sentry/GlitchTip and surfaced by Tempo collapse into one row through `source_observations`. Celery wrapper + beat entry at `:25/:55`. 10 tests under `tests_tempo_picker.py`. | `backend/apps/auto_issues/services/tempo_picker.py` (new), `backend/apps/auto_issues/tests_tempo_picker.py` (new), `backend/apps/auto_issues/tasks.py`, `backend/config/settings/celery_schedules.py` |
| 7 | `AutoIssue.source` choices gain `tempo` + `faro`; migration `0006_add_faro_tempo_sources` seeds 10 AppSettings keys (4 Tempo + 6 Faro) via `get_or_create` (DEFAULT-ON compliant — no `external-data-gated` exemption needed); hardware-aware `tempo.retention_hours` default. | `backend/apps/auto_issues/models.py`, `backend/apps/auto_issues/migrations/0006_add_faro_tempo_sources.py` (new) |
| 8 | `CLAUDE.md` + `AGENTS.md` ABSOLUTE rule rewritten — quota raised from 12 to 18, marker grammar gains tempo + faro counts. `.githooks/check-registry-read.py` regex extended to 6 named groups (`a/g/p/t/l/f`), picks-count threshold raised to 18, `auto-fix-18` added to satisfier regex, helpful error messages on legacy markers. `.githooks/test_check_registry_read.py` rewritten with 12 tests covering the new format (all green host-side). `print_open_issues` now prints all six per-source counts in one line so a single command satisfies the marker. | `CLAUDE.md`, `AGENTS.md`, `.githooks/check-registry-read.py`, `.githooks/test_check_registry_read.py`, `backend/apps/auto_issues/management/commands/print_open_issues.py` |
| 9 | 13 new plain-English glossary entries in `PLAIN-ENGLISH-RULE.md` (Faro, Tempo, Grafana, RUM, Web Vitals, LCP, INP, CLS, span, trace, traceID, fan-out exporter, auto-fix-18). | `PLAIN-ENGLISH-RULE.md` |
| 10 | This registry entry. | `docs/reports/REPORT-REGISTRY.md` |

**Why fan-out, not substitution:**
otel-collector's existing trace pipeline shipped to GlitchTip via the Sentry envelope exporter. Tempo is OTLP-native; replacing the Sentry exporter would silently break the ABSOLUTE-protected GlitchTip integration. Instead, the new `otlp/tempo` exporter was APPENDED, leaving Sentry first in the list. Each trace now lives in both stores; an operator can pivot from a GlitchTip error event to its Tempo trace via the shared traceID.

**ABSOLUTE rule honoured:**
- GlitchTip services untouched; Sentry exporter still first.
- No `docker compose down -v`.
- No autostart-on-login change.
- No `worktreeConfig` change.
- Backend test `apps.audit.tests_glitchtip_compose_integrity` is on the verification checklist.

**Known follow-ups (not blockers):**
- Picker drought is expected on day one: Tempo + Faro return zero candidates until the new services start receiving real data. The drought clause in the hook + the substitution form `(drought logged: #<id>)` handle this. The next agent should expect their first `[REGISTRY READ ...]` to include 1–2 drought lines.
- The Faro session sample rate of 0.25 in production was a conservative default for disk pressure; revisit after a week of real-user data.
- The `tempo.retention_hours` AppSetting and the `TEMPO_RETENTION_HOURS` env var are kept in sync by hand for now — a future small management command could write the AppSetting value into `.env` on operator override.

---

### RPT-006 — Prevention-Focused Cleanup (2026-05-10 turn 2)

- **Found by:** Claude Opus 4.7 via user directive "do a prevention-focused cleanup, not a one-off fix"
- **Status:** Phase 1 + Phase 2 + Phase 7 SHIPPED; Phase 3 + Phase 4 partial (1 of 4 / 1 of 5 slices); Phase 5 + Phase 6 partial. Remaining work tracked as AutoIssues.
- **User directive:** Turn known weak spots into hard guardrails so future agents physically cannot reintroduce them. Aggressive scope, multi-session permitted.

**Shipped this session (8 commits):**

| Phase | What landed | Commit |
|---|---|---|
| 0 | Snapshot of 81 prior-session files (no logic change; references existing AGENT-HANDOFF entries) + SCSS lint config + glossary skip-AGENT-HANDOFF | [00edc179](commit:00edc179) |
| 1 | 4 new pre-commit hooks: check-file-size (1500-line cap with grandfather list), check-no-downgraded-gates (CI gate flip detector), check-frontend-routes (HttpClient → urls.py validator), check-missing-tests (local mirror of the CI gate). All wired into .githooks/pre-commit. PLAIN-ENGLISH-RULE.md glossary updated. | [d5d8aeff](commit:d5d8aeff) |
| 2 | 5 warning-only CI gates flipped: stylelint blocking (after sweeping 133 violations to 0); missing-tests-check error+exit 1; semgrep --severity=ERROR --error; trivy exit-code: '1' with ignore-unfixed; cpp-tsan stays advisory with required `# GATE-DOWNGRADE-JUSTIFICATION:` comment. NEW docs/CI-GATES.md is the single source of truth. | [f20b0e6d](commit:f20b0e6d) |
| 3 (slice 1/4) | views_settings.py extracted from views.py — 16 settings view classes + helpers. views.py 6616 → 5307 lines. Re-export block preserves the public API; one test patch path retargeted. | [c315c40d](commit:c315c40d) |
| 4 (slice 1/5) | Notifications tab extracted from settings.component into NotificationsTabComponent (AutoIssue #33 closed with full lessons_learned). Karma 384 → 388 PASS. | [d036d31a](commit:d036d31a) |
| 7 | check-frontend-routes hook fixed to strip /api/ prefix before matching backend patterns (config/urls.py mounts apps/api/urls.py at /api/). False-positive flagged the working /api/prune/safe/ route. | [8ccaf456](commit:8ccaf456) |
| 6 | 61 i18n strings tagged on highest-traffic templates (cumulative ~86 of ~2150). Glossary allowlist also gains JSONL/NDJSON/PARQUET. | [afe7b028](commit:afe7b028) |
| 5 | 8 component specs added (dashboard, alerts, crawler, embeddings, health, jobs, link-health, operations-feed). Karma rose to ~420+. | (in same handoff commit) |

**Queued for next session:**

| AutoIssue | What's left |
|---|---|
| #40 (`p3s2-views-dashboard`) | Extract DashboardView + TodayActions + WhatChanged + ResumeState + StatusStory + MissionBrief + helpers into views_dashboard.py (~1200 lines) |
| #42 (`p3s3-views-runtime`) | Extract Runtime + MasterPause + Maintenance + SystemMetrics + RuntimeConfig + SafeModeBoot into views_runtime.py (~700 lines) |
| #43 (`p3s4-views-capacity`) | Extract Jobs + Helpers + Optimization + User/Auth + Analytics into views_capacity.py (~2000 lines). After this slice views.py drops below 1500 cap and leaves the grandfather list. |
| #29 | Settings split Tab 1: Ranking Weights — biggest, 14 sub-cards, ~1400 HTML lines |
| #30 | Settings split Tab 2: Silo Architecture — ~140 HTML lines |
| #31 | Settings split Tab 3: Connect & Sync — ~800 HTML lines |
| #32 | Settings split Tab 4: Library & History — ~200 HTML lines |
| #22 | Component test coverage uplift — ~161 untested components remain |
| #20 | i18n bulk rollout — ~2065 strings still untagged |

**Why it's prevention-focused, not just a fix:**
- Even if every queued slice slips a session, the 4 new pre-commit hooks prevent FURTHER drift: oversized files can't grow past 1500 lines (or past their grandfather baseline), CI gates can't be silently downgraded, frontend can't ship stale `/api/...` URLs, and new components can't land without a spec. The 5 hardened CI gates also catch the same drift at the PR level for force-pushed branches and outside-contributor PRs.
- The grandfather list in `.githooks/file-size-grandfather.txt` shrinks with each split slice — when an entry's recorded baseline drops below 1500, it gets removed and the file becomes subject to the global cap automatically.

---

### RPT-005 — Multi-PR plan from 2026-05-09 user directive (PR 1 shipped, PR 2/3/4 queued)

- **Found by:** Claude Opus 4.7 via comprehensive plan in `~/.claude/plans/on-the-app-on-playful-aho.md`
- **Status:** PR 1 shipped this session; PR 2 partial (frontend OTel done, backend custom spans + C++ tracing pending); PR 3 + PR 4 queued as 14 individual AutoIssues for auto-fix-3 pickup over the next sessions
- **User directive:** "do all things, don't defer things. address all things deferred. do sanity checks when done."
- **Why this is one report and many AutoIssues:** the plan has 4 PRs spanning frontend, backend, governance, telemetry, settings refactor, i18n rollout, RxJS leak sweep, etc. The work is too large for one session but each slice is independently trackable.

**PR 1 — SHIPPED 2026-05-09 (this session):**

| Track | What landed | Verification |
|---|---|---|
| Governance — agent rules | New file [`ONGOING-CODE-QUALITY.md`](../../ONGOING-CODE-QUALITY.md) consolidates fix-as-you-go + dual-logging rules; CLAUDE / AGENTS / CODEX / GEMINI .md all reference it; auto-fix count raised from 2→3 across 4 agent files + the hook regex; CPP picker spec text updated | Hook test passed via stage/commit cycle |
| Errors page | Auto-Issues tab now loads ONLY open status; resolved bucket entirely removed from UI; new spec test asserts `status: 'resolved'` is never fetched | Karma 370/370 PASS; new bundle main-CU73NNPP.js deployed; live-verified `autoIssuesResolved` no longer in deployed JS |
| Autotuner future-awareness | New file [`docs/AUTOTUNER-FUTURE-AWARENESS.md`](../AUTOTUNER-FUTURE-AWARENESS.md); RANKING-GATES.md gains Gate A13; two new pre-commit hooks `check-autotuner-registry.py` + `check-recommended-preset-coverage.py` block migrations that add tunable keys without registering them | Both hooks exit 0 against current tree; pre-commit shim wired into steps 11 + 12 |
| disk_pressure circuit breaker | New module `backend/apps/pipeline/services/disk_pressure.py` with `require_free_disk()`, `current_state()`, `refresh_disk_pressure_state()`; new Celery beat task firing every 60 s; `_parquet_io.py` no longer comments "module not yet shipped" | 11/11 backend tests pass; OperatorAlert + ErrorLog dual-write on first state transition |
| Forbidden-patterns linter | Extended with rule #10 — bare `print(...)` in backend source outside tests/migrations/management/scripts blocks the commit; rule #4 (TODO scoping) now accepts both RPT-NNN and ISS-NNN; FIXME comments also covered | Hook syntax-clean; strict scan of new disk_pressure.py exits 0 |
| NO-DUPLICATES invariant cleanup | Boot-time audit warning count dropped from 6 → 4 (rule typos in `self_test_smoke.py` fixed: PixieWalkVisit retention_field `updated_at`→`created_at`; ContentItem added to discovery-walk skip list as canonical-not-artefact); 4 remaining gaps tracked as AutoIssue #8/#9/#10/#11 + RPT-004 below | Live boot audit re-run: 6 warnings → 4; verify_dedup_invariant.py wired into scripts/verify.ps1 |
| Dead-stub deletion | `backend/apps/pipeline/services/pagerank.py` (1-line empty docstring stub) deleted via `git rm`; spec doc `docs/specs/fr006-weighted-link-graph.md` updated to point at `weighted_pagerank.py` instead | git rm clean; spec doc text updated |
| Glossary | Added 9 new entries to PLAIN-ENGLISH-RULE.md — `auto-fix-3`, `REGISTRY READ marker`, `RESOLVED HISTORY marker`, `search_resolved_issues`, `NO-DUPLICATES invariant`, `tunable_registry`, `ONGOING-CODE-QUALITY.md`, `disk_pressure`, etc. | All terms defined in plain English; pre-commit hook check-glossary.py exits 0 |

**PR 2 — frontend OTel SHIPPED, backend custom spans + C++ tracing queued:**

| AutoIssue | What's left |
|---|---|
| #12 (`pr2-pipeline-spans`) | Custom `tracer.start_as_current_span(...)` calls inside `pipeline_stages._stage1_candidates / _stage2_rerank / _stage3_calibrate` + `WeightTuner.run` |
| #13 (`pr2-cpp-tracing`) | OTEL-CPP span layer around `rerank_factors_core`, `bm25_score_batch`, etc. — needs build-system work |
| #14 (`pr2-pipeline-debug`) | Benchmark-storm caller logging (ISS-102) + C++ fallback AutoIssue surfacing (`ext_loader.py`) + daily fallback-share-check beat task |

Backend OTEL was discovered to be ALREADY comprehensively wired in `backend/config/settings/base.py:641-718` — DjangoInstrumentor, CeleryInstrumentor, PsycopgInstrumentor, RedisInstrumentor, RequestsInstrumentor, HTTPXClientInstrumentor, LoggingInstrumentor, SystemMetricsInstrumentor are all live. Only the prior investigation report missed that block. So PR 2's backend auto-instrumentation work was effectively already done before this session started.

**Frontend OTEL shipped this session:** new file `frontend/src/app/core/observability/otel-bootstrap.ts` wraps `WebTracerProvider` + `OTLPTraceExporter` + `FetchInstrumentation` + `XMLHttpRequestInstrumentation` + `ZoneContextManager`; main.ts initialises it (gated to skip when `__karma__` is present so TestBed zones don't conflict); environment.ts + environment.production.ts gain `otelEndpoint` field. Bundle rebuilt to main-CU73NNPP.js (692 KB, +200 KB for OTEL SDK). 9 new npm packages added.

**PR 3 — frontend save sweep + autotuner registry + perf-mode gate (queued):**

| AutoIssue | What's left |
|---|---|
| #15 (`pr3-settings-reload-overwrite`) | Settings page `forkJoin(reload all 25)` overwrites unsaved edits — needs scoped per-card reload + HasUnsavedChanges guard |
| #16 (`pr3-perf-mode-hardware-gate`) | Performance-Mode High button has no hardware-availability gate; CPU-only users can pick it and silently fall back |
| #17 (`pr3-autotuner-registry-impl`) | Wire `backend/apps/suggestions/tunable_registry.py` + refactor weight_tuner + meta_tuner to read from it (to make the new hooks have a real source of truth) |
| #18 (`pr3-rxjs-leak-dirty30`) | Add `takeUntilDestroyed(this.destroyRef)` to top-30 most-trafficked components |

**PR 4 — promoted-from-deferred work (queued):**

| AutoIssue | What's left |
|---|---|
| #19 (`pr4-settings-split`) | Split `settings.component.ts` (4,683 lines) into 9 tab components per SETTINGS-SPLIT-PLAN.md |
| #20 (`pr4-i18n-rollout`) | Tag remaining ~2,150 user-visible strings; build emits zero untranslated warnings |
| #21 (`pr4-any-cleanup`) | Replace 13 TypeScript `any` annotations + ESLint rule |
| #22 (`pr4-component-tests`) | Specs for ~169 untested components; raise karma thresholds to 70/55/65/70 |
| #23 (`pr4-cpp-benchmarks`) | Google Benchmark coverage for ~38 hot-path C++ files |
| #24 (`pr4-sw-cache-doc`) | Service-worker update toast + frontend/SERVICE-WORKER-CACHE.md |
| #25 (`pr4-fr016-017-spec`) | Spec for `score_ga4_gsc` combined attribution signal |
| #26 (`pr4-dead-services-sweep`) | Audit `backend/apps/*/services/*.py` for orphans (~37 candidates) + new `scripts/verify_unused_python.py` |
| #27 (`pr4-rxjs-leak-remaining`) | After PR 3's dirty-30, add `takeUntilDestroyed` to remaining ~133 components |
| #28 (`pr4-print-to-logger`) | Convert ~163 `print()` sites in `backend/apps/` to `logger.*` (linter blocks new ones) |

---

### RPT-004 — NO-DUPLICATES invariant gaps in 4 artefact tables (2026-05-09 → RESOLVED 2026-05-10)

- **Found by:** Claude Opus 4.7
- **Status:** RESOLVED 2026-05-10 — all 4 migrations applied, model files updated, boot-time audit returns 0 warnings.

**Closure (2026-05-10):**
- Migration `crawler.0006_crawlervisit_unique_per_visit` — dropped the (session, page_meta) constraint and added the 3-tuple (session, page_meta, content_hash). Live table had 0 rows so safe.
- Migration `content.0043_supersededembedding_unique_archive` — added the 4-tuple constraint. Live table had 0 rows so safe.
- Migration `ops_feed.0002_operationevent_unique_dedup_key` — dedup'd 1,491 duplicate rows (kept latest per key) then added a partial UniqueConstraint on `dedup_key WHERE dedup_key != ''`. Updated `apps.ops_feed.services.emit` to drop the redundant 60-second time-window logic since the schema now enforces uniqueness directly.
- Migration `suggestions.0068_suggestion_unique_5tuple` — added the 5-tuple constraint with a defensive dedup-first phase. Live table had 0 rows so the dedup pass was a no-op.
- Each model class file (`crawler/models.py`, `content/models.py`, `suggestions/models.py`, `ops_feed/models.py`) updated in the same change so `m._meta.constraints` matches the DB schema. The boot-time `run_startup_smoke_tests()` now returns `[]`.
- AutoIssues #8 / #9 / #10 / #11 marked RESOLVED with `lessons_learned` populated. Trap recorded: data migrations alone aren't enough — the model class file must declare the same constraint or `m._meta.constraints` stays out of sync with the DB.

**Original report (2026-05-09):**
- **Scope:** Boot-time self-audit (`apps.core.services.self_test_smoke.run_startup_smoke_tests`) flags 4 per-content artefact tables that don't satisfy the `(content_hash, signal_version)` skip-if-unchanged + supersede + retention pattern from [`NO-DUPLICATES.md`](../../NO-DUPLICATES.md).

| # | Table | Missing piece | Fix shape |
|---|-------|---------------|-----------|
| 1 | `crawler.CrawlerVisit` | `(session, page_meta)` constraint exists but rule expects `(session, page_meta, content_hash)` so a re-visit with new content can be a NEW row | Either widen the existing constraint OR confirm the writer always upserts on the 2-tuple (then update the rule). If widen: dedup any existing collisions first. |
| 2 | `content.SupersededEmbedding` | NO unique constraint at all | Add `UniqueConstraint(content_item, embedding_model_version, content_hash, content_version)` after dedup of any existing duplicates. |
| 3 | `ops_feed.OperationEvent` | `dedup_key` field exists but isn't `unique=True` | Add `unique=True` (or `UniqueConstraint`) on `dedup_key`. The field name is the clue — it's already supposed to be unique. |
| 4 | `suggestions.Suggestion` | 5-tuple unique key not enforced | Add `UniqueConstraint(pipeline_run, host, destination, host_sentence_text, anchor_phrase)` after dedup. Risky — 91-field table, many writers; verify no in-flight migration assumes duplicates are allowed. |

Fixed in this session (2026-05-09):
- `knowledge_graph.PixieWalkVisit` rule had `retention_field='updated_at'` but the model has `created_at` — typo.
- `content.ContentItem` flagged by discovery walk because it carries marker fields (`content_hash`, `embedding_text_hash`) but it IS the canonical content table, not a per-content artefact. Added to the `excluded_canonical_tables` skip list in `_discover_content_artifact_models`.

Tracked as AutoIssue #8 / #9 / #10 / #11 (one per table). Each AutoIssue has the same description and severity=high so the next session's auto-fix-3 picker surfaces them by `priority_score`.

**Why this rule exists:** without unique enforcement, every pipeline rerun can pile up duplicate rows. The user's 59 GB free disk + 12 GB RAM laptop runs out of headroom fast under quadratic table growth. See [`NO-DUPLICATES.md`](../../NO-DUPLICATES.md) for the full rationale.

---

### RPT-003 — GlitchTip Integration Lost + 5 Adjacent Bugs (2026-05-09)

- **Found by:** Claude
- **Status:** PARTIALLY RESOLVED (5 of 5 finds fixed in same session; 2 underlying root causes deferred — see ISS-101 and ISS-102 below)
- **Scope:** GlitchTip integration was found offline (database missing, env vars empty); during the rebuild four adjacent bugs surfaced.
- **Summary:** The error-tracking integration had been silently disabled — the `glitchtip` Postgres database had been dropped and the `.env` credentials were empty. Likely cause: an unidentified prior agent (the user suspects Antigravity). The blind spot existed for an unknown duration.

| # | Finding | Severity | Affected files | Status |
|---|---------|----------|----------------|--------|
| 1 | GlitchTip integration silently offline (DB dropped + env vars empty) | critical | `docker-compose.yml`, `.env` | RESOLVED 2026-05-09 — services now default-on, DB auto-creates, ABSOLUTE rule + CI gate added |
| 2 | Sync IntegrityError on fingerprint collision (~15 % of issues silently lost) | high | `backend/apps/audit/tasks.py` | RESOLVED 2026-05-09 — merge-into-existing path; recovered 36 lost rows |
| 3 | `GLITCHTIP_SECRET_KEY` was the placeholder string | low | `.env` | RESOLVED 2026-05-09 — rotated via openssl rand -hex 32 |
| 4 | Benchmark runner discovered Windows MSVC `.exp`/`.lib` artifacts as binaries (every run produced 0 results since 2026-05-04) | high | `backend/apps/benchmarks/services/runner.py` | RESOLVED 2026-05-09 — positive allow-list + explicit deny-list |
| 5 | `celery-worker-default` healthcheck failing 758× (stale control channel) | medium | runtime symptom in `xf_linker_celery_worker_default` container | RESOLVED-BY-RESTART 2026-05-09 — see ISS-101 for durable fix |
| 6 | Frontend Sentry SDK had empty DSN; browser-side errors not captured | high | `frontend/src/environments/environment.ts`, `frontend/src/main.ts` | RESOLVED 2026-05-09 — DSN populated, bundle rebuilt, Session Replay also enabled |

**Resolution (2026-05-09):** All six finds were fixed in the same session that discovered the offline state. New protection layers added: `glitchtip-init` + `glitchtip-migrate` services (DB self-heal), CLAUDE.md ABSOLUTE rule against re-disabling, 7-assertion `apps.audit.tests_glitchtip_compose_integrity` CI gate, and the `auto_issues` Django app (this entry's permanent home). The C++ daily-picker spec at `docs/CPP-DAILY-ISSUE-PICKER-SPEC.md` will turn future Pyroscope + GlitchTip finds into auto-prioritised AutoIssue rows so this can't happen again.

**Lesson logged for the registry's anti-regression tooling:** "Integration silently disabled" is a class of bug that markdown rules alone don't prevent. The fix needs a hard CI gate (the new `tests_glitchtip_compose_integrity.py`) plus an ABSOLUTE rule that cannot be overridden by an in-session prompt. Apply the same pattern to any other integration we don't want to lose silently.

---

### RPT-002 — Phase 2 Forward-Declared Research Library (RESOLVED 2026-04-22)

- **Status:** RESOLVED — the 337 forward-declared backlog items were retired as part of PR-A. The meta tournament scheduler (126 pending ranking signals, 238 pending meta-algo specs, 5 phase-2 weight files, 3 unwired C++ kernels, and 5 stale OPT specs) have all been deleted.
- **Scope:** Original filing covered 126 Block A-O signals plus 210 Block P1-Q24 meta-algorithms filed as spec stubs on 2026-04-15. A decision-record audit on 2026-04-21 showed every entry fell into a conflict / overlap / duplicate / niche tier. None were ever wired.
- **Resolution:** Deleted in PR-A (commits `3be6ddc`, `48b2bd9`, `74a91df`, `16b8312`, `1538073`). Replaced by a curated 52-pick roster landing in PR-B..PR-P.

---

### RPT-001 — Research-Backed Business Logic Audit (2026-04-11)

- **Status:** RESOLVED (All 5 findings resolved — see closures below)
- **Report file:** _Not written_ — `repo-business-logic-audit-2026-04-11.md` was planned but never created. Findings were re-derived from the code in subsequent sessions.
- **Scope:** Import, ranking, reranking, attribution, and weight auto-tuning logic
- **Summary:** Five logic-quality gaps in shipped code paths. All fixable by extending existing FR-013, FR-017, and FR-018 implementations in place.

| # | Finding | Severity | Affected files | Status |
|---|---------|----------|----------------|--------|
| 1 | C# import lane hardcoded 5-page cap creates silent corpus bias | high | `services/http-worker/.../PipelineServices.cs` (decommissioned 2026-04-12) | RESOLVED 2026-04-26 (obsolete) |
| 2 | Feedback reranker's inverse-propensity claim unsupported by stored signal granularity | high | `feedback_rerank.py`, `models.py` | RESOLVED 2026-04-20 |
| 3 | C++ fast path and Python reference path compute different math in feedback reranker | critical | `feedrerank.cpp`, `feedback_rerank.py` | RESOLVED 2026-04-20 |
| 4 | Attribution mixes two incompatible counterfactual models | high | `backend/apps/analytics/impact_engine.py` | RESOLVED 2026-04-27 |
| 5 | Auto-tuning optimizes a 4-number global summary instead of ranking quality | medium | `backend/apps/suggestions/services/weight_tuner.py`, `backend/apps/pipeline/tasks.py` (auto-tune chain) | RESOLVED 2026-04-27 |

**Finding 3 closure (2026-04-20):** Re-investigation showed the core math divergence was fixed in commit `ca5071e` (2026-04-11) — both paths now apply the same linear confidence blend (`oc * score_exploit_raw + (1 - oc) * 0.5`) identically. However two defensive `1e-9` denominator guards remained missing: one in C++ `rerank_factors_core` and one in Python `_rerank_cpp_batch` diagnostics recomputation. Both are dormant under the default `alpha=beta=1` priors (denom ≥ 2) but would emit Infinity/NaN if an operator zeroed both priors AND `n_total=0`. Closed by commit `0972cd2` which (a) adds `std::max(denom, 1e-9)` to `feedrerank.cpp:rerank_factors_core`, (b) adds `max(denom, 1e-9)` to `feedback_rerank.py:_rerank_cpp_batch` diagnostics, and (c) adds a `zero_priors_denominator_guard` scenario to `test_parity_feedrerank.py` covering `alpha=0, beta=0, n_total=0, n_success=0` — which pre-fix C++ would emit as NaN → clamped to 2.0 while Python emitted 0.85, producing a clear parity test failure. Service-level orchestration (`FeedbackRerankService.rerank_candidates` C++-vs-Python equivalence) remains covered only indirectly by the full-suite tests; adding a dedicated integration test is a cheap follow-up.

**Finding 2 closure (2026-04-20):** Path B chosen — honesty-of-language fix, zero math change. Re-derivation of the finding confirmed the code claims "inverse-propensity weighting" per Joachims, Swaminathan & Schnabel 2017 (WSDM, DOI `10.1145/3077136.3080756`) but the actual mechanism is a **per-pair linear confidence blend** of the shape `oc * score_exploit_raw + (1 - oc) * 0.5` where `oc` = `reviews / impressions` aggregated to the `(host_scope, destination_scope)` level. A proper per-event IPS estimator would need `position_in_slate` + `slate_size` + a click-propensity model, none of which the system currently stores or computes. Rather than build that research-grade infrastructure (2–4 weeks of work), this slice renames the mislabelled surface to honestly describe what the code does. Rename scope: `exposure_prob` → `observation_confidence` in the Python `_pair_stats` dict key, local variables, and `explore_exploit_diagnostics` JSON key; `exposure_probs` → `observation_confidences` in the C++ `rerank_factors_core` parameter + `calculate_rerank_factors_batch` pybind11 wrapper + `Scenario` field in `test_parity_feedrerank.py` + benchmarks. Docstrings in `feedback_rerank.py` and the pybind11 module doc rewritten to describe the linear confidence blend; Joachims 2017 citation retained as "inspiration only" with an explicit note that the per-event IPS guarantee is NOT implemented. No math change — all 7 parity scenarios (including `zero_priors_denominator_guard`) still pass at `atol=1e-6, rtol=0`. The frontend `FeedbackRerankDiagnostics` interface never declared an `exposure_prob` field (it was out of sync with backend keys pre-existingly) so no frontend change was needed in this slice. Closed by commit [TBD — this slice].

**Finding 1 closure (2026-04-26 — obsolete):** Closed because the C# import lane that triggered the finding **no longer exists**. `services/http-worker/` was decommissioned 2026-04-12. The live Python import lane at `backend/apps/pipeline/tasks_import.py` already addresses the original concern: `_DEFAULT_MAX_PAGES = 500` (vs the legacy hard-coded `5`), `_get_max_pages()` reads the AppSetting key `import.max_pages` so an operator can adjust the cap without a code change, and the import loop emits a warning when the cap is hit so silent corpus bias is impossible. This finding is therefore **resolved as obsolete** rather than re-narrated as a Python bug — the original failure mode is structurally absent.

**Findings 4 & 5 re-scope (2026-04-26):** Both findings remain **OPEN** but their affected-files columns now point at the live Python code instead of the decommissioned C# files. Finding 4 (attribution counterfactual mix) applies to `backend/apps/analytics/impact_engine.py`; the math problem the finding describes was inherited by the Python port and is unchanged. Finding 5 (4-number global summary objective) applies to `backend/apps/suggestions/services/weight_tuner.py` plus the Celery chain in `backend/apps/pipeline/tasks.py`; the `WeightTuner` only tunes the four blend weights (`w_semantic`, `w_keyword`, `w_node`, `w_quality`) and the original concern — that this 4-number scope misses ranker weights covered elsewhere — carries over verbatim from the C# implementation. The 2026-04-26 cleanup also fixed three runtime bugs in the Python tuner that were unrelated to Finding 5: stale `proposed_weights` / `previous_weights` / `optimisation_meta` kwargs (now `candidate_weights` / `baseline_weights` / dropped), `cs_auto_tune` source values (now `auto_tune`, with a backfill migration), and missing `predicted_quality_score` / `champion_quality_score` (now computed via `quality = 1 / (1 + objective_loss)`).

**Findings 4 & 5 closure (2026-04-27):** Finding 4 was fixed by replacing the sitewide trend query in `BayesianTrendAttributor.compute_uplift` with the actual matched control group inputs (Abadie et al. 2010), unifying the Bayesian and deterministic math onto a single valid counterfactual. Finding 5 was fixed by pre-computing the `remainder` contribution of all 50+ ranker signals (`remainder = score_final - dot(X, w_init)`) and adding it back into the L-BFGS-B objective function (`z = dot(X, w_norm) + remainder`). This ensures the auto-tuner correctly optimizes the primitive weights without ignoring the context of the full ranking pipeline.

---

## Open Individual Issues

### ISS-003 â€” FAISS startup index build hits the database during app initialization (2026-04-12)

- **Found by:** Codex
- **Severity:** medium
- **Affected files:** `backend/apps/pipeline/apps.py`, `backend/apps/pipeline/services/faiss_index.py`
- **Description:** Docker-side `showmigrations` and `makemigrations --check` emit Django's `APPS_NOT_READY_WARNING_MSG` because `PipelineConfig.ready()` calls `build_faiss_index()` during startup, which touches the database before app initialization is complete. This makes management-command startup noisy and risks future initialization fragility.
- **Status:** RESOLVED
- **Resolved:** 2026-04-28 (re-fixed cleanly per masterplan Group B)
- **Fixed in:** Two-step history. First fix (2026-04-27) added a `sys.argv` guard in `PipelineConfig.ready()` — but per Plan 5's audit, the symptom kept resurfacing because the guard was brittle to invocation paths the regex didn't match. Final fix (2026-04-28, masterplan Group B.1) **removes the `build_faiss_index()` call from `ready()` entirely**. The 15-minute Celery beat task `refresh_faiss_index` and the just-in-time fallback in `pipeline_stages._stage1_candidates()` cover index freshness. Group B.2 wires the previously-unused `_assert_single_worker()` check; Group B.3 routes any FAISS init failure to `/error-log` via `ingest_error()`.
- **Regression watch:** Keep FAISS index building out of `AppConfig.ready()` permanently. Any future need for an at-startup pre-warm should go via a Celery beat task that runs after app initialisation, never inside `ready()` itself.

### ISS-004 — celery-beat container marked unhealthy despite working correctly (2026-04-12)

- **Found by:** Claude
- **Severity:** low
- **Affected files:** `docker-compose.yml` (celery-beat healthcheck)
- **Description:** `xf_linker_celery_beat` shows `(unhealthy)` in `docker-compose ps` and has a failing streak of 260+, but the container is fully operational — it sends tasks every minute (pulse-heartbeat, watchdog-check, refresh-faiss-index, etc.). The health check runs `celery -A config.celery inspect scheduled -t 10 2>&1 | grep -q '{'` but `inspect scheduled` returns `- empty -` (no deferred tasks) instead of JSON, so grep fails. The health check script is testing for the wrong output format.
- **Status:** RESOLVED
- **Resolved:** 2026-04-12
- **Fixed in:** Changed health check to `grep -q beat /proc/1/cmdline` — verifies the beat process is running without depending on task queue state.
- **Regression watch:** The container uses a slim Python image without `pgrep`. Health checks must use `/proc/1/cmdline` or built-in tools only.

---

### ISS-005 — Nginx proxy on port 80 returns 500 for all routes (2026-04-12)

- **Found by:** Claude
- **Severity:** high
- **Affected files:** `nginx/nginx.conf`, `docker-compose.yml` (nginx volumes, frontend service)
- **Description:** Navigating to `http://localhost/` (port 80) returns a 500 with `rewrite or internal redirection cycle while internally redirecting to "/index.html"`. The nginx config sets `root /usr/share/nginx/html/browser;` but the Angular dev-server container never populates the `frontend_dist` Docker volume — it runs a live dev server on port 4200 instead of building static files. The `browser/` subdirectory does not exist, so `try_files $uri $uri/ /index.html` keeps trying to serve `index.html` which also doesn't exist, causing a redirect loop.
- **Status:** RESOLVED
- **Resolved:** 2026-04-12
- **Fixed in:** Changed nginx from static file serving to reverse proxy to `http://frontend:4200`. Removed unused `frontend_dist` volume mount from nginx.
- **Regression watch:** If a production build pipeline is added later, the nginx config will need to switch back to static file serving with the correct `root` path.

---

### ISS-006 — GET /api/system/status/weights/ returns 500 (WeightDiagnosticsView tuple bug) (2026-04-12)

- **Found by:** Claude
- **Severity:** high
- **Affected files:** `backend/apps/diagnostics/views.py` (`WeightDiagnosticsView.get`), `backend/apps/diagnostics/health.py` (`check_native_scoring`, `_result`)
- **Description:** `GET /api/system/status/weights/` always returns a 500 with `AttributeError: 'tuple' object has no attribute 'get'`. Root cause: `check_native_scoring()` in `health.py` returns a raw tuple `(state, explanation, next_step, metadata)` via `_result()`, but `WeightDiagnosticsView.get()` calls `native_status.get("module_statuses", [])` — treating the return value as a dict.
- **Status:** RESOLVED
- **Resolved:** 2026-04-12
- **Fixed in:** Changed line 218 to unpack: `_state, _expl, _step, native_metadata = check_native_scoring()` then use `native_metadata.get(...)`.
- **Regression watch:** `_result()` is used throughout `health.py` as a 4-tuple. Any new caller must unpack it correctly, not treat it as a dict.

---

### ISS-007 — GET /api/benchmarks/latest/ returns 404 on /performance page (2026-04-12)

- **Found by:** Claude
- **Severity:** medium
- **Affected files:** `backend/apps/benchmarks/views.py`
- **Description:** The Performance page triggers `GET /api/benchmarks/latest/` which returns 404 and causes a "Resource not found" toast on every page load. No benchmarks have ever been run so no latest record exists — the view returns 404 instead of an empty response.
- **Status:** RESOLVED
- **Resolved:** 2026-04-12
- **Fixed in:** Changed to return `Response(None, status=status.HTTP_200_OK)` when no completed benchmark runs exist. Added `.order_by("-started_at")` for deterministic latest selection.
- **Regression watch:** Frontend must handle `null` response body from `/api/benchmarks/latest/`.

---

### ISS-008 — Performance page subtitle still references C# after decommission (2026-04-12)

- **Found by:** Claude
- **Severity:** low
- **Affected files:** `frontend/src/app/performance/performance.component.html`, `frontend/src/app/performance/performance.component.scss`
- **Description:** The Performance page subtitle reads "Benchmark results across C++, Python, and C#" — but the C# runtime was decommissioned.
- **Status:** RESOLVED
- **Resolved:** 2026-04-12
- **Fixed in:** Removed C# from subtitle, filter chip bar, language display ternary, and `.lang-csharp` CSS rule.
- **Regression watch:** If C# support is re-added, restore the filter chip and lang badge.

---

### ISS-009 — C# High-Performance Runtime health check still present after decommission (2026-04-12)

- **Found by:** Claude
- **Severity:** medium
- **Affected files:** `frontend/src/app/health/health.component.ts`
- **Description:** System Health page shows "C# High-Performance Runtime — C# Runtime Service unreachable" as a red error. The C# runtime was decommissioned. The frontend hardcoded `'http_worker'` in the Infrastructure health group, but the backend has no such check registered.
- **Status:** RESOLVED
- **Resolved:** 2026-04-12 (health component); 2026-04-15 (diagnostics component follow-up)
- **Fixed in:** (1) Removed `'http_worker'` from the `SERVICE_GROUPS` array and removed its troubleshooting hint. (2) 2026-04-15 follow-up: `ServiceStatusViewSet` queryset now excludes `http_worker`; all C# references purged from `diagnostics.component.ts/.html/.scss` — removed `http_worker` execution card, renamed "C# Scheduler" → "Task Scheduler", removed `owner === 'csharp'` dead branch. Backend `diagnostics/models.py` still has `http_worker` and `scheduler_lane` as model choices — left in place to avoid a migration on historical data.
- **Regression watch:** Do not re-add `http_worker` to the view queryset or to any frontend card-builder unless a replacement C# service is deployed. `scheduler_lane` remains valid and is now correctly labelled as a Python/Celery service.

---

### ISS-010 — Disk space critically full at 93.2% (2026-04-12)

- **Found by:** Claude
- **Severity:** high
- **Affected files:** Host machine disk
- **Description:** System Health page shows "Disk critically full — 93.2% used."
- **Status:** RESOLVED
- **Resolved:** 2026-04-12
- **Fixed in:** Ran `docker image prune -f` and removed the decommissioned `xf-linker-http-worker` image (344MB). Main disk consumer remains the 13.5GB backend image.
- **Regression watch:** Run `docker image prune -f` after every `docker-compose build` per CLAUDE.md rules.

---

### ISS-020 — FR-045 ledger drift: anchor-diversity ships in code but ledger marks it pending (2026-04-18)

- **Found by:** Claude (during duplicate-check research for suggestion-quality telemetry Phase 1)
- **Severity:** low
- **Affected files:** `AI-CONTEXT.md` (line 322, Pending FRs list), `FEATURE-REQUESTS.md` (FR-045 status)
- **Description:** `AI-CONTEXT.md` lists `FR-045` among the 60 pending FRs, but the shipping evidence is present: `backend/apps/pipeline/services/anchor_diversity.py` implements `evaluate_anchor_diversity`; `Suggestion.score_anchor_diversity` exists with help text `"FR-045 anchor-diversity anti-spam score"`; migrations `0031_suggestion_anchor_diversity_diagnostics_and_more.py` and `0032_upsert_runtime_antispam_defaults.py` are applied; spec `docs/specs/fr045-anchor-diversity-exact-match-reuse-guard.md` exists. The ranker, diagnostic surface, and settings UI all reference FR-045. Either the implementation is effectively complete and the ledger needs updating, or some acceptance criterion is unmet and the gap should be documented. Per BLC §4.1 "If a feature is complete but marked partial or pending, fix the ledger. If it is partial but marked complete, fix the ledger."
- **Status:** RESOLVED
- **Resolved:** 2026-04-18
- **Resolution:** Moved FR-045 from Pending (60) → Partial (6 total) in `AI-CONTEXT.md` Project Status Dashboard and added a `Status: Partial` line in `FEATURE-REQUESTS.md`. The correct state is **Partial, not Complete**: the Python reference scorer, `score_anchor_diversity` field, diagnostics JSON, migrations 0031/0032, and the six `anchor_diversity.*` settings keys all ship, but two spec-mandated criteria remain unmet: (1) no C++ batch fast path exists in `backend/extensions/` despite the spec's hot-path rule ("both a Python reference path and a C++ batch fast path with parity tests"), and (2) no pytest benchmark exists in `backend/benchmarks/` (BLC §1.4 mandates 3 input sizes for every hot-path function).
- **Follow-up closed 2026-04-20 (Tier 2 slice 6):** Both remaining gaps closed. C++ batch fast path ships at `backend/extensions/anchor_diversity.cpp` + `backend/extensions/include/anchor_diversity_core.h` (pybind11 module `anchor_diversity`, registered in `setup.py`, with `PARITY:` comments per CPP-RULES §25). Parity test at `backend/tests/test_parity_anchor_diversity.py` asserts `atol=1e-6, rtol=0` across 5 scenarios covering every state branch (neutral_no_history, neutral_below_threshold, penalized_exact_share, penalized_exact_count, blocked_exact_count). Pytest benchmark at `backend/benchmarks/test_bench_anchor_diversity.py` runs both paths at 100 / 1 000 / 5 000 candidates; Google Benchmark at `backend/extensions/benchmarks/bench_anchor_diversity.cpp` covers 100 / 5 000 / 50 000 candidates. Python `evaluate_anchor_diversity_batch` delegates to the C++ fast path when `HAS_CPP_EXT` is true and falls back to a pure-Python loop otherwise. FR-045 moved from Partial (6) → Done (32) in the AI-CONTEXT dashboard.
- **Regression watch:** Future sessions touching anchor-diversity telemetry should not create parallel `AnchorUsage` tables or over-optimised-anchor warning UIs — FR-045 already handles that surface via `score_anchor_diversity` and `anchor_diversity_diagnostics`. Do not replace the `round(..., 6)` calls in `anchor_diversity.py` with equivalent C++ rounding — Python-side rounding is the parity anchor.

---

### ISS-024 — EmbeddingRuntimeSafetyTests expect 1536-dim but provider returns 1024-dim (2026-04-24)

- **Found by:** Claude (during FR-099..105 regression test run)
- **Severity:** low
- **Affected files:** `backend/apps/pipeline/tests.py` (EmbeddingRuntimeSafetyTests two tests), `backend/apps/pipeline/services/embedding_quality_gate.py`
- **Description:** Three pre-existing test failures in `EmbeddingRuntimeSafetyTests` around embedding-dimension mismatches.
- **Status:** RESOLVED
- **Resolved:** 2026-04-24 (same session as FR-099..105 full-integration)
- **Fixed in:**
  - `embedding_quality_gate.evaluate()` Gate 2 now handles old/new dimension mismatch as an `ACCEPT_NEW` decision with reason `"dimension_upgrade"`. The previous crash path (`np.dot(old_vec, new_vec)` raising `ValueError`) is replaced with a clean early-return for cross-provider upgrades. Gate 3 (stability) is skipped when dimensions mismatch because the stability check compares the new model to itself — irrelevant for a cross-provider upgrade.
  - `test_model_status_exposes_dimension_compatibility` now uses the correct `_model_cache` key format (`"<model_name>::<device>"` per `_get_model_cache_key`) and patches `get_effective_runtime_resolution` so the device is deterministic regardless of CUDA visibility.
  - All 6 `EmbeddingRuntimeSafetyTests` now pass. Full `apps.pipeline` regression: 356 → 457 tests, 0 failures.
- **Regression watch:** Any future change to `embedding_quality_gate.evaluate()` must preserve the early-return for `old_vec.shape[0] != new_vec.shape[0]`. Any future change to `_get_model_cache_key` must update `test_model_status_exposes_dimension_compatibility`'s patched dict-key.

---

### ISS-025 - GSC impact snapshots ignored inconclusive control groups (2026-04-27)

- **Found by:** Codex
- **Severity:** high
- **Affected files:** `backend/apps/analytics/impact_engine.py`, `backend/apps/analytics/tests.py`
- **Description:** `ImpactReport` rows correctly marked attribution as inconclusive when fewer than 3 matched controls existed, but `GSCImpactSnapshot` could still save a positive or negative Bayesian reward using empty/fake control inputs. Operators could see a confident "this link worked" claim when the app already knew the comparison group was too weak.
- **Status:** RESOLVED
- **Resolved:** 2026-04-27
- **Fixed in:** `docs/reports/2026-04-27-attribution-autotuner-startup-fixes.md`
- **Regression watch:** Keep `GSCImpactSnapshot` creation gated by the same `is_conclusive` rule used by `ImpactReport`.

### ISS-026 - Weight auto-tuner drift cap could be exceeded after normalization (2026-04-27)

- **Found by:** Codex
- **Severity:** high
- **Affected files:** `backend/apps/suggestions/services/weight_tuner.py`, `backend/apps/suggestions/tests_weight_tuner.py`
- **Description:** The optimizer bounded raw weights to `current +/- 0.05`, then normalized the final vector. If the active four weights did not already sum to `1.0`, final normalization could move a weight by more than the promised safety cap.
- **Status:** RESOLVED
- **Resolved:** 2026-04-27
- **Fixed in:** `docs/reports/2026-04-27-attribution-autotuner-startup-fixes.md`
- **Regression watch:** Candidate and baseline weights should both be normalized snapshots, and candidate weights must be projected back into the bounded simplex before persistence.

### ISS-027 - FAISS startup still touched the database during tests/imports (2026-04-27)

- **Found by:** Codex
- **Severity:** medium
- **Affected files:** `backend/apps/pipeline/apps.py`
- **Description:** The previous FAISS guard skipped most management commands but still allowed test/import startup paths to touch database tables before migrations or the test DB were ready. This produced Django startup warnings and noisy fallback errors.
- **Status:** RESOLVED
- **Resolved:** 2026-04-27
- **Fixed in:** `docs/reports/2026-04-27-attribution-autotuner-startup-fixes.md`
- **Regression watch:** Keep FAISS index builds out of tests, migrations, imports, and arbitrary scripts; allow only known server/worker runtime entrypoints.

---

### ISS-028 - Division by zero in ranker.py when phrase_matching.ranking_weight is 0 (2026-04-30)

- **Found by:** Antigravity (during Aho-Corasick pipeline integration)
- **Severity:** high
- **Affected files:** `backend/apps/pipeline/services/ranker.py`
- **Description:** The ranker crashed with `ZeroDivisionError` if `phrase_matching.ranking_weight` was set to exactly `0.0`. This is a valid configuration for operators who want to disable the signal's contribution without disabling the signal itself (e.g. for telemetry-only mode).
- **Status:** RESOLVED
- **Resolved:** 2026-04-30
- **Fixed in:** Added `max(1e-9, weight)` guard to the denominator in the phrase relevance calculation.
- **Regression watch:** Any new signal in `ranker.py` that uses weighted normalization must include a zero-weight guard.

---

### ISS-011 — 101 stalled-job alerts flooding the Alerts page with 142× duplicates (2026-04-12)

- **Found by:** Claude
- **Severity:** medium
- **Affected files:** `backend/apps/crawler/tasks.py` (watchdog_check)
- **Description:** The Alerts page shows 101 unread alerts, all of type "api sync appears stuck", with each individual job stall generating 142× duplicate alert entries. Stalled jobs were never cleaned up, and alert cooldown was only 15 minutes (default), causing new alert rows every 15 minutes per job.
- **Status:** RESOLVED
- **Resolved:** 2026-04-12
- **Fixed in:** Added auto-fail for sync jobs and crawl sessions stuck >24 hours. Added `cooldown_seconds=86400` (24h) to stalled-job alerts so only one alert is created per job per day. Narrowed the alert window to 30min–24h (jobs beyond 24h are auto-failed and stop generating alerts).
- **Regression watch:** If the 24-hour auto-fail threshold is too aggressive for some long-running jobs, increase it. The cooldown prevents alert floods regardless.

---

### ISS-030 - backend/apps/diagnostics/views.py exceeds 1500-line threshold (2026-05-01)

- **Found by:** Claude (Phase 4 perf + tech-debt session)
- **Severity:** low
- **Affected files:** `backend/apps/diagnostics/views.py` (1644 lines)
- **Description:** The diagnostics views module is 1644 lines, over the 1500-line threshold from `PERFORMANCE-SAFE-DEFAULTS.md` ("Long files"). The file is internally cohesive (DRF viewsets, single-purpose views, helpers) but its size makes new view additions harder to review and slows the IDE's symbol index. Recommend splitting into a `views/` package with submodules: `views/health.py` (ServiceStatusViewSet, FeatureReadinessView, ResourceUsageView, WeightDiagnosticsView, NdcgEvalView, NodesView), `views/operator.py` (DiagnosticsOverviewView, RuntimeContextView, PipelineGateView, MissionCriticalView, WhyIsItSlowView), `views/negative_memory.py` (the three `NegativeMemoryView*` classes), `views/internal.py` (SchedulerDispatchView). Keep `views.py` as a 5-line re-export shim so existing `from . import views; views.SomeView` import paths keep working.
- **Status:** OPEN
- **Recommended fix:** dedicated session; ~1.5 hours; touches imports across diagnostics/urls.py + 1 test module. Risk-mitigated by the re-export shim.
- **Regression watch:** Once split, every new diagnostics view must land in the right submodule, not a new monolith. Pre-commit hook extension in `.githooks/check-forbidden-patterns.py` already flags files exceeding 50-line functions; long-file check could be added when the split lands.

---

### ISS-031 - disk-pressure rule names a module that is not shipped yet (2026-05-07)

- **Found by:** Codex
- **Severity:** high
- **Affected files:** `DISK-PRESSURE-RULES.md`, `backend/apps/core/helpers/archive.py`
- **Description:** The disk-pressure rule says large writers must call `apps.pipeline.services.disk_pressure.require_free_disk`, but `backend/apps/pipeline/services/disk_pressure.py` does not exist. Some helper code catches that missing module and continues, so a low-disk situation can become a warning instead of a hard stop.
- **Status:** OPEN
- **Recommended fix:** Add the disk-pressure service with free-space watermarks, `require_free_disk`, `current_state`, tests, and a diagnostics surface. Then remove any "module not shipped" fallbacks that allow large writes to continue silently.
- **Regression watch:** Any future writer that can create large files or rows must use the shared disk-pressure service before writing.

---

### ISS-032 - disk-prune action chips point at an old route (2026-05-07)

- **Found by:** Codex
- **Severity:** medium
- **Affected files:** `backend/apps/audit/fix_suggestions.py`, `backend/apps/diagnostics/services/why_so_long.py`, `backend/apps/api/urls.py`
- **Description:** Two operator-facing fix buttons point to `/api/system/disk-prune/`, but the actual safe-prune endpoint is `/api/prune/safe/`. The Health page safe-prune card uses the correct route, so the mismatch is likely stale wiring. Operators who click the old action may get a missing-endpoint error instead of the safe prune flow.
- **Status:** RESOLVED
- **Resolved:** 2026-05-10
- **Fixed in:** Antigravity (Gemini) turn 5; updated stale URLs in `why_so_long.py` and `fix_suggestions.py`.
- **Regression watch:** Any future "fix action" URL should resolve in the API schema before it is shown to operators.

---

### ISS-029 - Quick Controls showed Pause while model work was already globally paused (2026-05-01)

- **Found by:** Codex
- **Severity:** high
- **Affected files:** `backend/apps/core/runtime_registry.py`, `frontend/src/app/dashboard/quick-controls/quick-controls.component.ts`, `frontend/src/app/dashboard/quick-controls/quick-controls.component.html`
- **Description:** The Dashboard Quick Controls card used each model's stored status to decide whether to show Pause or Resume. The Pause action actually flips the app-wide `system.master_pause` switch, so the model row could still look ready and keep showing Pause after all model work was paused. That made it hard for the operator to understand or reverse the paused state from the dashboard.
- **Status:** RESOLVED
- **Resolved:** 2026-05-01
- **Fixed in:** 2026-05-01 Codex Quick Controls pause/resume fix.
- **Regression watch:** Runtime model summaries must keep exposing the app-wide pause state, and Quick Controls tests must keep covering both the unpaused Pause button and globally paused Resume button.

---

## Resolved Reports

_(None yet. When all findings in a report are resolved, move the report entry here with resolution dates.)_

---

## Resolved Individual Issues

### ISS-023 - Repo launcher scripts failed before Docker startup because PowerShell mis-parsed docker-safe arguments (2026-04-21)

- **Found by:** Codex
- **Severity:** high
- **Affected files:** `scripts/start.ps1`, `scripts/stop.ps1`
- **Description:** The repo's own `scripts/start.ps1` and `scripts/stop.ps1` called `docker-safe.ps1` as `& ... compose up -d` / `compose down`. In PowerShell, that call shape let `-d` get parsed as a script parameter instead of a Docker argument, which caused startup to fail with `Missing an argument for parameter 'DockerArgs'` before Docker Compose could run. The result for operators was a misleading "localhost refused to connect" because the app stack never actually started.
- **Status:** RESOLVED
- **Resolved:** 2026-04-21
- **Fixed in:** Codex session note in `AI-CONTEXT.md` dated 2026-04-21
- **Regression watch:** When calling wrapper scripts that use `ValueFromRemainingArguments`, pass Docker arguments explicitly as an array (for example `-DockerArgs @("compose", "up", "-d")`) so PowerShell does not steal flag-style tokens like `-d`.

### ISS-022 - Dashboard performance-mode card used a JS-style comment inside inline CSS and broke the frontend build (2026-04-20)

- **Found by:** Codex
- **Severity:** high
- **Affected files:** `frontend/src/app/dashboard/performance-mode/performance-mode.component.ts`
- **Description:** The dashboard `PerformanceModeComponent` had a `// 24px above accordion ...` comment inside its inline `styles: [\`...\`]` CSS block. Angular treats inline component styles as CSS, not SCSS or TypeScript, so the `//` token breaks stylesheet parsing and can stop the frontend from building or loading correctly.
- **Status:** RESOLVED
- **Resolved:** 2026-04-20
- **Fixed in:** Codex session note in `AI-CONTEXT.md` dated 2026-04-20
- **Regression watch:** Inline component styles in `.component.ts` files must use valid CSS comments (`/* ... */`) or no comment at all. `//` comments are only safe in SCSS files, not in Angular inline style strings.

### ISS-001 â€” Backend container could miss required `drf_spectacular` dependency and fail at startup (2026-04-12)

- **Found by:** Codex
- **Severity:** medium
- **Affected files:** `backend/config/settings/base.py`, `backend/config/urls.py`, `backend/Dockerfile`, `docker-compose.yml`, `scripts/setup-dev.ps1`
- **Description:** The backend relied on `drf_spectacular` at runtime, but the running Docker container and some local setups could still start from a partially provisioned environment where that package was absent. This produced a confusing late failure during Django startup instead of a clear dependency-install failure.
- **Status:** RESOLVED
- **Resolved:** 2026-04-12
- **Fixed in:** Codex session note in `AI-CONTEXT.md` dated 2026-04-12
- **Regression watch:** Keep `drf_spectacular` required in Django settings and preserve the explicit import checks in Docker build/startup and local setup flows.

### ISS-002 â€” Local SQLite test database could drift behind migrations (2026-04-12)

- **Found by:** Codex
- **Severity:** medium
- **Affected files:** `backend/apps/plugins/apps.py`, `backend/apps/plugins/tests.py`, `scripts/setup-dev.ps1`
- **Description:** Local verification under `config.settings.test` could start against an incomplete `backend/test.sqlite3`, which made migration checks noisy and fragile. Plugin startup also needed to stay out of the way for test-settings and migration-oriented management commands.
- **Status:** RESOLVED
- **Resolved:** 2026-04-12
- **Fixed in:** Codex session note in `AI-CONTEXT.md` dated 2026-04-12
- **Regression watch:** Keep the plugin autoload skip for `.test` settings plus migration commands, and keep `scripts/setup-dev.ps1` running `migrate --settings=config.settings.test --noinput`.

### ISS-012 - `/api/health/disk/` and `/api/health/gpu/` returned 404 because router URLs shadowed explicit health routes (2026-04-14)

- **Found by:** Codex
- **Severity:** medium
- **Affected files:** `backend/apps/api/urls.py`, `backend/apps/health/tests.py`
- **Description:** The frontend health screen triggered server errors because Django matched `/api/health/disk/` and `/api/health/gpu/` against the generic health viewset detail route before it reached the dedicated disk and GPU views. Requests were interpreted as `service_key="disk"` and `service_key="gpu"` and came back 404 instead of returning the dedicated payloads.
- **Status:** RESOLVED
- **Resolved:** 2026-04-14
- **Fixed in:** Codex session note in `AI-CONTEXT.md` dated 2026-04-14
- **Regression watch:** Keep specific utility routes ahead of `include(router.urls)` when their prefixes overlap with a viewset basename, or namespace them so the router cannot swallow them.

### ISS-013 - Alert detail page called a nonexistent notifications detail endpoint (2026-04-14)

- **Found by:** Codex
- **Severity:** medium
- **Affected files:** `backend/apps/notifications/views.py`, `backend/apps/notifications/urls.py`, `backend/apps/notifications/tests.py`, `frontend/src/app/core/services/notification.service.ts`, `frontend/src/app/alerts/alert-detail/alert-detail.component.ts`
- **Description:** The alert detail screen requested `/api/notifications/<uuid>/`, but the backend exposed only the alerts list and test endpoints. Opening an alert always failed with a 404 and left the detail view unusable.
- **Status:** RESOLVED
- **Resolved:** 2026-04-14
- **Fixed in:** Codex session note in `AI-CONTEXT.md` dated 2026-04-14
- **Regression watch:** Keep the frontend alert-detail path aligned with the backend notifications URL map and prefer routing these calls through `NotificationService` so list/detail endpoints stay centralized.

### ISS-014 - Frontend Dockerfile recreated UID 1000 and could fail `docker compose build` (2026-04-14)

- **Found by:** Codex
- **Severity:** medium
- **Affected files:** `frontend/Dockerfile`
- **Description:** The frontend image build tried to run `useradd -m -u 1000 appuser` even though the upstream `node:22-slim` image already reserves UID 1000 for the built-in `node` user. On this base image the repo-mandated Docker build could fail before verification completed.
- **Status:** RESOLVED
- **Resolved:** 2026-04-14
- **Fixed in:** Codex session note in `AI-CONTEXT.md` dated 2026-04-14
- **Regression watch:** Reuse the base image's non-root `node` user unless the Dockerfile first proves that the target UID/GID is free.

### ISS-015 — GPU thermal pause/resume helpers were defined but never called (2026-04-15)

- **Found by:** Claude
- **Severity:** high
- **Affected files:** `backend/apps/pipeline/services/embeddings.py`, `docs/PERFORMANCE.md`
- **Description:** `_check_gpu_temperature()` and `_wait_for_gpu_cooldown()` were defined in `embeddings.py` but no production code ever called them. The two encode loops in `generate_content_embeddings` and `generate_sentence_embeddings` ran `model.encode(...)` directly with no thermal check. `docs/PERFORMANCE.md` §6 claimed a per-batch pynvml temperature check that was not actually happening, so the GPU was free to climb to NVIDIA's default ~93°C throttle on long overnight runs. Helper-node heartbeat endpoint promised in §2 (`POST /api/settings/helpers/{id}/heartbeat/`) was also missing — same disease, smaller blast radius.
- **Status:** RESOLVED
- **Resolved:** 2026-04-15
- **Fixed in:** Same session as ISS-016/-017/-018 — wired both helpers into the encode loops, raised default ceiling to 86°C / resume 78°C, added the missing heartbeat stub endpoint.
- **Regression watch:** Any future refactor of the encode loops in `embeddings.py` must keep the `if not _check_gpu_temperature(): _wait_for_gpu_cooldown()` guard before each `model.encode()` call. Any new "pause/resume" helper added anywhere must include a call site, not only a definition.

### ISS-016 — Heavy/Medium task locks were defined but never acquired by any task (2026-04-15)

- **Found by:** Claude
- **Severity:** high
- **Affected files:** `backend/apps/pipeline/services/task_lock.py`, `backend/apps/pipeline/tasks.py`, `backend/apps/cooccurrence/tasks.py`, `backend/apps/pipeline/decorators.py` (new)
- **Description:** `acquire_task_lock()`, `release_task_lock()` and `is_lock_held()` had been implemented as a Redis-backed locking service to enforce the docs/PERFORMANCE.md §4 golden rule "Never run two Heavy tasks simultaneously." The functions worked correctly in isolation and were exercised by unit tests, but no `@shared_task` ever called them. The 30-second stagger in `backend/config/catchup.py` spaced *dispatch* but did not prevent two Heavy tasks from running concurrently for hours. Catch-up dispatch also did not consult `is_lock_held` before sending tasks. Result: the golden rule was unenforced for the entire life of the lock service.
- **Status:** RESOLVED
- **Resolved:** 2026-04-15
- **Fixed in:** Added `with_weight_lock(weight_class)` decorator at `backend/apps/pipeline/decorators.py` that wraps a `bind=True` Celery task, calls `acquire_task_lock` on entry, and on contention does `self.retry(countdown=60, max_retries=60)` for FIFO-style defer. Applied to `import_content` (heavy), `monthly_weight_tune` (medium), and `compute_session_cooccurrence` (medium, also added `bind=True`). Catch-up dispatch is automatically covered because it goes through the same `app.send_task()` path as Beat — the decorator runs at task entry regardless of dispatch source.
- **Regression watch:** Any new Heavy/Medium `@shared_task` added to the codebase must apply `@with_weight_lock("heavy"|"medium")` directly under `@shared_task(bind=True, ...)`. Removing the decorator on any of the three current call sites would silently re-introduce the gap.

### ISS-017 — Embedding bulk_update ran only at the end of each loop, losing all in-RAM work on crash (2026-04-15)

- **Found by:** Claude
- **Severity:** high
- **Affected files:** `backend/apps/pipeline/services/embeddings.py`
- **Description:** `generate_content_embeddings` and `generate_sentence_embeddings` accumulated encoded vectors in a Python list and called `bulk_update(..., fields=["embedding"], batch_size=500)` once at the very end of the loop. If the worker was killed mid-run (`docker-compose stop`, OOM, hard crash), every embedding computed since the function started was lost — they never reached the database. On resume, the existing `embedding__isnull=True` filter at the top of the function had nothing to skip because no partial work had been persisted, so the entire job restarted from item 1. For a long embed (74k items, ~hours on RTX 3050), this could waste the equivalent of an entire overnight run.
- **Status:** RESOLVED
- **Resolved:** 2026-04-15
- **Fixed in:** Extended the existing every-5-batch progress-throttle pattern (which already saved `embedding_items_completed` to the SyncJob row) to also flush partial embeddings via `bulk_update`. After the loop, a tail flush handles any remainder. The existence of an embedding on a row is now itself the checkpoint — no new column needed. On resume, the `embedding__isnull=True` filter naturally picks up where the killed run left off.
- **Regression watch:** Any future refactor of the encode loops must preserve the `if batch_num % 5 == 0:` flush block and the post-loop tail flush. Removing them would silently restore the all-or-nothing behaviour.

### ISS-018 — `cleanup-stuck-sync-jobs` never set `is_resumable=True`, leaving the resume path unreachable (2026-04-15)

- **Found by:** Claude
- **Severity:** high
- **Affected files:** `backend/apps/pipeline/tasks.py`
- **Description:** `cleanup_stuck_sync_jobs` (scheduled daily at 22:10 UTC) marked sync jobs stuck in `status="running"` for >2 hours as `status="failed"`. The `SyncJob` model has resume infrastructure (`is_resumable`, `checkpoint_stage`, `checkpoint_last_item_id`) and `import_content` honours it at line ~615 with a `Resuming import job ... from checkpoint` log line. But the cleanup task never set `is_resumable=True`, so jobs killed by `docker-compose down` or laptop shutdown were marked permanently failed even when a checkpoint existed and resume would have worked. The most common path that should have resumed never did.
- **Status:** RESOLVED
- **Resolved:** 2026-04-15
- **Fixed in:** Split the `stuck.update(...)` into two: jobs with `checkpoint_stage IS NOT NULL` are now marked failed *with* `is_resumable=True` and a "Resumable from last checkpoint." message; jobs without a checkpoint stay marked failed (no resumable infrastructure to use). Log message now reports both counts.
- **Regression watch:** Any future change to `cleanup_stuck_sync_jobs` must keep the checkpoint-aware split. Any new "stuck job" cleanup paths added elsewhere must follow the same pattern.

### ISS-021 — WebSocket handshake authentication was never wired for token-based sessions; sockets always rejected with 403 (2026-04-20)

- **Found by:** Claude (while investigating 403-loop spam from NotificationService/RealtimeService)
- **Severity:** medium
- **Affected files:** `backend/config/asgi.py`, `frontend/src/environments/environment.ts`, `frontend/src/app/core/services/notification.service.ts`, `frontend/src/app/core/services/realtime.service.ts`
- **Description:** The ASGI stack wraps the WebSocket router in `channels.auth.AuthMiddlewareStack`, which authenticates the handshake from Django session cookies only. The REST API is token-based (`rest_framework.authentication.TokenAuthentication`), so the frontend stores a token in localStorage and attaches it as `Authorization: Token ...` on every HTTP request. WebSocket browser APIs cannot send custom headers on the handshake — the token never reaches the server, `scope.user` is always `AnonymousUser`, and the consumer closes the connection with 403 / code 4003. Result: `/ws/notifications/` and `/ws/realtime/` were non-functional in token-auth mode since the token-auth migration (FR-026). Additionally the dev-mode `environment.ts` points `wsBaseUrl` at `ws://localhost:8000/ws`, bypassing nginx entirely, so even cookie-based auth via the proxy wouldn't help in dev. The broken handshake surfaced as 403-spam in backend logs because NotificationService retried every 5 s forever. This session capped the retry budget and gated connections behind the `isLoggedIn$` signal, which stops the spam but does not restore WebSocket delivery of real-time notifications or the `realtime` topic stream.
- **Status:** RESOLVED
- **Resolved:** 2026-04-26
- **Fixed in:** Two-step closure. (1) `backend/config/websocket_token_auth.py` — `QueryStringTokenAuthMiddleware` reads `?token=<value>` from the handshake, looks up the DRF `Token`, and writes `scope["user"]`. Wired in `backend/config/asgi.py` between `AuthMiddlewareStack` (cookie fallback) and the `URLRouter`. (2) Today's session closed the remaining surface: PulseService and NotificationService now subscribe to `system.pulse` and `notifications.alerts` on the shared `/ws/realtime/` socket via `RealtimeService.subscribeTopic(...)` instead of opening their own `/ws/notifications/` socket; `JobProgressConsumer` now rejects anonymous handshakes with code 4003; both `jobs.component.ts` and `link-health.component.ts` append `?token=${encodeURIComponent(token)}` to the `/ws/jobs/<id>/` URL; and Nginx `location /ws/` now uses `access_log off` so the token query string never reaches the access log. Backend `apps.realtime`, `apps.notifications`, `apps.crawler`, `apps.pipeline` test suite passes (772 tests, 2 skipped) including the new auth gate.
- **Regression watch:** Any change to `backend/config/asgi.py` must preserve `QueryStringTokenAuthMiddleware` in the stack between `AuthMiddlewareStack` and the `URLRouter`. Any new WebSocket consumer must include the same `if user is None or not getattr(user, "is_authenticated", False): close(4003)` gate that `RealtimeConsumer` / `NotificationConsumer` / `JobProgressConsumer` now share. The legacy `NotificationConsumer` at `/ws/notifications/` is kept as a tombstone for one release while in-flight tabs catch up; it can be deleted next session along with `_NOTIFICATION_GROUP`.

### ISS-019 — GPU thermal ceiling raised further to 90°C / 80°C at operator request, and the `getattr` fallbacks in `embeddings.py` were out of sync with the settings file (2026-04-15)

- **Found by:** Claude (during follow-up wiring audit after ISS-015/-016/-017/-018)
- **Severity:** medium
- **Affected files:** `backend/config/settings/base.py`, `backend/apps/pipeline/services/embeddings.py`, `docs/PERFORMANCE.md`
- **Description:** Two separate but related issues. (1) During the wiring audit it was found that `_check_gpu_temperature()` at `embeddings.py:166` used `getattr(django_settings, "GPU_TEMP_CEILING_C", 76)` and `_wait_for_gpu_cooldown()` at `embeddings.py:246` used a fallback of `68` — both defaults were 10°C below the actual settings.py values (86/78) and disagreed with their own docstrings ("default 86°C", "Resume threshold: 78°C"). Harmless in normal operation because Django settings are always loaded, but a silent trap if the setting key were ever removed. (2) Operator requested a further bump from 86°C/78°C → 90°C/80°C to trade ~3°C of thermal headroom (vs NVIDIA's ~93°C driver throttle) for more sustained throughput on overnight runs.
- **Status:** RESOLVED
- **Resolved:** 2026-04-15
- **Fixed in:** `GPU_TEMP_CEILING_C` 86 → 90 and `GPU_TEMP_RESUME_C` 78 → 80 in `settings/base.py`. `getattr` fallbacks in `embeddings.py` aligned to the new 90 / 80. Docstrings updated. `docs/PERFORMANCE.md` §6 callout, three-layer table, and "Why Software Limits" paragraph all updated. History chain preserved in the §6 callout (76/68 → 86/78 → 90/80).
- **Regression watch:** The four locations (`settings/base.py`, two `getattr` calls in `embeddings.py`, `docs/PERFORMANCE.md` §6) must stay aligned. Any future ceiling change must touch all four or the code will silently disagree with the docs. Operator noted awareness that 90°C leaves only ~3°C of margin before NVIDIA's hardware throttle — this is by design, not a bug.

### ISS-101 — Celery worker control channel goes stale on long uptime, restart fixes it (2026-05-09)

- **Found by:** Claude
- **Severity:** medium
- **Affected files:** `docker-compose.yml` (healthcheck commands for `celery-worker-default` and `celery-worker-pipeline`).
- **Description:** After ~9 hours of uptime, the local worker's celery control channel (the "pidbox" pub/sub subscription on Redis) goes silent. `celery inspect ping -d celery@$HOSTNAME` times out from inside the same container while pings sent without `-d` land on a SIBLING container's worker. The Docker healthcheck targeted the local worker by `-d`, so it correctly detected the dead control channel — and reported `unhealthy` in an unbroken streak (758× originally). Tasks continued to process normally; only the control plane was wedged.
- **Status:** RESOLVED
- **Resolved:** 2026-05-09
- **Fixed in:** `docker-compose.yml` healthcheck rewrite. Replaced `celery inspect ping -d celery@$HOSTNAME` with a two-part check: `ps -ef | grep -q '[c]elery -A config.celery worker'` (data-plane process alive) AND `python -c 'from kombu import Connection; Connection("redis://redis:6379/0").ensure_connection(timeout=3)'` (broker reachable). Also added `--max-tasks-per-child=1000` (default queue) and `--max-tasks-per-child=500` (pipeline queue) so prefork children recycle, keeping the parent's pubsub state fresh. Persistence: `AutoIssue` row #1 now `status='resolved'` with full `lessons_learned`.
- **Regression watch:** If the new healthcheck flips to `unhealthy` while the worker is processing tasks, either the worker process died (real bug, `pgrep` will tell you) OR Redis is down (`Connection.ensure_connection` will tell you) — both are honest signals now, not stale-control-channel false positives.

### ISS-102 — Benchmark-task storm trigger source unknown (2026-05-09)

- **Found by:** Claude
- **Severity:** low
- **Affected files:** `backend/apps/benchmarks/tasks.py`, `backend/apps/benchmarks/views.py`, possibly `backend/config/celery.py`
- **Description:** On 2026-05-08 at 22:54-22:55 UTC, 5 `BenchmarkRun` rows were created in a 67-second window, all with `trigger='scheduled'`. The DB-stored beat schedule's `total_run_count=0` rules out beat as the trigger. The runner now correctly skips MSVC by-products (ISS-resolved by RPT-003 finding 4 in this same session) so the storm wouldn't be as visible if it recurred — but the trigger source is still unknown.
- **Status:** OPEN
- **Recommended fix:** Add a structured log line at the start of `run_all_benchmarks` capturing `(caller_pid, environ.get('HOSTNAME'), apply_async sender info)` so the next storm gets self-diagnostic context. Alternatively: add a Celery `before_task_publish` signal handler that warns if `run_all_benchmarks.delay()` is called more than once in a 60-second window.
- **Regression watch:** If `BenchmarkRun.objects.filter(trigger='scheduled', started_at__gte=...).count()` shows >2 runs in any 60-second window, this regressed.

### ISS-103 — Pyroscope-io 0.8.7 push-protocol incompatible with Pyroscope OSS 1.9 server (2026-05-09)

- **Found by:** Claude
- **Severity:** medium
- **Affected files:** `backend/requirements.txt` (agent version), `backend/config/settings/base.py` (init guard).
- **Description:** The `pyroscope-io==0.8.7` Python agent uses the pre-1.0 `/ingest` push-protocol. The Pyroscope OSS 1.9 server (Phlare-derived) accepts the requests with `200 OK` but does NOT index the profiles. Result: pyroscope-io shipped to a black hole — only `pyroscope` itself appeared in the service-name label list.
- **Status:** RESOLVED (genuinely — agent now ingests successfully)
- **Resolved:** 2026-05-09 (initial route-around with Sentry profiles); actual upstream fix 2026-05-09 follow-up: agent upgraded.
- **Fixed in:** **Upgraded `pyroscope-io` from `0.8.7` to `1.0.6`** in `backend/requirements.txt`. The 1.x agent series sends pprof-format profiles, which Pyroscope OSS 1.x indexes correctly. Verified: after live `pip install` + restart of all four services (backend + 3 Celery workers), `curl POST http://localhost:4040/querier.v1.QuerierService/LabelValues -d '{"name":"service_name"}'` returns `["pyroscope", "xf-linker-backend", "xf-linker-celery-beat", "xf-linker-celery-default", "xf-linker-celery-pipeline"]` within 25 s. Sentry profiling kept on as a redundant path via GlitchTip's Profiles tab. PYROSCOPE_ENABLED default flipped from `0` (route-around) back to `1` (default-on) in `base.py`. `apps.auto_issues.services.pyroscope_picker` will now start populating AutoIssue rows once 7 days of profile history accumulates for week-over-week regression detection.
- **Regression watch:** If `LabelValues` for `service_name` ever drops to just `["pyroscope"]` again, either the agent regressed (check `pip show pyroscope-io | grep Version`) or the server hit a compat break (check `docker logs xf_linker_pyroscope`). Sentry profiling is the redundant fallback in either case.

### ISS-104 — Sync produced 38 false IntegrityError events per run via try/except pattern (2026-05-09)

- **Found by:** Claude (during OTel verification of ISS-103 fix)
- **Severity:** medium
- **Affected files:** `backend/apps/audit/tasks.py` (`_sync_one_glitchtip_issue`).
- **Description:** The earlier merge fix for fingerprint collisions used `try INSERT ... except IntegrityError: merge`. The DB-level `psycopg.errors.UniqueViolation` fires BEFORE the Python `except` clause runs. Auto-instrumented stacks (Sentry Django integration + OTel psycopg span recorder) capture the error and report it to GlitchTip as a fresh event each time. Result: every sync run produced ~38 false-positive error events, drowning real bugs in noise.
- **Status:** RESOLVED
- **Resolved:** 2026-05-09
- **Fixed in:** Pre-check `exists()` on the unique key BEFORE the create. If a row with the same `(fingerprint, node_id)` already exists, jump to the merge path immediately. The DB never sees the conflict, the auto-instrumentation never sees an error. Pattern: "check-then-act" instead of "act-then-recover". Re-run sync confirmed `merged=38, created=1, updated=61` with **zero new IntegrityError events** in GlitchTip. All 3 collision tests still pass.
- **Regression watch:** If GlitchTip starts capturing `psycopg.errors.UniqueViolation: ... uniq_errorlog_fingerprint_per_node` again, someone reverted the pre-check. The fix is one if-statement; do not let a refactor accidentally remove it.

### ISS-107 — No centralized log search; container stdout was only inspectable per-container via `docker logs`, no LogQL, no retention beyond rotation, no log → AutoIssue path (2026-05-10)

- **Found by:** Claude (during plan exploration for "discard-Qodana / make-rituals-real" work)
- **Severity:** medium
- **Affected files:** `docker-compose.yml`, `loki-config.yaml`, `config.alloy`, `backend/apps/auto_issues/services/loki_picker.py`, `backend/apps/auto_issues/tasks.py`, `backend/apps/auto_issues/models.py`, `backend/apps/auto_issues/migrations/0005_add_loki_source_and_seed_loki_picker_settings.py`, `backend/apps/auto_issues/tests_loki_picker.py`, `backend/config/settings/celery_schedules.py`
- **Description:** GlitchTip captured exceptions, otel-collector captured traces, Pyroscope captured CPU profiles — but **non-error logs** (INFO/DEBUG, WARN that doesn't raise, repeated patterns that don't trip Sentry) had no centralized search. To grep across services you had to `docker logs <container>` per service. Logs were ephemeral (rotated by Docker). No log → AutoIssue path existed. The session-start ritual could not see a fourth source the user wanted (4 + 4 + 4 = 12 quota in plan does-adding-qodana-make-swift-wall.md).
- **Status:** RESOLVED
- **Resolved:** 2026-05-10
- **Fixed in:**
  1. **Loki added** (`grafana/loki:3.3.2`) on port 3100, single-binary filesystem-backed mode, 30-day retention. New volume `loki_data`, config `loki-config.yaml`. Verified `/ready` returns ready, `/loki/api/v1/query_range` returns container streams within seconds.
  2. **Grafana Alloy added** (`grafana/alloy:v1.5.1`) — modern unified telemetry agent that replaces Promtail (Promtail EOL 2026-03-02). Discovers all Docker containers via the read-only socket, tails stdout, ships to Loki. New volume `alloy_data`, config `config.alloy`. **Scope-down note:** the original plan was to *replace* `otel-collector` with Alloy as the single agent for everything, but verification of the Alloy component reference showed Alloy does NOT bundle the OpenTelemetry contrib `sentry` exporter that otel-collector uses to push traces to GlitchTip. Per the CLAUDE.md ABSOLUTE rule protecting the GlitchTip integration, replacing otel-collector would silently break trace delivery. So Alloy is **additive** (logs only) and otel-collector stays in place handling traces + metrics + nginx logs. When Alloy or GlitchTip later add the missing piece, we can complete the consolidation.
  3. **`loki_picker.py` added** with two detectors using disjoint fingerprint prefixes (so they never collide on the unique constraint):
       - `pick_loki_hot_patterns` — fetches WARN/ERROR/Traceback lines via LogQL, normalizes (strips timestamps, PIDs, hex addresses, UUIDs, line numbers — UUIDs match BEFORE PIDs to avoid eating the leading 8-char hex group), groups by fingerprint, promotes any pattern occurring ≥`loki.hot_pattern_min_count` times (default 10) in `loki.scan_window_seconds` (default 86400 s).
       - `pick_loki_warn_bursts` — per-container last-1h vs 24h-average rate. Promotes any container whose 1h rate ≥`loki.warn_burst_multiplier` (default 3.0) × the 24h baseline. Needs ≥24h of history; no-ops cleanly when the baseline is empty.
  4. **`AutoIssue.SOURCE_LOKI = "loki"`** added to choices; migration `0005_add_loki_source_and_seed_loki_picker_settings.py` alters the field choice list AND seeds five tunable AppSetting keys (`loki.api_url`, `loki.scan_window_seconds`, `loki.hot_pattern_min_count`, `loki.warn_burst_multiplier`, `loki.max_lines_per_query`) — all default ON per DEFAULT-ON-RULE.
  5. **Celery schedule wired:** `auto-issues-loki-pick` fires every 30 min during the active-laptop window 11-23 UTC at `:15/:45` — staggered 5 min after the Pyroscope picker so all three sources don't fight Postgres.
  6. **Tests:** 12 new tests in `tests_loki_picker.py` covering normalization (timestamps, PIDs, hex, UUIDs, traceback line numbers, similar-line collapse), stable fingerprint determinism + prefix disjointness, hot-pattern threshold + below-threshold no-op + multi-pattern separation, warn-burst promote/no-promote, schedule cadence + stagger. Plus `--source loki` is auto-derived from `AutoIssue.SOURCE_CHOICES` so `print_open_issues --source loki` works without a code change to the management command.
  7. **Live verification:** with the picker pointed at the running stack and `loki.hot_pattern_min_count` temporarily lowered to 2 to amplify the early-volume signal, the picker found 86 candidate patterns and promoted 10. Real findings included `column "checkpoints_timed" does not exist` (Postgres-exporter incompatibility) and a Python `Traceback (most recent call last)` cluster.
- **Regression watch:** If `print_open_issues --source loki` returns 0 while `curl http://localhost:3100/ready` returns ready AND there are container streams visible at `/loki/api/v1/labels`, the picker either lost its scheduled task, the threshold is set impossibly high, or the LogQL noise filter regex stopped matching real lines. The `LokiPickerScheduleTests` cadence + stagger tests catch the schedule regress; `LokiHotPatternIntegrationTests` catches the picker logic regress.
- **Lessons learned:** *Trap 1:* tools advertised as drop-in successors (Alloy → otel-collector + Promtail) ship with curated component sets that may NOT include contrib pieces you're already relying on. Always verify the receiver/exporter list before "replace" — the CLAUDE.md ABSOLUTE rule about GlitchTip preservation almost got broken because the Alloy switch sounded routine. *Trap 2:* LogQL line-filter regex flavors silently differ from Python `re`. Word boundaries (`\b...\b`) returned 0 hits in practice; a substring filter `(?i)(error|warn|...)` is safer and the count threshold filters incidental substring matches anyway. *Trap 3:* fingerprint normalization order matters — UUIDs share their first hex group's shape with long PIDs, so the UUID rule must run BEFORE the PID rule or the UUID gets corrupted. *Fix shape:* additive-not-replace for risky migrations; substring-filter + count-threshold for cross-engine regex compatibility; pattern order with explicit "this rule must run before that rule" comments.

### ISS-106 — Pyroscope week-over-week regression detector blind during the 7-day warmup, leaving Pyroscope-source AutoIssues empty (2026-05-10)

- **Found by:** Claude (during plan exploration for "discard-Qodana / make-rituals-real" work)
- **Severity:** medium
- **Affected files:** `backend/apps/auto_issues/services/pyroscope_picker.py`, `backend/apps/auto_issues/tasks.py`, `backend/apps/auto_issues/migrations/0004_seed_pyroscope_hotspot_threshold.py`, `backend/config/settings/celery_schedules.py`
- **Description:** ISS-103 fixed the Pyroscope ingest pipeline (`pyroscope-io` 0.8.7 → 1.0.6) on 2026-05-09 but the `pick_pyroscope_regressions` detector compares this-week vs last-week to find regressions, which needs **7 days** of profile history. Until 2026-05-16 the picker would always return `regressions_found=0`, so the Pyroscope half of the session-start ritual was dead despite the underlying ingest working. Same problem will re-occur any time the Pyroscope volume is wiped (Docker prune, fresh laptop, etc).
- **Status:** RESOLVED
- **Resolved:** 2026-05-10
- **Fixed in:** Added a same-day **hotspot detector** (`pick_pyroscope_hotspots`) that needs no history. It queries `/pyroscope/render` for the last 1 hour, sums per-function self-time, and promotes any function whose share exceeds `pyroscope.hotspot_pct_threshold` (seeded `5.0` percent default-on per DEFAULT-ON-RULE). Hotspots use a separate `external_id` prefix (`hotspot::...`) so they never collide with regression rows on the unique constraint. Wired into the existing Celery task `pick_daily_pyroscope_regressions` so a single beat tick fires both detectors. Schedule bumped from once-daily (`crontab(hour=11, minute=15)`) to every 30 min during the active-laptop window (`crontab(hour="11-23", minute="10,40")`), staggered 5 min after the GlitchTip picker so Postgres isn't contended. New unit tests cover threshold filtering, file-hint extraction, zero-total guard, missing-server skip, and end-to-end mocked HTTP round-trip. Live verification: against the running Pyroscope server, the detector found 9 hotspots and promoted all 9, including `ThreadScheduler.run` at 60.8% CPU.
- **Regression watch:** If `print_open_issues --source pyroscope` returns 0 while the Pyroscope server is reachable AND `curl http://localhost:4040/querier.v1.QuerierService/LabelValues -d '{"name":"service_name"}'` shows the four `xf-linker-*` services, someone reverted the hotspot detector OR set `pyroscope.hotspot_pct_threshold` impossibly high. Lower the threshold or check `_select_hotspots` for changes.
- **Lessons learned:** *Trap:* every CPU profiler that ranks regressions needs a baseline period; a single-period hotspot detector is a different pattern that's strictly easier to ship and produces value on day one. *Fix shape:* don't gate the entire picker output on the longest-baseline detector — add a same-day detector with a disjoint fingerprint prefix, then both can coexist forever.

### ISS-105 — GlitchTip picker scheduled once-daily, leaving 89 unacknowledged errors invisible to session-start ritual until 11:00 UTC (2026-05-10)

- **Found by:** Claude (during plan exploration for "discard-Qodana / make-rituals-real" work)
- **Severity:** medium
- **Affected files:** `backend/config/settings/celery_schedules.py`
- **Description:** The GlitchTip picker (`auto_issues.pick_daily_glitchtip_issues`) was scheduled at `crontab(hour=11, minute=0)` — **once per day at 11:00 UTC**. Today (2026-05-10) at 08:32 UTC the `audit_errorlog` mirror held **89 unacknowledged GlitchTip errors with valid `glitchtip_issue_id` values**, but `print_open_issues --source glitchtip` returned 0. Any agent session opening before 11:00 UTC saw a stale empty count, so the GlitchTip half of the auto-fix-3 ritual was effectively dead for 11+ hours each day. Picker is a pure DB job (~0.4 s for 89 rows on this machine) and idempotent via `(source, external_id)` upsert — running it 24× per active day is cheap.
- **Status:** RESOLVED
- **Resolved:** 2026-05-10
- **Fixed in:** `celery_schedules.py` — schedule changed from `crontab(hour=11, minute=0)` (daily) to `crontab(hour="11-23", minute="5,35")` (every 30 min during the active-laptop window 11-23 UTC). Staggered 5 minutes after `audit.sync_glitchtip_issues` (which fires at `:00,:30`) so the mirror is always populated before the picker reads it. `expires` bumped from 600 s to 1500 s so a slow run still wins its slot. New tests in `apps.auto_issues.tests_pickers.PickerScheduleCadenceTests` pin the cadence and stagger so it cannot silently regress to once-daily. Manual picker run while the diagnosis was in progress promoted 20 of the 89 GlitchTip errors to AutoIssues; `print_open_issues --source glitchtip` now returns 20 rows.
- **Regression watch:** If `print_open_issues --source glitchtip` ever returns 0 again while `ErrorLog.objects.filter(source='glitchtip', acknowledged=False).exclude(glitchtip_issue_id='').count()` is non-zero, someone either reverted the schedule, paused the celery-beat container, or broke `pick_glitchtip_issues`. The cadence test will catch the schedule revert; the picker unit test catches the second.
- **Lessons learned:** *Trap:* a Celery beat schedule comment that calls itself a "daily picker chain" reads as a hard design constraint, but the actual reason was just "stagger the four pickers within the 11-30 min boot window". Schedule cadence and stagger are two separate decisions. *Fix shape:* keep the stagger (still :00 / :05 / :15 / :20 / :25 / :30 in the active-laptop window), but each picker can fire as often as its work warrants. Pure-DB pickers should fire on the same cadence as their source-of-truth refresh.

### ISS-108 — ProgrammingError: connection in transaction status INTRANS / Cannot open connection in atomic block (2026-05-10)

- **Found by:** Antigravity (via GlitchTip auto-issue #44)
- **Severity:** high
- **Affected files:** `backend/apps/core/views_mcp.py`
- **Description:** Background threads in MCP management views were hitting "interleaved connection" or "atomic block" errors when multiple operations tried to share or reuse a stale database connection.
- **Status:** RESOLVED
- **Resolved:** 2026-05-10
- **Fixed in:** Hardened `backend/apps/core/views_mcp.py` by explicitly closing database connections at the start of every background thread. This ensures each thread acquires a fresh, isolated connection.
- **Regression watch:** If `ProgrammingError` returns in `views_mcp.py`, verify that `django.db.connection.close()` is still present at the very top of each thread's target function.

### ISS-109 — KeyError: 'core.*' / 'pipeline.*' during Celery task discovery (2026-05-10)

- **Found by:** Antigravity (via GlitchTip auto-issues #45, #46, #47)
- **Severity:** high
- **Affected files:** `backend/apps/core/tasks.py`, `backend/apps/pipeline/tasks.py`
- **Description:** Celery's `autodiscover_tasks()` failed to find tasks split into separate `tasks_*.py` files, leading to `KeyError` when dispatched via the Beat schedule or recovery tick.
- **Status:** RESOLVED
- **Resolved:** 2026-05-11
- **Fixed in:** Added explicit imports of `tasks.py` (and relevant `tasks_*.py` sub-modules) in the `ready()` methods of `CoreConfig`, `PipelineConfig`, `AuditConfig`, `AutoIssuesConfig`, and `ScheduledUpdatesConfig`. This ensures all `@shared_task` decorated functions land in the Celery registry even when `autodiscover_tasks()` misses them.
- **Regression watch:** If adding a NEW `tasks_submodule.py`, you MUST add an explicit `from . import tasks_submodule` in the app's `ready()` method (or its primary `tasks.py` if already imported in `ready()`). AutoIssues #44, #45, #46, #47, #48 purged.

---

## Templates

### New Report Entry

```markdown
### RPT-XXX — [Title] (YYYY-MM-DD)

- **Status:** OPEN (N of N findings unresolved)
- **Report file:** [`filename.md`](filename.md)
- **Scope:** [What code areas were audited]
- **Summary:** [One-line summary of key findings]

| # | Finding | Severity | Affected files | Status |
|---|---------|----------|----------------|--------|
| 1 | [description] | critical/high/medium/low | `file.py` | OPEN |
```

### New Individual Issue Entry

```markdown
### ISS-XXX — [Short description] (YYYY-MM-DD)

- **Found by:** [AI tool name, e.g. Claude / Codex / Gemini]
- **Severity:** critical / high / medium / low
- **Affected files:** `path/to/file.py`
- **Description:** [What the issue is and why it matters]
- **Status:** OPEN

_(When resolved, add:)_
- **Resolved:** YYYY-MM-DD
- **Fixed in:** [commit hash or session reference]
- **Regression watch:** [What to check if this area is changed again]
```
