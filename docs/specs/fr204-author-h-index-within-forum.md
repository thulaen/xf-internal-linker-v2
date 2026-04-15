# FR-204 - Author H-Index Within Forum

## Overview
Hirsch's `h`-index measures both productivity and impact in a single integer: an author has `h`-index `h` if at least `h` of their publications have been cited at least `h` times each. Adapted to a forum, this becomes "an author has `h`-index `h` if at least `h` of their posts have received at least `h` upvotes/likes/positive reactions each". Used as an additive author-trust boost so consistently impactful authors rank above one-hit-wonders and one-shot accounts.

## Academic source
**Hirsch, J. E. (2005).** "An Index to Quantify an Individual's Scientific Research Output." *Proceedings of the National Academy of Sciences (PNAS)*, vol. 102, no. 46, pp. 16569-16572. DOI: `10.1073/pnas.0507655102`. The original `h`-index definition (§II) and its rank-based interpretation (§III) form the basis for this signal.

## Formula
For author `u`, sort posts `p₁, p₂, …, p_n` in *descending* order of upvote count `c(p_i)`. The forum H-index is:
```
h(u) = max { k ∈ ℕ : c(p_k) ≥ k }                  (Hirsch Eq. 1, adapted)
```

Equivalently:
```
h(u) = |{ p ∈ posts(u) : c(p) ≥ rank(p) }|         where rank uses descending order
```

Time-decay variant (`h_α`-index) for forum freshness:
```
h_α(u) = max { k : c(p_k) · exp(−α · age_days(p_k)) ≥ k },   α = 0.005
```

Final additive boost (mapped to `[0, 1]`):
```
h_boost(u) = min(1.0, h(u) / h_norm),   h_norm = 50  (per-forum tunable)
```

## Starting weight preset
```python
"author_h_index.enabled": "true",
"author_h_index.ranking_weight": "0.0",
"author_h_index.use_time_decay": "true",
"author_h_index.alpha_decay": "0.005",
"author_h_index.h_norm": "50",
"author_h_index.metric": "upvotes",     # or "likes" or "positive_reactions"
```

## C++ implementation
- File: `backend/extensions/author_h_index.cpp`
- Entry: `int h_index(const int* citation_counts, int n);`  ·  `double h_index_decayed(const int* counts, const double* ages, int n, double alpha);`
- Complexity: `O(n log n)` for the descending sort + `O(n)` linear scan
- Thread-safety: pure function on a per-author array; computed in parallel across authors via OpenMP
- SIMD: `_mm256_max_epi32` accelerates the descending sort prefix scan
- Builds against pybind11

## Python fallback
`backend/apps/pipeline/services/author_h_index.py::h_index(...)` — uses `numpy.sort` and a vectorised linear scan.

## Benchmark plan
| Authors × posts | C++ target | Python target |
|---|---|---|
| 1 K × 50 | < 5 ms | < 50 ms |
| 10 K × 50 | < 50 ms | < 500 ms |
| 100 K × 100 | < 1 s | < 12 s |

## Diagnostics
- Per-author `h` and `h_α`
- Top-10 highest-h authors
- Distribution of `h` across all authors (median, p90, p99)
- Whether time-decay was applied
- C++ vs Python badge

## Edge cases & neutral fallback
- Author with 0 posts → `h = 0`, neutral
- Author with all-zero citation counts → `h = 0`
- Author with one massive post (e.g. 10 K upvotes, all other 0) → `h = 1` (by definition)
- Negative upvote count (downvoted) → clamped to `0` before sort, flag `negative_clamped`
- NaN / Inf in age → treat as `age = 0`, flag `nan_age`

## Minimum-data threshold
`≥ 5` posts per author before the score is trusted; below this returns neutral `0.0`.

## Budget
Disk: <1 MB  ·  RAM: <80 MB at 100 K authors × avg 100 posts (per-author int32 array)

## Scope boundary vs existing signals
FR-204 does NOT overlap with FR-006 weighted link graph (which scores *pages*, not authors) or FR-117 HITS hub score (which is graph-topology based). It is a *content-impact* author signal, distinct from FR-206 account-age gravity (tenure-based) and FR-208 mod endorsement (authority-based).

## Test plan bullets
- unit tests: author with `[10, 8, 5, 4, 3, 1]` upvotes → `h = 4`; author with `[2, 1]` → `h = 1`
- parity test: C++ vs Python `h` exactly equal (integer)
- decay test: `h_α(u)` ≤ `h(u)` always (decay can only lower the score)
- integration test: ranking unchanged when `ranking_weight = 0.0`
- monotonicity test: adding a new high-upvote post can only increase `h(u)`
- regression test: a power-poster with many low-impact posts is correctly placed below an occasional high-impact poster
