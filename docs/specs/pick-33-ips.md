# Pick #33 — Inverse-Propensity Scoring for position bias (Joachims 2017)

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 33 |
| **Canonical name** | Position-bias IPS estimator |
| **Settings prefix** | `position_bias_ips` |
| **Pipeline stage** | Score (bias correction) |
| **Shipped in commit** | `879ecc5` (PR-N, 2026-04-22) |
| **Helper module** | [backend/apps/pipeline/services/position_bias_ips.py](../../backend/apps/pipeline/services/position_bias_ips.py) |
| **Tests module** | [backend/apps/pipeline/test_feedback_signals.py](../../backend/apps/pipeline/test_feedback_signals.py) — `PositionBiasIPSTests` |
| **Benchmark module** | `backend/benchmarks/test_bench_position_bias_ips.py` (pending G6) |

## 2 · Motivation

Users click position 1 much more than position 10, regardless of
relevance — it's a browsing-order artefact, not a ranking signal.
Naive training on clicks learns "put previously-clicked docs at top"
(a tautology). IPS debiases the clicks: divide each observed click
by its examination propensity (probability the user saw that
position). Items at low-propensity positions thus get their clicks
up-weighted, so the training signal reflects intrinsic relevance.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Joachims, T., Swaminathan, A. & Schnabel, T. (2017). "Unbiased learning-to-rank with biased feedback." *WSDM*, pp. 781-789. |
| **Open-access link** | <https://www.cs.cornell.edu/people/tj/publications/joachims_etal_17a.pdf> |
| **Relevant section(s)** | §4 — power-law propensity `p(d) = 1/d^η`; §4.3 — η fitting via swap-experiment MLE. |
| **What we faithfully reproduce** | The formula + MLE fit via `scipy.optimize.minimize_scalar`. |
| **What we deliberately diverge on** | Nothing. |

## 4 · Input contract

- **`power_law_propensity(position: int, *, eta=1.0) -> float`**
- **`ips_weight(*, position: int, eta=1.0, max_weight=10.0) -> float`**
- **`reweight_clicks(position_click_counts: Mapping[int, int], *,
  eta, max_weight) -> dict[int, float]`**
- **`fit_eta_from_interventions(logs: Iterable[InterventionLog], *,
  eta_min=0.1, eta_max=3.0) -> float`**
- **`average_reweighted_click_rate(*, click_events, eta, max_weight)`**

## 5 · Output contract

- Propensity in `(0, 1]`; ips_weight in `[1, max_weight]`.
- Reweighted click count is a `float`, not an `int`.
- **Determinism.** Deterministic per input.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `position_bias_ips.enabled` | bool | `true` | Recommended preset policy | No | — | Off = raw CTRs |
| `position_bias_ips.eta` | float | `1.0` | Joachims §5 — measured η ≈ 0.9–1.1 on Yahoo/Arxiv SERPs | Yes | `uniform(0.2, 3.0)` | Higher η = stronger position-bias correction |
| `position_bias_ips.max_weight` | float | `10.0` | Swaminathan-Joachims 2015 counterfactual risk minimisation — clip reduces variance at cost of residual bias | Yes | `uniform(2.0, 100.0)` | Smaller = lower variance, more bias |

## 7 · Pseudocode

See `apps/pipeline/services/position_bias_ips.py`. Core:

```
function power_law_propensity(position, eta):
    return 1 / position ** eta

function ips_weight(position, eta, max_weight):
    return min(1 / power_law_propensity(position, eta), max_weight)

function fit_eta_from_interventions(logs, eta_min, eta_max):
    scipy.optimize.minimize_scalar(
        -log_likelihood, bounds=(eta_min, eta_max), method="bounded"
    )
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/pipeline/services/weight_tuner.py` | CTR aggregates per position | IPS-weighted click counts for unbiased training |
| `apps/analytics/impact_engine.py` | GSC CTR data | Unbiased aggregate metrics |

## 9 · Scheduled-updates job

- **Key:** `position_bias_ips_refit`
- **Cadence:** weekly (Sun 18:10)
- **Priority:** low
- **Estimate:** 5 min
- **Multicore:** no (scipy fit on ~1000 logs)
- **RAM:** ≤ 16 MB

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | < 10 MB | — |
| Disk | Single eta value + audit log | — |
| CPU | Fit ~50 ms on 1000 logs; weight lookup < 1 µs | benchmark small |

## 11 · Tests

| Test name | Invariant verified |
|---|---|
| `test_power_law_propensity_monotone_decreasing` | Math |
| `test_position_one_has_propensity_one` | Boundary |
| `test_bad_position_rejected` | Validation |
| `test_ips_weight_clipped` | Clip works |
| `test_reweight_clicks_scales_deeper_positions_more` | Direction |
| `test_average_reweighted_ctr_produces_finite` | Numerical sanity |
| `test_fit_eta_from_interventions_returns_positive` | MLE works |
| `test_fit_eta_rejects_empty_logs` | Validation |
| `test_fit_eta_rejects_all_zero_clicks` | Validation |

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 10 weight lookups | < 1 µs | > 10 µs |
| medium | 1 000 intervention logs fit | < 100 ms | > 1 s |
| large | 100 000 intervention logs | < 5 s | > 60 s |

## 13 · Edge cases & failure modes

- **No intervention logs** → can't fit η; fall back to default 1.0.
- **All logs at same position** → no info; fit returns the bounds.
- **Extremely deep positions** (100+) produce huge `ips_weight`
  before clipping — clipping is necessary.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| GSC intervention logs | Training data for η fit |

| Downstream | Reason |
|---|---|
| #34 Cascade Click | Both consume click logs; orthogonal debiasing |
| Weight tuner #41 | Unbiased training loss |

## 15 · Governance checklist

- [ ] `position_bias_ips.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows
- [x] `FEATURE-REQUESTS.md` entry
- [x] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry
- [x] Helper module (PR-N)
- [ ] Benchmark module
- [x] Test module (PR-N)
- [x] `position_bias_ips_refit` scheduled job registered (W1)
- [ ] TPE search space declared
- [ ] Weight tuner wired (W3)
