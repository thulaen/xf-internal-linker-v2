# Pick #03 — Circuit Breaker

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 3 |
| **Canonical name** | Circuit Breaker (Nygard 2007) |
| **Settings prefix** | `circuit_breaker` |
| **Pipeline stage** | Source |
| **Shipped in commit** | `6d925b1` (PR-C, 2026-04-22) |
| **Helper module** | [backend/apps/sources/circuit_breaker.py](../../backend/apps/sources/circuit_breaker.py) — **thin re-export** from [apps/pipeline/services/circuit_breaker.py](../../backend/apps/pipeline/services/circuit_breaker.py) |
| **Tests module** | [backend/apps/sources/tests.py](../../backend/apps/sources/tests.py) — `CircuitBreakerImportTests` + existing pipeline tests |
| **Benchmark module** | [backend/benchmarks/test_bench_circuit_breaker.py](../../backend/benchmarks/test_bench_circuit_breaker.py) (pending G6) |

## 2 · Motivation

When an upstream service (XenForo, WP, GA4) is down, naively calling
it in a loop wastes CPU, consumes rate-limit budget, and extends the
outage's impact on us. Nygard's Circuit Breaker wraps the remote
call with state: after `k` failures in a row, the breaker *opens*
and every subsequent call returns a fast-fail without hitting the
upstream. After a cooldown it briefly goes *half-open* — lets one
test call through — and either closes again on success or re-opens
on failure. This isolates the linker from cascading outages.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Nygard, M. T. (2007). *Release It! Design and Deploy Production-Ready Software.* Pragmatic Bookshelf. ISBN 978-0-9787392-1-8. Chapter 5 "Stability Patterns", pattern: Circuit Breaker. |
| **Open-access link** | <https://pragprog.com/titles/mnee2/release-it-second-edition/> (2nd ed. covers same pattern) |
| **Relevant section(s)** | Chapter 5.1 — three-state machine (closed / open / half-open) and the two transitions' counts / timers |
| **What we faithfully reproduce** | The three-state FSM, failure-count threshold, cooldown timer, half-open single-probe. |
| **What we deliberately diverge on** | We re-use the **pre-existing** `apps/pipeline/services/circuit_breaker.py` (shipped as part of FR-025) rather than shipping a second module. The Source-layer module is a thin re-export so `from apps.sources import circuit_breaker` works in Source-layer call sites without introducing a duplicate. |

## 4 · Input contract

- **`failure_threshold: int`** — consecutive failures to open the
  circuit. Domain `[1, ∞)`.
- **`recovery_timeout_seconds: float`** — cooldown before half-open
  probe. Domain `(0, ∞)`.
- **`expected_exception: type[BaseException]`** — only exceptions of
  this type count toward the failure threshold.

## 5 · Output contract

- **`CircuitBreaker.call(fn, *args, **kwargs)`** — runs `fn`,
  returns its value on success, raises the underlying exception or
  `CircuitBreakerOpen` when the circuit is open.
- **`CircuitBreaker.state`** → `"closed" | "half_open" | "open"`.
- **Idempotent.** Repeated `call` in state `open` returns
  `CircuitBreakerOpen` without invoking `fn`.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `circuit_breaker.enabled` | bool | `true` | Recommended preset policy | No | — | Master toggle |
| `circuit_breaker.failure_threshold` | int | `5` | Nygard 2007 §5.1 recommends 3–10; Google SRE book §22 settles on 5 as the empirically sweetest | Yes | `int(2, 20)` | Lower = trips on flaky upstreams; higher = patient but slow to isolate |
| `circuit_breaker.recovery_timeout_seconds` | float | `30.0` | Nygard 2007 §5.1 — "long enough for transient upstream issues to resolve, short enough to recover quickly" | Yes | `loguniform(5.0, 600.0)` | Time the circuit sits open before a probe |

## 7 · Pseudocode

```
state ∈ {closed, half_open, open}
failure_count: int
opened_at: float | None

function call(fn):
    if state == open:
        if now() - opened_at >= recovery_timeout:
            state = half_open
        else:
            raise CircuitBreakerOpen

    try:
        result = fn()
    except expected_exception:
        failure_count += 1
        if state == half_open or failure_count >= threshold:
            state = open
            opened_at = now()
        raise
    else:
        # success
        if state == half_open:
            state = closed
            failure_count = 0
        else:
            failure_count = 0
        return result
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/sync/services/*` | Wrap XenForo / WP API calls | Fast-fail during outages |
| `apps/analytics/*_client.py` | Wrap GA4 / GSC calls | Same |
| `apps/crawler/services/site_crawler.py` | Wrap per-origin HTTP | Skip sites that are persistently down |

**Wiring status.** The shared `apps/pipeline/services/circuit_breaker.py`
module is already used by `apps/plugins/hooks.py` and
`apps/realtime/consumers.py`. Source-layer call sites (syncers,
analytics) still use ad-hoc try/except. Wiring the Source-layer
re-export is in W2.

## 9 · Scheduled-updates job

None — breaker state lives in memory with the worker process. A
sidecar job to persist breaker snapshots across restarts may be
added later if operators ask for it.

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | < 1 KB per breaker instance | benchmark small |
| Disk | 0 | — |
| CPU time | < 1 µs per call | benchmark small |

## 11 · Tests

| Test name | Invariant verified |
|---|---|
| `test_closed_breaker_passes_through` | Default state is closed |
| `test_n_failures_open_circuit` | FSM transition |
| `test_open_circuit_rejects_without_calling_fn` | Blast-shield semantics |
| `test_recovery_timeout_triggers_half_open` | Timer accounting |
| `test_half_open_success_closes` | Success path |
| `test_half_open_failure_reopens` | Failure path |
| `test_only_expected_exception_counts` | `expected_exception` filter |

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 1 breaker × 1 000 calls | < 5 ms | > 50 ms |
| medium | 20 breakers × 100 000 interleaved calls | < 300 ms | > 3 s |
| large | 200 breakers × 1 000 000 calls | < 5 s | > 30 s |

## 13 · Edge cases & failure modes

- **Clock skew between workers.** Each breaker has its own clock so
  two workers' breakers can disagree about `opened_at`; that's
  correct behaviour since the FSM is per-worker.
- **Non-expected exception raised.** Propagated immediately; does
  not affect breaker state.
- **Half-open concurrent probes.** Two concurrent `call`s in
  half-open both invoke `fn` (acceptable — we favour simplicity
  over strict single-probe; Nygard discusses this as a tolerable
  divergence).

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| #2 Exponential Backoff | Breaks the retry cycle when upstream is firmly down |

| Downstream | Reason |
|---|---|
| Any external-API caller | Breaker fast-fails propagate to job-level error handling |

## 15 · Governance checklist

- [ ] `circuit_breaker.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows
- [ ] `FEATURE-REQUESTS.md` entry
- [ ] `AI-CONTEXT.md` ledger entry
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry
- [x] Helper module (re-export) written (PR-C)
- [ ] Benchmark module written
- [x] Test module written (PR-C)
- [ ] TPE search space declared
- [ ] Source-layer callers wired (W2)
