# META-194 — Causal Forest

## Overview
**Category:** Causal inference (heterogeneous treatment effect via honest random forest)
**Extension file:** `causal_forest.cpp`
**Replaces/improves:** Parametric CATE models that impose functional form; plain RF that is not honest
**Expected speedup:** ≥4x over Python grf/econml reference implementation
**RAM:** <256 MB | **Disk:** <1 MB

## Algorithm

```
Input: n samples (X_i, T_i, Y_i), forest size B, subsample fraction s
Output: τ̂(x) for any query point x

for b = 1..B:
    draw subsample S_b of size ⌊s·n⌋
    split S_b in half: S_b^split, S_b^estim               // honest sample splitting
    grow tree on S_b^split, choosing splits to maximise heterogeneity of T-Y relationship
    for each leaf L:
        compute residualised score α_L using S_b^estim rows falling in L:
            τ̂_L = Σ_{i in L} (Y_i · (T_i − ê)) · w_i   /   Σ_{i in L} w_i · (T_i − ê)²
for query x:
    τ̂(x) = (1/B) · Σ_b τ̂_{L_b(x)}
```

- **Paper update rule (Athey/Tibshirani/Wager):** honest splitting (sample-splitting: split on half, estimate leaves on other half); leaf estimate `τ̂(x) = (1/n_L)·Σ_{i∈L(x)} (Y_i·(T_i − ê)·some weight)`
- **Time complexity:** O(B · n · log n) training; O(B · depth) inference per query
- **Space complexity:** O(B · n_leaves) tree storage

## Academic Source
Athey, S., Tibshirani, J. & Wager, S. (2019). "Generalized Random Forests". Annals of Statistics, Vol. 47, No. 2, pp. 1148-1178. DOI: 10.1214/18-AOS1709

## C++ Interface (pybind11)

```cpp
struct CausalForest {
    std::vector<uint8_t> opaque;    // serialised forest blob
    int n_trees;
};
CausalForest causal_forest_fit(
    const float* X, int n, int d,
    const uint8_t* T, const float* Y,
    int n_trees, float subsample_frac, int max_depth,
    int min_leaf_size, uint64_t rng_seed
);

std::vector<float> causal_forest_predict(
    const CausalForest& forest,
    const float* X_query, int n_query, int d
);
```

## Memory Budget
- Runtime RAM: <256 MB for n=1e5, d=50, B=500, depth=12 (~200 MB forest nodes)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: arena-backed node pool; no per-node `new`

## Performance Target
- Python baseline: `econml.grf.CausalForest`
- Target: ≥4x faster (parallel tree building, contiguous arena)
- Benchmark: 3 sizes — n=1e3/B=100, n=1e4/B=200, n=1e5/B=500

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

See `backend/extensions/CPP-RULES.md` for full mandate.

**Threading:** Per-tree OpenMP parallelism with thread-local RNG streams; no shared mutable.

**Memory:** Arena allocator for nodes. No raw `new`/`delete` per node. `reserve()` up front. Bounds-checked in debug.

**Object lifetime:** Forest blob owns arena; no dangling leaf pointers after serialisation.

**Type safety:** Explicit `static_cast` narrowing. `T ∈ {0,1}` validated.

**SIMD:** AVX2 FMA in leaf τ̂ reduction; `_mm256_zeroupper()` on exit. `alignas(64)` on node layout.

**Floating point:** Double accumulator in leaf residualisation. NaN/Inf entry checks on X, Y.

**Performance:** No `std::function` hot loops. No `dynamic_cast`. Histogram-split for continuous features.

**Error handling:** Destructors `noexcept`. Validate `min_leaf_size ≥ 2` for honest split feasibility. pybind11 catches.

**Build:** No cyclic includes. Static/anonymous namespace.

**Security:** No `system()`. No `printf(user_string)`. RNG state seeded per tree, not global.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_194.py` | Matches econml GRF within 5% on synthetic DGP |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥4x faster than econml GRF |
| 5 | `pytest test_edges_meta_194.py` | n=2 (degenerate), constant T, single-feature, min_leaf too big |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races across parallel trees |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None — self-contained tree builder; optional propensity input from META-191

## Pipeline Stage Non-Conflict
- **Owns:** Non-parametric heterogeneous CATE τ̂(x)
- **Alternative to:** META-195 (T/S/X meta-learners using any base regressor)
- **Coexists with:** META-193 (DR) — DR pseudo-outcomes can regularise honest-leaf τ̂ targets

## Test Plan
- Randomised trial with known τ(x) = 2·x_1: verify correlation ≥ 0.9 at n = 5000
- Constant T (all 0 or all 1): verify raises ValueError
- Identical features for every row: verify all trees become stumps with mean τ̂
- Honesty check: verify training rows used for splitting are excluded from leaf estimation
- RNG determinism: verify identical forest for identical seed
