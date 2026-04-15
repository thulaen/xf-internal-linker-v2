# META-170 — DBSCAN

## Overview
**Category:** Density-based clusterer
**Extension file:** `dbscan.cpp`
**Replaces/improves:** `sklearn.cluster.DBSCAN` Python neighbour-query loop
**Expected speedup:** ≥10x over sklearn for N=100k, d=128
**RAM:** <500 MB | **Disk:** <1 MB

## Algorithm

```
Input: points X ∈ ℝ^{N×d}, radius ε, minPts
Output: labels c ∈ {−1, 0, 1, ...}^N     (−1 = noise)

mark all points UNVISITED
for each p in X:
    if p is VISITED: continue
    mark p VISITED
    N_ε(p) = { q : ||q − p|| ≤ ε }
    if |N_ε(p)| < minPts: label[p] = NOISE
    else:
        start new cluster C
        expand cluster from p:
            for each q ∈ seed queue:
                if q unlabelled: label[q] = C
                if |N_ε(q)| ≥ minPts: add N_ε(q) \ queue to seed queue
```

- **Time complexity:** O(N log N) with k-d tree; O(N²) brute force
- **Space complexity:** O(N·d + average |N_ε|)
- **Convergence:** Deterministic single pass; order-independent cluster memberships (boundary points may vary)

## Academic Source
Ester M., Kriegel H.-P., Sander J., Xu X., "A density-based algorithm for discovering clusters in large spatial databases with noise," *Proc. KDD 1996*, pp. 226–231. DOI: 10.5555/3001460.3001507

## C++ Interface (pybind11)

```cpp
// DBSCAN using k-d tree; writes cluster labels
void dbscan_fit(
    const float* X, int N, int d,
    float eps, int min_pts,
    int* out_labels, int* out_n_clusters
);
```

## Memory Budget
- Runtime RAM: <500 MB for N=100k, d=128 (k-d tree arena + label buffer)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: arena-backed k-d tree nodes and seed queue, no per-query `new`

## Performance Target
- Python baseline: `sklearn.cluster.DBSCAN`
- Target: ≥10x faster for N=100k, d=128
- Benchmark: N ∈ {10k, 100k, 500k}, d ∈ {8, 128}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. Parallel ε-neighbourhood queries via OpenMP with per-thread seed buffers.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. Arena/pool/RAII only. `reserve()` before fills. Seed queue capped to N.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing. No signed/unsigned mismatch on indices.

**SIMD:** AVX2 FMA for squared-L2 distance in range queries. `_mm256_zeroupper()` at epilogue. `alignas(64)` on point buffers.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks on X. Use squared ε to avoid sqrt in inner loop.

**Performance:** No `std::endl` loops. No `std::function` hot loops. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all. Reject `min_pts < 1` and `eps ≤ 0`.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. Scrub sensitive memory.

Full rules: see `backend/extensions/CPP-RULES.md`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_170.py` | ARI ≥0.98 vs. sklearn on moons/blobs |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥10x faster than sklearn |
| 5 | `pytest test_edges_meta_170.py` | All noise, single cluster, duplicates, N=500k handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- k-d tree primitive (shared with META-163/171/172)

## Pipeline Stage Non-Conflict
- **Owns:** Density-based clustering with noise labelling.
- **Alternative to:** META-171 (HDBSCAN), META-172 (OPTICS).
- **Coexists with:** Near-duplicate clustering UI (FR-014) — DBSCAN is the baseline option.
- No conflict with ranking: runs offline only on feature/embedding spaces.

## Test Plan
- Two moons: verify recovers 2 clusters + minimal noise
- All-noise input (ε too small): verify labels all −1
- Single dense cluster: verify 1 cluster, 0 noise
- Duplicates: verify deterministic labelling
- N=500k: verify completes within 60s on 8-core CPU
