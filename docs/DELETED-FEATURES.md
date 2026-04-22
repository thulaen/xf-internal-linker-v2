# Deleted Features — Gravestone

Do not re-implement anything on this list without (a) a fresh plan that justifies revisiting it and (b) explicit user approval.

This file is the human-readable ledger of features and identifiers that were deliberately retired. The machine-readable counterpart — used by the CI gate — is `backend/scripts/deleted_tokens.txt`. The gate fails the build if any listed identifier reappears outside the small allow-list (this file, the plan file, the gate script, and git history).

Why this exists: Without a gravestone + CI gate, future AI sessions grep old specs or doc crumbs and try to resurrect a deleted feature — the "spinning in circles" problem the retirement plan explicitly calls out.

---

## 2026-04-22 — PR-A slice 1: FR-225 Meta Tournament system

Retired the nightly meta-rotation tournament in favour of a fixed 52-meta roster + 1pm-11pm Scheduled Updates orchestrator (per `plans/check-how-many-pending-tidy-iverson.md`).

Gone for good:

- FR-225 (tournament scheduler feature request).
- Code modules: `backend/apps/suggestions/services/meta_rotation_scheduler.py`, `backend/apps/suggestions/services/meta_slot_registry.py`.
- Django models: `MetaTournamentResult`, `HoldoutQuery` (tables dropped via migration `0034_drop_meta_tournament_tables`).
- API views: `MetaTournamentView`, `MetaTournamentRunView`, `MetaTournamentPinView`.
- URL routes: `/api/system/status/meta-tournament/`, `/run/`, `/pin/`.
- Frontend component: `frontend/src/app/diagnostics/meta-tournament/` (folder + TS class).
- Celery beat entry: `meta-rotation-tournament` / `suggestions.meta_rotation_tournament`.
- Registry objects: `META_SLOT_REGISTRY`, `MetaSlotConfig`.
- Helper functions: `run_meta_tournament`, `_evaluate_meta_on_holdout`, `_should_promote`.
- Spec file: `docs/specs/fr225-meta-rotation-scheduler.md`.

## 2026-04-22 — PR-A slice 2: 3 unwired C++ kernels + 5 stale optimisation specs

Retired three pybind11 kernels that had no production readers (only benchmarks referenced them), plus five specs that planned optimisations *for* those kernels.

Gone for good:

- C++ kernels: `strpool`, `inv_index`, `pulse_metrics` (sources + `*_core.h` headers + `bench_*.cpp` benchmark executables).
- FRs: FR-091 (cpp-extension-retrofit — listed five imaginary kernels that never shipped).
- OPTs: OPT-73, OPT-75, OPT-78, OPT-89 (abseil hashmap / mutex retrofits + pipeline-accel orchestrator).
- Spec files: `fr091-cpp-extension-retrofit.md`, `opt-73-abseil-hashmap-inv-index.md`, `opt-75-abseil-hashmap-strpool.md`, `opt-78-abseil-mutex.md`, `opt-89-pipeline-accel.md`.
- Write-only pulse-metrics push inside `backend/apps/crawler/tasks.py` heartbeat (no consumer ever read the ring-buffer summary).

## Upcoming entries (reserved)

- PR-A slice 4 — All 161 pending ranking signals (blocks A-O + FR-038..FR-090 forward settings). These fall into conflict/overlap/duplicate/niche tiers per the plan and were never wired.
- PR-A slice 5 — ~184 pending meta-algos not in the 52-pick roster (META-40..META-249 minus the kept 8 plus new specs).

Each future slice will append its own section here and its banned identifiers to `backend/scripts/deleted_tokens.txt`.
