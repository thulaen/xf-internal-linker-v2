# Pick #10 — Freshness Crawl Scheduling (Cho & Garcia-Molina 2003)

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 10 |
| **Canonical name** | Cho-Garcia-Molina age-weighted freshness scheduler |
| **Settings prefix** | `freshness_scheduler` |
| **Pipeline stage** | Crawl |
| **Shipped in commit** | `f8548e4` (PR-D, 2026-04-22) |
| **Helper module** | [backend/apps/sources/freshness_scheduler.py](../../backend/apps/sources/freshness_scheduler.py) |
| **Tests module** | [backend/apps/sources/tests.py](../../backend/apps/sources/tests.py) — `FreshnessSchedulerTests` |
| **Benchmark module** | [backend/benchmarks/test_bench_freshness_scheduler.py](../../backend/benchmarks/test_bench_freshness_scheduler.py) (pending G6) |

## 2 · Motivation

Re-crawling every known URL on a daily schedule is wasteful — most
forum threads and archive pages don't change week-to-week, and a
handful of active topics change hourly. Cho & Garcia-Molina prove
that to maximise **age-weighted freshness** under a fixed crawl
budget, pages should be re-crawled at a rate proportional to
`sqrt(importance × change_rate)`. A page that changes twice as often
gets refetched √2× more often, not 2× — the diminishing-returns
curve comes directly from minimising expected information staleness.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Cho, J. & Garcia-Molina, H. (2003). "Effective page refresh policies for Web crawlers." *ACM Transactions on Database Systems* 28(4): 390-426. |
| **Open-access link** | <http://infolab.stanford.edu/~olston/publications/tods03.pdf> |
| **Relevant section(s)** | §4 — age-weighted freshness metric; §5 — optimal-frequency derivation (equation 17: `f*(p_i) ∝ sqrt(w_i λ_i)`); §6 — Poisson change-rate estimation with regularisation |
| **What we faithfully reproduce** | The `f* ∝ sqrt(w × λ)` law (implemented as `raw = sqrt(1 / (importance × λ))`); Laplace-smoothed change-rate estimation `p̂ = (changes + 1) / (crawls + 2)` so zero-change observations don't produce infinite intervals. |
| **What we deliberately diverge on** | The paper's Poisson process assumes continuous-time change; we use discrete per-crawl change counts (matching what the crawler actually records). The MLE is identical for our use case. |

## 4 · Input contract

- **`CrawlObservation(crawls: int, changes: int,
  average_interval_seconds: float)`** — summary of a URL's past
  re-crawl history.
  - `crawls >= 0`, `changes >= 0`, `changes <= crawls`.
  - `average_interval_seconds > 0`.
- **`next_refresh_interval_seconds(observation, *, importance=1.0,
  min_interval_seconds=6*3600, max_interval_seconds=30*24*3600,
  bootstrap_interval_seconds=86400) -> FreshnessDecision`**

## 5 · Output contract

- **`FreshnessDecision`** frozen dataclass:
  - `interval_seconds: int` — recommended time until next refresh
  - `estimated_change_rate_per_second: float` — λ̂ from Cho-GM
    estimator
  - `change_probability: float` — Laplace-smoothed p̂
  - `raw_interval_seconds: float` — pre-clamp interval
  - `reason: str` — one of `bootstrap`, `clamped_min`, `clamped_max`,
    `cho_gm_sqrt_law` so diagnostics show why a URL got the interval
    it did.
- **Invariants.**
  - `min_interval ≤ interval_seconds ≤ max_interval`.
  - Monotonic in change_rate (higher λ → shorter interval).
  - Monotonic in importance (higher importance → shorter interval).
  - Zero-change history → finite interval (Laplace smoothing
    guarantee).
- **Determinism.** Pure function.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `freshness_scheduler.enabled` | bool | `true` | Recommended preset policy | No | — | Off = uniform daily re-crawl |
| `freshness_scheduler.min_interval_seconds` | int | `21600` (6 h) | Plan §Crawl layer — "laptop-sleep-safe floor"; prevents hot-looping on volatile pages | Yes | `int(3600, 86400)` | Raising reduces load on volatile origins |
| `freshness_scheduler.max_interval_seconds` | int | `2592000` (30 days) | Plan §Crawl layer — above this re-crawl becomes a "crystal-seed sweep" not a refresh | Yes | `int(604800, 7776000)` | Controls freshness of archival content |
| `freshness_scheduler.bootstrap_interval_seconds` | int | `86400` (24 h) | Plan §Crawl layer — long enough to avoid hot-loop on misconfig, short enough to learn real volatility within a week | Yes | `int(3600, 604800)` | Fresh-URL default until we have observations |
| `freshness_scheduler.default_importance` | float | `1.0` | Cho-GM 2003 — `w=1` is the neutral prior | No | — | Setting per-site importance via a dedicated site-importance table is cleaner than tuning a global scalar |

## 7 · Pseudocode

```
function estimate_change_rate_per_second(obs):
    # Laplace-smoothed p̂
    p_hat = (obs.changes + 1) / (obs.crawls + 2)
    # Cho-GM Poisson estimator
    lambda_hat = -log(1 - p_hat) / obs.average_interval_seconds
    return lambda_hat, p_hat

function next_refresh_interval_seconds(obs, importance, min_int, max_int, bootstrap_int):
    if obs is None or obs.crawls == 0:
        return FreshnessDecision(
            interval = clamp(bootstrap_int, min_int, max_int),
            reason = "bootstrap",
        )
    lambda_hat, p_hat = estimate_change_rate_per_second(obs)
    # Cho-GM square-root law: higher importance × higher change-rate ⇒ shorter interval
    raw = sqrt(1.0 / (importance * lambda_hat))
    clamped = int(clamp(raw, min_int, max_int))
    return FreshnessDecision(
        interval = clamped,
        lambda_hat = lambda_hat,
        p_hat = p_hat,
        raw = raw,
        reason = (
            "clamped_min" if clamped == min_int else
            "clamped_max" if clamped == max_int else
            "cho_gm_sqrt_law"
        ),
    )
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/crawler/services/site_crawler.py` | Per-URL `CrawlObservation` from `CrawledPageMeta` history | Schedule next refresh at `now + interval_seconds` |
| `apps/pipeline/services/pipeline_loaders.py` | Same during initial load | Seed per-URL cadence on first ingestion |

**Wiring status.** Helper exists (PR-D). Crawler still uses a single
daily cadence. Wiring lands in W2 — will require a new
`refresh_interval_seconds` column on `CrawledPageMeta` and re-queueing
logic keyed off `last_crawled_at + interval`.

## 9 · Scheduled-updates job

- **Key:** `crawl_freshness_scan`
- **Cadence:** daily 13:30
- **Priority:** critical
- **Estimate:** 15–60 min
- **Multicore:** yes (per-origin parallel)
- **Depends on:** none
- **RAM:** ≤ 64 MB (streaming per-URL)
- **Disk:** ≤ 5 MB state (refresh-interval column)

Scan runs daily to re-compute per-URL intervals based on the latest
change history; the crawler itself follows the intervals each tick.

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | < 5 MB @ 1 M URLs (streaming, not in-memory state) | benchmark medium |
| Disk | < 5 MB (refresh-interval column per URL) | — |
| CPU | < 1 µs per `next_refresh_interval_seconds` call | benchmark small |

## 11 · Tests

| Test name | Invariant verified |
|---|---|
| `test_zero_crawls_returns_bootstrap` | Bootstrap branch |
| `test_higher_change_rate_shortens_interval` | Monotonicity |
| `test_higher_importance_shortens_interval` | Monotonicity |
| `test_zero_change_history_finite_interval` | Laplace smoothing |
| `test_interval_clamped_below_min` | Clamp floor |
| `test_interval_clamped_above_max` | Clamp ceiling |
| `test_reason_field_reports_clamping` | Operator visibility |
| `test_invalid_observation_rejected` | Input validation |

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 1 000 URLs scored | < 5 ms | > 50 ms |
| medium | 100 000 URLs scored | < 300 ms | > 3 s |
| large | 10 000 000 URLs scored | < 30 s | > 5 min |

## 13 · Edge cases & failure modes

- **`crawls = 0, changes = 0`** → bootstrap interval.
- **`crawls = 1, changes = 0`** → Laplace smoothing gives `p̂ = 1/3 ≈
  0.33`, interval ≈ reasonable.
- **`crawls = 0, changes > 0`** rejected at `CrawlObservation`
  construction (`changes > crawls` invariant).
- **`importance = 0` or negative** → `ValueError`. Zero importance is
  undefined under the sqrt law.
- **Very volatile URL (changes every crawl)** → `p̂ → 1.0`; interval
  collapses to `min_interval_seconds`. Laplace smoothing prevents
  infinite λ.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| #6 Conditional GET | Conditional GET makes the frequent refresh cheap (304 saves body download) |

| Downstream | Reason |
|---|---|
| Crawler frontier | Consumes `interval_seconds` to schedule next fetch |

## 15 · Governance checklist

- [ ] `freshness_scheduler.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows (+ `refresh_interval_seconds` column)
- [x] `FEATURE-REQUESTS.md` entry
- [x] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry
- [x] Helper module (PR-D)
- [ ] Benchmark module
- [x] Test module (PR-D)
- [ ] `crawl_freshness_scan` scheduled job registered (W1)
- [ ] TPE search space declared
- [ ] Crawler wired (W2)
