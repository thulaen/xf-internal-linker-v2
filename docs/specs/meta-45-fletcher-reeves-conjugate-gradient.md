# META-45 — Fletcher-Reeves Conjugate Gradient

## Overview
**Category:** Optimizer (non-linear conjugate gradient, matrix-free)
**Extension file:** `cg_fletcher_reeves.cpp`
**Replaces/improves:** `scipy.optimize.minimize(method='CG')` for very large d (>2000) where even L-BFGS-B history is wasteful
**Expected speedup:** ≥4x over scipy CG
**RAM:** <8 MB | **Disk:** <1 MB

## Algorithm
```
Input: x0 ∈ ℝ^d, gradient ∇f
Output: x* ≈ argmin f(x)

g_0 = ∇f(x_0)
d_0 = −g_0
for k = 0..max_iter:
    if ‖g_k‖ ≤ ε: return x_k
    α_k = strong_wolfe_line_search(x_k, d_k)
    x_{k+1} = x_k + α_k · d_k
    g_{k+1} = ∇f(x_{k+1})
    β_k^{FR} = ‖g_{k+1}‖² / ‖g_k‖²                  # Fletcher-Reeves 1964 eq. (3)
    d_{k+1} = −g_{k+1} + β_k^{FR} · d_k             # update: d_{k+1} = −∇f_{k+1} + β·d_k
    if k mod d == 0: d_{k+1} = −g_{k+1}             # restart for global convergence
```
- Time complexity: O(max_iter · (d + line-search·f-eval))
- Space complexity: O(d) — only x, g, d kept; no Hessian
- Convergence: Al-Baali 1985 proved global convergence with strong Wolfe and σ ≤ 0.5; n-step quadratic termination on convex quadratics

## Academic source
**Fletcher, R., & Reeves, C. M. (1964).** "Function minimization by conjugate gradients." *Computer Journal*, 7(2), 149-154. DOI: `10.1093/comjnl/7.2.149`.
Convergence analysis: Al-Baali, M. (1985). "Descent property and global convergence of the Fletcher-Reeves method with inexact line search." *IMA J. Numer. Anal.*, 5(1), 121-124. DOI: `10.1093/imanum/5.1.121`.

## C++ Interface (pybind11)
```cpp
// Fletcher-Reeves non-linear CG with strong Wolfe line search and periodic restart
std::vector<double> cg_fletcher_reeves(
    const double* x0, int d,
    std::function<double(const double*)> f,
    std::function<void(const double*, double*)> grad,
    int max_iter, double tol_grad, int restart_every,
    int max_line_search
);
```

## Memory budget
- Runtime RAM: <8 MB (d up to 100000 → 2.4 MB for x, g, d)
- Disk: <1 MB
- Allocation: three aligned 64-byte `std::vector<double>` of size d; reused across iterations

## Performance target
- Python baseline: `scipy.optimize.minimize(method='CG')`
- Target: ≥4x faster
- Benchmark: d ∈ {1000, 10000, 100000} on quadratic and Rosenbrock

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — `-Wall` through `-Werror`, no raw `new`/`delete` in hot path, SIMD `‖g‖²` and `−g + β·d` with `_mm256_zeroupper()`, flush-to-zero on init, double accumulator for ‖g‖² over d>100, NaN/Inf entry checks, `noexcept` destructors, restart guard (every d steps) prevents loss of conjugacy from numerical drift.

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_45.py` | Matches scipy CG within 1e-4 |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥4x faster than scipy |
| 5 | Edge cases | Quadratic terminates ≤d steps / NaN / d=100000 pass |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- Strong-Wolfe line search (shared with META-43, META-44)

## Pipeline stage (non-conflict)
**Owns:** matrix-free large-d optimizer slot
**Alternative to:** META-43 L-BFGS-B (small/medium d), META-40 Newton, META-44 BFGS
**Coexists with:** META-54 GP-EI HPO, META-50 Lookahead

## Test plan
- Convex quadratic d=100: terminates within d iterations (textbook CG property)
- Rosenbrock d=2: converges within 50 iterations with restarts
- Restart correctness: forced restart every d resets d_{k+1} to −g_{k+1}
- NaN in gradient: raises `ValueError`
- d=100000 random quadratic: meets target time
