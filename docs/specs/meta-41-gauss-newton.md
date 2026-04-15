# META-41 — Gauss-Newton

## Overview
**Category:** Optimizer (least-squares, second-order approximation)
**Extension file:** `gauss_newton.cpp`
**Replaces/improves:** META-04 coordinate ascent and META-40 full Newton when problem is non-linear least-squares (residuals r(x))
**Expected speedup:** ≥6x over `scipy.optimize.least_squares(method='lm')` for the pure Gauss-Newton path
**RAM:** <12 MB | **Disk:** <1 MB

## Algorithm
```
Input: x0 ∈ ℝ^d, residual function r: ℝ^d → ℝ^m, Jacobian J ∈ ℝ^{m×d}
Output: x* ≈ argmin ½·‖r(x)‖²

for t = 0..max_iter:
    r_t = r(x_t)                          # m residuals
    J_t = J(x_t)                          # m×d Jacobian (Gauss, Theoria Motus 1809)
    g_t = J_tᵀ · r_t                       # gradient of ½‖r‖²
    if ‖g_t‖ ≤ ε: return x_t
    A_t = J_tᵀ · J_t                       # normal equations matrix (d×d, SPD)
    Δ_t = solve(A_t · Δ = −g_t)           # Cholesky on JᵀJ
    α_t = backtracking_line_search(x_t, Δ_t)
    x_{t+1} = x_t + α_t · Δ_t              # update: x_{t+1} = x_t − (JᵀJ)⁻¹·Jᵀr
```
- Time complexity: O(max_iter · (m·d² + d³))
- Space complexity: O(m·d) for J + O(d²) for JᵀJ
- Convergence guarantees: locally quadratic when r(x*) = 0; linear with rate ‖r(x*)‖ otherwise (Nocedal & Wright Thm 10.1)

## Academic source
**Gauss, C. F. (1809).** "Theoria motus corporum coelestium in sectionibus conicis solem ambientium." Hamburg: Perthes & Besser. Modern reference: Nocedal & Wright, *Numerical Optimization*, Springer 2006, Ch. 10.

## C++ Interface (pybind11)
```cpp
// Gauss-Newton with Cholesky on normal equations and Armijo line search
std::vector<double> gauss_newton(
    const double* x0, int d,
    std::function<void(const double*, double*)> residual,    // writes m floats
    std::function<void(const double*, double*)> jacobian,    // writes m*d row-major
    int m, int max_iter, double tol, double armijo_c
);
```

## Memory budget
- Runtime RAM: <12 MB (m ≤ 10000, d ≤ 100)
- Disk: <1 MB
- Allocation: aligned 64-byte buffers for J, JᵀJ, residual vector; `reserve(m*d)`

## Performance target
- Python baseline: `scipy.optimize.least_squares(method='lm')`
- Target: ≥6x faster on pure GN (no damping)
- Benchmark: m ∈ {500, 5000, 10000} × d ∈ {10, 50, 100}

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — `-Wall` through `-Werror -Wsign-conversion`, no raw `new`/`delete` in hot paths, double accumulator for `JᵀJ` reductions, SIMD GEMM with `_mm256_zeroupper()`, flush-to-zero on init, NaN/Inf entry checks on x0 and r, `noexcept` destructors, no `std::function` inside the inner J·r loop (cache function pointer once).

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_41.py` | Output matches scipy `lm` within 1e-4 |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥6x faster than Python |
| 5 | Edge cases | Empty / single / rank-deficient J / NaN / m=10000 pass |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- META-12 / inline Cholesky for JᵀJ solve
- META-42 Levenberg-Marquardt as the fallback when JᵀJ is rank-deficient

## Pipeline stage (non-conflict)
**Owns:** least-squares optimizer slot
**Alternative to:** META-42 Levenberg-Marquardt (damped variant), META-40 full Newton (general loss)
**Coexists with:** META-04 coordinate ascent (different problem class), META-54 GP-EI (HPO around it)

## Test plan
- Curve-fit y = a·exp(b·x) on synthetic data: converges to true (a, b) within 1e-6
- Zero residual at x0: returns x0 in zero iterations
- Rank-deficient Jacobian: raises `ValueError` (or hands off to META-42)
- NaN in residual: raises `ValueError`
- m=10000, d=50: completes within target time
