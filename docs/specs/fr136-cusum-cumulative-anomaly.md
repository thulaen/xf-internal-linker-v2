# FR-136 — CUSUM Cumulative Anomaly Detector

## Overview
CUSUM (Cumulative Sum) is the oldest and most reliable online anomaly detector for slow drifts that escape simple threshold tests. For internal linking, CUSUM watches each page's daily click rate, view rate, and dwell time and raises a small "drift score" when a sustained shift accumulates. This complements FR-080 (freshness decay) and FR-135 (PELT) by being a *low-latency online* detector — it fires on the same day the drift starts, not after enough data accumulates to fit segments.

## Academic source
Page, E. S. "Continuous inspection schemes." *Biometrika*, 41(1/2), pp. 100–115, 1954. DOI: 10.1093/biomet/41.1-2.100.

## Formula
Two one-sided cumulative sums tracking positive and negative drift from a target mean `μ_0`:

```
S_t^+ = max(0, S_{t−1}^+ + (x_t − μ_0) − k)
S_t^− = max(0, S_{t−1}^− − (x_t − μ_0) − k)
S_0^+ = S_0^− = 0
```

where `k = δ · σ / 2` is the slack (allowed deviation), `δ` is the minimum shift size to detect (in σ units), and `σ` is the in-control standard deviation. An alarm is raised when

```
S_t^+ > h     (upward drift)
S_t^− > h     (downward drift)
h = h_σ · σ
```

Average run length (ARL) under control: `ARL_0 ≈ exp(2 h k / σ²) − 2 h k / σ² − 1` (Siegmund's approximation). The "drift score" exposed to the ranker is

```
drift_score = clip( max(S_t^+, S_t^−) / h, 0, 1 )
```

## Starting weight preset
```python
"cusum_anomaly.enabled": "true",
"cusum_anomaly.ranking_weight": "0.0",
"cusum_anomaly.delta_sigmas": "1.0",
"cusum_anomaly.threshold_h_sigmas": "5.0",
"cusum_anomaly.warmup_observations": "20",
```

## C++ implementation
- File: `backend/extensions/cusum_anomaly.cpp`
- Entry: `CusumState cusum_update(CusumState prev, double x, double mu, double sigma, double delta, double h)`
- Complexity: O(1) per update; O(n) for batch over `n` observations.
- Thread-safety: state is per-page, no global mutation. Each page's CUSUM state lives in `pages` table as serialised struct (16 bytes). No SIMD needed.

## Python fallback
`backend/apps/pipeline/services/cusum_anomaly.py::cusum_update`, `cusum_batch`

## Benchmark plan
| n updates | Python (μs) | C++ target (μs) | Speedup |
|---|---|---|---|
| 100 | 90 | <10 | ≥9x |
| 10,000 | 8,800 | <800 | ≥10x |
| 1,000,000 | 880,000 | <80,000 | ≥11x |

## Diagnostics
UI: small chip "drift up" / "drift down" / "in control" on each page. Debug fields: `cusum_pos`, `cusum_neg`, `mu_baseline`, `sigma_baseline`, `last_alarm_ts`, `drift_score`, `arl_estimate`.

## Edge cases & neutral fallback
σ = 0 (constant series) → set σ = 1e-6 floor, drift_score = 0. Missing observations → carry CUSUM state forward unchanged. Reset after alarm: `S^+ = S^− = 0` and re-estimate `μ_0` from next 20 observations. NaN input → ignore. Negative `h` or `δ` → raise ValueError. Warmup period: `drift_score = 0.0` until `warmup_observations` collected.

## Minimum-data threshold
20 observations to estimate `μ_0` and `σ` before drift score becomes non-neutral.

## Budget
Disk: 16 bytes/page persistent state ·  RAM: <2 MB total for all pages

## Scope boundary vs existing signals
FR-135 (PELT) is *retrospective* and detects multiple changepoints from full history. FR-136 is *online* and detects only the current drift in O(1) per update — it cannot identify past changepoints. FR-138 (Mann-Kendall) tests for monotonic trend over a fixed window; CUSUM is sequential and parameter-free in window length.

## Test plan bullets
- Constant `μ_0` synthetic stream → no alarm, `S^+ = S^− ≈ 0` throughout.
- Step shift `μ_0 → μ_0 + 2σ` at t=200 → alarm raised within `2σ²/(δ·σ − k)` ≈ 5 steps of true shift.
- Slow linear drift → alarm raised when accumulated deviation exceeds `h·σ`.
- σ = 0 input → no division-by-zero, drift_score = 0.
- NaN observation → state unchanged, no crash.
- Reset after alarm correctly recomputes `μ_0`.
- Persistence: serialise CusumState, deserialise, continue updating without loss.
- Bounds: `0 ≤ drift_score ≤ 1` always.
