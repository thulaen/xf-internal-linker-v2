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

## 2026-04-22 — PR-A slice 4: 126 pending ranking signals (Block A-O / FR-099..FR-224)

Retired the full Block A-O forward-declared signal library. Every signal in these four files was inert — no production scoring path consumed them — and each one fell into a conflict, overlap, duplicate, or "no-consumer niche" tier per the plan's Part 1 manifest.

Gone for good:

- Weight files:
    - `backend/apps/suggestions/recommended_weights_phase2_signals_a_d.py` (Block A-D, FR-099..FR-133)
    - `backend/apps/suggestions/recommended_weights_phase2_signals_e_h.py` (Block E-H, FR-134..FR-169)
    - `backend/apps/suggestions/recommended_weights_phase2_signals_i_l.py` (Block I-L, FR-170..FR-203)
    - `backend/apps/suggestions/recommended_weights_phase2_signals_m_o.py` (Block M-O, FR-204..FR-224)
- Spec files: 126 `docs/specs/fr099-*.md` through `docs/specs/fr224-*.md` (one per signal).
- Registry wiring: imports removed from `backend/apps/suggestions/recommended_weights.py`; `_SIGNAL_FILES` parser list removed from `backend/apps/suggestions/meta_registry.py` (the settings tab no longer emits phantom "signal" family rows for deleted prefixes).
- FRs: FR-099 through FR-224 (every feature request in the pending signal range).

All 126 signal prefixes added to `backend/scripts/deleted_tokens.txt` so the gate will fail if any reappears.

Note: the smaller `recommended_weights_forward_settings.py` file (FR-038..FR-090 range) contains a mix of pending signal entries and pipeline-configuration entries. Its cleanup is deferred to slice 5 / slice 6 where each entry is inspected individually.

## Upcoming entries (reserved)

- PR-A slice 5 — ~184 pending meta-algos not in the 52-pick roster (META-40..META-249 minus the kept 8 plus new specs).
- PR-A slice 6 — Doc scrubbing (AI-CONTEXT.md, FEATURE-REQUESTS.md, REPORT-REGISTRY.md, v2-master-plan.md, BUSINESS-LOGIC-CHECKLIST.md, PERFORMANCE.md, signal_registry.py comments).

Each future slice will append its own section here and its banned identifiers to `backend/scripts/deleted_tokens.txt`.
