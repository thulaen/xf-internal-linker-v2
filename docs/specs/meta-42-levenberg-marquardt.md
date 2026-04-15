# META-42 — Levenberg-Marquardt

## Overview
**Category:** Optimizer (damped least-squares, trust-region-style)
**Extension file:** `levenberg_marquardt.cpp`
**Replaces/improves:** META-41 Gauss-Newton when JᵀJ is ill-conditioned or rank-deficient; replaces `scipy.optimize.least_squares(method='lm')`
**Expected speedup:** ≥5x over scipy's MINPACK-backed `lm`
**RAM:** <12 MB | **Disk:** <1 MB

## Algorithm
```
Input: x0 ∈ ℝ^d, residuals r, Jacobian J, damping λ_0, factor ν > 1
Output: x* ≈ argmin ½·‖r(x)‖²

λ ← λ_0
for t = 0..max_iter:
    r_t = r(x_t); J_t = J(x_t)
    g_t = J_tᵀ · r_t
    if ‖g_t‖_∞ ≤ ε_g: return x_t
    A_t = J_tᵀ · J_t + λ · diag(J_tᵀJ_t)            # Marquardt 1963 scaling
    Δ_t = solve(A_t · Δ = −g_t)                     # Cholesky on damped system
    ρ = (f(x_t) − f(x_t + Δ_t)) / (½·Δ_tᵀ·(λ·Δ_t − g_t))   # gain ratio
    if ρ > 0:
        x_{t+1} = x_t + Δ_t                          # update: x_{t+1} = x_t − (JᵀJ + λI)⁻¹·Jᵀr
        λ ← λ · max(1/3, 1 − (2ρ − 1)³); ν ← 2
    else:
        λ ← λ · ν; ν ← 2·ν                           # Marquardt damping rule
```
- Time complexity: O(max_iter · (m·d² + d³))
- Space complexity: O(m·d + d²)
- Convergence: globally convergent to a stationary point under standard smoothness (Marquardt 1963 §3; Moré 1978 Thm 4.5)

## Academic source
**Levenberg, K. (1944).** "A method for the solution of certain non-linear problems in least squares." *Quarterly of Applied Mathematics*, 2(2), 164-168. DOI: `10.1090/qam/10666`.
**Marquardt, D. W. (1963).** "An algorithm for least-squares estimation of nonlinear parameters." *SIAM J. Applied Math.*, 11(2), 431-441. DOI: `10.1137/0111030`.

## C++ Interface (pybind11)
```cpp
// Levenberg-Marquardt with adaptive damping and Cholesky solve
std::vector<double> levenberg_marquardt(
    const double* x0, int d,
    std::function<void(const double*, double*)> residual,
    std::function<void(const double*, double*)> jacobian,
    int m, int max_iter,
    double lambda0, double tol_grad, double tol_step
);
```

## Memory budget
- Runtime RAM: <12 MB (m ≤ 10000, d ≤ 100)
- Disk: <1 MB
- Allocation: `std::vector<double>` aligned 64-byte for J, JᵀJ, gradient, scratch Cholesky

## Performance target
- Python baseline: `scipy.optimize.least_squares(method='lm')`
- Target: ≥5x faster
- Benchmark: m ∈ {500, 5000, 10000} × d ∈ {10, 50, 100}

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — `-Wall` through `-Werror`, no raw `new`/`delete` in hot paths, SIMD GEMM with `_mm256_zeroupper()`, flush-to-zero on init, double accumulator for JᵀJ, NaN/Inf checks on residual evaluation, `noexcept` destructors, RAII scratch arena reused across iterations.

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_42.py` | Matches scipy `lm` within 1e-4 |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥5x faster than Python |
| 5 | Edge cases | rank-deficient J / huge λ / NaN / m=10000 pass |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- META-41 Gauss-Newton (shared J, JᵀJ build path)
- Inline Cholesky on damped normal equations

## Pipeline stage (non-conflict)
**Owns:** robust least-squares optimizer slot
**Alternative to:** META-41 Gauss-Newton (no damping), META-40 full Newton (general loss)
**Coexists with:** META-54 GP-EI (HPO selecting λ_0), META-04 coordinate ascent (different problem class)

## Test plan
- Rosenbrock as least-squares (r1 = 10(y − x²), r2 = 1 − x): converges to (1,1)
- Rank-deficient J: damping prevents blow-up, converges to least-norm solution
- Identity at optimum: stops in 0 iterations
- NaN in r: raises `ValueError`
- m=10000, d=50: meets target time and accuracy
