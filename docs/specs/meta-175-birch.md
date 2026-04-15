# META-175 — BIRCH

## Overview
**Category:** Hierarchical clusterer for large data (streaming-capable)
**Extension file:** `birch.cpp`
**Replaces/improves:** `sklearn.cluster.Birch` Python CF-tree insertion loop
**Expected speedup:** ≥10x over sklearn for N=500k, d=64
**RAM:** <400 MB | **Disk:** <1 MB

## Algorithm

```
Input: stream/batch of points X ∈ ℝ^{N×d}, branching factor B, threshold T
Output: CF-tree T_final and flat labels c

CF = (N, LS, SS)                 # count, linear sum, squared sum
radius(CF) = √( SS/N − (LS/N)² )

for each new point x:
    descend CF-tree from root, choosing nearest CF per node
    if nearest leaf-CF absorbs x without radius > T:
        absorb: N += 1; LS += x; SS += x·x
    else:
        create new leaf entry; if node has > B entries, split via farthest-pair
        propagate merges/splits up toward root, rebuilding non-leaf CFs

optional: global clustering on leaf CFs (e.g. agglomerative or k-means)
```

- **Time complexity:** O(N · log_{B}(#leaves) · d) insertion; O(L²) for global step
- **Space complexity:** O(#CF-entries · d), bounded by memory budget
- **Convergence:** Deterministic single scan; two-scan mode refines boundary absorptions

## Academic Source
Zhang T., Ramakrishnan R., Livny M., "BIRCH: an efficient data clustering method for very large databases," *Proc. ACM SIGMOD 1996*, pp. 103–114. DOI: 10.1145/233269.233324

## C++ Interface (pybind11)

```cpp
// BIRCH CF-tree fit with optional global clustering step
void birch_fit(
    const float* X, int N, int d,
    int branching_factor, float threshold,
    int n_clusters_hint,
    int* out_labels, int* out_n_subclusters
);
```

## Memory Budget
- Runtime RAM: <400 MB for N=500k, d=64 (CF-tree leaves bounded by threshold)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: arena-backed CF nodes; `reserve()` based on estimated leaf count

## Performance Target
- Python baseline: `sklearn.cluster.Birch()`
- Target: ≥10x faster for N=500k, d=64
- Benchmark: N ∈ {50k, 500k, 2M}, d ∈ {8, 64}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. Insertion is single-threaded (CF-tree mutation is not safely concurrent); final global step may be parallelised.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. Arena/pool/RAII only. `reserve()` before fills. CF nodes pool-allocated.

**Object lifetime:** Self-assignment safe. Splits must correctly release old nodes back to the pool.

**Type safety:** Explicit `static_cast` for narrowing. No signed/unsigned mismatch on indices.

**SIMD:** AVX2 FMA for CF radius and merge calculations. `_mm256_zeroupper()` at epilogue. `alignas(64)` on LS/SS vectors.

**Floating point:** Flush-to-zero on init. NaN/Inf checks on X. Double accumulator for SS (catastrophic cancellation risk). Protect radius sqrt against small negatives from FP rounding.

**Performance:** No `std::endl` loops. No `std::function` hot loops. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all. Reject B<2, threshold≤0.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. Scrub sensitive memory.

Full rules: see `backend/extensions/CPP-RULES.md`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_175.py` | ARI ≥0.9 vs. sklearn Birch on blobs |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥10x faster than sklearn Birch |
| 5 | `pytest test_edges_meta_175.py` | Single point, duplicates, threshold=∞, branching=2 handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None for insertion; META-168 or agglomerative hierarchy for optional global step

## Pipeline Stage Non-Conflict
- **Owns:** Streaming/large-N clustering when N exceeds RAM for other metas.
- **Alternative to:** META-168 (k-means) for huge datasets.
- **Coexists with:** k-means (META-168) used as global finaliser on BIRCH subclusters.
- No conflict with ranking: offline clustering only.

## Test Plan
- Stream 1M synthetic points, verify subcluster count ≤ budget
- Threshold sweep: small T → many subclusters; large T → few
- Duplicates: verify absorbed into same CF
- Branching factor 2 vs 50: verify both finish, compare quality
- N=2M: verify RAM stays under budget
