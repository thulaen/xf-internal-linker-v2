# META-172 — OPTICS

## Overview
**Category:** Density-based cluster ordering
**Extension file:** `optics.cpp`
**Replaces/improves:** `sklearn.cluster.OPTICS` Python loop
**Expected speedup:** ≥8x over sklearn for N=50k, d=128
**RAM:** <400 MB | **Disk:** <1 MB

## Algorithm

```
Input: points X ∈ ℝ^{N×d}, maximum radius ε, minPts
Output: cluster ordering and per-point reachability distance

core_dist(p) = distance to minPts-th NN within ε (or UNDEFINED)
reachability(p) = max( core_dist(o), dist(o, p) )     # for predecessor o

initialise priority queue (min-heap by reachability)
for each unprocessed p:
    mark processed, emit p in ordering
    if core_dist(p) defined:
        update seeds: for q ∈ N_ε(p) unprocessed,
            new_reach = max(core_dist(p), dist(p, q))
            if q not in heap or new_reach < reach[q]:
                reach[q] = new_reach; push/decrease-key
    pop min-reachability seed as next p
```

- **Time complexity:** O(N log N) with k-d tree; O(N²) brute
- **Space complexity:** O(N) heap + ordering + reachability vector
- **Convergence:** Deterministic; order depends on tie-breaking of equal reachabilities

## Academic Source
Ankerst M., Breunig M.M., Kriegel H.-P., Sander J., "OPTICS: Ordering Points To Identify the Clustering Structure," *Proc. ACM SIGMOD 1999*, pp. 49–60. DOI: 10.1145/304182.304187

## C++ Interface (pybind11)

```cpp
// OPTICS ordering with reachability and core distance outputs
void optics_fit(
    const float* X, int N, int d,
    float eps, int min_pts,
    int* out_order, float* out_reachability, float* out_core_dist
);
```

## Memory Budget
- Runtime RAM: <400 MB for N=50k, d=128 (k-d tree + heap + arrays)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: arena-backed heap nodes; three `std::vector` outputs sized N

## Performance Target
- Python baseline: `sklearn.cluster.OPTICS`
- Target: ≥8x faster for N=50k, d=128
- Benchmark: N ∈ {10k, 50k, 200k}, d ∈ {8, 128}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. Heap is single-threaded; parallelise ε-neighbourhood queries with OpenMP, aggregate on the producer thread.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. Arena/pool/RAII only. `reserve()` before fills.

**Object lifetime:** Self-assignment safe. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing. No signed/unsigned mismatch on indices.

**SIMD:** AVX2 FMA for squared-L2 distance. `_mm256_zeroupper()` at epilogue. `alignas(64)` on buffers.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Sentinel `+inf` for UNDEFINED reachability.

**Performance:** No `std::endl` loops. No `std::function` hot loops. Use `std::priority_queue` carefully — no decrease-key; prefer "lazy deletion" or a pairing heap.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all. Reject `min_pts<1`, `eps≤0`.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. Scrub sensitive memory.

Full rules: see `backend/extensions/CPP-RULES.md`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_172.py` | Reachability plot matches sklearn within 1e-3 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥8x faster than sklearn |
| 5 | `pytest test_edges_meta_172.py` | All noise, duplicates, disconnected points handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- k-d tree primitive (shared with META-163/170/171)

## Pipeline Stage Non-Conflict
- **Owns:** Ordered reachability plot — foundation for multi-ε cluster extraction.
- **Alternative to:** META-170 (DBSCAN), META-171 (HDBSCAN).
- **Coexists with:** Downstream ξ-extraction OR HDBSCAN for cluster labels from the ordering.
- No conflict with ranking: runs offline only.

## Test Plan
- Nested density blobs: verify reachability plot shows correct "valleys"
- Uniform noise: verify reachability ≈ constant near ε
- Duplicates: verify reachability = 0 (or core distance)
- Invalid eps=0: verify raises ValueError
- N=200k: verify ≤180s on 8-core CPU
