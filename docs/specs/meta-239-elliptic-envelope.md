# META-239 — Elliptic Envelope (Fast-MCD)

## Overview
**Category:** Anomaly detection — covariance based
**Extension file:** `elliptic_envelope.cpp`
**Replaces/improves:** Plain sample-covariance Mahalanobis outlier test (which breaks under contamination)
**Expected speedup:** ≥7x over `sklearn.covariance.EllipticEnvelope`
**RAM:** <32 MB | **Disk:** <1 MB

## Algorithm

```
Input: samples X ∈ ℝ^{n×d}, contamination α
Output: robust location μ̂, covariance Σ̂, outlier mask

Fast-MCD (paper, Section 2):
  h = ⌊(1 − α) · n⌋   (subset size, at least n/2)
  repeat R start-set draws:
    H₀ ← random h-subset
    for C-steps, k = 1..max_csteps:
      μ_k ← mean of X[H_{k-1}]
      Σ_k ← cov of X[H_{k-1}]
      d_i² ← (x_i − μ_k)ᵀ · Σ_k⁻¹ · (x_i − μ_k)
      H_k ← indices of h smallest d_i²
      if det(Σ_k) == det(Σ_{k-1}): break
  keep best H* = argmin_k det(Σ_k)

Threshold (paper, eq. 15):
  μ̂ ← mean on H*
  Σ̂ ← cov on H* (consistency-rescaled)
  outlier iff (x − μ̂)ᵀ · Σ̂⁻¹ · (x − μ̂) > χ²_{d, 1−α}
```

- **Time complexity:** O(R · max_csteps · n · d²)
- **Space complexity:** O(n + d²)

## Academic Source
Rousseeuw, P. J., and Van Driessen, K. "A fast algorithm for the minimum covariance determinant estimator." Technometrics 41, no. 3 (1999), pp. 212–223. DOI: 10.1080/00401706.1999.10485670

## C++ Interface (pybind11)

```cpp
// Robust location/covariance + anomaly mask via Fast-MCD
struct MCDResult {
    std::vector<float> location;      // μ̂, shape (d,)
    std::vector<float> covariance;    // Σ̂, shape (d, d)
    std::vector<int>   support_mask;  // indicator, shape (n,)
    std::vector<float> mahalanobis_sq; // shape (n,)
};
MCDResult fast_mcd_fit(
    const float* X, int n, int d,
    float contamination,
    int random_starts,
    int max_csteps,
    uint64_t seed
);
```

## Memory Budget
- Runtime RAM: <32 MB (Σ̂ + scratch for n≤100k, d≤64)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(n)`

## Performance Target
- Python baseline: `sklearn.covariance.EllipticEnvelope`
- Target: ≥7x faster via batched BLAS + shared Cholesky
- Benchmark: 1k, 10k, 100k samples × d=16, 32

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. Random starts can use `std::for_each(std::execution::par)` with per-thread RNGs.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. RAII only.

**Object lifetime:** Self-assignment safe. No dangling refs.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Max 12 YMM. `alignas(64)` on Σ̂.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for det. Cholesky adds ridge `1e-6·tr(Σ)/d` if singular.

**Performance:** No `std::endl` loops. No `std::function` hot loops. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. No `printf(user_string)`. No TOCTOU. Seeded RNG is deterministic.

Full reference: `backend/extensions/CPP-RULES.md`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_239.py` | μ̂, Σ̂ match sklearn MinCovDet within 1e-3 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥7x faster than Python reference |
| 5 | `pytest test_edges_meta_239.py` | Rank-deficient X, d>n, contamination=0 all handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Depends on META-241 (MCD core) — this spec wraps MCD with χ² thresholding
- Co-exists with META-237 LOF and META-238 One-class SVM

## Pipeline Stage Non-Conflict
- **Owns:** χ² Mahalanobis test using robust Σ̂
- **Alternative to:** META-237 LOF, META-238 One-class SVM
- **Coexists with:** META-241 MCD (MCD returns μ̂, Σ̂; this spec converts them into a boolean outlier mask)

## Test Plan
- Gaussian + 10% uniform contamination: verify ≥90% contaminated points flagged
- No contamination: verify outlier rate ≈ α chosen
- d > n: verify raises (cannot estimate covariance)
- Deterministic seed: verify same support_mask across runs
