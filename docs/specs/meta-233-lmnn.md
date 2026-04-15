# META-233 — Large Margin Nearest Neighbour (LMNN)

## Overview
**Category:** Distance metric learning
**Extension file:** `lmnn.cpp`
**Replaces/improves:** Fixed Mahalanobis matrix from META-232; supervised distance fine-tuning
**Expected speedup:** ≥8x over `metric-learn` Python LMNN per epoch
**RAM:** <64 MB | **Disk:** <1 MB

## Algorithm

```
Input: labelled samples (x_i, y_i), k target neighbours, push weight c
Output: linear transform L ∈ ℝ^{d×d} (then M = LᵀL)

Objective (paper, eq. 4):
  ε(L) = Σ_{i, j→i} ‖L(x_i − x_j)‖²
       + c · Σ_{i, j→i, l}
             (1 − y_il) · (1 + ‖L(x_i − x_j)‖² − ‖L(x_i − x_l)‖²)_+

where:
  j → i  means j is a target neighbour of i (same class)
  y_il = 1 iff y_i = y_l
  (·)_+ = max(·, 0)

Optimisation: SDP or sub-gradient descent on L
  for epoch = 1..max_epochs:
    compute active imposters l that violate margin
    accumulate gradient G from pulls + hinge pushes
    L ← L − η · G
    (project M = LᵀL to PSD)
```

- **Time complexity:** O(epochs · n · k · |active_imposters| · d²)
- **Space complexity:** O(d²) for L plus O(n·k) for neighbour lists

## Academic Source
Weinberger, K. Q., Blitzer, J., and Saul, L. K. "Distance metric learning for large margin nearest neighbor classification." Advances in Neural Information Processing Systems 18 (NIPS 2005), pp. 1473–1480. DOI: 10.5555/2976248.2976433

## C++ Interface (pybind11)

```cpp
// Train LMNN and return linear transform L
std::vector<float> lmnn_fit(
    const float* X, const int* y, int n, int d,
    int k_target, float push_weight_c,
    int max_epochs, float lr, float tol
);
std::vector<float> lmnn_transform(const float* X, int n, int d,
                                  const float* L, int d_out);
```

## Memory Budget
- Runtime RAM: <64 MB (L + active imposter list + gradient buffer for n≤50k)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(n*k)`

## Performance Target
- Python baseline: `metric_learn.LMNN` per epoch
- Target: ≥8x faster via SIMD gradient and cached squared distances
- Benchmark: 1k, 10k, 50k samples × d=32, k=3

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. RAII only. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling refs.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Max 12 YMM. `alignas(64)` on L matrix.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for objective sum. Hinge clamped to 0 strictly.

**Performance:** No `std::endl` loops. No `std::function` hot loops. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. No `printf(user_string)`. No TOCTOU.

Full reference: `backend/extensions/CPP-RULES.md`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_233.py` | Output matches metric-learn LMNN within 5% on held-out kNN accuracy |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥8x faster than Python reference |
| 5 | `pytest test_edges_meta_233.py` | Single class, tiny n, degenerate features all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Depends on META-232 (Mahalanobis form uses M = LᵀL)
- Co-exists with META-234 (NCA) as alternative metric learner

## Pipeline Stage Non-Conflict
- **Owns:** LMNN SDP-style objective with target/imposter triplets
- **Alternative to:** META-234 NCA, META-235 ITML (different objectives)
- **Coexists with:** META-232 Mahalanobis (which only defines the quadratic form)

## Test Plan
- Iris dataset: verify kNN accuracy after LMNN ≥ kNN on Euclidean
- Single-class input: verify raises ValueError (no imposters exist)
- Random labels: verify objective does not diverge
- Already-linearly-separable data: verify early convergence
