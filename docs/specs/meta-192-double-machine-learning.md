# META-192 — Double Machine Learning (DML)

## Overview
**Category:** Causal inference (Neyman-orthogonal, cross-fit ML nuisance)
**Extension file:** `dml.cpp`
**Replaces/improves:** IPW (META-191) when outcome model adds useful signal
**Expected speedup:** ≥5x over Python numpy cross-fit reduction
**RAM:** <32 MB | **Disk:** <1 MB

## Algorithm

```
Input: n samples (X_i, T_i, Y_i), K cross-fit folds
       outcome model m(X) = E[Y|X], propensity model e(X) = P(T=1|X)
Output: orthogonalised treatment effect θ̂

Split {1..n} into K folds F_1..F_K
for k = 1..K:
    fit m̂_k, ê_k on complement of F_k
    for i in F_k:
        Ỹ_i = Y_i − m̂_k(X_i)
        T̃_i = T_i − ê_k(X_i)

θ̂ = Σ_i T̃_i · Ỹ_i  /  Σ_i T̃_i²
```

- **Paper update rule (Chernozhukov et al.):** cross-fit nuisance models `m̂, ê`; orthogonalised estimator `θ̂ = E[(Y − m̂(X))·(T − ê(X))] / E[(T − ê(X))²]`
- **Time complexity:** O(n) for the reduction; nuisance training lives in the caller
- **Space complexity:** O(n) for residual buffers Ỹ, T̃

## Academic Source
Chernozhukov, V., Chetverikov, D., Demirer, M., Duflo, E., Hansen, C., Newey, W. & Robins, J. (2018). "Double/Debiased Machine Learning for Treatment and Structural Parameters". The Econometrics Journal, Vol. 21, No. 1, pp. C1-C68. DOI: 10.1111/ectj.12097

## C++ Interface (pybind11)

```cpp
struct DmlResult { double theta_hat; double se; double numerator; double denominator; };
DmlResult dml_estimate(
    const float* y_residual,    // [n]  Y_i − m̂_k(X_i)
    const float* t_residual,    // [n]  T_i − ê_k(X_i)
    int n
);
```

## Memory Budget
- Runtime RAM: <32 MB for n=1e7 (residuals supplied by caller; function keeps O(1))
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: none beyond scalar result struct

## Performance Target
- Python baseline: `np.dot(t_resid, y_resid) / np.dot(t_resid, t_resid)`
- Target: ≥5x faster with AVX2 FMA dual-accumulator pass
- Benchmark: 3 sizes — n=1e3, n=1e5, n=1e7

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

See `backend/extensions/CPP-RULES.md` for full mandate.

**Threading:** OpenMP reduction on numerator + denominator independently.

**Memory:** No raw `new`/`delete`. No heap allocation in hot path.

**Object lifetime:** Read-only input pointers.

**Type safety:** Explicit `static_cast` narrowing. No signed/unsigned mismatch.

**SIMD:** AVX2 FMA `_mm256_fmadd_ps` with double accumulator. `_mm256_zeroupper()` on exit. Kahan for n ≥ 1e6.

**Floating point:** Double accumulators mandatory. Guard `denominator` = 0 → raise. NaN/Inf entry checks.

**Performance:** No `std::function` hot loops. No `dynamic_cast`. Single fused pass.

**Error handling:** Destructors `noexcept`. SE via influence-function formula. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace.

**Security:** No `system()`. No `printf(user_string)`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_192.py` | Matches EconML LinearDML within 1e-6 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥5x faster than numpy reference |
| 5 | `pytest test_edges_meta_192.py` | Zero T̃ (denominator=0), n=1, constant Y, NaN |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races with OMP reduction |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Caller provides cross-fit residuals (nuisance models trained outside C++)

## Pipeline Stage Non-Conflict
- **Owns:** Orthogonal-moment reduction given residuals
- **Alternative to:** META-191 (IPW), META-193 (doubly robust)
- **Coexists with:** META-186 (self-training) — nuisance `m̂` and `ê` can be trained semi-supervised

## Test Plan
- Linear data with known θ: verify θ̂ → θ as n grows
- T̃ ≡ 0: verify raises ValueError (denominator zero)
- Constant Y: verify θ̂ = 0 exactly
- NaN residuals: verify raises ValueError
- Agreement with EconML `LinearDML` on synthetic DGP
