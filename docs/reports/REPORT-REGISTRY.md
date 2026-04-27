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
- **Resolved:** 2026-04-27
- **Fixed in:** Added a `sys.argv` guard in `PipelineConfig.ready()` to skip index initialization if the command is `manage.py` (with exceptions for `runserver` and `test`).
- **Regression watch:** Keep FAISS index building out of `AppConfig.ready()` for management commands and other startup paths that should remain side-effect free.

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
