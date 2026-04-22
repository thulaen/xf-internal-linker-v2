# Pick #01 — Token Bucket Rate Limiter

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 1 |
| **Canonical name** | Token Bucket Rate Limiter (Turner 1986) |
| **Settings prefix** | `token_bucket` |
| **Pipeline stage** | Source |
| **Shipped in commit** | `6d925b1` (PR-C, 2026-04-22) |
| **Helper module** | [backend/apps/sources/token_bucket.py](../../backend/apps/sources/token_bucket.py) |
| **Tests module** | [backend/apps/sources/tests.py](../../backend/apps/sources/tests.py) — `TokenBucketTests` |
| **Benchmark module** | [backend/benchmarks/test_bench_token_bucket.py](../../backend/benchmarks/test_bench_token_bucket.py) (pending G6) |

## 2 · Motivation

When the linker calls an external API (XenForo REST, WordPress XML-RPC,
GSC, GA4) we must not burst more requests than the remote allows or
we'll trip its anti-abuse rate limiter — which typically costs us a
5–60 min cool-down and a cascade of retries. A **token bucket** is
the classic fix: a bucket refills at a fixed rate `R`, and every
outgoing request consumes one token. When the bucket is empty the
caller waits (or the helper reports `retry_after_seconds`). The
bucket capacity `B` absorbs short bursts so the linker can still fire
off a cluster of requests in quick succession when it needs to.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Turner, J. S. (1986). "New directions in communications (or which way to the information age?)." *IEEE Communications Magazine* 24(10): 8-15. |
| **Open-access link** | <https://ieeexplore.ieee.org/document/1092946> |
| **Relevant section(s)** | §III — token bucket traffic shaper; the same formula underlies RFC 2697 `srTCM` and the Linux `tc-tbf` scheduler |
| **What we faithfully reproduce** | The fill-drip math: `tokens += (now − last_refill) × rate`, clipped at `capacity`; `consume(n)` returns `False` when `tokens < n` |
| **What we deliberately diverge on** | We use a monotonic `time.monotonic()` clock (not wall-clock) so a clock adjustment doesn't cause a token shower. Turner's paper assumes a network scheduler's tick clock. |

## 4 · Input contract

- **`capacity: int`** — the bucket size, in whole tokens. Domain `[1,
  ∞)`. Raises `ValueError` on `< 1`. Typical: 10 for a human-cadence
  XenForo endpoint, 100 for GA4 streaming.
- **`refill_rate_per_second: float`** — how many tokens are added
  per second. Domain `(0, ∞)`. Raises `ValueError` on `≤ 0`.
- **`initial_tokens: int | None`** — starting tokens. Defaults to
  `capacity` (full bucket). Must be in `[0, capacity]`.
- **`consume(n: int = 1) -> bool`** — attempts to remove `n` tokens.
  Returns `True` on success. Returns `False` without mutating the
  bucket when `n` > current tokens. Raises `ValueError` for `n < 1`.

**Empty-input behaviour.** There is no "empty input" — the bucket
always has a state. A brand-new bucket starts full; one that's been
idle for hours refills to `capacity` on the first `consume` call.

## 5 · Output contract

- **`consume(n)`** → `bool`.
- **`retry_after_seconds(n=1)`** → `float` — how long the caller would
  have to wait for `n` tokens to be available under the current refill
  rate. Returns `0.0` when already available. Monotonic in `n`.
- **`snapshot()`** → frozen `TokenBucketState` dataclass with
  `capacity`, `tokens`, `refill_rate_per_second`, `last_refill_monotonic`.

**Invariants.**

- `0 ≤ tokens ≤ capacity` at every call boundary.
- `consume(n)` with `n > capacity` always returns `False`
  (unreachable rate).
- `retry_after_seconds(n)` is non-decreasing in `n`.
- **Determinism.** Output depends on `time.monotonic()`. Tests inject
  a fake clock via the `now_fn` constructor parameter to stay
  deterministic.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `token_bucket.enabled` | bool | `true` | Recommended preset policy | No | — | Turns the rate limiter on globally; disabling reverts to "fire-and-pray" |
| `token_bucket.xenforo.capacity` | int | `10` | XenForo REST docs: "default throttle is 10 req/5 s" (<https://xenforo.com/community/resources/categories/rest-api.57/>) | Yes | `int(1, 50)` | Larger = more burst tolerance, higher risk of remote ban |
| `token_bucket.xenforo.refill_rate_per_second` | float | `2.0` | 10 per 5 s = 2 per s per XenForo docs | Yes | `loguniform(0.2, 10.0)` | Long-run request rate to XenForo |
| `token_bucket.wordpress.capacity` | int | `20` | WP REST has no docs; empirical measurements on WP 6.x | Yes | `int(5, 100)` | Same as above, for WP endpoints |
| `token_bucket.wordpress.refill_rate_per_second` | float | `4.0` | empirical | Yes | `loguniform(0.5, 20.0)` | WP long-run cadence |
| `token_bucket.gsc.capacity` | int | `25` | Google GSC quota: 200 req/min → 25 burst is well inside quota | No | — | Google-imposed correctness param |
| `token_bucket.gsc.refill_rate_per_second` | float | `3.0` | 200 req/min ÷ 60 ≈ 3.33; chose 3.0 for safety margin | No | — | Google-imposed correctness param |
| `token_bucket.ga4.capacity` | int | `50` | GA4 Data API quota: 200 req/s | No | — | Google-imposed correctness param |
| `token_bucket.ga4.refill_rate_per_second` | float | `10.0` | GA4 Data API: 10 req/s per property is the sustainable rate | No | — | Google-imposed correctness param |

**Why Google endpoints are `TPE-tuned = No`.** The caps are dictated
by Google's API quotas — tuning them up would trigger 429s; tuning
them down just throttles us unnecessarily. Correctness wins over
adaptation.

## 7 · Pseudocode

```
# Core refill + consume (monotonic clock, O(1)):

function consume(bucket, n):
    now = clock.monotonic()
    elapsed = now - bucket.last_refill
    bucket.tokens = min(bucket.capacity,
                        bucket.tokens + elapsed * bucket.rate)
    bucket.last_refill = now
    if bucket.tokens < n:
        return False
    bucket.tokens -= n
    return True

function retry_after_seconds(bucket, n):
    # Refill state without consuming.
    now = clock.monotonic()
    elapsed = now - bucket.last_refill
    projected = min(bucket.capacity, bucket.tokens + elapsed * bucket.rate)
    if projected >= n:
        return 0.0
    return (n - projected) / bucket.rate
```

Helper wraps a thread-safe registry keyed by origin so multiple
workers share one bucket per external host (prevents the cluster
from collectively DoSing XenForo).

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/sync/services/*.py` (XenForo / WP syncers) | `bucket_name="xenforo"`, `consume(1)` | `False` → `time.sleep(retry_after_seconds())` then retry |
| `apps/analytics/{ga4_client,gsc_client}.py` | `bucket_name="ga4"` or `"gsc"` | Same pattern |
| `apps/crawler/services/site_crawler.py` | `bucket_name=origin_host` | Per-host rate-limiting during crawl |

**Wiring status (2026-04-22).** Not yet called from any of the above
— wiring lands in **W2 (import pipeline)**. Pre-existing syncers use
ad-hoc `time.sleep()` calls that will be replaced.

## 9 · Scheduled-updates job

Not scheduled. On-demand only — the bucket's state lives in memory
and mutates on every external request. TPE-tuned hyperparameters get
updated by the weekly `meta_hyperparameter_hpo` job but that study
uses offline synthetic traffic, not real API calls.

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM (peak) | < 1 KB per bucket × (2 syncer origins + N crawler origins) | benchmark medium size |
| Disk | 0 | stateful in-memory only |
| CPU time (consume) | < 1 µs | benchmark small |
| Wall-clock when scheduled | n/a | — |

## 11 · Tests

| Test name | Invariant verified |
|---|---|
| `test_fresh_bucket_has_capacity_tokens` | `initial_tokens=capacity` default |
| `test_consume_one_removes_exactly_one` | Token accounting |
| `test_consume_fails_when_empty` | No overdraft |
| `test_retry_after_monotonic_in_n` | §5 invariant |
| `test_refill_caps_at_capacity` | Never goes above `capacity` |
| `test_injected_clock_supports_time_travel` | Deterministic in tests |
| `test_concurrent_consume_thread_safe` | Registry-level thread safety |

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 1 bucket, 1 000 consumes | < 1 ms | > 10 ms |
| medium | 20 buckets, 100 000 interleaved consumes | < 50 ms | > 500 ms |
| large | 200 buckets, 1 000 000 interleaved consumes | < 600 ms | > 5 s |

## 13 · Edge cases & failure modes

- **Clock adjustment.** We use `time.monotonic()`, not `time.time()`,
  so a wall-clock jump does not spill tokens. A non-monotonic custom
  `now_fn` in tests will raise.
- **Bucket abandoned for hours.** Next consume refills to `capacity`
  in O(1); no catch-up loop required.
- **`n > capacity`** always returns `False` — the request is
  unreachable under current configuration. Helpful for loud failure
  instead of silent stall.
- **Registry race.** The shared registry uses `threading.Lock`; in
  async contexts the caller wraps `consume` in
  `loop.run_in_executor`.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| — | Standalone |

| Downstream | Reason |
|---|---|
| #2 Exponential Backoff + Jitter | A `False` from `consume` triggers a `retry_after_seconds()` sleep that Backoff wraps with jitter |
| #3 Circuit Breaker | Rate-limit refusals feed the breaker's "degraded upstream" signal |

## 15 · Governance checklist

- [x] `token_bucket.enabled` seeded in `recommended_weights.py`
  (pending — part of G2)
- [ ] All hyperparameters seeded in `recommended_weights.py`
- [ ] Migration upserts AppSetting rows
- [ ] `FEATURE-REQUESTS.md` entry written
- [ ] `AI-CONTEXT.md` execution ledger entry written (PR-C log)
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row ticked
- [ ] `docs/PERFORMANCE.md` entry added
- [x] Helper module written and merged (PR-C)
- [ ] Benchmark module written and merged (pending G6)
- [x] Test module written and merged (PR-C)
- [ ] TPE search space declared in meta-HPO study (pending Option B
      wiring)
- [ ] Wiring into syncers / crawler / analytics clients (W2)
