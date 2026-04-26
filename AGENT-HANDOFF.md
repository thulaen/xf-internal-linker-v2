# 2026-04-26 05:00 - Claude Opus 4.7 (1M context)
[HANDOFF READ: 2026-04-26 04:35 by Claude Opus 4.7 - Docker socket-reset + lean backend command + autostart-off]

## Accomplishments — C# decommission cleanup + auto-tuner runtime fixes

### Live runtime bug fixes (Python auto-tuner was silently broken)

1. **`monthly_weight_tune` would crash on every successful optimization.** `WeightTuner.run()` at `backend/apps/suggestions/services/weight_tuner.py` was passing `proposed_weights`, `previous_weights`, and `optimisation_meta` to `RankingChallenger.objects.create()` — none of which are real model fields. Renamed to the live schema names (`candidate_weights`, `baseline_weights`) and dropped `optimisation_meta` (never existed). The metadata that was in `optimisation_meta` (sample_count, approval_rate, iterations, final_loss) is now in a single `logger.info(..., %s ...)` lazy-formatted call per `backend/PYTHON-RULES.md` §9.3.
2. **`evaluate_weight_challenger` was bypassing the SPRT comparator on every run** because `WeightTuner` never populated `predicted_quality_score` / `champion_quality_score` — both were `None`, so the task always took the auto-promote-on-missing-scores fallback. Fixed by computing `champion_quality = 1 / (1 + objective(w_init))` and `predicted_quality = 1 / (1 + objective(w_opt))` using the existing L-BFGS-B objective function. Both numbers are bounded in `(0, 1]` and computed by the same function so the SPRT 1.05 ratio comparator sees a fair signal.
3. **`source="cs_auto_tune"` writes against a retired choices list.** Migration `0028_alter_weightadjustmenthistory_source.py` (2026-04-12) removed `cs_auto_tune` from `WeightAdjustmentHistory.SOURCE_CHOICES`, but `tasks.py` lines 1851 and 2007 still wrote `source="cs_auto_tune"` on every promotion and rollback. Both call sites now write `source="auto_tune"`. New data migration `suggestions/0048_decommission_cs_labels.py` backfills any existing rows.
4. **Two additional bugs surfaced while writing the WeightTuner tests:** `backend/apps/suggestions/services/__init__.py` was missing entirely (the directory was a non-package), AND `weight_tuner.py:8` did `from .weight_preset_service import get_current_weights` but `weight_preset_service.py` lives in `apps/suggestions/`, not `services/`. Created `services/__init__.py` and switched to the absolute import `from apps.suggestions.weight_preset_service import get_current_weights`. Without these two fixes, `monthly_weight_tune` was crashing at the *import* of `WeightTuner`, before bug #1 even had a chance to fire.

### Schedule key rename + new migrations

- Renamed `monthly-cs-weight-tune` → `monthly-python-weight-tune` in `backend/config/settings/celery_schedules.py`, `backend/config/catchup_registry.py`, `frontend/src/app/jobs/scheduling-policy-card/scheduling-policy-card.component.ts`, and `docs/PERFORMANCE.md` §4.
- New migration `pipeline/0003_rename_monthly_cs_weight_tune_periodic_task.py` renames the existing `django_celery_beat.PeriodicTask` row so the database-backed scheduler stays in sync. Reversible.

### Help_text + label cleanup

- `RankingChallenger.run_id` / `baseline_weights` / `predicted_quality_score` and `WeightAdjustmentHistory.r_run_id` help_text strings now describe the Python L-BFGS-B optimizer, not the C# one. Migration `suggestions/0048_decommission_cs_labels.py`.
- `ServiceStatusSnapshot.SERVICE_CHOICES` keeps the keys `http_worker` and `scheduler_lane` (per ISS-009) but updates labels to `"Decommissioned HTTP worker (legacy)"` and `"Task Scheduler"`. Migration `diagnostics/0003_relabel_decommissioned_services.py`.

### Live backend / frontend wording cleanup

Touched (text only): `backend/apps/api/ml_views.py`, `backend/apps/suggestions/views.py`, `backend/apps/analytics/impact_engine.py`, `backend/apps/pipeline/services/circuit_breaker.py`, `backend/apps/pipeline/services/async_http.py`, `backend/apps/pipeline/consumers.py`, `backend/apps/diagnostics/views.py`, `backend/apps/diagnostics/signals.py`, `backend/apps/diagnostics/test_realtime_signals.py`, `backend/apps/benchmarks/{models,tasks,services/runner}.py`, `backend/config/settings/base.py`, `backend/extensions/CPP-RULES.md`. Deleted the unused `http_worker_breaker` definition in `apps/pipeline/services/circuit_breaker.py:167` and its re-export in `apps/sources/circuit_breaker.py` (zero call sites confirmed by grep). Dropped the always-zero `"csharp"` key from `apps/benchmarks/tasks.py` summary (frontend type already declared `{cpp, python}` only).

### Generated schema regenerated

- `python manage.py spectacular --color --file schema.yml` rebuilt `backend/schema.yml` cleanly.
- `npm run generate:api` rebuilt `frontend/src/app/api/schema.d.ts`. All five C# strings (description fields for `run_id`, `baseline_weights`, `predicted_quality_score`, `http_worker` enum, `scheduler_lane` enum) are gone.

### REPORT-REGISTRY rewrite

`docs/reports/REPORT-REGISTRY.md` RPT-001 table updated. Finding 1 (C# import lane 5-page cap) closed as **RESOLVED 2026-04-26 (obsolete)** — the C# lane no longer exists; live Python at `tasks_import.py` already addresses the original concern via `_DEFAULT_MAX_PAGES=500` + `import.max_pages` AppSetting + cap-warning log. Findings 4 and 5 stay OPEN but their affected-files columns now point at the live Python paths (`backend/apps/analytics/impact_engine.py` for #4; `backend/apps/suggestions/services/weight_tuner.py` + `backend/apps/pipeline/tasks.py` for #5). Three closure paragraphs added to the file documenting the rationale.

### Spec docs cleanup

Updated 11 spec files: `docs/BUSINESS-LOGIC-CHECKLIST.md`, `docs/PERFORMANCE.md`, `docs/specs/{fr017-bayesian-math-refinement,fr017-gsc-search-outcome-attribution,fr018-auto-tuned-ranking-weights,fr021-graph-based-link-candidate-generation,fr022-data-source-system-health-check,fr027-r-analytics-tidyverse-upgrade,fr097-crawl-priority-scheduling,opt-90-pixie-walk,opt-91-dom-extract,opt-92-bayes-attrib}.md`. The fr018 spec gained a `## Gate Justifications` section per RANKING-GATES Gate A (no new ranking signal, search space, or hyperparameter — runtime bug fix only). The OPT-90/91/92 specs updated from "C# native interop via P/Invoke" to "pybind11 modules called from Python" with provenance notes preserving the C# era as a tombstone. fr027 (R-analytics tidyverse) gained a "Second-wave update" subsection documenting that the C# Analytics Worker that originally replaced R was itself decommissioned 2026-04, with a three-column replacement table (R / current Python / interim C#).

### Tests added (8 new, all green)

- `backend/apps/suggestions/tests_weight_tuner.py` — 4 tests: live field names, both quality scores populated, scores bounded `(0, 1]`, no stale kwargs.
- `backend/apps/pipeline/tests_evaluate_weight_challenger.py` — 4 tests: promotion writes `source="auto_tune"`, rollback writes `source="auto_tune"`, neither writes `source="cs_auto_tune"`. SPRT evaluator is mocked to deterministically decide "promote" so the test isn't dependent on accumulated SPRT state.

## Status

- **Backend tests:** `apps.suggestions` (49) + `apps.diagnostics` (5) + `apps.benchmarks` (18) — all 72 pass. `apps.pipeline` — all 741 pass. New tests for the auto-tuner (8 new) — all pass.
- **Frontend:** `npm run build:prod` succeeds (two pre-existing nullish-coalescing warnings on `suggestion-detail-dialog.component.html` lines 455/458, untouched by this slice). `npm run test:ci` — 29 passes, 1 pre-existing failure (`SettingsComponent renders the telemetry settings cards on the WordPress sync tab` — `siloSvc.getFr099Fr105Settings is not a function`; I did not touch any settings file, see git diff confirmation).
- **Migrations:** all four new migrations applied cleanly (`suggestions/0048`, `diagnostics/0003`, `pipeline/0003`, `pipeline/0004`). `python manage.py makemigrations --check --dry-run` → "No changes detected."
- **Pre-existing migration drift surfaced and resolved this session:** `EmbeddingBakeoffResult` / `EmbeddingCostLedger` / `EmbeddingGateDecision` had un-migrated `TimestampedModel` field-option drift + index renames. Operator approved fixing it inline; auto-generated `pipeline/0004_rename_pipeline_bakeoff_cr_idx_*.py` is mechanical (3 RenameIndex + 9 AlterField on `created_at`/`id`/`updated_at`).

## Allowed historical references that remain (deliberate)

- All applied migrations under `apps/*/migrations/` that mention `cs_auto_tune` (suggestions/0020), `C# HttpWorker` / `C# Scheduler Lane` (diagnostics/0001, 0002), or any decommissioned identifier — applied migrations are immutable history.
- `frontend/src/app/settings/settings.component.ts:3205` mapping `cs_auto_tune: 'Auto-tuner (Python L-BFGS)'` — intentional bridging for any pre-existing DB rows the migration didn't catch (the source backfill in `suggestions/0048` only updates rows currently in the live DB; the frontend mapping protects against future surfacing of legacy values).
- `frontend/src/app/core/utils/highlight.utils.spec.ts` lines 21-22 — `'Use C++ and C#.'` is **test input** for the highlight-text utility, not a C# runtime claim.
- `backend/test_results.txt` (committed) — a historical test-output snapshot from before ISS-008/-009 fixed the legacy `HttpWorkerHealthTests` / `RuntimeConflictTests`. Those test classes no longer exist in `tests.py`. Cleaning up this file is out of scope for this slice; flagging here for a future cleanup session.
- `AI-CONTEXT.md`, `AGENT-HANDOFF.md`, `FEATURE-REQUESTS.md` historical entries — preserve cross-session continuity.
- Tombstone narrative inside the rewritten spec docs ("decommissioned 2026-04-12", "originally written for the C# era") — preserved by design as historical context for future agents.
- All "decommissioned 2026-04" / "originally written for the C# era" tombstone notes inside the rewritten spec docs.

## Files Touched

**Backend live code (Python edits):**
- `backend/apps/suggestions/services/weight_tuner.py` (full body of `WeightTuner.run()` + module imports + class docstring)
- `backend/apps/suggestions/services/__init__.py` (NEW — empty file to make the package importable)
- `backend/apps/suggestions/models.py` (5 help_text strings)
- `backend/apps/suggestions/views.py` (FR-018 endpoint comment block)
- `backend/apps/pipeline/tasks.py` (Part 8 block — 7 line edits)
- `backend/apps/pipeline/services/circuit_breaker.py` (module docstring + delete unused breaker)
- `backend/apps/pipeline/services/async_http.py` (drop 1 stale comment)
- `backend/apps/pipeline/consumers.py` (1 docstring)
- `backend/apps/sources/circuit_breaker.py` (drop unused breaker re-export)
- `backend/apps/diagnostics/models.py` (2 SERVICE_CHOICES labels)
- `backend/apps/diagnostics/views.py` (1 user-facing string)
- `backend/apps/diagnostics/signals.py` (2 comments)
- `backend/apps/diagnostics/test_realtime_signals.py` (1 test docstring)
- `backend/apps/benchmarks/{models,tasks,services/runner}.py` (3 docstring strings + drop csharp summary key)
- `backend/apps/api/ml_views.py` (module docstring)
- `backend/apps/analytics/impact_engine.py` (1 comment)
- `backend/config/settings/base.py` (delete + reword 2 comment blocks)
- `backend/config/settings/celery_schedules.py` (rename schedule key + comment)
- `backend/config/catchup_registry.py` (rename schedule key)

**Backend new migrations:**
- `backend/apps/suggestions/migrations/0048_decommission_cs_labels.py` (NEW — 4 AlterField + 1 RunPython backfill)
- `backend/apps/diagnostics/migrations/0003_relabel_decommissioned_services.py` (NEW — 1 AlterField on SERVICE_CHOICES)
- `backend/apps/pipeline/migrations/0003_rename_monthly_cs_weight_tune_periodic_task.py` (NEW — 1 RunPython, reversible)
- `backend/apps/pipeline/migrations/0004_rename_pipeline_bakeoff_cr_idx_*.py` (NEW, auto-generated — pre-existing TimestampedModel drift)

**Backend new tests:**
- `backend/apps/suggestions/tests_weight_tuner.py` (NEW — 4 tests)
- `backend/apps/pipeline/tests_evaluate_weight_challenger.py` (NEW — 4 tests)

**Backend regenerated:**
- `backend/schema.yml` (auto-generated from `manage.py spectacular`)

**Frontend:**
- `frontend/src/app/jobs/scheduling-policy-card/scheduling-policy-card.component.ts` (1 string)
- `frontend/src/app/api/schema.d.ts` (auto-generated from `npm run generate:api`)

**Docs:**
- `docs/reports/REPORT-REGISTRY.md` (RPT-001 only)
- `docs/BUSINESS-LOGIC-CHECKLIST.md` (8 line edits in §0/§1.3/§1.4/§2.1/§2.3/§4.4/§5/§6.1/§6.4)
- `docs/PERFORMANCE.md` (§4 task table)
- `docs/specs/fr017-bayesian-math-refinement.md`
- `docs/specs/fr017-gsc-search-outcome-attribution.md`
- `docs/specs/fr018-auto-tuned-ranking-weights.md` (substantial rewrite of §How-it-works + §Slices + §Gate-Justifications)
- `docs/specs/fr021-graph-based-link-candidate-generation.md`
- `docs/specs/fr022-data-source-system-health-check.md` (rewrite of §5 Analytics card + §11 HttpWorker tombstone + alert table)
- `docs/specs/fr027-r-analytics-tidyverse-upgrade.md` (added "Second-wave update" subsection)
- `docs/specs/fr097-crawl-priority-scheduling.md`
- `docs/specs/opt-90-pixie-walk.md`
- `docs/specs/opt-91-dom-extract.md`
- `docs/specs/opt-92-bayes-attrib.md`
- `backend/extensions/CPP-RULES.md` (1 line)

**Plan file (documentation only, lives outside the repo):**
- `C:\Users\goldm\.claude\plans\you-are-working-in-temporal-quiche.md`

## Addendum — clang-format CI gate fix (scope expansion, operator-confirmed)

Operator pasted a GitHub Actions failure log from CI step #14 (`cpp-format` — `find backend/extensions -name "*.cpp" -o -name "*.h" | grep -v '/build/' | xargs clang-format --dry-run --Werror --style=file`). The truncated tail of that log named four files (`anchor_diversity.cpp`, `bench_anchor_diversity.cpp`, `anchor_diversity_core.h`, `feedrerank_core.h`) but the full local re-run revealed **37 C++ files with clang-format violations** — pre-existing repo-wide formatting drift introduced by commits after `ab0d11b` (the previous "apply clang-format to all C++ files" commit). None of these files were touched by the C# decommission slice; the drift came from FR-045 (`45c20ab`) and the feedrerank rename (`475f4d3`).

**Verdict: real CI gate, not noise** — every flagged file still exists in the repo, the `.clang-format` config (Google + 4-space + 100-col) is genuine, and the `--Werror` flag means the gate is blocking.

**Fix applied:** installed `clang-format` 22.1.4 via pip wheel inside the backend container, ran `clang-format -i --style=file` on every `.cpp` and `.h` under `backend/extensions/` (excluding `/build/`). Re-ran the exact CI gate command — zero violations. Rebuilt all 14 pybind11 extensions via `python setup.py build_ext --inplace` — clean compile, all `.so` files refreshed. Re-ran the test suites — `apps.pipeline` 741/741 pass, `apps.suggestions` 49/49 pass, new auto-tuner regression tests 8/8 pass — confirming clang-format only touched whitespace and the C++/Python parity invariants are intact.

41 C++ files reformatted (37 violations + 4 already covered by partial overlap). The diff is mechanical (whitespace, line breaks, indentation). Spread across `extensions/*.cpp`, `extensions/include/*.h`, `extensions/benchmarks/*.cpp`, `extensions/benchmarks/*.h`, and `extensions/tests/*.cpp`.

## Next Steps for User

1. **Review the plan file** at `C:\Users\goldm\.claude\plans\you-are-working-in-temporal-quiche.md` if you want to see the original blueprint vs the deviations (the two unplanned-but-discovered bugs around `services/__init__.py` and the `.weight_preset_service` import path).
2. **Decide whether to commit this slice now or have me run additional tests first.** I have not committed anything (per the Branch Transparency rule). The dirty tree now has **87 modified files** (39 C# slice + 41 C++ format + 7 untracked new files).
3. **Pre-existing follow-ups flagged for separate slices:**
   - Remove `backend/test_results.txt` — historical snapshot that still references the long-deleted `HttpWorkerHealthTests`. Out of scope here.
   - Investigate the `siloSvc.getFr099Fr105Settings is not a function` frontend test failure in `frontend/src/app/settings/settings.component.spec.ts`. Unrelated to this slice — the missing method is in `silo-settings.service.ts`.
   - Two pre-existing nullish-coalescing warnings in `frontend/src/app/review/suggestion-detail-dialog.component.html` lines 455/458.
   - The conftest.py at `backend/conftest.py:12` calls `get_user_model()` at module import time, which prevents standalone `pytest tests/test_parity_*.py` runs (it works fine via `manage.py test` because Django's test runner initialises apps first). Cosmetic but annoying.
4. The auto-tuner can finally run successfully end-to-end after the `services/__init__.py` and `.weight_preset_service` import fixes. The next first-Sunday-of-the-month tick will exercise it.
5. **Suggested commit shape** if you commit now: split into two commits — first the C# decommission slice (39 modified + 7 untracked files, including migrations and new tests), then the clang-format pass (41 mechanical reformats). Each commit is self-contained and reversible.



## Accomplishments
- **Permanent fix for "Docker Desktop spinning forever after every reboot"**: rooted to orphan AF_UNIX socket reparse points (`dockerInference`, `engine.sock`) that Windows cannot delete. Built `scripts/reset-docker-sockets.ps1` which renames any directory containing an unreadable reparse point, and `scripts/install-docker-socket-reset-task.ps1` which registers a user-level Windows Scheduled Task `XFLinker-ResetDockerSockets` (AtLogOn, Hidden window, ExecutionPolicy Bypass). Task is now active.
- **Disabled Docker Inference Manager**: set `EnableDockerAI: false` and `InferenceCanUseGPUVariant: false` in `%APPDATA%\Docker\settings-store.json` so the Inference Manager does not even spawn. Linker stack does not use Docker Model Runner.
- **Trimmed backend `command:` in `docker-compose.yml`**: removed `pip install -r requirements.txt`, `import drf_spectacular` probe (both already done at build time in `backend/Dockerfile:62-63`). Container now goes from start to healthy in ~33s instead of ~90-180s, and there is no network dependency at container start so a cold-boot reboot will not loop the container forever. Kept `build_ext --inplace` because the bind mount of `./backend → /app` hides image-baked `.so` files.
- **CLAUDE.md updated** under Docker Rules with the orphan-socket fix, the autostart-off rule, and the lean-command rule. `scripts/start.ps1` got a header comment explaining the new boot semantics.

## Status
- **Docker Desktop**: 29.4.0, currently running and healthy.
- **Linker stack**: all 7 services `(healthy)`, GlitchTip profile services also up.
- **AutoStart in settings-store.json**: `false` (was already off when I arrived).
- **Scheduled Task XFLinker-ResetDockerSockets**: registered, ran successfully once (renamed a fresh secrets-engine orphan as a smoke test).
- **Backend image**: NOT rebuilt; `docker compose up -d` recreated only the backend container with the new compose-file command. Image is unchanged (still has pip install at build time).

## Next Steps for User
1. **Real test**: reboot the laptop. After login, do nothing for 30s, then click Docker Desktop. Whale icon should settle in ~30-60s (no spin), and `restart: always` should bring all containers back up (no need to run `start.ps1`).
2. If a future Docker Desktop release introduces a new orphan-socket location, append the path to `$candidateDirs` in `scripts/reset-docker-sockets.ps1`.
3. Optional follow-up: clean up the leftover `priceless_feistel` container (unrelated test scratch container, exited 11 hours ago). `docker rm priceless_feistel`.

## Files Touched
- `docker-compose.yml` — backend `command:` block (lines 118-127, now lean)
- `scripts/start.ps1` — header comment update
- `scripts/reset-docker-sockets.ps1` — NEW
- `scripts/install-docker-socket-reset-task.ps1` — NEW
- `CLAUDE.md` — two new bullets under Docker Rules
- `%APPDATA%\Docker\settings-store.json` — EnableDockerAI/InferenceCanUseGPUVariant set to false

# 2026-04-26 00:13 - Gemini 3.1 Pro (High)
[HANDOFF READ: 2026-04-25 by Antigravity — Stabilized frontend and Nginx infrastructure]

## Accomplishments
- **Login HTTP-to-HTTPS redirect fix**: Changed Nginx port 80 redirect from `301` to `308`. This preserves the POST method when the Service Worker traps the initial navigation on HTTP, preventing the login form from throwing a `405 Method Not Allowed`.
- **WebSocket Storms Fixed**: Fixed duplicate socket leaks in `PulseService` and `NotificationService` caused by multiple `isLoggedIn$` emissions. Appended missing auth token to `PulseService`.
- **Pull-To-Refresh Mobile Performance**: Re-engineered `appPullToRefresh`. Removed `@HostListener('pointermove')` which was flooding the Angular zone with >100 change detections per second during mobile swipes. Events are now bound manually using `Renderer2` wrapped in `NgZone.runOutsideAngular()`.

## Status
- **Nginx**: Healthy and correctly redirecting POST requests with 308.
- **Frontend**: Production build completed with performance and socket fixes.

## Next Steps for User
1. Test login flow and background telemetry.
2. Monitor system for any leftover toasts.

# 2026-04-25 22:35 - Antigravity
[HANDOFF READ: 2026-04-25 by Antigravity — Stabilized frontend and Nginx infrastructure]

## Accomplishments
- **Nginx 1.30 LTS Upgrade**: Rewrote config for HTTPS, HTTP/2, and dynamic DNS resolution (resolver 127.0.0.11).
- **Sluggishness Fix**: Reduced proxy_connect_timeout to 5s. This prevents Nginx from holding onto broken backend connections for 60s, which previously exhausted the browser's 6-connection-per-host limit and caused the UI to hang.
- **Login "Server error" Fix**: Auth-gated PulseService, AppearanceService, and FeatureFlagsService. They no longer hit authenticated endpoints before the user logs in, eliminating the 403 storms on the login page.
- **Build Recovery**: Fixed a missing MatCardModule import in DiagnosticsComponent that was breaking the production build of the frontend.
- **Service Worker Tuning**: Reconfigured ngsw-config.json to lazy-load chunks and cache boot-time settings, improving perceived startup speed.
- **Silent Error Cleanup**: Patched state-sync bugs in AppearanceService (logo/favicon removal) and added error handling to NotificationService summary loading.

## Status
- **Nginx**: Healthy (verified ok on /nginx-health).
- **Frontend**: Production build completed and assets published to frontend_dist.
- **SSL**: mkcert is active; https://localhost is ready.

## Next Steps for User
1. **Auto-Renewal**: Run scripts\install-cert-renewal-task.ps1 in an Administrator PowerShell to register the monthly certificate renewal task.
2. **Verify**: Visit https://localhost and confirm the green padlock and the absence of the "Server error" toast on login.
