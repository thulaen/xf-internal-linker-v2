# FR-020 - Runtime Model Registry, Hot Swap, and Helper Dispatch

## Summary

FR-020 owns model lifecycle, champion/candidate runtime state, safe hot swap, helper-aware placements, and the shared runtime summaries shown in Settings, Mission Critical, and System Health.

The purpose is operational, not ranking-semantic:

- keep `BAAI/bge-m3` as the seeded default champion without hardcoding it permanently;
- let stronger PCs or helper nodes register, warm, promote, drain, resume, and safely delete model placements;
- route batch and offline work using CPU, RAM, optional GPU, and optional native-kernel capability without creating a second helper or pause system.

## Academic Source

Primary sources:

- Ghodsi et al. (2011), "Dominant Resource Fairness: Fair Allocation of Multiple Resource Types", NSDI 2011.
- Schwarzkopf et al. (2013), "Omega: flexible, scalable schedulers for large compute clusters", EuroSys 2013.
- Verma et al. (2015), "Large-scale cluster management at Google with Borg", EuroSys 2015.
- Isard et al. (2007), "Dryad: distributed data-parallel programs from sequential building blocks", EuroSys 2007.

Repo-safe takeaways:

- multi-resource scheduling should consider the dominant resource, not CPU alone;
- in-flight work must keep its assigned runtime identity while new work can move to a promoted version;
- distributed batch work needs idempotent envelopes and resumable checkpoints so helper loss does not corrupt progress.

## Formula

### 1. Usable executor capacity

For helper or primary executor `n`:

```text
usable_cpu_n      = cpu_cores_n * cpu_cap_pct_n / 100
usable_ram_n      = ram_gb_n * ram_cap_pct_n / 100
usable_gpu_vram_n = gpu_vram_gb_n * gpu_cap_pct_n / 100
```

If no GPU exists, `usable_gpu_vram_n = 0`.

### 2. Task demand vector

For task lane `j`:

```text
r_j = (demand_cpu_j, demand_ram_j, demand_gpu_vram_j)
```

### 3. Dominant share

```text
cpu_share_jn = demand_cpu_j / max(usable_cpu_n, eps)
ram_share_jn = demand_ram_j / max(usable_ram_n, eps)
gpu_share_jn = demand_gpu_vram_j / max(usable_gpu_vram_n, eps)

dominant_share_jn = max(cpu_share_jn, ram_share_jn, gpu_share_jn)
```

This is the DRF core rule from Ghodsi et al. 2011.

### 4. Live pressure

```text
slot_pressure_n = active_jobs_n / max(max_concurrency_n, 1)
cpu_pressure_n  = cpu_pct_n / max(cpu_cap_pct_n, 1)
ram_pressure_n  = ram_pct_n / max(ram_cap_pct_n, 1)
gpu_pressure_n  = max(gpu_util_pct_n / 100, gpu_vram_used_n / gpu_vram_total_n)

effective_load_n = min(1, max(slot_pressure_n, cpu_pressure_n, ram_pressure_n, gpu_pressure_n))
```

### 5. Routing score

Eligible executors satisfy:

- lane capability match;
- `accepting_work = true`;
- helper heartbeat not stale or offline;
- required model placement warmed and healthy when applicable;
- required native kernels healthy when applicable;
- optional network RTT under lane threshold.

Select:

```text
route_score_jn = max(dominant_share_jn, effective_load_n)
winner_j       = argmin_n route_score_jn
```

### 6. Hot-swap safety rule

Let `m_old` be the current champion and `m_new` the candidate.

Promotion is allowed only when:

```text
status(m_new) = ready
AND health(m_new) = pass
AND compatibility(m_old, m_new) in {compatible, dimension_change_requires_backfill}
```

If dimensions differ:

```text
compatibility = dimension_change_requires_backfill
```

Then:

- new jobs bind to `m_new`;
- in-flight jobs keep `m_old`;
- a resumable backfill plan records progress until old artifacts can be drained and retired.

## Code Variable Mapping

- `usable_cpu`, `usable_ram`, `usable_gpu_vram`: `backend/apps/core/helper_router.py`
- `slot_pressure`, `cpu_pressure`, `ram_pressure`, `gpu_pressure`, `effective_load`: `backend/apps/core/helper_router.py`, `backend/apps/core/runtime_registry.py`
- `RuntimeModelRegistry`, `RuntimeModelPlacement`, `RuntimeModelBackfillPlan`, `HardwareCapabilitySnapshot`, `RuntimeAuditLog`: `backend/apps/core/runtime_models.py`
- runtime actions and guards: `backend/apps/core/views_runtime_registry.py`
- shared operator summary payload: `backend/apps/core/runtime_registry.py`

## Architecture Lane

- runtime lifecycle ownership: `FR-020`
- pause/resume/drain ownership: existing master pause and resumable job flow
- helper registration and liveness: existing helper registry plus heartbeat
- operator visibility: existing Mission Critical and System Health surfaces

## Real-World Constraints

- `BAAI/bge-m3` is the seeded default champion, but runtime code must treat it as replaceable.
- The control-plane overhead must stay below `100 MB RAM` and `50 MB disk`, excluding actual model artifacts.
- Live synchronous UI-time ranking stays local in v1.
- Helper execution in v1 is for batch and offline work only.
- Safe delete must block champion, active candidate, warming, draining, active-job-pinned, resumable-job-pinned, and active-backfill-pinned placements.
- Hardware snapshots and audit logs must be retention-bounded so repeated refreshes do not bloat the database.

## Researched Defaults

- default champion: `BAAI/bge-m3`
- default dimension: `1024`
- default batch size: `32`
- recommended profiles:
  - safe: batch `16`, concurrency `1`
  - balanced: batch `32`, concurrency `2`
  - high: batch `64`, concurrency `4`
- stale helper threshold: `> 120 s`
- offline helper threshold: `> 300 s`

These defaults are conservative operational starting points, not ranking weights.

## Diagnostics

Runtime surfaces must expose:

- active champion model;
- candidate model and status;
- device target and dimension;
- backfill status and progress;
- reclaimable disk from retired placements;
- helper counts by `online`, `busy`, `stale`, `offline`;
- aggregate RAM pressure;
- busiest helper and effective load;
- recent runtime audit log.

## Edge Cases

- no runtime registry rows: infer the seeded champion from current embedding setting and mark it as inferred;
- no helpers: route locally and keep helper health optional;
- helper heartbeat stale or offline: exclude from scheduling;
- CPU-only helper: eligible for CPU-safe and RAM-heavy lanes only;
- no GPU placement warmed: GPU-required lane stays on a qualifying executor only;
- dimension mismatch on promote: allow champion switch only with a backfill plan record;
- delete requested while jobs or backfills may still reference the placement: reject deletion.

## Scope Boundary vs Existing Signals

FR-020 does not define ranking weights or ranking math.

It must not:

- replace the current additive ranker;
- invent a second pause system;
- create a second helper registry;
- create a shadow Mission Critical or System Health API;
- change the semantics of FR-006 through FR-019 scoring signals.

## Benchmark

Operational targets:

- helper routing decision: `< 5 ms` for `<= 32` helpers
- runtime summary response: `< 150 ms` from warm database state
- hot-swap action write path: `< 100 ms` excluding actual model download
- control-plane retention:
  - runtime audit log bounded to latest `1000` rows
  - hardware snapshots bounded to latest `50` primary snapshots

## Pending

Explicitly deferred:

- live remote ranking RPC;
- automatic helper token rotation UI;
- remote artifact transport and checksum validation for real model binaries;
- cross-cluster scheduling beyond primary + helper topology.
