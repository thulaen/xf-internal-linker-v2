# Pick #50 — Conformal Prediction (Vovk-Gammerman-Shafer 2005)

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 50 |
| **Canonical name** | Split / inductive conformal prediction — distribution-free confidence intervals |
| **Settings prefix** | `conformal_prediction` |
| **Pipeline stage** | Reviewable |
| **Shipped in commit** | **PR-P — to ship** |
| **Helper module** | [backend/apps/pipeline/services/conformal_prediction.py](../../backend/apps/pipeline/services/conformal_prediction.py) |
| **Tests module** | `backend/apps/pipeline/test_reviewable.py` |
| **Benchmark module** | `backend/benchmarks/test_bench_conformal.py` (pending G6) |

## 2 · Motivation

"This suggestion has 90 % probability of being accepted" is only
useful if the 90 % is calibrated. Conformal Prediction gives a
**guaranteed coverage** confidence band: with user-chosen α=0.1, at
least 90 % of future suggestions' true outcomes fall inside the
predicted interval — no assumptions on the underlying data
distribution (beyond exchangeability). Operators can trust the
"90 %" literally.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Vovk, V., Gammerman, A. & Shafer, G. (2005). *Algorithmic Learning in a Random World.* Springer. ISBN 978-0-387-00152-4. |
| **Open-access link** | <https://link.springer.com/book/10.1007/b106715> (paywall); survey: <https://arxiv.org/abs/2107.07511>. |
| **Relevant section(s)** | Chapter 4 — inductive / split conformal prediction algorithm. |
| **What we faithfully reproduce** | Split-conformal algorithm: hold out calibration set, compute nonconformity scores, compute (1-α) quantile, use as interval half-width. |
| **What we deliberately diverge on** | Plan pick #52 ACI wraps this to handle drift — see ACI spec. |

## 4 · Input contract

- **`fit(calibration_scores: np.ndarray, calibration_labels: np.ndarray, *, alpha=0.1)`** —
  computes the (1-α) quantile of nonconformity scores.
- **`predict_interval(score: float) -> tuple[float, float]`** —
  returns `(lower, upper)` bounds.

## 5 · Output contract

- `ConformalInterval(lower, upper, width)` frozen dataclass.
- **Coverage guarantee.** Under exchangeability, true label falls
  inside `[lower, upper]` with probability ≥ `1 - α`.
- **Determinism.** Pure function.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `conformal_prediction.enabled` | bool | `true` | Recommended preset policy | No | — | Off = no confidence intervals |
| `conformal_prediction.target_miscoverage_alpha` | float | `0.10` | Standard 90 % confidence band | No | — | **Correctness param** — user-chosen coverage target |
| `conformal_prediction.calibration_set_fraction` | float | `0.2` | Vovk 2005 — 20 % holdout is a common choice | Yes | `uniform(0.05, 0.4)` | Bigger calibration = tighter intervals but less training data |

## 7 · Pseudocode

```
function fit(cal_scores, cal_labels, alpha):
    nonconformity = |cal_labels - cal_scores|  # residual magnitude
    n = len(nonconformity)
    quantile_level = ceil((n+1) * (1 - alpha)) / n
    return quantile(nonconformity, quantile_level)

function predict_interval(q, score):
    return (score - q, score + q)
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/suggestions/views.py` | Raw ranker score | Returns confidence interval; UI renders "85 % ± 3 %" |

## 9 · Scheduled-updates job

Calibration refit happens in the weekly `weight_tuner_lbfgs_tpe`
job alongside Platt calibration.

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | < 1 MB (just a quantile) | — |
| Disk | 8 bytes (one float) | — |
| CPU | O(n log n) calibration; O(1) prediction | benchmark small |

## 11 · Tests

- `test_coverage_guarantee_on_synthetic_exchangeable_data`
- `test_invalid_alpha_rejected`
- `test_empty_calibration_rejected`

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 100 calibration pairs | < 1 ms | > 10 ms |
| medium | 100 000 calibration pairs | < 50 ms | > 500 ms |
| large | 100 000 000 | < 30 s | > 5 min |

## 13 · Edge cases & failure modes

- **Distribution shift** — coverage guarantee breaks under shift.
  Mitigation: pick #52 ACI wraps this.
- **α outside (0, 1)** → `ValueError`.
- **Empty calibration set** → `ValueError`.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| Raw ranker scores + true labels | Training input |

| Downstream | Reason |
|---|---|
| Review queue UI | Displays the interval |
| #52 Adaptive Conformal Inference | Wraps this to maintain coverage under drift |

## 15 · Governance checklist

- [ ] `conformal_prediction.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows
- [ ] `FEATURE-REQUESTS.md` entry
- [ ] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry
- [ ] Helper module (PR-P)
- [ ] Benchmark module
- [ ] Test module (PR-P)
- [ ] TPE search space declared
- [ ] UI review panel wired (W4)
