# Helper-Constraint Rubric

**Plain English:** Every Celery task in this repo carries an `@HelperConstraint(...)` decorator that tells the Phase 4.9 helper-PC router how heavy the task is, whether it needs a GPU, where it writes its results, and roughly how long it takes. The router reads that metadata to decide whether to run the task on the main machine or hand it off to a secondary "helper" PC.

This document is the authoritative guide for picking decorator values when you add a new Celery task.

---

## The decorator

```python
from celery import shared_task
from apps.core.helpers import HelperConstraint

@shared_task(name="my_app.my_task", time_limit=600)
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=256,
    expected_seconds_p50=None,
)
def my_task(...):
    ...
```

**Order matters.** `@HelperConstraint` MUST be listed BELOW `@shared_task` (i.e. inside it) so Celery's wrapper sees the annotated callable. The metadata lands on `task.run.__helper_constraint__` where the router reads it.

**Scope.** Every task under `backend/apps/**/tasks*.py` and `backend/apps/**/runner.py` must carry the decorator. The new coverage test at `backend/apps/core/tests_helper_constraint_coverage.py` fails CI if any registered task in `apps.*` is missing it.

---

## Defaults (use these when in doubt)

| Argument                 | Default value         | What it means                                                |
|--------------------------|-----------------------|--------------------------------------------------------------|
| `cpu_intensive`          | `False`               | Task is mostly waiting on I/O or just shuffling DB rows.     |
| `gpu_required`           | `False`               | Task does not need a CUDA device.                            |
| `storage_writes_to`      | `"postgres_main"`     | Writes go to the main PC's Postgres.                         |
| `ram_peak_mb`            | `256`                 | Peak RAM usage stays under 256 MB.                           |
| `expected_seconds_p50`   | `None` (omit)         | Don't claim a runtime — let the router treat it as unknown.  |
| `requires_warmed_models` | `()` (omit)           | Task does not need a pre-loaded model (BGE-M3 etc).          |

A task that does nothing more than read a few rows, write a few rows, and finish in well under a minute should keep all defaults.

---

## When to override the defaults

### `cpu_intensive=True`

Set when the task does any of:
- Aggregates >100K rows (Polars `group_by`, numpy reductions, `bulk_update` over a large queryset).
- Walks a graph or runs a clustering / scoring loop in Python.
- Re-fits a small model (TF-IDF refresh, calibration fit, hub detection).
- Calls a long-running Rust extension that does the actual compute.

When you set `cpu_intensive=True`, also set `ram_peak_mb=512` unless you have evidence the task is heavier.

### `gpu_required=True`

Set ONLY when the task imports `torch` and runs work on a CUDA device — e.g. embedding generation, embedding-provider bake-off, embedding-accuracy audit. Pair with `ram_peak_mb≥4000` because the BGE-M3 model alone holds ~2.5 GB of weights and a batch fills the rest.

If the task gracefully degrades when no CUDA device is present (logs "no_cuda" and returns), keep `gpu_required=False` — the router can still place it on a CPU-only helper. `gpu_memory_cleanup` is the canonical example.

### `storage_writes_to`

| Value              | Use when…                                                                                       |
|--------------------|--------------------------------------------------------------------------------------------------|
| `"postgres_main"`  | The task writes anything to the main Postgres DB (the default for almost every task).            |
| `"redis"`          | The task only updates a Redis cache key (rare — most cache writes happen as side-effects).       |
| `"helper_archive"` | The task is read-mostly on Postgres + writes its output to the helper's SMB share. Helper-routable. |
| `"none"`           | Pure-compute / read-only task. Returns a value but writes nothing anywhere.                      |

**Important:** `"postgres_main"` causes the router to return `None` and keep the task on the main machine. That is the safe default — only switch to `"helper_archive"` or `"none"` once you have actually traced every write path the task touches and confirmed nothing lands in the main DB.

### `ram_peak_mb`

| Workload                                                          | Suggested value |
|-------------------------------------------------------------------|-----------------|
| Tiny — a few DB rows in/out, no aggregation                       | `256` (default) |
| Polars / numpy aggregation over >100K rows                        | `512`           |
| Multi-million-row batch jobs, FAISS index refresh                 | `1024`–`2048`   |
| BGE-M3 or other GPU model loaded into memory                      | `4000`+         |

### `expected_seconds_p50`

Optional. Set when you have a credible historical p50 from production telemetry. The router uses it to keep long-running tasks on main where Postgres latency is lower. Skip it for new tasks until you have data — a wrong number is worse than no number.

### `requires_warmed_models`

Optional. Set when the task assumes a specific model is already loaded into the worker's memory. The router will only place the task on helpers whose `warmed_model_keys` already include every entry in this tuple.

> **Note:** the `bge-m3` examples below are historical. Production embeddings now come from a paid CPU provider (see [`docs/specs/fr-cpu-paid-embeddings-runtime.md`](specs/fr-cpu-paid-embeddings-runtime.md)), so there is no in-process BGE-M3 model holding ~2.5 GB of GPU weights any more. The `requires_warmed_models` / `gpu_required` mechanism still works for any future in-process model; treat the BGE-M3 numbers as an illustration of a heavy GPU task, not the current embedding path.

---

## Worked examples

### Light DB-bound cleanup task (defaults)

```python
@shared_task(name="suggestions.prune_rejected_pairs")
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=256,
)
def prune_rejected_pairs() -> dict:
    """Delete RejectedPair rows older than the configured retention window."""
    ...
```

### CPU-intensive analytics aggregation

```python
@shared_task(bind=True, name="analytics.sync_ga4_telemetry", time_limit=600)
@HelperConstraint(
    cpu_intensive=True,        # Polars aggregation across all GA4 event rows
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=512,
    expected_seconds_p50=300,
)
def sync_ga4_telemetry(self, ...) -> dict:
    ...
```

### GPU-bound embedding audit

```python
@shared_task(bind=True, name="pipeline.embedding_accuracy_audit", time_limit=3900)
@HelperConstraint(
    cpu_intensive=True,
    gpu_required=True,
    storage_writes_to="postgres_main",
    ram_peak_mb=4000,
    expected_seconds_p50=1800,
    requires_warmed_models=("bge-m3-onnx",),
)
def embedding_accuracy_audit(self, ...) -> dict:
    ...
```

---

## What changes after annotating a task

1. **Linter goes quiet.** `.githooks/check-forbidden-patterns.py` stops printing `missing-helper-constraint` for that task.
2. **Coverage test stays green.** `apps.core.tests_helper_constraint_coverage` walks every registered task and asserts `__helper_constraint__` is set; new tasks without the decorator fail CI.
3. **Router can read the metadata.** `apps.core.helper_router.route_task("my_app.my_task")` returns a `HelperNode` (when off-loadable) or `None` (when the task must stay on main).
4. **Behaviour does not change.** The decorator is metadata-only — it stashes a `_ConstraintMeta` on the function and returns it unchanged. No call path, signature, retry policy, or time-limit is altered.
