# Performance & Resource Management

> **This is a living document.** Every AI agent (Claude, Codex, Gemini) must read it before touching scheduled tasks, concurrency, resource usage, or GPU work. It is cross-referenced from `CLAUDE.md` and `AGENTS.md`.

## 1. Purpose & Governance

This document defines the resource constraints, scheduling rules, and performance mandates for the XF Internal Linker. It is **mutable** — AIs are expected to suggest improvements backed by evidence.

**Rules for changing this document:**

- Every optimisation claim must cite an academic paper, patent, RFC, or established systems engineering principle. No snake oil, no fugazi, no unsubstantiated claims.
- Before suggesting a change, verify the current hardware profile (Section 2) by reading system specs. The framework is stable; the numbers come from the hardware.
- Performance findings must be filed in the Report Registry (`docs/reports/REPORT-REGISTRY.md`):
  - **MEDIUM**: 2–5× slower than expected
  - **HIGH**: >5× slower than expected
  - **CRITICAL**: incorrect results from an optimisation
- Opinions are welcome. Guesses are not.

---

## 2. Current Hardware Profile

> **Mutable section.** If you detect hardware changes (new GPU, RAM upgrade, new helper node), update this section and file a Report Registry entry noting the change.

### Primary Node

| Spec | Value | Last verified |
|------|-------|---------------|
| Machine | MSI Cyborg 15 A12UDX (laptop) | 2026-04-13 |
| CPU | Intel Core i5-12450H, 8 cores / 12 threads, ~2.0 GHz base | 2026-04-13 |
| RAM | 16 GB (2 × 8 GB DDR4) | 2026-04-13 |
| GPU | NVIDIA GeForce RTX 3050 6 GB Laptop GPU | 2026-04-13 |
| GPU Driver | 595.79 | 2026-04-13 |
| OS | Windows 11 Home, Build 26200 | 2026-04-13 |
| Docker Runtime | Docker Desktop (WSL 2 backend) | 2026-04-13 |

**How to re-verify:**
```bash
systeminfo | head -20
nvidia-smi --query-gpu=name,memory.total,temperature.gpu,driver_version --format=csv,noheader
wmic memorychip get capacity
wmic cpu get name,numberofcores,numberoflogicalprocessors
```

### Helper Nodes

> Populated as nodes are registered via Settings > Helpers tab.

| Name | CPU | RAM | GPU VRAM | Role | Allowed Queues | Status |
|------|-----|-----|----------|------|----------------|--------|
| *(none registered)* | — | — | — | — | — | — |

Each helper node reports its own capabilities via `POST /api/settings/helpers/{id}/heartbeat/`. Safety defaults: 60% CPU cap, 60% RAM cap per helper.

---

## 3. Container Memory Budget

> **Mutable table.** When total RAM changes, redistribute headroom proportionally.
>
> Bin-packing principle: pack workloads to maximise utilisation while preserving a headroom buffer for spikes. See [Verma et al. 2015, "Large-scale cluster management at Google with Borg", EuroSys '15] for the theory behind container sizing with headroom margins.

| Service | Memory Limit | Purpose | Scaling Notes |
|---------|-------------|---------|---------------|
| postgres | 2 GB | PostgreSQL 17 + pgvector | Grows with index count. Monitor `shared_buffers`. |
| redis | 640 MB | Celery broker + cache + channels | Steady-state. Increase only if cache hit rate drops below 90%. |
| backend | 2.56 GB | Django + Daphne ASGI (2 workers) | Scales with concurrent HTTP connections. |
| celery-worker-default | 1.5 GB | Light/default-queue background work | Operator-tunable concurrency (1-6). Restart required after changes. |
| celery-worker-pipeline | 2 GB | Pipeline + embeddings queues | Fixed at concurrency 1 because the FAISS index is process-local. |
| celery-beat | 128 MB | Scheduler only | Minimal. No scaling needed. |
| nginx | 128 MB | Reverse proxy + static files | Minimal. |
| frontend | 1 GB | Angular dev server (dev profile only) | Only when `--profile dev` is active. |
| glitchtip | 256 MB × 2 | Error tracking (debug profile only) | Only when `--profile debug` is active. |

**Current total (default profile):** ~9.0 GB committed to Docker.

**Full equation:**
```
Docker (~9.0 GB) + Chrome (~200 MB/tab x 15 tabs = 3 GB) + Windows kernel (~2.5 GB) ~= 14.5 GB
Headroom: ~1.5 GB
```

---

## 4. Task Weight Classes & Queue Contract

> **Golden rule: Never run two Heavy tasks simultaneously.**
>
> On constrained hardware, serial execution of heavy tasks outperforms parallel execution due to memory pressure, cache thrashing, and swap overhead. See [Dean & Barroso 2013, "The Tail at Scale", CACM 56(2)] for why latency variability increases under resource contention.

### Weight Class Definitions

| Class | Peak Memory | Concurrency Rule |
|-------|------------|------------------|
| **Heavy** | >1 GB peak | Max 1 at a time. Second Heavy waits in FIFO queue. |
| **Medium** | 200 MB – 1 GB | Max 1 at a time. Same FIFO rule as Heavy. |
| **Light** | <200 MB | No lock required. Runs freely. |

### Task Classification

| Task | Threshold | Priority | Weight | Queue |
|------|-----------|----------|--------|-------|
| `nightly-xenforo-sync` | 26 h | 10 | Heavy | pipeline |
| `monthly-xenforo-full-sync` | 35 d | 20 | Heavy | pipeline |
| `monthly-wordpress-full-sync` | 35 d | 25 | Heavy | pipeline |
| `monthly-cs-weight-tune` | 35 d | 90 | Medium | pipeline |
| `weekly-session-cooccurrence` | 8 d | 70 | Medium | pipeline |
| `nightly-data-retention` | 26 h | 50 | Light | default |
| `cleanup-stuck-sync-jobs` | 26 h | 55 | Light | default |
| `nightly-benchmarks` | 26 h | 60 | Light | default |
| `weekly-reviewer-scorecard` | 8 d | 75 | Light | default |
| `weekly-weight-rollback-check` | 8 d | 80 | Light | default |
| `12-week-prune-stale-data` | 13 w | 95 | Light | default |
| `crawler-auto-prune` | 5 w | 96 | Light | default |
| `check_silent_failure` | 26 h | 40 | Light | default |
| `check_zero_suggestion_run` | 26 h | 42 | Light | default |
| `check_post_link_regression` | 26 h | 44 | Light | default |
| `check_autotune_status` | 26 h | 46 | Light | default |

**Not eligible for catch-up** (too frequent or stateless): `periodic-system-health-check`, `refresh-faiss-index`, `pulse-heartbeat`, `watchdog-check`, `daily-gsc-spike-check`.

### Queue Contract

| Queue | Accepts | Notes |
|-------|---------|-------|
| `pipeline` | Heavy + Medium tasks | Runs on `celery-worker-pipeline`, fixed at concurrency 1 and lock-guarded. |
| `embeddings` | Heavy embedding work | Shares `celery-worker-pipeline` and stays at concurrency 1 for FAISS correctness. |
| `default` | Light tasks | Runs on `celery-worker-default`, with operator-tunable concurrency from `system.default_queue_concurrency`. |

---

## 5. Schedule Contract

> Heavy tasks run in the **13:00–15:00 UTC afternoon window** so they actually run on a laptop that's powered down overnight. This is a trade-off: heavy jobs may contend with Chrome + development work during the afternoon, but every task is guaranteed to fire at its scheduled slot. Priority-ordered dispatch follows [Schwarzkopf et al. 2013, "Omega: flexible, scalable schedulers for large compute clusters", EuroSys '13]. (History: the window was 21:00–22:30 UTC before 2026-04-19 — moved into the afternoon after the operator confirmed their laptop is typically off between 23:00 and 07:00 local.)

### Afternoon Window (13:00–15:00 UTC)

All heavy and medium scheduled tasks are concentrated here. 13:00–15:00 UTC maps to 14:00–16:00 BST in summer and 13:00–15:00 GMT in winter — both inside the operator's 14:00–17:00 local afternoon window. If the laptop was off during the window (e.g. power loss, travel), the catch-up system (see `backend/config/catchup.py`) dispatches overdue tasks on next boot in priority order with a 30-second stagger between Heavy tasks.

### Catch-Up Rules

1. On worker startup, query `PeriodicTask.last_run_at` for each registered task.
2. If `now - last_run_at > threshold`, mark as overdue.
3. Dispatch in priority order (lower number = higher priority).
4. 30-second stagger between Heavy tasks to avoid memory spikes.
5. Respect task locks — never dispatch if a Heavy lock is held.

---

## 6. GPU Self-Limiting

> **90 °C is the configurable ceiling.** The app pauses GPU work when the chip reaches it and resumes once it cools to 80 °C. This is enforced in software because the OEM locks nvidia-smi power management on this laptop. The ceiling is tunable via `GPU_TEMP_CEILING_C` / `GPU_TEMP_RESUME_C` environment variables. History: 76 °C / 68 °C → 86 °C / 78 °C (2026-04-15, ISS-015) → 90 °C / 80 °C (same day, operator preference; ISS-019). Note that 90 °C leaves only ~3 °C of headroom before NVIDIA's ~93 °C driver throttle, so transient throttling during sustained runs is possible by design.
>
> Application-level thermal management is effective when OS-level controls are unavailable. See [Park et al. 2018, "Reducing GPU Energy in HPC/DNN Training via Efficient Tensor-Core Usage", arXiv:1803.04014] for the principle of software-controlled GPU power management.

### Three-Layer Protection

| Layer | Mechanism | Threshold |
|-------|-----------|-----------|
| 1. Temperature ceiling | `pynvml` temp check before each GPU batch | Pause at ≥90°C, resume at ≤80°C |
| 2. VRAM fraction | `torch.cuda.set_per_process_memory_fraction()` | Mode-dependent (see below) |
| 3. Batch size cap | `EMBEDDING_BATCH_SIZE` setting | 32 (default) |

### Mode-Dependent VRAM Allocation

These percentages are **relative to detected VRAM** — they scale automatically with GPU upgrades.

| Performance Mode | VRAM Fraction | On RTX 3050 6 GB | Rationale |
|-----------------|---------------|-------------------|-----------|
| Safe | 25% | 1.5 GB | Minimal GPU use. Chrome + dev work take priority. |
| Balanced | 25% | 1.5 GB | Same as Safe — daytime work is not GPU-intensive. |
| High Performance | 80% | 4.8 GB | Evening/overnight. User has closed Chrome. |

### FAISS Pool Cap

`gpu_resources.setTempMemory(512 * 1024 * 1024)` — 512 MB. Adjustable per helper node based on available VRAM.

### Why Software Limits

The NVIDIA driver on this MSI laptop does not expose power management controls via `nvidia-smi`. The `nvidia-smi -pl` command returns "N/A" for power limits. Software-based thermal management is the only available control surface. The three-layer protection above is equivalent to hardware throttling but triggered earlier (90°C vs NVIDIA's default ~93°C thermal throttle).

---

## 7. C++ First Rule

> If a C++ extension exists for the operation, call it. Python is the fallback and reference implementation only.
>
> Hot-path speedups dominate overall throughput by [Amdahl's Law, 1967]: if a hot path accounts for 80% of execution time and C++ provides a 10× speedup, overall throughput improves by ~4.5×. Python fallback exists for correctness verification and environments where C++ compilation fails.

- See `backend/PYTHON-RULES.md` §19 for the Python side of this mandate.
- See `backend/extensions/CPP-RULES.md` §25 for the C++ side.
- The `ext_loader.py` service handles fallback logic. It logs a warning when falling back to Python.

---

## 8. Benchmark Mandate

> Every hot-path function must have a benchmark at 3 input sizes before merge. No exceptions.
>
> Single-point benchmarks are misleading — they hide algorithmic complexity. A function that appears fast at n=10 may be O(n²) and unacceptable at n=10,000. Multi-size benchmarks reveal the true scaling behaviour. See [Fleming & Wallace 1986, "How Not to Lie with Statistics: The Correct Way to Summarize Benchmark Results", CACM 29(3)].

- **C++**: `backend/extensions/benchmarks/bench_*.cpp` using Google Benchmark. Sizes: small / medium / large.
- **Python**: `backend/benchmarks/test_bench_*.py` using pytest-benchmark. Sizes: small / medium / large.
- Points to the benchmark rule in `CLAUDE.md`.

---

## 9. Running Alongside Chrome

> **Mutable section.** Update when hardware changes or Docker profiles are adjusted.

### Memory Formula

```
Total = Docker committed + Chrome (est. 200 MB/tab × N tabs) + Windows kernel (~2.5 GB)
Headroom = Total RAM - Total
```

### Current Baseline

| Component | Memory | Notes |
|-----------|--------|-------|
| Docker (default profile) | ~9.0 GB | 7 services |
| Chrome (15 tabs) | ~3.0 GB | Estimated. Varies by page complexity. |
| Windows 11 kernel | ~2.5 GB | Includes WSL 2 overhead. |
| **Total** | **~14.5 GB** | |
| **Headroom** | **~1.5 GB** | Tight. Triggers swap if Chrome is heavy. |

### With Helper Nodes

When a helper node handles Heavy GPU work, the primary node's `celery-worker-pipeline` can reduce its memory limit, freeing headroom for more Chrome tabs. Recalculate this formula when adding a helper.

---

## 10. Multi-Node Scaling

> Forward-looking section. Designed for growth as helper nodes are added.
>
> Checkpoint-based fault tolerance follows [Isard et al. 2007, "Dryad: Distributed Data-Parallel Programs from Sequential Building Blocks", EuroSys '07]: work is chunked so any node can resume from the last central checkpoint after a helper loss.

### Architecture

- **Central coordinator** (primary node) owns: checkpoints, manifests, leases, health state, final status.
- **Helper nodes** keep: only disposable local scratch. All durable state lives on the coordinator.
- Work is chunked so any node can resume from the last central checkpoint after a helper loss.

### Scaling Rules

1. GPU-only embedding jobs are assigned only to nodes that pass warmup + CUDA check.
2. CPU-bound work (spaCy, text cleaning) can be distributed to any healthy helper.
3. Each helper respects its own safety caps (60% CPU, 60% RAM by default).
4. The coordinator never assumes a helper is alive — heartbeat timeout → work returns to resumable state.

---

## 11. How to Add a New Scheduled Task

Three steps:

1. **Register in `backend/config/settings/celery_schedules.py`** — add the Beat schedule entry with the appropriate cron expression in the 21:00–22:30 UTC window (for Heavy/Medium) or at any time (for Light).
2. **Register in `backend/config/catchup_registry.py`** — add the task to the catch-up registry with its threshold, priority, queue, and weight class.
3. **Assign weight class in this document** — add a row to the Task Classification table in Section 4.

---

## 12. Optimisation Opportunities Log

> Running list of potential improvements spotted by any AI during other work. **Never implement without user approval.** Always cite evidence.

| # | Description | Estimated Gain | Evidence / Citation | Status |
|---|-------------|---------------|---------------------|--------|
| *(none yet)* | — | — | — | — |

**How to add an entry:** Describe the opportunity, estimate the gain (e.g., "3× speedup on embedding batches"), cite the evidence (paper, benchmark result, or profiling data), and set status to `proposed`. The user will review and set status to `accepted`, `rejected`, or `implemented`.

---

## 13. Performance Verification in Production Mode — Mandatory Rule

> **Every AI agent (Claude, Codex, Gemini, and any future model) must read this section before measuring, profiling, benchmarking, or claiming to "fix" a slowness report.**

### The rule

**Performance work MUST run against the production-mode compose stack.** Dev-mode behaviour (`ng serve`, uvicorn `--reload`, Django `DEBUG=True`, Celery `--loglevel=info`, `CHOKIDAR_USEPOLLING=1`) adds per-request overhead at every layer. Numbers taken from a dev stack are misleading — they will either invent problems that do not exist in prod, or hide problems that do.

### What "production mode" means in this repo

The canonical boot command is:

```bash
docker compose --env-file .env up --build
```

That is the **only** boot command. The dual-mode dev/prod compose split (with `-f` overrides) was retired on 2026-04-22 — see `docs/DELETED-FEATURES.md`. Every `docker compose up` now launches the stack with:

- `DJANGO_SETTINGS_MODULE=config.settings.production` and `DJANGO_DEBUG=False` on backend + all Celery services.
- Uvicorn **without** `--reload` and with 4 workers.
- Celery at `--loglevel=warning`.
- Angular built once with `ng build --configuration=production` (AOT, minified, hashed, no source maps) by the one-shot `frontend-build` service, then served as static files from the `frontend_dist` volume.
- Nginx using `nginx/nginx.prod.conf` with long-cache headers on hashed assets, gzip on, API/WS/admin proxies unchanged.
- GlitchTip behind `--profile debug` (opt-in only).

### When this rule applies

- Any "feels slow / sluggish" investigation.
- Any benchmark, Performance-trace, or Lighthouse run whose numbers are used to justify a code change.
- Any PR that claims a perf improvement — the "after" numbers must come from the prod stack.
- Any Report-Registry finding tagged with severity MEDIUM/HIGH/CRITICAL under §1 (2–5× / >5× / incorrect results).

### Test / unit-runner runs

- Unit/integration test runs (`ng test`, `pytest`) bypass the stack entirely — they use their own SQLite test settings (`config.settings.test`) and don't need docker.
- UI layout work should still run through the prod stack; rebuild the `frontend-build` image (`docker compose build frontend-build`) and bounce `nginx` to see your change.

### Reporting requirements

Any performance claim posted to the user or written into the Report Registry must state **how the numbers were produced**. Examples:

- ✅ "Dashboard idle scripting time dropped from 34% to 7% (prod stack, commit abc123)."
- ✅ "Benchmark hit 250 ms p95 on the prod stack after rebuilding `frontend-build` and `backend`."
- ❌ "The dashboard feels faster now." (No numbers, no commit reference.)

### Cross-references

- `CLAUDE.md` — top-level rule reminder (Docker Rules section).
- `AGENTS.md` § Code Quality Mandate > Performance — same rule, worded for all agents.
- `AI-CONTEXT.md` Session Gate — prod-stack verification is a MUST-READ for any performance session.
- `docker-compose.yml` — the single canonical compose stack (no overrides).
- `backend/config/settings/production.py` — Django prod settings (HTTPS-hardening flags are env-driven so a local run over plain HTTP still works).
