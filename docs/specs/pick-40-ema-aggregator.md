# Pick #40 — EMA Feedback Aggregator (Brown 1959)

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 40 |
| **Canonical name** | Exponential Moving Average feedback smoother |
| **Settings prefix** | `ema_aggregator` |
| **Pipeline stage** | Feedback |
| **Shipped in commit** | `879ecc5` (PR-N, 2026-04-22) |
| **Helper module** | [backend/apps/pipeline/services/ema_aggregator.py](../../backend/apps/pipeline/services/ema_aggregator.py) |
| **Tests module** | [backend/apps/pipeline/test_feedback_signals.py](../../backend/apps/pipeline/test_feedback_signals.py) — `EMATests` |
| **Benchmark module** | `backend/benchmarks/test_bench_ema.py` (pending G6) |

## 2 · Motivation

Per-suggestion feedback (accept, reject, edit, click) arrives noisy.
A single bad day shouldn't tank a good suggestion's score; a single
lucky day shouldn't promote a bad one. EMA smooths the signal with
a controllable memory window: `s_t = α·x_t + (1-α)·s_{t-1}`. Smaller
α = longer memory (stable but slow to react); larger α = shorter
memory (reactive but noisier).

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Brown, R. G. (1959). "Statistical forecasting for inventory control." *Operations Research* 7(6): 691-705. |
| **Open-access link** | <https://pubsonline.informs.org/doi/abs/10.1287/opre.7.6.691> (paywall); formula widely reproduced in TS-forecasting texts. |
| **Relevant section(s)** | §2 — exponential smoothing recurrence. |
| **What we faithfully reproduce** | The recurrence + carry-forward state. |
| **What we deliberately diverge on** | Nothing. |

## 4 · Input contract

- **`ema(series: Sequence[float], *, alpha=0.1, seed=None) ->
  EMASummary`** — run EMA over a series.
- **`ema_per_key(series_by_key: Mapping, *, alpha=0.1, seeds=None) ->
  dict[str, EMASummary]`** — batch per-key.
- **`alpha_from_half_life(half_life_steps: float) -> float`** —
  convert "half-life in events" to α.
- Bad α → `ValueError`.

## 5 · Output contract

- `EMASummary(final_value, observation_count, smoothing_alpha)`.
- Empty series + no seed → `final_value=0`, `observation_count=0`.
- **Determinism.** Pure function.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `ema_aggregator.enabled` | bool | `true` | Recommended preset policy | No | — | Off = raw last-event value |
| `ema_aggregator.alpha` | float | `0.1` | Brown 1959; empirical — halves event influence every ~7 steps, balances reactivity vs stability on daily cadence | Yes | `uniform(0.01, 0.5)` | Smaller = longer memory |
| `ema_aggregator.half_life_steps_hint` | float | `7.0` | Operator-friendly alt-knob: equivalent α via `alpha_from_half_life` | Yes | `uniform(1.0, 90.0)` | Events until 50 % weight |

## 7 · Pseudocode

See `apps/pipeline/services/ema_aggregator.py`. Core recurrence:
`s_t = α·x_t + (1-α)·s_{t-1}`.

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/pipeline/services/feedback_rerank.py` | Daily feedback counts per suggestion | Smoothed per-suggestion feedback score |
| `apps/analytics/impact_engine.py` | Engagement time series | Smoothed metric for dashboard |

## 9 · Scheduled-updates job

- **Key:** `feedback_aggregator_ema_refresh`
- **Cadence:** daily 13:05
- **Priority:** critical
- **Estimate:** 2 min
- **Multicore:** no
- **RAM:** ≤ 16 MB

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | negligible (streaming) | — |
| Disk | 8 bytes per keyed EMA state | — |
| CPU | < 100 ns per update | benchmark small |

## 11 · Tests

All 9 `EMATests` pass.

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 1 000 observations | < 1 ms | > 10 ms |
| medium | 10 000 000 observations | < 3 s | > 30 s |
| large | 10 000 keys × 1 000 observations each | < 2 s | > 20 s |

## 13 · Edge cases & failure modes

- **Gaps in input series** — helper doesn't time-weight; callers that
  need "days since last event" must pre-process.
- **Out-of-order series** — helper assumes chronological order; order
  sensitivity is inherent to EMA.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| #34 Cascade Click, #33 IPS | Produce unbiased daily feedback |

| Downstream | Reason |
|---|---|
| Feedback reranker | Primary consumer |

## 15 · Governance checklist

- [ ] `ema_aggregator.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows
- [ ] `FEATURE-REQUESTS.md` entry
- [ ] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry
- [x] Helper module (PR-N)
- [ ] Benchmark module
- [x] Test module (PR-N)
- [ ] `feedback_aggregator_ema_refresh` scheduled job registered (W1)
- [ ] TPE search space declared
- [ ] Feedback reranker wired (W3)
