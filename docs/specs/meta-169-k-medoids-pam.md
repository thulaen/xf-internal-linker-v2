# META-169 — k-medoids (PAM)

## Overview
**Category:** Partitioning clusterer (medoid-based, robust)
**Extension file:** `kmedoids_pam.cpp`
**Replaces/improves:** `sklearn_extra.cluster.KMedoids` Python PAM loop
**Expected speedup:** ≥8x over Python PAM for N=5k
**RAM:** <200 MB | **Disk:** <1 MB

## Algorithm

```
Input: points X ∈ ℝ^{N×d} (or pairwise distances D), cluster count K
Output: medoid indices M ⊂ {0..N-1} with |M|=K, and assignments c

# Build phase — greedy initial medoid selection
repeat K times: pick i* minimising Σ_i min_{m ∈ M} d(x_i, x_m)

# Swap phase
repeat until no swap improves cost:
    for each (m ∈ M, o ∉ M):
        compute ΔCost of replacing m with o
    apply best swap if ΔCost < 0

assign c_i = argmin_{m ∈ M} d(x_i, x_m)
minimise Σ_i d(x_i, μ_{C_i})     # total deviation objective
```

- **Time complexity:** O(K · (N−K)² · d) per swap iteration
- **Space complexity:** O(N²) if D precomputed, else O(N·d)
- **Convergence:** Monotone decrease of total deviation; local minimum

## Academic Source
Kaufman L. & Rousseeuw P.J., "Clustering by means of medoids," *Statistical Data Analysis Based on the L₁-Norm and Related Methods*, pp. 405–416, North-Holland, 1987. Later book reprint DOI: 10.1002/9780470316801

## C++ Interface (pybind11)

```cpp
// PAM with build + swap phases; returns medoid indices and labels
void kmedoids_pam(
    const float* X_or_D, int N, int d_or_precomputed,
    int K, int max_iters,
    int* out_medoids, int* out_labels, float* out_total_deviation
);
```

## Memory Budget
- Runtime RAM: <200 MB for N=5k distance matrix
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector<float>` distance cache, `reserve()` up-front

## Performance Target
- Python baseline: `sklearn_extra.cluster.KMedoids(method='pam')`
- Target: ≥8x faster for N=5k, K=16
- Benchmark: N ∈ {500, 5k, 20k}, K ∈ {8, 32}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. Parallel swap evaluation via OpenMP `reduction(min:)`.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. Arena/pool/RAII only. `reserve()` before fills. Distance matrix is the single biggest allocation — guard against `N² > budget`.

**Object lifetime:** Self-assignment safe. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing. No signed/unsigned mismatch on medoid indices.

**SIMD:** AVX2 FMA for distance compute when X is passed. `_mm256_zeroupper()` at epilogue. `alignas(64)` on distance rows.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for total-deviation objective.

**Performance:** No `std::endl` loops. No `std::function` hot loops. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all. Reject K > N.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. Scrub sensitive memory.

Full rules: see `backend/extensions/CPP-RULES.md`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_169.py` | Same medoids as sklearn_extra on synthetic blobs |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥8x faster than Python reference |
| 5 | `pytest test_edges_meta_169.py` | K=1, K=N, duplicates, sparse outliers handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (standalone; can consume precomputed distance)

## Pipeline Stage Non-Conflict
- **Owns:** Medoid-based robust clustering, especially for non-Euclidean distances.
- **Alternative to:** META-168 (k-means; PAM preferred for outlier-heavy data).
- **Coexists with:** Distance caches from ranker (e.g. cosine distance buffers).
- No conflict with ranking: PAM is offline only.

## Test Plan
- L₁ blobs: verify PAM beats k-means on outlier-contaminated data
- Precomputed D path: verify exact match with on-the-fly X path
- K=1: verify medoid = point minimising Σ d
- Zero-distance duplicates: verify deterministic medoid choice
- N<K: verify raises ValueError
