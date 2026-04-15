# FR-147 — Count-Sketch Signed Frequency Estimator

## Overview
Count-Min (FR-146) only handles non-negative counts and is biased upward. Count-Sketch uses a second hash family that maps each item to `+1` or `−1`, allowing unbiased frequency estimates and supporting negative updates (e.g., decrementing when an event is removed). This makes Count-Sketch the preferred sketch for *changes* in anchor frequency over a sliding window — adds and deletes both work. FR-147 complements FR-146 (which serves the read-mostly case) by enabling streaming windowed analytics like "anchor frequency over last 30 days, with old days subtracted off".

## Academic source
Charikar, M., Chen, K., and Farach-Colton, M. "Finding frequent items in data streams." *Theoretical Computer Science*, 312(1), pp. 3–15, 2004 (extended from ICALP '02). DOI: 10.1016/S0304-3975(03)00400-6.

## Formula
Initialise a 2D array `C[d][w]` of zeros. Pick `d` pairwise-independent hash functions `h_i : U → [0, w)` and `d` independent sign hash functions `s_i : U → {−1, +1}`.

**Update** (insert item `x` with count `c`, possibly negative):
```
For i = 1..d:
  C[i][h_i(x)] += s_i(x) · c
```

**Estimate** (median-of-medians for unbiased frequency):
```
f̂(x) = median_{i = 1..d} ( s_i(x) · C[i][h_i(x)] )
```

The median is preferred over min (used by Count-Min) because Count-Sketch entries are signed and can be negative; the median is robust to both positive and negative collision noise. With probability `1 − δ`, the error satisfies

```
|f̂(x) − f(x)| ≤ ε · ‖f‖_2
```

(L₂ norm, not L₁), with parameters

```
w = ⌈ 3 / ε² ⌉
d = ⌈ 8 ln(1/δ) ⌉
```

For `ε = 0.01` and `δ = 0.01`: `w = 30,000`, `d = 37`. L₂ guarantee is tighter than L₁ for skewed distributions, making Count-Sketch better than Count-Min for heavy-hitter detection.

## Starting weight preset
```python
"count_sketch.enabled": "true",
"count_sketch.ranking_weight": "0.0",
"count_sketch.epsilon": "0.01",
"count_sketch.delta": "0.01",
"count_sketch.hash_function": "murmurhash3",
"count_sketch.sign_hash_seed": "0xC0FFEE",
```

## C++ implementation
- File: `backend/extensions/count_sketch.cpp`
- Entry: `void cs_update(int32_t* C, int d, int w, uint64_t hash, int sign_seed, int32_t c)`, `int32_t cs_estimate(const int32_t* C, int d, int w, uint64_t hash, int sign_seed)`
- Complexity: O(d) per update; O(d log d) per query (for sorting the d signed counts to take median; or O(d) using nth_element).
- Thread-safety: atomic increments under multi-threaded ingest. SIMD: estimate's d signed lookups vectorisable; median uses `std::nth_element`. Memory: `d · w · 4` bytes.

## Python fallback
`backend/apps/pipeline/services/count_sketch.py::CountSketch` (mirrors `streamlit-aggrid` and `bounter` reference implementations).

## Benchmark plan
| n updates | Python (ms) | C++ target (ms) | Speedup |
|---|---|---|---|
| 10,000 | 35 | <3 | ≥11x |
| 1,000,000 | 3,800 | <320 | ≥12x |
| 100,000,000 | 380,000 | <32,000 | ≥12x |

## Diagnostics
UI: numeric "anchor 'paywall' freq ≈ 217 (95% CI [195, 239])". Debug fields: `estimated_frequency`, `epsilon`, `delta`, `width_w`, `depth_d`, `negative_updates_count`, `median_signed_estimates`, `L2_norm_estimate`.

## Edge cases & neutral fallback
Empty sketch → all estimates 0. Negative result possible (unlike Count-Min); clip to 0 if interpreting as count, expose raw signed value otherwise. NaN inputs → ValueError. d even → median is mean of two middle values (slightly higher variance); recommend odd d. Hash and sign hashes must be independent (use different seeds).

## Minimum-data threshold
None — Count-Sketch is unbiased at any cardinality.

## Budget
Disk: ~4.4 MB per sketch at ε=0.01, δ=0.01 (37 × 30,000 × 4 B) ·  RAM: same; reduce w by relaxing ε for small-data scenarios

## Scope boundary vs existing signals
FR-146 (Count-Min) supports only non-negative updates and gives upper-bound estimates. FR-147 (Count-Sketch) supports signed updates and gives unbiased estimates with L₂ error guarantee. FR-148 (Space-Saving) tracks top-k items deterministically; FR-147 estimates frequency for *any* item. FR-150 (Lossy Counting) gives ε-approximate counts with deterministic guarantees but not signed.

## Test plan bullets
- Insert and delete same item equal times → estimate ≈ 0.
- Compare median-based estimate against exact `Counter`: error < ε·‖f‖_2 in 99% of trials.
- Hash and sign hashes independent: collision probability matches theoretical 1/w.
- d = 1 → degenerates to single estimate (no median benefit).
- Persistence: serialise signed C array, deserialise, continue.
- Concurrent atomic updates produce same result as sequential.
- Sliding window: add new day, subtract oldest day → estimate matches windowed exact count within ε·‖f‖_2.
- Negative-count input → estimate negative, exposed via `raw_signed_estimate`.
