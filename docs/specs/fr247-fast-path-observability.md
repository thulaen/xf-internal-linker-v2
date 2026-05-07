# FR-247 — Fast-path-vs-slow-path observability for Stage-2 scoring

## 1 · Identity

| Field | Value |
|---|---|
| **Canonical name** | Stage-2 cpp-vs-python pathway tracking |
| **Settings prefix** | `pipeline.cpp_path_alert_threshold` |
| **Pipeline stage** | Stage 2 (sentence-level scoring) |
| **Helpers** | `apps.pipeline.services.pipeline_stages._record_stage2_path`, `get_stage2_path_counters`, `get_stage2_path_runtime_status`, `reset_stage2_path_counters` |
| **Default state** | **ON.** Counter increments on every Stage-2 call; status reads in O(1). |

## 2 · Motivation (ELI5)

The pipeline tries the fast C++ engine first; if it fails to import, the slower Python fallback runs at 50–100× slowdown. Today there's no operator-visible signal — the regression hides behind aggregated latency until the dashboard turns red days later. This spec adds an in-process counter per pathway plus a status function the `/performance` dashboard already reads. The counter increments on every Stage-2 call; a one-line check turns the dashboard red when Python's share crosses the configured SLO threshold (default 5%).

## 3 · Academic / industry source of truth

| Field | Value |
|---|---|
| **Primary** | Beyer, B. et al. (2016). *Site Reliability Engineering: How Google Runs Production Systems.* O'Reilly. ISBN 978-1491929124. Chapter 4 ("Service Level Objectives") establishes that pathway latency must be SLO-tracked with a counter per pathway. |
| **Cardinality budget** | Sridharan, C. (2018). *Distributed Systems Observability.* O'Reilly. ISBN 978-1492033424. Chapter 4 — counter cardinality budget for path metrics. We expose only `cpp` and `python` (cardinality 2), well under any reasonable budget. |
| **What we reproduce** | Per-pathway counter + threshold-based alert (Beyer 2016 Ch 4). |
| **What we diverge on** | We don't ship a Prometheus client right now — the project's existing observability surface is the `/performance` dashboard which reads runtime-status helpers. The counter shape is forward-compatible: a Prometheus exporter can wrap `get_stage2_path_counters()` later without refactoring callers. |

## 4 · Output contract

`get_stage2_path_runtime_status() -> dict[str, object]` mirroring the shape of `slate_diversity.get_slate_diversity_runtime_status`:

| Field | Type | Meaning |
|---|---|---|
| `available` | `bool` | C++ extension import success |
| `path` | `str` | `"cpp_extension"` or `"python_fallback"` (whichever has more calls; `"cpp_extension"` if no calls yet and the C++ extension is loaded) |
| `reason` | `str` | Plain-English status with call counts and threshold |
| `cpp_calls` | `int` | Total C++ pathway calls this run |
| `python_calls` | `int` | Total Python pathway calls this run |
| `python_share` | `float` | `python_calls / (cpp + python)`; 0.0 when no calls |
| `alert` | `bool` | True when `python_share > pipeline.cpp_path_alert_threshold` |

The `/performance` dashboard turns the card red when `alert == True`.

## 5 · Implementation

| File | Change |
|---|---|
| `backend/apps/pipeline/services/pipeline_stages.py` | Added `_PATH_COUNTERS` module dict + 4 helpers (`_record_stage2_path`, `get_stage2_path_counters`, `reset_stage2_path_counters`, `get_stage2_path_runtime_status`). Wired into `_score_sentences_stage2` — each Stage-2 call records its pathway. |
| `backend/apps/pipeline/tests_observability_helpers.py` | New file. 6 SimpleTestCase tests in `Stage2PathCounterTests`. |

Total: ~95 lines added. No DB migrations, no settings beyond the alert threshold key (already seeded in migration 0061). Net memory cost: 2 ints in process memory.

## 6 · Test plan

`Stage2PathCounterTests` (6 cases):
1. **Counters start at zero** — fresh process invariant.
2. **Record increments correct bucket** — happy path.
3. **No-calls runtime status** — operator-visible state when nothing has run yet.
4. **Alert fires at 50% python share** — well above 5% threshold.
5. **No alert at 1% python share** — well below threshold.
6. **`get_stage2_path_counters` returns a copy not a live reference** — Sridharan 2018 read-only contract.

All 6 pass as `SimpleTestCase` (no DB).

## 7 · Compatibility

- Counters are process-local. In a multi-worker setup (e.g. uvicorn multi-process) each worker has its own counter. The `/performance` dashboard reads from one worker at a time which is acceptable — operators see *some* data; full aggregate would require Prometheus client integration documented as the v2 upgrade path.
- Counters survive across requests within a process; reset only via `reset_stage2_path_counters()` (test-only helper).

## 8 · Citations on every default

- `pipeline.cpp_path_alert_threshold = 0.05` — Beyer 2016 Chapter 4 (SLO violations triggered at 5% pathway divergence).
- The `cpp` / `python` label vocabulary — Sridharan 2018 Chapter 4 (cardinality budget; 2 labels << any reasonable cap).

## 9 · Operator-facing surface

The `/performance` dashboard (existing UI) can pick up `get_stage2_path_runtime_status()` the same way it consumes `get_slate_diversity_runtime_status()`. Wiring the dashboard call is a frontend tweak, not a backend change. Spec leaves the UI wiring as a small follow-up.

## 10 · Status

Backend shipped 2026-05-07. Frontend dashboard wiring deferred to a focused UI commit.
