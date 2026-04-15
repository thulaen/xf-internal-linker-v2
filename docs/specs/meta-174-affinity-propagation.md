# META-174 — Affinity Propagation

## Overview
**Category:** Exemplar-based clusterer (message passing)
**Extension file:** `affinity_propagation.cpp`
**Replaces/improves:** `sklearn.cluster.AffinityPropagation` Python loop
**Expected speedup:** ≥6x over sklearn for N=2k
**RAM:** <200 MB | **Disk:** <1 MB

## Algorithm

```
Input: similarity matrix s ∈ ℝ^{N×N}, damping λ ∈ [0.5, 1), max_iters
Output: exemplar indices E and cluster assignments c

initialise responsibilities r and availabilities a to 0

repeat until convergence or max_iters:
    # responsibility
    r(i, k) = s(i, k) − max_{k' ≠ k} ( a(i, k') + s(i, k') )

    # availability
    a(i, k) = min(0, r(k, k) + Σ_{i' ∉ {i, k}} max(0, r(i', k)))     # i ≠ k
    a(k, k) = Σ_{i' ≠ k} max(0, r(i', k))

    damp: r ← λ·r_old + (1−λ)·r_new;  a ← λ·a_old + (1−λ)·a_new

exemplars E = { k : r(k, k) + a(k, k) > 0 }
c_i = argmax_{k ∈ E} s(i, k)
```

- **Time complexity:** O(iters · N²)
- **Space complexity:** O(N²)
- **Convergence:** Empirically converges with damping 0.5–0.9; not guaranteed in pathological cases

## Academic Source
Frey B.J., Dueck D., "Clustering by passing messages between data points," *Science* 315(5814):972–976, 2007. DOI: 10.1126/science.1136800

## C++ Interface (pybind11)

```cpp
// Affinity propagation with damping; writes labels and exemplar indices
void affinity_propagation_fit(
    const float* similarity_matrix, int N,
    float damping, int max_iters, float tol,
    int* out_labels, int* out_exemplars, int* out_n_exemplars
);
```

## Memory Budget
- Runtime RAM: <200 MB for N=2k (three N×N matrices r, a, s)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: three `std::vector<float>` matrices sized N², `reserve()` up-front

## Performance Target
- Python baseline: `sklearn.cluster.AffinityPropagation()`
- Target: ≥6x faster for N=2k
- Benchmark: N ∈ {200, 2k, 5k}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. Row-parallel r and a updates via OpenMP; no shared writes across threads.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. Arena/pool/RAII only. `reserve()` before fills. N² matrices guarded against `N > RAM_LIMIT/12`.

**Object lifetime:** Self-assignment safe. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing. No signed/unsigned mismatch on indices.

**SIMD:** AVX2 FMA for message updates. `_mm256_zeroupper()` at epilogue. `alignas(64)` on matrix rows.

**Floating point:** Flush-to-zero on init. NaN/Inf checks on s. Damping λ clamped to `[0.5, 0.999]`. Double accumulator for `Σ max(0, r)` reductions.

**Performance:** No `std::endl` loops. No `std::function` hot loops. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all. Reject N<1 and invalid damping.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. Scrub sensitive memory.

Full rules: see `backend/extensions/CPP-RULES.md`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_174.py` | ARI ≥0.95 vs. sklearn on synthetic blobs |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥6x faster than sklearn |
| 5 | `pytest test_edges_meta_174.py` | Constant similarities, all-self preference, no convergence handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (standalone; can consume precomputed similarity)

## Pipeline Stage Non-Conflict
- **Owns:** Exemplar-based clustering when K is unknown and a similarity matrix is available.
- **Alternative to:** META-168 (k-means), META-169 (k-medoids), META-173 (Mean Shift).
- **Coexists with:** Similarity-matrix builders from the ranker (cosine/BM25 kernels).
- No conflict with ranking: AP is offline.

## Test Plan
- Three well-separated blobs: verify 3 exemplars and ARI ≥0.95 against labels
- Preference = median(s): verify sensible cluster count
- Non-converging input (no damping): verify raises ConvergenceWarning
- N=5k: verify runtime budget respected
- NaN similarities: verify raises ValueError
