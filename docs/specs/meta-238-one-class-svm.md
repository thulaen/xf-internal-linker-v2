# META-238 — One-class SVM

## Overview
**Category:** Anomaly detection — boundary
**Extension file:** `one_class_svm.cpp`
**Replaces/improves:** Manual thresholding when anomalies are rare and no labels exist
**Expected speedup:** ≥6x over `sklearn.svm.OneClassSVM`
**RAM:** <64 MB | **Disk:** <1 MB

## Algorithm

```
Input: samples X ∈ ℝ^{n×d}, ν ∈ (0, 1], kernel φ
Output: weight w, offset ρ, decision function

Primal (paper, eq. 10):
  min_w,ξ,ρ  (1/2)·‖w‖² − ρ + (1/(ν·N)) · Σ_i ξ_i
  subject to ⟨w, φ(x_i)⟩ ≥ ρ − ξ_i,   ξ_i ≥ 0

Dual (paper, eq. 13):
  min_α  (1/2) · Σ_ij α_i · α_j · K(x_i, x_j)
  subject to  0 ≤ α_i ≤ 1/(ν·N)
              Σ_i α_i = 1

Decision (paper, eq. 11):
  f(x) = sign( Σ_i α_i · K(x_i, x) − ρ )
  f(x) = +1  → inside / normal
  f(x) = −1  → outside / anomaly

ν bounds both the fraction of support vectors and the fraction of training outliers.

Optimisation: SMO (Sequential Minimal Optimisation) — see Platt 1998.
```

- **Time complexity:** O(iters · n²) for SMO; O(n_sv · d) per prediction
- **Space complexity:** O(n_sv · d) for support vectors plus O(n²) Gram matrix (chunked)

## Academic Source
Schölkopf, B., Williamson, R. C., Smola, A. J., Shawe-Taylor, J., and Platt, J. "Estimating the support of a high-dimensional distribution." Neural Computation 13, no. 7 (2001), pp. 1443–1471. DOI: 10.1162/089976601750264965

## C++ Interface (pybind11)

```cpp
// Train one-class SVM and predict anomaly indicator
struct OneClassSvmModel {
    std::vector<float> support_vectors;
    std::vector<float> dual_coefs;
    float rho;
    int kernel_type; float gamma;
};
OneClassSvmModel one_class_svm_fit(
    const float* X, int n, int d,
    int kernel_type, float gamma, float nu,
    float tol, int max_iters
);
std::vector<int> one_class_svm_predict(
    const OneClassSvmModel& m, const float* X, int n, int d
);
```

## Memory Budget
- Runtime RAM: <64 MB (chunked Gram + support vectors for n≤20k)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(n_sv*d)`

## Performance Target
- Python baseline: `sklearn.svm.OneClassSVM`
- Target: ≥6x faster via SIMD kernel evaluation + cached Gram blocks
- Benchmark: 1k, 5k, 20k samples × d=16

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. RAII only. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling refs.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Max 12 YMM. `alignas(64)` on support vectors.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for dual objective. Kernel `exp` argument clamped to avoid underflow.

**Performance:** No `std::endl` loops. No `std::function` hot loops. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. No `printf(user_string)`. No TOCTOU.

Full reference: `backend/extensions/CPP-RULES.md`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_238.py` | Predictions match sklearn OneClassSVM within 99% agreement |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥6x faster than Python reference |
| 5 | `pytest test_edges_meta_238.py` | ν=0 (edge), ν=1 (all outliers), degenerate kernel handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Standalone (SMO inner loop is self contained)
- Co-exists with META-237 LOF and META-239 Elliptic envelope as alternatives

## Pipeline Stage Non-Conflict
- **Owns:** support-vector boundary of the normal region
- **Alternative to:** META-237 LOF (local density), META-239 Elliptic envelope (covariance)
- **Coexists with:** META-240 autoencoder reconstruction error (different signal)

## Test Plan
- Clearly bi-modal 2D data: verify anomaly region is between modes
- All identical points: verify predicts +1 everywhere
- ν near 0 with outliers: verify model still trains (does not NaN)
- RBF kernel with very large γ: verify does not overflow
