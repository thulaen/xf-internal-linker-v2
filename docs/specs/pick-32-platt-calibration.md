# Pick #32 — Platt sigmoid calibration

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 32 |
| **Canonical name** | Platt scaling — logistic calibration of raw scores |
| **Settings prefix** | `platt_calibration` |
| **Pipeline stage** | Score (calibration) |
| **Shipped in commit** | `6cea1ef` (PR-L, 2026-04-22) |
| **Helper module** | [backend/apps/pipeline/services/platt_calibration.py](../../backend/apps/pipeline/services/platt_calibration.py) |
| **Tests module** | [backend/apps/pipeline/test_platt_calibration.py](../../backend/apps/pipeline/test_platt_calibration.py) |
| **Benchmark module** | `backend/benchmarks/test_bench_platt.py` (pending G6) |

## 2 · Motivation

Operators read "85 %" more easily than "RRF score 0.032". A calibrated
probability lets the UI show a percentage that actually means
something — a 70 %-probability suggestion should be accepted 70 % of
the time across enough samples. Platt scaling turns a raw score `f`
into `P = sigmoid(A·f + B)` via MLE on held-out `(score, label)`
pairs. Two-parameter fit, convex optimisation, works on any score
function.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Platt, J. C. (1999). "Probabilistic outputs for support vector machines and comparisons to regularized likelihood methods." *Advances in Large Margin Classifiers*, pp. 61-74. MIT Press. |
| **Open-access link** | <https://www.cs.colorado.edu/~mozer/Teaching/syllabi/6622/papers/Platt1999.pdf> |
| **Relevant section(s)** | §4 — soft-target derivation `(N_pos+1)/(N_pos+2)` and `1/(N_neg+2)` to prevent saturation. |
| **What we faithfully reproduce** | The two-parameter logistic fit + soft targets. |
| **What we deliberately diverge on** | Use `scipy.optimize.minimize(L-BFGS-B)` on the NLL directly instead of Platt's gradient-descent pseudo-code — L-BFGS-B converges faster and is already a project dep. |

## 4 · Input contract

- **`fit(*, scores: Iterable[float], labels: Iterable[int]) ->
  PlattCalibration`** — MLE fit.
- Labels must be 0 or 1; mixed-class input required.
- **`PlattCalibration.predict(score: float) -> float`** —
  post-calibration probability.
- **`.predict_many(scores)`** — vectorised.

## 5 · Output contract

- `PlattCalibration(slope, bias, n_positives, n_negatives)` frozen.
- `slope` typically < 0 when higher scores → higher probability
  (sigmoid formula uses `exp(A·f + B)` in denominator).
- **Invariants.**
  - `predict(score) ∈ [0, 1]` for any real score.
  - Slope 0 and bias 0 ⇒ predict is 0.5 (neutral prior).
- **Determinism.** Deterministic given inputs (L-BFGS-B is
  deterministic).

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `platt_calibration.enabled` | bool | `true` | Recommended preset policy | No | — | Off = UI shows raw RRF scores |
| `platt_calibration.soft_targets` | bool | `true` | Platt 1999 §4 — prevents saturation on tiny datasets | No | — | Correctness / numerical |
| `platt_calibration.refit_cadence_days` | int | `7` | Weekly refit via weight_tuner job; empirical — probabilities drift under distribution shift | Yes | `int(1, 30)` | Faster refit = more adaptive |
| `platt_calibration.min_training_pairs` | int | `50` | Empirical — below 50 the fit is highly variable | Yes | `int(10, 500)` | Floor on training set size |

## 7 · Pseudocode

See `apps/pipeline/services/platt_calibration.py`. Core:

```
from scipy.optimize import minimize
import numpy as np

function fit(scores, labels):
    validate shapes, require both classes present
    n_pos = sum(labels == 1); n_neg = sum(labels == 0)
    t_pos = (n_pos + 1) / (n_pos + 2)
    t_neg = 1 / (n_neg + 2)
    targets = where(labels == 1, t_pos, t_neg)

    def nll(params):
        a, b = params
        logits = a * scores + b
        pos_term = logaddexp(0, logits) * targets
        neg_term = logaddexp(0, -logits) * (1 - targets)
        return sum(pos_term + neg_term)

    result = minimize(nll, x0=[0, log((n_neg+1)/(n_pos+1))], method="L-BFGS-B")
    return PlattCalibration(slope=result.x[0], bias=result.x[1], ...)
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/pipeline/services/ranker.py` | Raw RRF scores + feedback labels | Stores fitted calibration; applies at display time |
| `apps/suggestions/services/weight_tuner.py` | Refits during weekly tuner | Persists new slope/bias to AppSetting |

## 9 · Scheduled-updates job

Fit is part of the weekly `weight_tuner_lbfgs_tpe` job — same L-BFGS-B
infrastructure.

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | < 5 MB for 10k training pairs | — |
| Disk | 32 bytes per stored calibration (slope, bias) | — |
| CPU (fit) | < 100 ms on 10k pairs | benchmark medium |
| CPU (predict) | < 1 µs per score | benchmark small |

## 11 · Tests

| Test name | Invariant verified |
|---|---|
| `test_returns_platt_calibration_with_class_counts` | Shape |
| `test_recovers_monotone_relationship` | Fit works |
| `test_slope_is_negative_for_increasing_relationship` | Sign convention |
| `test_mismatched_lengths_rejected` | Validation |
| `test_empty_inputs_rejected` | Validation |
| `test_non_binary_labels_rejected` | Validation |
| `test_single_class_rejected` | Validation |
| `test_predict_clamped_in_zero_one` | Output range |
| `test_predict_many_matches_predict_pointwise` | Vectorised equivalence |
| `test_symmetric_around_zero_logit_is_point_five` | Math |
| `test_small_balanced_set_fits` | Soft targets work |

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 100 pairs | < 50 ms | > 500 ms |
| medium | 10 000 pairs | < 500 ms | > 5 s |
| large | 1 000 000 pairs | < 15 s | > 2 min |

## 13 · Edge cases & failure modes

- **Single class** in training (all positives / all negatives) —
  `ValueError`; caller must collect both classes.
- **Scores all identical** — fit collapses; slope near 0, bias near
  class prior. Handled gracefully by L-BFGS-B.
- **Extreme scores** — numerical overflow clipped by `logaddexp`.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| #31 RRF | Raw input score |
| Feedback loop | Provides the (score, label) training pairs |

| Downstream | Reason |
|---|---|
| UI suggestion card | Shows calibrated % |
| #50 Conformal Prediction | Alt uncertainty estimate; operators can use either |

## 15 · Governance checklist

- [ ] `platt_calibration.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows
- [x] `FEATURE-REQUESTS.md` entry
- [x] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry
- [x] Helper module (PR-L)
- [ ] Benchmark module
- [x] Test module (PR-L)
- [ ] TPE search space declared
- [ ] Ranker + UI wired (W3 + W4)
