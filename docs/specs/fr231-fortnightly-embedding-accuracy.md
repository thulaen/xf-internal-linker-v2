# FR-231 — Fortnightly embedding-accuracy audit

## 1 · Identity

| Field | Value |
|---|---|
| **Canonical name** | Fortnightly embedding-accuracy audit |
| **Settings prefix** | `embedding.accuracy_*`, `embedding.audit_*` |
| **Pipeline stage** | Embed |
| **Helper module** | `backend/apps/pipeline/services/embedding_audit.py` |
| **Celery task** | `backend/apps/pipeline/tasks_embedding_audit.py` (`pipeline.embedding_accuracy_audit`) |
| **Benchmark module** | `backend/benchmarks/test_bench_embedding_audit.py` |

## 2 · Motivation (ELI5)

Embeddings can silently rot: a row ends up NULL because a container rebuilt
the DB, a vector's dimension no longer matches the current model because the
operator swapped provider, or the numbers drift because an upstream library
changed how it tokenises. Once every two weeks, Thursday 13:00–22:59 UTC, we
scan every content embedding, classify what's broken, and re-embed only the
flagged items. Zero duplicates on the healthy ones.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Primary** | Voorhees, 1999 — *"The TREC-8 Question Answering Track Report"* (NIST Special Publication 500-246) |
| **Retrieval metrics** | Järvelin & Kekäläinen, 2002 — *"Cumulated gain-based evaluation of IR techniques"* (ACM TOIS 20(4)) |
| **Drift detection pattern** | Gama et al., 2014 — *"A survey on concept drift adaptation"* (ACM Computing Surveys 46(4)) |
| **Relevant sections** | Gama §3 "performance-based detection"; Voorhees §4 "qrel sampling" |
| **What we reproduce** | The norm-and-resample drift detector (compare stored vector to a fresh re-embed; flag items where cosine < threshold). |
| **What we diverge on** | We use a fortnightly cadence instead of continuous streaming — matches laptop-class resource budgets from `docs/PERFORMANCE.md` §5. |

## 4 · Input contract

`scan_embedding_health(*, current_signature, current_dimension, norm_tolerance=0.02, drift_threshold=0.9999, resample_size=50)`

- **current_signature** — `str` — the provider+model+dim string currently considered canonical.
- **current_dimension** — `int` — expected vector length.
- **norm_tolerance** — `float` — acceptable deviation from unit L2 norm.
- **drift_threshold** — `float` — minimum cosine (stored, fresh re-embed) before flagging.
- **resample_size** — `int` — random sample drawn from the healthy set for resample check.

Empty DB (no ContentItem rows) → returns an `AuditReport` with all counters zero and `flagged_pks=[]`. No error.

## 5 · Output contract

`AuditReport(total, ok, null, wrong_dim, wrong_signature, drift_norm, drift_resample, flagged_pks)`.

- `total` = rows scanned.
- Sum of `ok` + each drift bucket equals `total`.
- `flagged_pks` is a list of ContentItem PKs the caller should feed to `generate_all_embeddings(pks, force_reembed=False)`.
- Deterministic given the same DB state and a seeded RNG (`random.Random(42)` used for the resample subset).

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? |
|---|---|---|---|---|
| `embedding.accuracy_check_enabled` | bool | `true` | Project policy | No |
| `embedding.audit_resample_size` | int | 50 | Voorhees 1999 — small qrel sample is sufficient for drift signal | No |
| `embedding.audit_norm_tolerance` | float | 0.02 | Gama 2014 §3 — tight-band drift detector | No |
| `embedding.audit_drift_threshold` | float | 0.9999 | Internal — cosine near-1 for stable models | No |
| `embedding.accuracy_last_run_at` | str (ISO) | `""` | Written by the task | — |

Seeded by `apps/core/migrations/0013_seed_embedding_provider_defaults.py` so fresh installs pick up sane values on first migrate.

## 7 · Schedule + catch-up

- Celery Beat: `crontab(minute=0, hour=13, day_of_week=4)` — Thursdays 13:00 UTC (matches the Heavy/Medium window in `docs/PERFORMANCE.md` §5).
- Fortnight gate: task exits early if `last_run_at` is less than 13 days ago.
- Window gate: if `13 ≤ hour < 23` UTC fails (started early/late), task self-retries with `countdown=300` up to the 1-hour soft time limit.
- Catch-up: `backend/config/catchup_registry.py` threshold 336h, priority 35, queue `pipeline`, weight `medium` — missed runs dispatch automatically on next worker boot.

## 8 · Test plan

1. **Unit** — `_scan_inner_loop` test via `benchmark/test_bench_embedding_audit.py` with synthetic unit-norm vectors proves norm + dim gates fire correctly.
2. **Integration** — manually dispatch: `embedding_accuracy_audit.delay(fortnightly=False, force=True)`. Confirm `PipelineDiagnostic` row with correct counts.
3. **Catch-up** — set `embedding.accuracy_last_run_at` to 20 days ago, restart worker, confirm dispatch within 5 min of `worker_ready`.
4. **Budget** — `docker stats` during a 10 000-item run — worker RSS must stay under the Medium envelope (~1 GB).
