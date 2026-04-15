# META-241 — Minimum Covariance Determinant (MCD)

## Overview
**Category:** Robust covariance estimation
**Extension file:** `mcd.cpp`
**Replaces/improves:** Sample covariance `numpy.cov` when data may be contaminated
**Expected speedup:** ≥8x over `sklearn.covariance.MinCovDet`
**RAM:** <32 MB | **Disk:** <1 MB

## Algorithm

```
Input: samples X ∈ ℝ^{n×d}, subset size h with ⌊(n+d+1)/2⌋ ≤ h ≤ n
Output: robust μ̂, Σ̂, and support set H* of size h

Core objective (paper, eq. 2):
  H* = argmin_{H ⊆ {1..n}, |H| = h}  det( cov(X[H]) )

Exhaustive search is infeasible. In practice: random starts + C-steps
(Rousseeuw & Van Driessen Fast-MCD; see also META-239):
  for each random start:
    H₀ ← random d+1 sized subset
    fit μ₀, Σ₀
    for k = 1..max_csteps:
      d_i² ← (x_i − μ_{k-1})ᵀ · Σ_{k-1}⁻¹ · (x_i − μ_{k-1})
      H_k ← indices of h smallest d_i²
      (μ_k, Σ_k) ← mean, covariance of X[H_k]
      if det(Σ_k) == det(Σ_{k-1}): break
  retain best H*

Rescale (paper, Section 4):
  c ← consistency factor  = median(d_i²) / χ²_{d, 0.5}
  Σ̂ ← c · Σ_best

The plain-paper definition (Rousseeuw 1984) is the combinatorial form; the
Fast-MCD heuristic is the standard computational path.
```

- **Time complexity:** O(starts · csteps · n · d²)
- **Space complexity:** O(n + d²)

## Academic Source
Rousseeuw, P. J. "Least median of squares regression." Journal of the American Statistical Association 79, no. 388 (1984), pp. 871–880. DOI: 10.1080/01621459.1984.10477105

## C++ Interface (pybind11)

```cpp
// Robust covariance via MCD combinatorial subset selection
struct MCDCore {
    std::vector<float> location;      // μ̂, shape (d,)
    std::vector<float> covariance;    // Σ̂ (rescaled), shape (d, d)
    std::vector<int>   support_mask;  // indicator, shape (n,)
    float              best_logdet;
};
MCDCore mcd_fit(
    const float* X, int n, int d,
    int h_subset_size,
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
- Python baseline: `sklearn.covariance.MinCovDet`
- Target: ≥8x faster via batched C-steps and shared Cholesky factorisation
- Benchmark: 1k, 10k, 100k samples × d=16, 32

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. Random starts parallelised with per-thread RNGs.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. RAII only.

**Object lifetime:** Self-assignment safe. No dangling refs.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Max 12 YMM. `alignas(64)` on Σ̂.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for log-det. Add diagonal ridge if Cholesky fails.

**Performance:** No `std::endl` loops. No `std::function` hot loops. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. No `printf(user_string)`. No TOCTOU. Seeded RNG is deterministic.

Full reference: `backend/extensions/CPP-RULES.md`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_241.py` | μ̂, Σ̂ match sklearn MinCovDet within 1e-3 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥8x faster than Python reference |
| 5 | `pytest test_edges_meta_241.py` | Rank-deficient X, h=n, h at minimum all handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Depends on META-218 (LAPACK bindings) for Cholesky
- Used by META-239 (Elliptic envelope) as the robust covariance engine

## Pipeline Stage Non-Conflict
- **Owns:** robust μ̂, Σ̂ and support-set selection
- **Alternative to:** sample `numpy.cov` when data is contaminated
- **Coexists with:** META-239 (which adds χ² thresholding on top of this μ̂, Σ̂)

## Test Plan
- Clean gaussian: verify μ̂, Σ̂ close to `numpy.cov`
- 30% contamination: verify Σ̂ matches clean covariance within 10%
- h = n (no trimming): verify MCD reduces to ordinary covariance
- d > n: verify raises (cannot estimate covariance)
