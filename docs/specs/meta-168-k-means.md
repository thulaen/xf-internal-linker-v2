# META-168 — k-means (Lloyd's algorithm)

## Overview
**Category:** Partitioning clusterer
**Extension file:** `kmeans.cpp`
**Replaces/improves:** `sklearn.cluster.KMeans` Python fit loop on embedding centroids
**Expected speedup:** ≥10x over sklearn for N=50k, d=768
**RAM:** <500 MB | **Disk:** <1 MB

## Algorithm

```
Input: points X ∈ ℝ^{N×d}, cluster count K, max_iters
Output: cluster assignments c ∈ {0..K-1}^N and centroids μ ∈ ℝ^{K×d}

initialise μ via k-means++ seeding
repeat until convergence or max_iters:
    # assignment step
    c_i = argmin_j ||x_i − μ_j||²

    # update step (MacQueen / Lloyd)
    μ_j = (1 / |C_j|) · Σ_{x ∈ C_j} x

    if Σ_i ||x_i − μ_{c_i}||² changes by < tol: break
```

- **Time complexity:** O(iters · N · K · d)
- **Space complexity:** O(N + K·d)
- **Convergence:** Monotone decrease of WCSS; local minimum (not global)

## Academic Source
MacQueen J., "Some methods for classification and analysis of multivariate observations," *Proc. 5th Berkeley Symp. on Math. Stat. and Prob.*, 1967. Lloyd S.P., "Least squares quantization in PCM," *IEEE Trans. Information Theory* 28(2):129–137, 1982. DOI: 10.1109/TIT.1982.1056489

## C++ Interface (pybind11)

```cpp
// k-means with k-means++ init; returns cluster labels and centroids
void kmeans_fit(
    const float* X, int N, int d,
    int K, int max_iters, float tol,
    int* out_labels, float* out_centroids, int* out_iters, float* out_inertia
);
```

## Memory Budget
- Runtime RAM: <500 MB for N=50k, d=768, K=256 (double-buffered centroids)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: contiguous `std::vector<float>` for centroids, labels arena-backed

## Performance Target
- Python baseline: `sklearn.cluster.KMeans(n_init=1)`
- Target: ≥10x faster for N=50k, d=768, K=64
- Benchmark: N ∈ {1k, 50k, 200k}, d ∈ {64, 768}, K ∈ {8, 64, 256}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. Parallel assignment via OpenMP with `schedule(static)`; atomics on cluster-size counters document memory ordering.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. Arena/pool/RAII only. `reserve()` before fills.

**Object lifetime:** Self-assignment safe. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing. No signed/unsigned mismatch.

**SIMD:** AVX2 `_mm256_fmadd_ps` for distance compute. `_mm256_zeroupper()` at epilogue. Max 12 YMM. `alignas(64)` on centroid buffers.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks on X. Kahan summation for centroid update when N>100k.

**Performance:** No `std::endl` loops. No `std::function` hot loops. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all. Handle empty clusters by re-seeding farthest point.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. Scrub sensitive memory.

Full rules: see `backend/extensions/CPP-RULES.md`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_168.py` | Same ARI ≥0.95 vs. sklearn on synthetic blobs |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥10x faster than sklearn |
| 5 | `pytest test_edges_meta_168.py` | K=1, K=N, duplicates, empty clusters handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- k-means++ seeder (vendored inside this module)

## Pipeline Stage Non-Conflict
- **Owns:** Partitioning clustering of embeddings / feature vectors.
- **Alternative to:** META-169 (k-medoids), META-173 (Mean Shift), META-174 (Affinity Propagation).
- **Coexists with:** Near-duplicate clustering UI (FR-014) can consume k-means labels.
- No conflict with ranking: clustering output feeds offline diversification, not scoring.

## Test Plan
- Three Gaussian blobs: verify recovers centroids within 5% after 20 iters
- K=1: verify μ = mean of all X
- K=N: verify each point in its own cluster
- Duplicates: verify stable labels (deterministic tie-break)
- NaN input: verify raises ValueError
