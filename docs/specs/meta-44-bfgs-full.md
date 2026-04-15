# META-44 — Full BFGS

## Overview
**Category:** Optimizer (quasi-Newton, full Hessian approximation)
**Extension file:** `bfgs_full.cpp`
**Replaces/improves:** `scipy.optimize.minimize(method='BFGS')` for small-to-medium d (≤500) where storing a dense Hessian approximation is affordable
**Expected speedup:** ≥5x over scipy BFGS
**RAM:** <12 MB | **Disk:** <1 MB

## Algorithm
```
Input: x0 ∈ ℝ^d, gradient ∇f, initial inverse-Hessian H_0 = I
Output: x* ≈ argmin f(x)

for k = 0..max_iter:
    g_k = ∇f(x_k)
    if ‖g_k‖ ≤ ε: return x_k
    p_k = −H_k · g_k                         # search direction
    α_k = strong_wolfe_line_search(x_k, p_k)
    s_k = α_k · p_k
    x_{k+1} = x_k + s_k
    y_k = ∇f(x_{k+1}) − g_k
    ρ_k = 1 / (y_kᵀs_k)                       # curvature condition: y_kᵀs_k > 0
    # BFGS secant update (Broyden 1970, Fletcher 1970, Goldfarb 1970, Shanno 1970):
    H_{k+1} = (I − ρ_k·s_k·y_kᵀ) · H_k · (I − ρ_k·y_k·s_kᵀ) + ρ_k·s_k·s_kᵀ
```
- Time complexity: O(max_iter · d²) per iteration (rank-2 update + matrix-vector)
- Space complexity: O(d²) for inverse-Hessian approximation
- Convergence: superlinear under strong Wolfe + smoothness (Nocedal & Wright Thm 6.6)

## Academic source
**Broyden, C. G. (1970).** "The convergence of a class of double-rank minimization algorithms." *J. Inst. Math. Appl.*, 6(1), 76-90. DOI: `10.1093/imamat/6.1.76`.
**Fletcher, R. (1970).** "A new approach to variable metric algorithms." *Computer J.*, 13(3), 317-322. DOI: `10.1093/comjnl/13.3.317`.
**Goldfarb, D. (1970).** "A family of variable metric updates derived by variational means." *Math. Comput.*, 24(109), 23-26. DOI: `10.1090/S0025-5718-1970-0258249-6`.
**Shanno, D. F. (1970).** "Conditioning of quasi-Newton methods for function minimization." *Math. Comput.*, 24(111), 647-656. DOI: `10.1090/S0025-5718-1970-0274029-X`.

## C++ Interface (pybind11)
```cpp
// Full BFGS with strong Wolfe line search; updates dense inverse Hessian
std::vector<double> bfgs_full(
    const double* x0, int d,
    std::function<double(const double*)> f,
    std::function<void(const double*, double*)> grad,
    int max_iter, double tol_grad, int max_line_search
);
```

## Memory budget
- Runtime RAM: <12 MB (d ≤ 500 → 2 MB H matrix)
- Disk: <1 MB
- Allocation: aligned 64-byte `std::vector<double>` for H, scratch s, y, p; rank-2 update SIMD-accelerated

## Performance target
- Python baseline: `scipy.optimize.minimize(method='BFGS')`
- Target: ≥5x faster
- Benchmark: d ∈ {20, 100, 500} on Rosenbrock and convex quadratic

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — `-Wall` through `-Werror -Wsign-conversion`, no raw `new`/`delete` in update path, SIMD rank-2 update with `_mm256_zeroupper()`, flush-to-zero on init, double accumulator for inner products, NaN/Inf entry checks, `noexcept` destructors, curvature-condition guard (skip update if y_kᵀs_k ≤ 0), no `std::function` calls inside H-update.

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_44.py` | Matches scipy BFGS within 1e-4 |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥5x faster than scipy |
| 5 | Edge cases | Negative curvature / NaN / d=500 pass |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- Strong-Wolfe line search (shared with META-43 L-BFGS-B, META-45 CG)

## Pipeline stage (non-conflict)
**Owns:** dense quasi-Newton optimizer slot
**Alternative to:** META-43 L-BFGS-B (limited memory), META-40 Newton (exact Hessian), META-45 CG (no Hessian)
**Coexists with:** META-54 GP-EI HPO, META-04 coordinate ascent (different problem class)

## Test plan
- 2D Rosenbrock from (−1.2, 1.0): converges within 25 iterations
- Convex quadratic d=100: superlinear convergence verified
- Negative curvature step rejected: H not updated, line search shortens
- NaN in gradient: raises `ValueError`
- d=500: meets target time and accuracy
