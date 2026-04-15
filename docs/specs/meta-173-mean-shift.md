# META-173 — Mean Shift Clustering

## Overview
**Category:** Mode-seeking clusterer
**Extension file:** `mean_shift.cpp`
**Replaces/improves:** `sklearn.cluster.MeanShift` Python loop
**Expected speedup:** ≥8x over sklearn for N=10k, d=64
**RAM:** <200 MB | **Disk:** <1 MB

## Algorithm

```
Input: points X ∈ ℝ^{N×d}, bandwidth h, kernel K (Gaussian/Epanechnikov)
Output: mode assignments c and discovered modes {μ_j}

for each seed x ∈ X:
    x_t ← x
    repeat until convergence:
        m(x_t) = ( Σ_i K(x_t − x_i) · x_i ) / ( Σ_i K(x_t − x_i) )  − x_t
        x_t ← x_t + m(x_t)
    record converged mode

merge modes within tolerance h/2; assign labels by nearest mode
```

- **Time complexity:** O(iters · N² · d) brute; O(iters · N · log N · d) with ball-tree
- **Space complexity:** O(N + M) where M = # modes
- **Convergence:** Proven convergent for Epanechnikov kernel (flat top); empirically convergent for Gaussian

## Academic Source
Comaniciu D., Meer P., "Mean shift: a robust approach toward feature space analysis," *IEEE Trans. Pattern Analysis and Machine Intelligence* 24(5):603–619, 2002. DOI: 10.1109/34.1000236

## C++ Interface (pybind11)

```cpp
// Mean shift with Gaussian or Epanechnikov kernel
void mean_shift_fit(
    const float* X, int N, int d,
    float bandwidth, int kernel_id,
    int max_iters, float tol,
    int* out_labels, float* out_modes, int* out_n_modes
);
```

## Memory Budget
- Runtime RAM: <200 MB for N=10k, d=64 (ball-tree arena + mode table)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: arena-backed ball-tree nodes, `reserve()` mode buffer up-front

## Performance Target
- Python baseline: `sklearn.cluster.MeanShift(bin_seeding=False)`
- Target: ≥8x faster for N=10k, d=64
- Benchmark: N ∈ {1k, 10k, 50k}, d ∈ {2, 64}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. Per-seed trajectories parallelised via OpenMP; mode merging is sequential at the end.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. Arena/pool/RAII only. `reserve()` before fills.

**Object lifetime:** Self-assignment safe. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing. No signed/unsigned mismatch on indices.

**SIMD:** AVX2 FMA for kernel weight and weighted-mean compute. `_mm256_zeroupper()` at epilogue. `alignas(64)` on trajectory buffers.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Guard `Σ K = 0` with a small-mass fallback. Double accumulator for weighted mean.

**Performance:** No `std::endl` loops. No `std::function` hot loops. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all. Reject bandwidth ≤ 0.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. Scrub sensitive memory.

Full rules: see `backend/extensions/CPP-RULES.md`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_173.py` | ARI ≥0.95 vs. sklearn on synthetic blobs |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥8x faster than sklearn |
| 5 | `pytest test_edges_meta_173.py` | Small bandwidth (all singletons), large bandwidth (one mode) handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Ball-tree primitive (vendored; considered for sharing if another meta needs it)

## Pipeline Stage Non-Conflict
- **Owns:** Mode-seeking clustering without predefined K.
- **Alternative to:** META-168 (k-means), META-169 (k-medoids), META-174 (Affinity Propagation).
- **Coexists with:** Near-duplicate UI (FR-014) — Mean Shift selectable when K is unknown.
- No conflict with ranking: offline clustering only.

## Test Plan
- Two Gaussian blobs with h = σ: verify 2 modes found within tolerance
- Very small bandwidth: verify ~N modes (near-identity)
- Very large bandwidth: verify a single mode
- Flat kernel vs. Gaussian: verify both converge on clean data
- NaN input: verify raises ValueError
