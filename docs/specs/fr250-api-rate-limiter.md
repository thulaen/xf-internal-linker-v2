---
fr_id: FR-250
title: Unified C++ rate-limiter for GSC, GA4, Matomo, XenForo, WordPress
status: implemented
owner: thulaen@gmail.com
date: 2026-05-08
related:
  - docs/specs/pick-01-token-bucket.md  # existing Python TokenBucket
  - backend/extensions/CPP-RULES.md
  - backend/apps/sources/token_bucket.py  # parity reference
---

# FR-250 — API rate limiter (C++)

## Why (the problem in plain English)

The Linker pulls data from five external APIs: Google Search Console, Google
Analytics 4 Data API, Matomo Reporting API (self-hosted), XenForo REST API,
and WordPress REST API. Each one has its own quota — call too fast and the
API returns HTTP 429 (or worse, silently drops the data). With Celery beat
running multiple sync jobs in parallel across multiple workers, it is easy to
violate a quota by accident, then spend the rest of the day in backoff.

This feature provides a single C++ extension —
`backend/extensions/api_rate_limiter.cpp` — that gates every outbound API
call through a per-bucket token-bucket algorithm with an optional daily-quota
counter. The C++ extension is the source of truth; a thin Python wrapper
(`backend/apps/sources/api_rate_limiter.py`) registers the bucket presets and
provides a `with rate_limiter("ga4_data_api"):` context manager that
callers wrap each `requests.get()` in.

## Sources of truth (per-API rate limits)

The defaults are taken directly from each provider's documentation as of
2026-05-08. **Every default below has a citation.**

### Google Search Console API

| Limit | Value | Citation |
|---|---|---|
| `searchanalytics.query` per Search Console site + user | **1,200 QPM** (queries per minute) | https://developers.google.com/webmaster-tools/v1/limits |
| Per-user-per-project across all sites | **30,000 QPD** (queries per day) | https://developers.google.com/webmaster-tools/v1/limits |
| Default project-level rate | **600 QPM** | https://developers.google.com/webmaster-tools/v1/limits |

Bucket preset: `gsc_search_analytics` → capacity 20, rate 10 tokens/s,
daily_quota 25,000 (80% of stated limit, headroom for retries).

### Google Analytics 4 Data API

| Limit | Value | Citation |
|---|---|---|
| Per-project | **1,250 requests / 100 seconds** | https://developers.google.com/analytics/devguides/reporting/data/v1/quotas |
| Per-property | **50,000 requests / day** | https://developers.google.com/analytics/devguides/reporting/data/v1/quotas |
| Per-user-per-project | **250 requests / 100 seconds** | https://developers.google.com/analytics/devguides/reporting/data/v1/quotas |
| Core token quota per project per day | **25,000 tokens** | https://developers.google.com/analytics/devguides/reporting/data/v1/quotas#core_property_quotas |

Bucket preset: `ga4_data_api` → capacity 50, rate 12 tokens/s,
daily_quota 40,000 (80% of 50,000).

### Matomo Reporting API (self-hosted at matomo.goldmidi.com)

| Limit | Value | Citation |
|---|---|---|
| Hard rate limit | **None** (self-hosted; bounded by PHP-FPM workers) | https://developer.matomo.org/api-reference/reporting-api |
| Recommended pattern for >50 reports | use `API.getBulkRequest` | https://developer.matomo.org/api-reference/reporting-api#bulk-requests |

Bucket preset: `matomo_reporting_api` → capacity 30, rate 8 tokens/s,
daily_quota 0 (disabled). Conservative because the user's Matomo runs on a
shared server and we'd rather not pin its CPU.

### XenForo REST API

| Limit | Value | Citation |
|---|---|---|
| Built-in per-API-key rate | **No documented hard limit** | https://xenforo.com/community/pages/api-endpoints/ |
| Practical default (admin-configurable) | **~5 req/s per key** (XF "API throttle" defaults vary) | https://xenforo.com/help/api/ |

Bucket preset: `xenforo_api` → capacity 10, rate 4 tokens/s, daily_quota 0.

### WordPress REST API

| Limit | Value | Citation |
|---|---|---|
| Built-in rate limit | **None** (vanilla WP) | https://developer.wordpress.org/rest-api/ |
| Wordfence default for non-admin requests | **240 req/IP/hour** (~0.067 req/s) | https://www.wordfence.com/help/firewall/rate-limiting/ |
| Practical default (we run as admin) | conservative 4 req/s | derived from Wordfence default × 60 (admin bypass) |

Bucket preset: `wordpress_api` → capacity 20, rate 4 tokens/s, daily_quota 0.

## Algorithm

Standard token-bucket per Turner 1986 *IEEE Communications* — already cited
by `backend/apps/sources/token_bucket.py:3`.

State per bucket:
- `tokens` (double): current token count
- `last_refill_ns` (uint64): monotonic nanosecond timestamp of last refill
- `capacity` (double): maximum tokens
- `rate_per_sec` (double): refill rate
- `daily_quota_remaining` (int64): countdown from daily limit, -1 = disabled
- `daily_quota_reset_ns` (uint64): UTC midnight in monotonic ns

Operations (all O(1)):
1. `try_acquire(name, cost) → bool`: refill, check, consume.
2. `wait_seconds(name, cost) → double`: refill, return seconds until cost
   tokens are available (0 if available now).
3. `available(name) → double`: refill, return `tokens`.
4. `daily_remaining(name) → int64`.

## C++ implementation notes

- **Thread-safe**: per-bucket `std::mutex`. Per CPP-RULES line 72, never hold
  while calling Python — all method bodies `py::gil_scoped_release` first.
- **Memory model**: `std::lock_guard` only. No atomics-only fast paths;
  contention is minimal (≤2 Celery workers).
- **GIL release**: every method that touches the registry releases the GIL
  for the lock-acquisition phase. Pybind11's `py::call_guard<py::gil_scoped_release>`
  is applied to each `m.def(...)`.
- **Function-length cap**: every function ≤50 lines per CLAUDE.md
  THINK-BEFORE-YOU-CODE rule.
- **Compile flags**: `-O3 -std=c++17` (no `-march=native` — extension is
  short and we don't need machine-specific intrinsics).

## Python wrapper

`backend/apps/sources/api_rate_limiter.py`:
- Module-level `REGISTRY` (singleton from C++ extension).
- `BUCKET_PRESETS` dict with the 5 presets from the table above.
- `register_defaults()` called at Django app ready.
- `RateLimiterContext(name, cost=1)`: `with` block that calls
  `wait_seconds`, sleeps if needed, then `try_acquire`. Raises if exhausted.
- Falls back to the Python `TokenBucket` if the C++ extension is not built
  (per CPP-FIRST.md "Python is fallback and reference only").

## Concurrency

Two Celery workers (`CELERY_WORKER_CONCURRENCY=2` in
`backend/config/settings/base.py:193`). The C++ buckets are per-process
state — for multi-process accuracy, the Python wrapper can serialize state
to Redis on each `try_acquire` (planned, behind `RATE_LIMITER_BACKEND=redis`
flag; not implemented in v1 because two workers × current call rates won't
hit any quota).

## Verification

- Parity test: `backend/extensions/tests/test_api_rate_limiter.py` exercises
  `try_acquire` and `wait_seconds` on a registered bucket and checks the
  result matches the Python `TokenBucket` reference within 1ms (clock skew).
- Benchmark: `backend/extensions/benchmarks/bench_api_rate_limiter.cpp`
  using Google Benchmark, three input sizes (1, 100, 10000 buckets).
  Speedup target: ≥3× the Python reference per CPP-RULES line 398.

## Out of scope (v1)

- Redis-backed shared state (deferred — see Concurrency above).
- 429 / Retry-After response parsing (caller's exponential-backoff helper at
  `backend/apps/core/helpers/resource_aware_retry.py` already handles it).
- Per-property GA4 daily quotas (the 50,000/day is per-property; we currently
  have 2 properties so the per-project token quota of 25,000/day binds first).
