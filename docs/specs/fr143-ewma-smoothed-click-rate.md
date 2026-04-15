# FR-143 — EWMA Smoothed Click Rate

## Overview
Daily click counts on forum pages are noisy. An exponentially weighted moving average (EWMA) gives a smoothed estimate that responds to recent changes without overreacting to single-day spikes. FR-143 produces a per-page smoothed click-rate signal that complements FR-080 (freshness decay, time-since-last-update) and FR-136 (CUSUM, drift detection) by providing the *current best estimate* of click rate that the ranker uses for click-probability features. EWMA is the simplest, lowest-RAM smoother: O(1) memory per page.

## Academic source
Roberts, S. W. "Control chart tests based on geometric moving averages." *Technometrics*, 1(3), pp. 239–250, 1959. DOI: 10.1080/00401706.1959.10489860.

## Formula
For observed series `X_1, X_2, …`, the EWMA at time t is

```
S_t = α · X_t + (1 − α) · S_{t−1}
S_0 = X_1
```

where `0 < α ≤ 1` is the smoothing parameter. Equivalent expansion as weighted sum:

```
S_t = α · Σ_{k=0..t−1} (1 − α)^k · X_{t−k}  +  (1 − α)^t · S_0
```

Effective sample size (effective number of observations contributing significantly to `S_t`):

```
n_eff = (2 − α) / α
```

Variance under iid null:

```
Var(S_t) = σ² · (α / (2 − α)) · (1 − (1 − α)^{2t})
```

Half-life (lag at which weight drops to 0.5):

```
h = − ln 2 / ln(1 − α)
```

For α = 0.1 → half-life ≈ 6.6 observations. For α = 0.3 → half-life ≈ 1.94.

## Starting weight preset
```python
"ewma_smoothed.enabled": "true",
"ewma_smoothed.ranking_weight": "0.0",
"ewma_smoothed.alpha": "0.1",
"ewma_smoothed.warmup_observations": "5",
"ewma_smoothed.reset_on_gap_days": "30",
```

## C++ implementation
- File: `backend/extensions/ewma_smoothed.cpp`
- Entry: `double ewma_update(double prev_S, double x_new, double alpha)` plus `EwmaState ewma_batch(const double* x, int n, double alpha, double S0)`
- Complexity: O(1) per update; O(n) for batch. Trivially streaming.
- Thread-safety: state is per-page scalar (8 bytes) stored in DB; no shared state. No SIMD needed (purely sequential O(1) update). Memory: O(1) per page in RAM during update.

## Python fallback
`backend/apps/pipeline/services/ewma_smoothed.py::ewma_update`, `ewma_batch` (mirrors `pandas.Series.ewm(alpha=...).mean()`).

## Benchmark plan
| n updates | Python (ms) | C++ target (ms) | Speedup |
|---|---|---|---|
| 100 | 0.5 | <0.05 | ≥10x |
| 100,000 | 480 | <50 | ≥9x |
| 100,000,000 | 480,000 | <40,000 | ≥12x |

## Diagnostics
UI: numeric "smoothed clicks/day: 12.4 (raw today: 18)". Debug fields: `S_t_smoothed`, `alpha_used`, `effective_n`, `half_life_days`, `last_observation`, `last_update_ts`, `gap_days_since_last_update`.

## Edge cases & neutral fallback
First observation → `S_0 = X_1` (cold-start). Long gap (> reset_on_gap_days) → reset `S = X_new`. NaN input → carry `S` forward unchanged. α = 0 → `S` never updates (use ValueError). α = 1 → `S = X_new` always (no smoothing). Negative observation (impossible for click count) → ValueError. Underflow not possible (only multiplication and addition of finite values).

## Minimum-data threshold
After `warmup_observations` updates, `S_t` is reported with high confidence. Before warmup, it is reported but flagged as low-confidence in diagnostics.

## Budget
Disk: 8 bytes/page persistent state ·  RAM: <2 MB total for all pages

## Scope boundary vs existing signals
FR-080 (freshness decay) is a function of *time since update*, not an observed click rate. FR-136 (CUSUM) detects *deviation* from baseline, not the level itself. FR-137 (STL) decomposes into trend+seasonal+remainder; FR-143 produces a single smoothed level. FR-144/FR-145 (HyperLogLog) count unique visitors, not clicks. EWMA is the canonical "what is the current click rate?" signal.

## Test plan bullets
- Constant input `X_t = 10` → `S_t → 10` exponentially.
- Step input from 5 to 15 at t=50 → `S_t` reaches 0.95 · 15 + 0.05 · 5 = 14.5 by half-life × log_2(20) ≈ 28 steps after step.
- Single-spike input → `S_t` rises slightly then decays back.
- α = 1 → `S_t = X_t` (no smoothing).
- Long gap triggers reset, no division-by-zero.
- NaN input ignored, state preserved.
- Persistence: serialise `S_t`, deserialise, continue without loss.
- Compare against `pandas.ewm(alpha=α, adjust=False).mean()`: identical within float epsilon.
