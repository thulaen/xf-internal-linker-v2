# FR-134 — Kleinberg Burst Detection

## Overview
Forum threads and topic clusters often experience sudden bursts of activity (a thread that suddenly attracts many posts, a tag that suddenly trends). Kleinberg's burst-detection model labels intervals where the arrival rate of events shifts from a baseline state to an elevated state, complementing the existing per-page freshness and velocity signals (FR-007, FR-035, FR-072) by attaching a *state-machine* score rather than a raw rate. Pages currently in a "burst" state become more attractive link targets because they capture in-the-moment reader interest.

## Academic source
Kleinberg, J. "Bursty and hierarchical structure in streams." *Proceedings of the 8th ACM SIGKDD International Conference on Knowledge Discovery and Data Mining (KDD '02)*, pp. 91–101, 2002. DOI: 10.1145/775047.775061.

## Formula
Two-state HMM with states `q_0` (baseline rate `α_0`) and `q_1` (elevated rate `α_1 = s · α_0`, where `s > 1` is the scaling parameter). For an event sequence with inter-arrival gaps `x_1, …, x_n`, fit a state assignment `q = (q_{i_1}, …, q_{i_n})` minimising the cost

```
c(q) = Σ_{t=1..n} −ln f_{q_{i_t}}(x_t) + Σ_{t=1..n−1} τ(q_{i_t}, q_{i_{t+1}})
```

where `f_j(x) = α_j · exp(−α_j · x)` is the exponential gap density at state `j`, and the transition cost is

```
τ(i, j) = (j − i) · γ · ln n   if j > i
τ(i, j) = 0                    if j ≤ i
```

with `γ ≥ 0` controlling burst sensitivity. Burst weight at level 1 is `b = (t_end − t_start) · (α_1 − α_0)`.

## Starting weight preset
```python
"kleinberg_burst.enabled": "true",
"kleinberg_burst.ranking_weight": "0.0",
"kleinberg_burst.gamma": "1.0",
"kleinberg_burst.scale_s": "2.0",
"kleinberg_burst.min_events": "8",
```

## C++ implementation
- File: `backend/extensions/kleinberg_burst.cpp`
- Entry: `std::vector<BurstInterval> kleinberg_burst(const double* gaps, int n, double gamma, double s)`
- Complexity: O(n · k) where `k` is the number of states (k=2 here, so effectively O(n))
- Thread-safety: pure function, no shared state. SIMD: log/exp via `std::log1p` and pre-tabulated `α_j`. Memory: stack-allocated DP buffer of size `2n` doubles.

## Python fallback
`backend/apps/pipeline/services/kleinberg_burst.py::compute_burst_state`

## Benchmark plan
| n events | Python (ms) | C++ target (ms) | Speedup |
|---|---|---|---|
| 100 | 6 | <1 | ≥6x |
| 10,000 | 540 | <80 | ≥6x |
| 1,000,000 | 65,000 | <9,000 | ≥7x |

## Diagnostics
UI badge "Burst active" on a page when `state == 1`; debug fields `burst_state`, `burst_weight`, `burst_start_ts`, `burst_end_ts`, `gap_mean_baseline`, `gap_mean_burst`, `viterbi_cost`.

## Edge cases & neutral fallback
Empty gap sequence, single event, all identical timestamps (zero gaps → set ε floor of 1e-3 sec), `α_0 = 0` (return neutral 0.5), Viterbi underflow (work in log-space throughout), monotonically decreasing rate (no burst, return baseline).

## Minimum-data threshold
At least 8 events within the analysis window before burst score is non-neutral; below this, store `score = 0.5` and `state = neutral_insufficient_events`.

## Budget
Disk: <1 MB  ·  RAM: <8 MB per page (DP buffers freed after analysis)

## Scope boundary vs existing signals
FR-007 (link freshness) is a monotonic recency decay; FR-035 (link-network velocity) measures aggregate edge growth; FR-072 (trending velocity) measures view-rate slope. FR-134 is *binary state classification* via HMM, not a continuous decay or slope, so it captures regime *changes* the others miss.

## Test plan bullets
- Synthetic Poisson stream with rate-doubling at t=500 → burst detected within ±5 events of true onset.
- Synthetic stationary stream → no burst detected, `state = 0` throughout.
- Single event → neutral fallback, no exception.
- All-zero gaps → ε floor applied, no division-by-zero.
- `γ = 0` → trivially classifies every event as burst (sanity check).
- `γ → ∞` → never enters burst state (sanity check).
- Burst end correctly detected when rate returns to baseline.
- Score in `[0.5, 1.0]` and `state ∈ {0, 1}` always.
