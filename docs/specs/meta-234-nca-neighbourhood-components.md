# META-234 — Neighbourhood Components Analysis (NCA)

## Overview
**Category:** Distance metric learning
**Extension file:** `nca.cpp`
**Replaces/improves:** Manual feature selection for kNN
**Expected speedup:** ≥7x over scikit-learn `NeighborhoodComponentsAnalysis` per epoch
**RAM:** <48 MB | **Disk:** <1 MB

## Algorithm

```
Input: labelled samples (x_i, y_i), transform dim d_out
Output: linear transform A ∈ ℝ^{d_out × d}

Softmax over neighbour probabilities (paper, eq. 1–2):
  p(x_i → x_j) = exp(−‖A·x_i − A·x_j‖²)
               / Σ_{k ≠ i} exp(−‖A·x_i − A·x_k‖²)
  p(x_i → x_i) = 0

Objective (paper, eq. 3):
  f(A) = Σ_i Σ_{j : y_j = y_i} p(x_i → x_j)

Gradient (paper, eq. 6):
  ∂f/∂A = 2·A · Σ_i ( p_i · Σ_k p_ik · x_ik · x_ikᵀ
                      − Σ_{j : y_j = y_i} p_ij · x_ij · x_ijᵀ )
  where x_ij = x_i − x_j

Optimise f(A) via gradient ascent (LBFGS or Adam).
```

- **Time complexity:** O(epochs · n² · d · d_out)
- **Space complexity:** O(n · d_out + d·d_out)

## Academic Source
Goldberger, J., Roweis, S., Hinton, G., and Salakhutdinov, R. "Neighbourhood components analysis." Advances in Neural Information Processing Systems 17 (NIPS 2005), pp. 513–520. DOI: 10.5555/2976040.2976105

## C++ Interface (pybind11)

```cpp
// Train NCA and return linear transform A
std::vector<float> nca_fit(
    const float* X, const int* y, int n, int d,
    int d_out, int max_epochs, float lr, float tol
);
std::vector<float> nca_transform(const float* X, int n, int d,
                                 const float* A, int d_out);
```

## Memory Budget
- Runtime RAM: <48 MB (softmax probabilities n×n for n≤2k; chunked for larger)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(n*n)` chunked

## Performance Target
- Python baseline: `sklearn.neighbors.NeighborhoodComponentsAnalysis`
- Target: ≥7x faster via fused softmax + gradient SIMD
- Benchmark: 500, 2k, 10k samples × d=32

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. RAII only. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling refs.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Max 12 YMM. `alignas(64)` on A matrix.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for softmax normaliser. Max-subtraction trick to prevent exp overflow.

**Performance:** No `std::endl` loops. No `std::function` hot loops. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. No `printf(user_string)`. No TOCTOU.

Full reference: `backend/extensions/CPP-RULES.md`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_234.py` | Output matches sklearn NCA within 5% on held-out kNN accuracy |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥7x faster than Python reference |
| 5 | `pytest test_edges_meta_234.py` | Single class, duplicate points, n=1 all handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Depends on META-232 (produces a metric used by downstream kNN)
- Co-exists with META-233 (LMNN) and META-235 (ITML) as alternative supervised metrics

## Pipeline Stage Non-Conflict
- **Owns:** softmax-based stochastic neighbour objective
- **Alternative to:** META-233 LMNN, META-235 ITML
- **Coexists with:** META-232 Mahalanobis (NCA produces the transform A that defines M = AᵀA)

## Test Plan
- Iris dataset: verify NCA improves 1-NN accuracy vs Euclidean
- d_out < d: verify dimensionality reduction preserves class structure
- Single class: verify raises ValueError
- Duplicate labels identical features: verify softmax stays finite
