# META-40 — Newton's Method

## Overview
**Category:** Optimizer (second-order)
**Extension file:** `newton_method.cpp`
**Replaces/improves:** META-04 coordinate ascent and META-34 Adam for smooth twice-differentiable losses where Hessian is cheap (d ≤ 200)
**Expected speedup:** ≥8x over `scipy.optimize.minimize(method='Newton-CG')`
**RAM:** <8 MB | **Disk:** <1 MB

## Algorithm
```
Input: x0 ∈ ℝ^d, gradient ∇f, Hessian H = ∇²f, tol ε
Output: x* ≈ argmin f(x)

for t = 0..max_iter:
    g_t = ∇f(x_t)                          # (Newton 1685, eq. 1)
    if ‖g_t‖ ≤ ε: return x_t
    H_t = ∇²f(x_t)
    Δ_t = solve(H_t · Δ = −g_t)            # Cholesky if SPD, LU otherwise
    α_t = backtracking_line_search(x_t, Δ_t)   # Armijo, c=1e-4
    x_{t+1} = x_t + α_t · Δ_t              # update rule: x_{t+1} = x_t − H⁻¹·∇f
```
- Time complexity: O(max_iter · (d³ + d²)) — Cholesky dominates
- Space complexity: O(d²) for Hessian + O(d) for gradient
- Convergence guarantees: locally quadratic (Nocedal & Wright, *Numerical Optimization* 2nd ed., Thm 3.5)

## Academic source
**Newton, I. (1685) / Raphson, J. (1690).** "Method of Fluxions" / "Analysis Aequationum Universalis." Manuscript and treatise. Modern reference: Nocedal & Wright, *Numerical Optimization*, Springer 2006, Ch. 3, ISBN: `978-0-387-30303-1`.

## C++ Interface (pybind11)
```cpp
// Full Newton step with Cholesky solve and Armijo line search
std::vector<double> newton_method(
    const double* x0, int d,
    std::function<double(const double*)> f,
    std::function<void(const double*, double*)> grad,
    std::function<void(const double*, double*)> hess,
    int max_iter, double tol, double armijo_c
);
```

## Memory budget
- Runtime RAM: <8 MB (d ≤ 200 → ≤ 320 KB Hessian + scratch)
- Disk: <1 MB (compiled .so/.pyd)
- Allocation: `std::vector<double>` with `reserve(d*d)` for Hessian, aligned 64-byte for SIMD Cholesky

## Performance target
- Python baseline: `scipy.optimize.minimize(method='Newton-CG', jac=g, hess=H)`
- Target: ≥8x faster
- Benchmark: d ∈ {20, 100, 200} on Rosenbrock and quadratic bowl

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — flags from `-Wall` through `-Werror -Wconversion -Wshadow`, no raw `new`/`delete` in hot paths, no `std::recursive_mutex`, SIMD Cholesky uses `_mm256_zeroupper()`, flush-to-zero on init, double accumulator for inner products, `noexcept` destructors, RAII scratch buffers, no `std::endl` in inner loops.

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_40.py` | Output matches scipy Newton-CG within 1e-4 |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥8x faster than Python |
| 5 | Edge cases | Empty / single / NaN / Inf / d=200 pass |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races (single-threaded; passes trivially) |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- META-12 Cholesky factorisation (if present) — otherwise inline LAPACKE `dpotrf` call
- META-04 line-search helpers (Armijo backtracking)

## Pipeline stage (non-conflict)
**Owns:** second-order optimizer slot
**Alternative to:** META-41 Gauss-Newton (residual-only), META-43 L-BFGS-B (limited memory), META-44 BFGS
**Coexists with:** META-04 coordinate ascent (different slot — coordinate vs full-space), META-50 Lookahead wrapper

## Test plan
- 2D Rosenbrock from (−1.2, 1.0): converges to (1, 1) within 12 iterations
- Identity Hessian + zero grad: returns x0 unchanged in one step
- NaN in x0: raises `ValueError`
- Singular Hessian: falls back to Levenberg-Marquardt damping (delegate to META-42) or raises
- Quadratic bowl: converges in exactly one step (textbook Newton property)
