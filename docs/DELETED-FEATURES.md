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

## 2026-04-22 — PR-A slice 5: 238 pending meta-algo specs + 5 phase-2 weight files

Retired the Phase-2 pending meta-algorithm library. Every entry was forward-declared (enabled=false in most cases), never wired, and was only referenced by `recommended_weights.py` merges and the meta_registry parser — no production scorer consumed these keys.

Gone for good:

- Weight files (5 removed):
    - `backend/apps/suggestions/recommended_weights_phase2_metas_p1_p6.py` (blocks P1..P6, META-40..META-75)
    - `backend/apps/suggestions/recommended_weights_phase2_metas_p7_p12.py` (blocks P7..P12, META-76..META-105)
    - `backend/apps/suggestions/recommended_weights_phase2_metas_q1_q8.py` (blocks Q1..Q8)
    - `backend/apps/suggestions/recommended_weights_phase2_metas_q9_q16.py` (blocks Q9..Q16)
    - `backend/apps/suggestions/recommended_weights_phase2_metas_q17_q24.py` (blocks Q17..Q24)
- Spec files (238 removed): `docs/specs/meta-NN-*.md` for every META-04..META-249 except the 8 that map to roster picks (META-43 L-BFGS-B, META-55 TPE, META-77 LambdaLoss, META-87 Platt Scaling, META-91 Cosine Annealing, META-96 SWA, META-102 OHEM, META-103 Reservoir Sampling).
- Registry wiring: 5 imports + 5 `.update()` calls dropped from `recommended_weights.py`; `_FILE_TO_FAMILY_RANGE` in `meta_registry.py` emptied.

When PR-B through PR-P ship actual implementations for roster picks, they will add fresh settings keys directly to `recommended_weights.py` and write new specs for the implementations.

## 2026-04-22 — PR-A slice 6: doc scrubbing (no new capabilities gone)

House-cleaning pass that drove the phantom-reference gate to 0.

What changed (no feature loss):

- `FEATURE-REQUESTS.md`: hard-deleted the FR-091, FR-225 entries plus the 126 pending-signal rows and 210 pending-meta rows in the Phase-2 Forward-Declared Backlog section. The corresponding specs/code were already gone in slices 1-5; these were dangling pointers.
- `AI-CONTEXT.md`: removed the phantom-pointing dashboard row, the OPT-73..89 range reference, and the `meta-rotation-tournament` schedule mention. Replaced with a forward pointer to the decision record.
- `docs/reports/REPORT-REGISTRY.md`: marked RPT-002 as **RESOLVED** (the 337-item backlog was retired in PR-A) with a pointer to `docs/DELETED-FEATURES.md`.
- `docs/GAP-41-AUDIT.md`: stripped the line pointing to the deleted `diagnostics/meta-tournament/` component.
- `backend/apps/diagnostics/signal_registry.py`: dropped the commented-out `FR-091 C++ Extension Retrofit` SignalDefinition placeholder.
- `backend/apps/suggestions/recommended_weights_forward_settings.py`: dropped the inert `cpp_retrofit.*` block tied to FR-091.
- `docs/specs/opt-74/76/77/79-abseil-*.md` and `opt-83-farmhash-hasher.md` / `opt-88-phrase-inventory.md`: removed the "shared with OPT-73" / "if OPT-73 is installed" citations since OPT-73 (abseil-hashmap-inv-index) was deleted in slice 2.

## 2026-04-22 — PR-A slice 7: dev Angular frontend compose setup retired

Consolidated the compose stack down to a single prod-mode file. Local work now runs against the same Angular production bundle + Django production settings that a live deployment uses, so any measurement or screenshot taken while working matches what operators actually see.

Gone for good:

- `docker-compose.prod.yml` — contents merged into `docker-compose.yml`; the file is deleted.
- `docker-compose.override.yml` — held the `frontend-dev` HMR profile and the GlitchTip debug-profile overrides. The GlitchTip fix (separate `/glitchtip` DB instead of sharing the linker's DB) was ported into `docker-compose.yml`.
- `frontend/Dockerfile` — the ng-serve dev Dockerfile. Only `frontend/Dockerfile.prod` survives.
- Dev-frontend compose service identifiers: `frontend-dev` (override profile name), `xf_linker_frontend_dev` (container name), `xf_linker_frontend` (dev container name — the prod equivalent is `xf_linker_frontend_build`).

Why: per the PERFORMANCE.md rule ("performance work MUST run against this stack, not the dev server"), the dual-mode setup invited measurement skew and tempted future AIs to "just run dev for now." Removing the option removes the temptation.

Replacement workflow for developers:

- `docker compose --env-file .env up --build` — boots the whole stack with the prod Angular bundle behind nginx on port 80.
- Optional debug profile (GlitchTip): `docker compose --profile debug up`.
- There is no longer a port-4200 Angular dev server. Frontend iteration means rebuilding the `xf-linker-frontend-prod` image; use `docker compose build frontend-build` and then `docker compose up -d nginx`.

All dev-frontend identifiers added to `backend/scripts/deleted_tokens.txt` so the phantom-reference gate fails if any reappear.

## Upcoming entries (reserved)

(None currently — PR-A is closing out. PR-B..PR-P will ship features, not retirements.)

Each future slice will append its own section here and its banned identifiers to `backend/scripts/deleted_tokens.txt`.
