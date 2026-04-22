# Pick #02 — Exponential Backoff with Full Jitter

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 2 |
| **Canonical name** | Exponential Backoff + Full Jitter (Metcalfe-Boggs 1976; AWS 2015) |
| **Settings prefix** | `backoff` |
| **Pipeline stage** | Source |
| **Shipped in commit** | `6d925b1` (PR-C, 2026-04-22) |
| **Helper module** | [backend/apps/sources/backoff.py](../../backend/apps/sources/backoff.py) |
| **Tests module** | [backend/apps/sources/tests.py](../../backend/apps/sources/tests.py) — `BackoffTests` |
| **Benchmark module** | [backend/benchmarks/test_bench_backoff.py](../../backend/benchmarks/test_bench_backoff.py) (pending G6) |

## 2 · Motivation

A transient failure from an external API (network blip, remote
restart, 503) is usually healed by waiting a moment and retrying.
The simplest retry — "wait 1 s" — turns into a synchronised thundering
herd when a thousand clients all fail at once and wait the same 1 s.
Exponential backoff doubles the wait each retry; adding **full
jitter** randomises it so the herd disperses. AWS Architecture Blog
2015 shows full jitter (a uniform random `[0, cap]`) beats equal
jitter and "decorrelated" jitter in aggregate completion time.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Metcalfe, R. M. & Boggs, D. R. (1976). "Ethernet: Distributed packet switching for local computer networks." *Communications of the ACM* 19(7): 395-404. Brooker, M. (2015). "Exponential Backoff and Jitter." AWS Architecture Blog. |
| **Open-access link** | <https://dl.acm.org/doi/10.1145/360248.360253> (Metcalfe-Boggs); <https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/> (Brooker) |
| **Relevant section(s)** | Metcalfe-Boggs §III — binary exponential backoff on collision; Brooker — *Full Jitter* strategy, equation `sleep = random(0, min(cap, base * 2^attempt))` |
| **What we faithfully reproduce** | AWS Full-Jitter formula. `sleep = random_uniform(0, min(cap, base * 2^attempt))`. |
| **What we deliberately diverge on** | We expose both a generator (`retry_context`) and a decorator (`retry`) so callers can pick the idiom that fits their call site. The paper just gives the scalar formula. |

## 4 · Input contract

- **`base_delay_seconds: float`** — first sleep magnitude. Domain
  `(0, ∞)`. Typical: `0.5` s.
- **`max_delay_seconds: float`** — cap on any single sleep. Domain
  `(0, ∞)`. Typical: `60.0` s.
- **`max_attempts: int`** — total retries including the initial one.
  Domain `[1, ∞)`. Typical: `5`.
- **`retry_on: tuple[type[BaseException], ...]`** — exception types
  that trigger a retry. Others propagate immediately.
- **`rng: random.Random | None`** — injected RNG for testing; defaults
  to a thread-local `random.Random()`.

**Empty-input.** `max_attempts=1` degenerates to "try once, no
retry" — valid, not an error.

## 5 · Output contract

- **Decorator `@retry(...)`** returns the underlying callable's return
  value on success. Raises the *last* exception on final-attempt
  failure.
- **`retry_context(...)` generator** yields `(attempt, next_sleep)`
  tuples so callers can log / increment metrics between retries.
- **`full_jitter_delay(attempt, base, cap, rng)`** → `float` in
  `[0, min(cap, base * 2^attempt)]`.

**Invariants.**

- Every `full_jitter_delay` output is in `[0, cap]`.
- Mean wait across many invocations at attempt `k` equals
  `0.5 * min(cap, base * 2^k)`.
- Delivered exceptions are the final attempt's — not the first.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `backoff.enabled` | bool | `true` | Recommended preset policy | No | — | Turns all retries off (forces immediate failure) |
| `backoff.base_delay_seconds` | float | `0.5` | AWS Architecture Blog 2015 reference implementation | Yes | `loguniform(0.05, 2.0)` | Raises floor on retry wait; higher = gentler on upstream |
| `backoff.max_delay_seconds` | float | `60.0` | AWS Architecture Blog 2015 reference implementation; matches Google's internal libraries | Yes | `loguniform(5.0, 600.0)` | Ceiling on single wait; critical when upstream is down for tens of minutes |
| `backoff.max_attempts` | int | `5` | Google SRE book §22 — 5 retries covers 99th-percentile transient outage duration | Yes | `int(1, 10)` | Total attempt budget |

**Why `enabled` is `TPE-tuned = No`.** It's a toggle, not a scalar.
TPE wouldn't converge on a binary knob when NDCG is near-flat in
both states.

## 7 · Pseudocode

```
function full_jitter_delay(attempt, base, cap, rng):
    # attempt is 0-based: 0 for the first retry after the initial call
    exp_cap = min(cap, base * 2 ** attempt)
    return rng.uniform(0.0, exp_cap)

function retry(fn, base, cap, max_attempts, retry_on, rng):
    last_exc = None
    for attempt in 0..max_attempts-1:
        try:
            return fn()
        except retry_on as exc:
            last_exc = exc
            if attempt == max_attempts - 1:
                raise
            time.sleep(full_jitter_delay(attempt, base, cap, rng))
    raise last_exc  # unreachable, but keeps static analysis happy
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/sync/services/*` | `retry_on=(requests.exceptions.ConnectionError, requests.exceptions.HTTPError)` | Propagate final failure to the scheduler |
| `apps/analytics/{ga4,gsc}_client.py` | Same | Same |
| `apps/crawler/services/site_crawler.py` | `retry_on=(httpx.RequestError,)` | Skip page on final failure |

**Wiring status.** Not yet imported by production call sites. Existing
syncers retry with bespoke `time.sleep(2 ** attempt)` loops that
**do not include jitter** — replacing those is W2's job.

## 9 · Scheduled-updates job

None — transient-failure backoff is a per-call concern, not a
scheduled refresh.

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM (peak) | < 1 KB per in-flight retry | — |
| Disk | 0 | — |
| CPU time | < 1 µs (pure arithmetic) | benchmark small |

## 11 · Tests

| Test name | Invariant verified |
|---|---|
| `test_full_jitter_in_range` | §5 bounds |
| `test_mean_delay_scales_exponentially` | Monte Carlo mean matches `0.5*cap` within 5 % |
| `test_decorator_succeeds_after_n_retries` | Retry count accounting |
| `test_decorator_raises_final_exception` | Final-failure behaviour |
| `test_non_listed_exception_propagates_immediately` | `retry_on` filter |
| `test_zero_max_attempts_rejected` | Input validation |
| `test_injected_rng_deterministic` | Tests can control timing |

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 10 attempts × 1 000 delay draws | < 1 ms | > 10 ms |
| medium | 10 attempts × 100 000 delay draws | < 30 ms | > 300 ms |
| large | 10 attempts × 10 000 000 delay draws | < 3 s | > 30 s |

## 13 · Edge cases & failure modes

- **`base * 2^attempt` overflow** — prevented by the `min(cap, …)`
  clamp. Documented in-code.
- **Callable raises a type outside `retry_on`** — propagated
  immediately; no retry, no sleep.
- **Injected RNG returns a constant** — the helper still works (used
  in deterministic tests); Monte Carlo invariants are the only
  behaviour that assumes a real RNG.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| #1 Token Bucket | Rate-limit refusals become retries handled by this pick |

| Downstream | Reason |
|---|---|
| #3 Circuit Breaker | A retry that keeps failing with `ConnectionError` trips the breaker |

## 15 · Governance checklist

- [ ] `backoff.enabled` seeded in `recommended_weights.py`
- [ ] All hyperparameters seeded in `recommended_weights.py`
- [ ] Migration upserts AppSetting rows
- [ ] `FEATURE-REQUESTS.md` entry written
- [ ] `AI-CONTEXT.md` execution ledger entry written
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row ticked
- [ ] `docs/PERFORMANCE.md` entry added
- [x] Helper module written and merged (PR-C)
- [ ] Benchmark module written and merged
- [x] Test module written and merged (PR-C)
- [ ] TPE search space declared in meta-HPO study
- [ ] Wired into syncers / analytics / crawler (W2)
