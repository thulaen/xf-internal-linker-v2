# META-86 — SCAD Penalty

## Overview
**Category:** Non-convex sparsity regulariser (P8 regularisation block)
**Extension file:** `scad_penalty.cpp`
**Replaces/improves:** L1 LASSO bias toward zero on large coefficients — SCAD removes shrinkage bias for big weights while retaining sparsity for small ones
**Expected speedup:** ≥4x over Python LLA (local linear approximation) loop
**RAM:** <8 MB | **Disk:** <1 MB

## Algorithm

```
Input: feature matrix X ∈ ℝ^{n×p}, y ∈ ℝ^n, λ > 0, a > 2 (paper recommends a = 3.7)
Output: β* with selective non-shrinkage on large |β_j|

Penalty (per coefficient β):
  p_λ(β) =
    λ·|β|                                           if |β| ≤ λ
    (a·λ·|β| − (β² + λ²) / 2) / (a − 1)             if λ < |β| ≤ a·λ
    (a + 1)·λ² / 2                                  if |β| > a·λ

Prox (SCAD soft-threshold, paper Eq. 2.5):
  prox_{η·p_λ}(z) =
    sign(z)·max(|z| − η·λ, 0)                       if |z| ≤ 2·η·λ
    ((a − 1)·z − sign(z)·η·a·λ) / (a − 2)           if 2·η·λ < |z| ≤ a·λ
    z                                               if |z| > a·λ

Coordinate-descent outer loop:
  for j = 1..p (cyclic):
      r_j  ← residual ignoring β_j
      β_j  ← prox_{η·p_λ}( Xᵀ_j · r_j )
```

- **Time complexity:** O(iter · n · p)
- **Space complexity:** O(p + n)
- **Convergence:** Local optimum (non-convex); LLA initialisation from LASSO recommended

## Academic source
Fan, J. and Li, R., "Variable Selection via Nonconcave Penalized Likelihood and Its Oracle Properties", *Journal of the American Statistical Association*, 96(456):1348–1360, 2001. DOI 10.1198/016214501753382273.

## C++ Interface (pybind11)

```cpp
// Element-wise SCAD prox
void scad_prox(const float* z, int p, float lambda, float a, float step, float* out);

// Full SCAD-penalised regression via coordinate descent
std::vector<float> scad_fit(
    const float* X, int n, int p,
    const float* y,
    float lambda, float a,
    float step, float tol, int max_iter,
    const float* warm_start_or_null
);
```

## Memory Budget
- Runtime RAM: <8 MB (β + residual + per-feature column-norm cache)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: pre-sized vectors; column norms cached at fit start

## Performance Target
- Python baseline: `ncvreg`-style LLA loop reimplemented with NumPy
- Target: ≥4x faster on n=p=1000
- Benchmark: 3 sizes — (n,p) ∈ {(100,50), (1000,500), (10000,5000)}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled. Validate `a > 2` at entry.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays. SCAD prox vectorised over `p` (branch-free using selects).

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for residual reductions >100 elements.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`. Residual updated incrementally.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all. Reject `a ≤ 2` with ValueError.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

Adheres to `backend/extensions/CPP-RULES.md` in full.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_86.py` | Matches `ncvreg` R package within 1e-3 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `pytest backend/benchmarks/test_bench_scad.py` | ≥4x speedup on 3 sizes |
| 5 | `pytest test_edges_meta_86.py` | p=1, λ=0, |β| > aλ (no shrinkage), warm-start cold all handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | Oracle property | On synthetic sparse problem with large signals, large β recovered without bias |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- META-82 FISTA (LLA inner solver)
- pybind11 ≥ 2.10

## Pipeline stage non-conflict declaration
- **Owns:** Non-convex SCAD prox + LLA-style coordinate-descent solver
- **Alternative to:** L1 LASSO when oracle (unbiased) recovery of large coefficients is desired
- **Coexists with:** META-82 FISTA (used as inner LASSO solver for LLA), META-84 group LASSO, META-85 fused LASSO

## Test Plan
- Synthetic data with large + small true coefficients: verify large ones recovered without shrinkage bias
- a = 3.7 (paper default): verify default path
- a = 2.001 (boundary): verify still produces valid prox (no division-by-zero)
- λ = 0 reduces to OLS — parity with `np.linalg.lstsq`
- |z| > aλ: verify prox(z) = z exactly (no shrinkage)
