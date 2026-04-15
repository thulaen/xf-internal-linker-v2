# FR-149 — T-Digest Quantile Tracker

## Overview
Many ranking decisions need quantiles, not means: "is this page's dwell time in the top 10% of the corpus?" requires the 90th percentile of dwell time, which a streaming sketch can estimate without storing the full series. T-Digest is a state-of-the-art quantile sketch with sub-1% error at the tails (where percentile estimates matter most for rank cutoffs) using KB of memory. FR-149 complements FR-076 (dwell-time profile match), FR-088 (save-bookmark rate), and isotonic-calibration (meta-09) by giving online quantile lookups for any continuous signal.

## Academic source
Dunning, T. "The t-digest: efficient estimates of distributions." *arXiv:1902.04023*, 2019. URL: https://arxiv.org/abs/1902.04023. (Earlier paper: Dunning, T. and Ertl, O. "Computing extremely accurate quantiles using t-digests." 2014, https://github.com/tdunning/t-digest.)

## Formula
Maintain a set of *centroids* `C = { (m_1, w_1), …, (m_n, w_n) }` where `m_i` is the centroid mean and `w_i` is its weight. Centroids are sorted by mean. The t-digest uses a *scale function* `k(q)` that controls centroid density across the quantile axis:

```
k(q) = (δ / 2π) · arcsin(2q − 1)
```

with normalising constant `δ` (compression parameter, typical δ = 100–200). The constraint on each centroid is

```
k(q_i + w_i / W) − k(q_i) ≤ 1
```

where `W = Σ w_i` is total weight and `q_i = (Σ_{j<i} w_j + w_i/2) / W` is the centroid's quantile position. This makes centroids dense near `q = 0` and `q = 1` (small `w_i`) and sparse near `q = 0.5` (large `w_i`), giving uniform relative accuracy at the tails.

**Insertion** (item `x` with weight 1):
1. Find nearest centroid by mean: `C_j = argmin_i |m_i − x|`.
2. If `w_j + 1` still satisfies the constraint, merge: `m_j ← (w_j · m_j + x) / (w_j + 1)`, `w_j ← w_j + 1`.
3. Else create a new centroid `(x, 1)`.
4. Periodically compress (e.g., every 5 · δ insertions): sort centroids by mean, traverse left-to-right re-merging where constraints allow.

**Quantile query** (`q ∈ [0, 1]`):
- Locate the two centroids whose cumulative quantiles bracket `q`.
- Linearly interpolate between their means.

Error: O(1/δ) absolute error in `q`, scaled by the local density `k'(q)`.

## Starting weight preset
```python
"t_digest.enabled": "true",
"t_digest.ranking_weight": "0.0",
"t_digest.compression_delta": "100",
"t_digest.compress_every_n_inserts": "500",
"t_digest.scale_function": "k1_arcsin",
```

## C++ implementation
- File: `backend/extensions/t_digest.cpp`
- Entry: `void td_add(TDigestState* state, double x, double weight)`, `double td_quantile(const TDigestState* state, double q)`
- Complexity: O(log δ) per insertion (binary search for nearest centroid in sorted vector); O(δ) for periodic compression. O(log δ) per quantile query.
- Thread-safety: per-instance state; concurrent inserts need a mutex (centroid array is shared). SIMD: distance search vectorisable. Memory: O(δ) doubles for means + weights ≈ 1.6 KB at δ=100.

## Python fallback
`backend/apps/pipeline/services/t_digest.py::TDigest` (mirrors `tdigest` PyPI package and `pyDigest`).

## Benchmark plan
| n insertions | Python (ms) | C++ target (ms) | Speedup |
|---|---|---|---|
| 10,000 | 32 | <3 | ≥10x |
| 1,000,000 | 3,500 | <300 | ≥11x |
| 100,000,000 | 380,000 | <32,000 | ≥11x |

## Diagnostics
UI: numeric "median dwell: 42s, p90: 220s, p99: 580s". Debug fields: `centroid_count`, `total_weight_W`, `compression_delta`, `quantile_estimates_p50_p90_p99`, `last_compression_at_n`, `min_observed`, `max_observed`.

## Edge cases & neutral fallback
Empty digest → quantile query returns NaN (or 0 with state flag). Single observation → quantile = that value for any q. Identical observations → all centroids merge into one. NaN/Inf input → ValueError. Compression must run before query for accuracy. q < 0 or q > 1 → ValueError. Weighted insertions (w > 1) supported for batched ingest.

## Minimum-data threshold
At least 50 observations before quantile queries are reliable (below this, single observations dominate centroids).

## Budget
Disk: ~1.6 KB per digest at δ=100 ·  RAM: O(δ) per active digest; for 1000 active digests at δ=100, total ~1.6 MB

## Scope boundary vs existing signals
FR-149 estimates *quantiles* (percentile rank); FR-143 (EWMA) estimates *mean*. Both are streaming summaries but answer different questions. FR-150 (Lossy Counting) tracks top items by frequency, not quantile cuts. Meta-09 (quantile normalizer) requires per-feature quantile distributions; FR-149 supplies these as online updates instead of batch recomputation.

## Test plan bullets
- Insert N(0, 1) Gaussian samples → estimated p50 ≈ 0, p84.13 ≈ 1, p97.72 ≈ 2 within 1% relative error.
- Tail accuracy: p99.9 within 1% of true.
- Identical observations → all merge; quantile query returns that value for any q.
- Single observation → quantile returns that value.
- Empty digest → NaN or neutral fallback.
- Compare to `scipy.stats.scoreatpercentile`: relative error < 1% at p10, p50, p90, p99.
- Persistence: serialise centroids, deserialise, continue.
- Merge two t-digests (concatenate centroids, then compress) → quantile of union matches single-pass estimate.
