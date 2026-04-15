# META-237 — Local Outlier Factor (LOF)

## Overview
**Category:** Anomaly detection — density based
**Extension file:** `lof.cpp`
**Replaces/improves:** Global z-score or fixed threshold flagging
**Expected speedup:** ≥8x over `sklearn.neighbors.LocalOutlierFactor`
**RAM:** <96 MB | **Disk:** <1 MB

## Algorithm

```
Input: samples X ∈ ℝ^{n×d}, neighbour count k
Output: LOF score per sample (higher = more anomalous)

k-distance(p) = distance from p to its k-th nearest neighbour
N_k(p)        = set of k nearest neighbours of p

reach-dist_k(p, o) = max(k-distance(o), d(p, o))

local reachability density (paper, eq. 3):
  lrd_k(p) = 1 / ( (1/k) · Σ_{o ∈ N_k(p)} reach-dist_k(p, o) )

Local Outlier Factor (paper, eq. 4):
  LOF_k(p) = (1/k) · Σ_{o ∈ N_k(p)} ( lrd_k(o) / lrd_k(p) )

Interpretation:
  LOF_k(p) ≈ 1    → point has similar density to its neighbours
  LOF_k(p) >> 1  → point is in a sparser region than its neighbours → outlier
```

- **Time complexity:** O(n·k) after kNN; O(n·log n·d) with VP-tree (or O(n²·d) brute force)
- **Space complexity:** O(n·k) for neighbour lists plus O(n) lrd

## Academic Source
Breunig, M. M., Kriegel, H.-P., Ng, R. T., and Sander, J. "LOF: Identifying density-based local outliers." Proceedings of the 2000 ACM SIGMOD International Conference on Management of Data, pp. 93–104. DOI: 10.1145/342009.335388

## C++ Interface (pybind11)

```cpp
// Compute LOF scores (higher = more anomalous)
std::vector<float> lof_fit_predict(
    const float* X, int n, int d,
    int k_neighbours,
    bool use_vp_tree  // false → brute force (small n)
);
```

## Memory Budget
- Runtime RAM: <96 MB (neighbour indices + lrd + scratch for n≤100k, k=20)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(n*k)`

## Performance Target
- Python baseline: `sklearn.neighbors.LocalOutlierFactor`
- Target: ≥8x faster via SIMD pairwise distance + VP-tree
- Benchmark: 1k, 10k, 100k samples × d=16, k=20

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. RAII only.

**Object lifetime:** Self-assignment safe. No dangling refs.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Max 12 YMM. `alignas(64)` on X.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for lrd averages. Division by lrd clamped `max(·, 1e-12)` to avoid inf when k duplicates.

**Performance:** No `std::endl` loops. No `std::function` hot loops. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. No `printf(user_string)`. No TOCTOU.

Full reference: `backend/extensions/CPP-RULES.md`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_237.py` | Output matches sklearn LOF within 1e-4 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥8x faster than Python reference |
| 5 | `pytest test_edges_meta_237.py` | All-duplicate samples, n<k, n=1 all handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Depends on META-165 / META-216 (VP-tree or k-NN) for neighbour search
- Co-exists with META-238 One-class SVM and META-239 Elliptic envelope

## Pipeline Stage Non-Conflict
- **Owns:** density-ratio outlier score
- **Alternative to:** META-238 (boundary model), META-239 (covariance model)
- **Coexists with:** META-240 autoencoder reconstruction error (orthogonal signal)

## Test Plan
- 2D gaussian blobs + one isolated point: verify isolated point's LOF >> 1
- All points identical: verify LOF = 1 for every sample (or NaN guarded)
- k > n-1: verify raises ValueError
- Large k on uniform grid: verify LOF approximately 1 everywhere
