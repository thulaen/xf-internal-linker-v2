# META-171 — HDBSCAN

## Overview
**Category:** Hierarchical density-based clusterer
**Extension file:** `hdbscan.cpp`
**Replaces/improves:** `hdbscan` Python package for embedding-space clustering
**Expected speedup:** ≥6x over Python hdbscan for N=50k, d=128
**RAM:** <600 MB | **Disk:** <1 MB

## Algorithm

```
Input: points X ∈ ℝ^{N×d}, minPts (min_cluster_size), min_samples
Output: flat labels c and per-cluster stabilities

# 1. Mutual reachability distance
core_k(p) = distance to minPts-th NN of p
d_mreach(p, q) = max( core_k(p), core_k(q), d(p, q) )

# 2. MST on complete graph using d_mreach (Prim/Boruvka)

# 3. Condensed hierarchy by removing edges in decreasing order:
#    when a branch shrinks below min_cluster_size, it becomes noise

# 4. Extract clusters maximising total stability
stability(C) = Σ_{p ∈ C} (1/ε_left(p) − 1/ε_birth(C))
select non-overlapping clusters with largest total stability
```

- **Time complexity:** O(N² d) brute MST; O(N·minPts + N log N) with Boruvka + k-d tree
- **Space complexity:** O(N) tree + O(N) stability table
- **Convergence:** Deterministic; no parameter tuning beyond min_cluster_size

## Academic Source
Campello R.J.G.B., Moulavi D., Sander J., "Density-based clustering based on hierarchical density estimates," *Proc. PAKDD 2013* (also KDD workshop 2013), LNCS 7819:160–172. DOI: 10.1007/978-3-642-37456-2_14

## C++ Interface (pybind11)

```cpp
// HDBSCAN with MST + condensed tree + stability extraction
void hdbscan_fit(
    const float* X, int N, int d,
    int min_cluster_size, int min_samples,
    int* out_labels, float* out_probabilities, float* out_stabilities
);
```

## Memory Budget
- Runtime RAM: <600 MB for N=50k, d=128 (MST edges + condensed tree)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: arena-backed MST edges and tree nodes, `reserve()` sized to N

## Performance Target
- Python baseline: `hdbscan.HDBSCAN()`
- Target: ≥6x faster for N=50k, d=128
- Benchmark: N ∈ {5k, 50k, 200k}, d ∈ {8, 128}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. Boruvka rounds parallelised; union-find with path compression uses atomics with `memory_order_relaxed` for rank, `memory_order_acq_rel` for parent.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. Arena/pool/RAII only. `reserve()` before fills.

**Object lifetime:** Self-assignment safe. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing. No signed/unsigned mismatch on node indices.

**SIMD:** AVX2 FMA for squared-L2 distances. `_mm256_zeroupper()` at epilogue. `alignas(64)` on point buffers.

**Floating point:** Flush-to-zero on init. NaN/Inf checks. Stability uses double accumulator; protect 1/ε where ε=0.

**Performance:** No `std::endl` loops. No `std::function` hot loops. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. Scrub sensitive memory.

Full rules: see `backend/extensions/CPP-RULES.md`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_171.py` | ARI ≥0.95 vs. Python hdbscan on blobs |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥6x faster than Python hdbscan |
| 5 | `pytest test_edges_meta_171.py` | min_cluster_size=N, all noise, duplicates handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- k-d tree primitive (shared with META-163/170/172)
- Union-find primitive (shared with MST-based metas)

## Pipeline Stage Non-Conflict
- **Owns:** Hierarchical density clustering with probabilistic soft assignments.
- **Alternative to:** META-170 (DBSCAN), META-172 (OPTICS).
- **Coexists with:** Near-duplicate clustering UI (FR-014) — HDBSCAN is a selectable backend.
- No conflict with ranking: runs offline only.

## Test Plan
- Multi-density blobs: verify HDBSCAN recovers more clusters than DBSCAN at a single ε
- min_cluster_size=N: verify exactly 1 cluster or all-noise
- Duplicates at core distance 0: verify no divide-by-zero
- Soft probabilities: verify sum ≤ 1 per point
- N=200k: verify ≤120s on 8-core CPU
