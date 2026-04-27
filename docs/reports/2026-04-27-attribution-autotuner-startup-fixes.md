# 2026-04-27 - Attribution, Auto-Tuner, and FAISS Startup Fixes

## Summary

This report covers three bug fixes found during a targeted backend review:

- FR-017 GSC impact snapshots could record a positive or negative reward even when the matched-control group was inconclusive.
- FR-018 auto-tuned ranking weights could move farther than the documented per-run drift cap after final normalization.
- FAISS startup still touched the database during test and import startup paths where migrations/test tables may not exist yet.

## Changes

- `backend/apps/analytics/impact_engine.py`
  - `GSCImpactSnapshot` is now written only when the matched-control group is conclusive (`control_match_count >= 3`).
  - Existing snapshots for the same suggestion/window are deleted when a recompute becomes inconclusive, so stale positive/negative claims do not linger.
  - Removed a broken `SearchMetric.property_url` read. `SearchMetric` does not have that field, and the Bayesian calculation does not need it.
- `backend/apps/suggestions/services/weight_tuner.py`
  - Baseline weights are normalized before objective/remainder math.
  - Candidate weights are projected back into the bounded simplex after L-BFGS-B, preserving sum `1.0` while enforcing the `0.05` per-weight drift cap.
  - Candidate quality is computed from the final projected weights rather than the raw optimizer output.
- `backend/apps/pipeline/apps.py`
  - FAISS startup build now runs only for safe runtime entrypoints (`manage.py runserver`, Celery, ASGI/WSGI server commands), not tests, imports, migrations, or arbitrary scripts.

## Source and Risk

- Attribution remains based on Abadie, Diamond & Hainmueller (2010) matched controls plus the existing Poisson-Gamma uplift model; this change only enforces the already-present minimum-control reliability rule.
- Auto-tuning remains the existing FR-018 L-BFGS-B optimizer over the four core blend weights. The change tightens the safety contract without expanding the search space.
- FAISS retrieval behavior at runtime is unchanged for server/worker entrypoints. The risk is that an unusual production launcher not named Celery, Daphne, Gunicorn, Uvicorn, or `manage.py runserver` will skip startup index build; that path still falls back to lazy/NumPy behavior already used when FAISS is unavailable.

## Verification

- `manage.py test apps.suggestions.tests_weight_tuner --noinput` passed.
- `manage.py test apps.analytics.tests.GSCSlice1Tests.test_inconclusive_control_group_does_not_create_impact_snapshot --noinput` passed.
- `manage.py makemigrations --check --dry-run` passed with no changes detected.
- `manage.py showmigrations` ran without the prior FAISS database-access warning.
- `ruff check` passed for the touched backend files.
- Full backend suite passed after rerunning outside the sandboxed temp-directory limitation: `manage.py test --noinput` = 1375 tests OK, 16 skipped.
- Docker migration checks passed: container `showmigrations` showed all migrations applied, and container `makemigrations --check --dry-run` reported no changes.
- Safe prune ran after Docker verification via `scripts/prune-verification-artifacts.ps1`.
