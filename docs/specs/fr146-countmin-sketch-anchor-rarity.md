# FR-146 — Count-Min Sketch for Anchor Rarity

## Overview
Anchor-text rarity is a strong ranking signal — a rare anchor like "Helvetica typeface licensing dispute" is a more confident topical match than a common anchor like "click here". Storing exact frequencies for every n-gram requires gigabytes; a Count-Min Sketch estimates frequency for any item with bounded error using only KB. FR-146 complements FR-009 (learned anchor vocabulary) and FR-045 (anchor diversity) by providing fast O(1) estimated frequency lookups for arbitrary candidate anchors without needing the anchor to be pre-indexed.

## Academic source
Cormode, G. and Muthukrishnan, S. "An improved data stream summary: the count-min sketch and its applications." *Journal of Algorithms*, 55(1), pp. 58–75, 2005. DOI: 10.1016/j.jalgor.2003.12.001.

## Formula
Initialise a 2D array `C[d][w]` of zeros, where `d` = number of hash functions, `w` = width (number of buckets). Pick `d` pairwise-independent hash functions `h_1, …, h_d : U → [0, w)`.

**Update** (insert item `x` with count `c`):
```
For i = 1..d:
  C[i][h_i(x)] += c
```

**Estimate** (query item `x`):
```
f̂(x) = min_{i = 1..d} C[i][h_i(x)]
```

Error guarantee: with probability `1 − δ`, the estimate satisfies

```
f(x) ≤ f̂(x) ≤ f(x) + ε · ‖f‖_1
```

where `‖f‖_1` is the total count of all items, and the parameters are chosen as

```
w = ⌈ e / ε ⌉
d = ⌈ ln(1/δ) ⌉
```

For `ε = 0.001` and `δ = 0.01`: `w = 2719`, `d = 5`. Total memory: `d · w · 4` bytes ≈ 54 KB for these parameters.

**Conservative update** (Estan & Varghese variant, more accurate for skewed data):
```
m = min_{i = 1..d} C[i][h_i(x)]
For i = 1..d:
  C[i][h_i(x)] = max(C[i][h_i(x)], m + c)
```

## Starting weight preset
```python
"countmin_anchor.enabled": "true",
"countmin_anchor.ranking_weight": "0.0",
"countmin_anchor.epsilon": "0.001",
"countmin_anchor.delta": "0.01",
"countmin_anchor.use_conservative_update": "true",
"countmin_anchor.hash_function": "murmurhash3",
```

## C++ implementation
- File: `backend/extensions/countmin_anchor.cpp`
- Entry: `void cms_update(uint32_t* C, int d, int w, uint64_t hash, uint32_t c)`, `uint32_t cms_estimate(const uint32_t* C, int d, int w, uint64_t hash)`
- Complexity: O(d) per update and per query (constant for fixed d).
- Thread-safety: updates need atomic increments under multi-threaded ingest. SIMD: not applicable (d hash lookups are scalar, but `min` over d ≤ 8 fits in one AVX register). Memory: `d · w · 4` bytes per sketch.

## Python fallback
`backend/apps/pipeline/services/countmin_anchor.py::CountMinSketch` (mirrors `count-min-sketch` PyPI package).

## Benchmark plan
| n updates | Python (ms) | C++ target (ms) | Speedup |
|---|---|---|---|
| 10,000 | 22 | <2 | ≥11x |
| 1,000,000 | 2,400 | <200 | ≥12x |
| 100,000,000 | 240,000 | <20,000 | ≥12x |

## Diagnostics
UI: numeric "anchor 'click here' frequency ≈ 12,400 (±50)". Debug fields: `estimated_frequency`, `epsilon`, `delta`, `width_w`, `depth_d`, `total_count_L1`, `conservative_update_used`, `hash_seed`.

## Edge cases & neutral fallback
Empty sketch → all estimates 0. Hash collisions cause overestimation, never underestimation (CMS is biased *up*). Negative counts not supported (use Count-Sketch FR-147 instead). NaN inputs → ValueError. Width or depth of 0 → ValueError. Conservative update reduces overestimation but is not strictly cheaper to query.

## Minimum-data threshold
None — CMS is accurate at any cardinality, only the relative error scales with `‖f‖_1`.

## Budget
Disk: 54 KB per sketch at default ε=0.001, δ=0.01 ·  RAM: 54 KB × number of active sketches (e.g., per-silo: 50 silos × 54 KB = 2.7 MB)

## Scope boundary vs existing signals
FR-009 (learned anchor vocabulary) is a curated, exact list of approved anchors. FR-146 estimates frequency for *any* candidate anchor including ones not in the vocabulary. FR-045 (anchor diversity guard) measures repetition of *exact* anchors used; FR-146 estimates how rare an anchor is across the *whole corpus*. FR-147 (Count-Sketch) supports negative counts; FR-146 is for non-negative frequencies only.

## Test plan bullets
- Insert {a:5, b:3, c:1} → all estimates ≥ true value, none > true + ε·‖f‖_1.
- Compare against exact `Counter`: max overestimation < ε·‖f‖_1 in 99% of trials.
- Hash collisions never cause underestimation (estimate ≥ true count always).
- Conservative update reduces overestimation by ~30% vs naive update on Zipfian input.
- Empty sketch → all estimates 0.
- Width 0 → ValueError.
- Persistence: serialise C, deserialise, continue.
- Concurrent updates with atomic ops produce same result as sequential.
