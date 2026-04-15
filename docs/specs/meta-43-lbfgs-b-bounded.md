# META-43 — L-BFGS-B (Bounded Limited-Memory BFGS)

## Overview
**Category:** Optimizer (quasi-Newton, limited memory, box-constrained)
**Extension file:** `lbfgs_b.cpp`
**Replaces/improves:** `scipy.optimize.minimize(method='L-BFGS-B')` (Fortran wrapper) for medium-d (50-2000) bounded problems
**Expected speedup:** ≥4x over scipy's L-BFGS-B
**RAM:** <20 MB | **Disk:** <2 MB

## Algorithm
```
Input: x0 ∈ ℝ^d, bounds [l_i, u_i], gradient ∇f, memory m (typ. 5-20)
Output: x* ≈ argmin f(x) s.t. l ≤ x ≤ u

Maintain history: {s_i, y_i, ρ_i} for i = t−m..t−1
    s_i = x_{i+1} − x_i; y_i = ∇f_{i+1} − ∇f_i; ρ_i = 1 / (y_iᵀs_i)

for t = 0..max_iter:
    g_t = ∇f(x_t)
    Compute Cauchy point x^c via gradient projection on bounds (Byrd 1995 §4)
    Identify free vs active set A
    Subspace minimisation on free coords using two-loop recursion:
        # two-loop: H_t·g_t in O(m·d)
        q ← g_t
        for i = t−1..t−m:
            α_i ← ρ_i · s_iᵀq
            q ← q − α_i · y_i
        r ← γ_t · q                                 # γ_t = (s_{t−1}ᵀy_{t−1}) / (y_{t−1}ᵀy_{t−1})
        for i = t−m..t−1:
            β ← ρ_i · y_iᵀr
            r ← r + (α_i − β) · s_i
        Δ_t ← −r                                    # search direction
    Project Δ_t onto box: Δ_t ← π_[l,u](x_t + Δ_t) − x_t
    α_t = strong_wolfe_line_search(x_t, Δ_t)
    x_{t+1} = x_t + α_t · Δ_t
    Push (s_t, y_t, ρ_t); evict oldest if |history| > m
```
- Time complexity: O(max_iter · (m·d + line-search·f-eval))
- Space complexity: O(m·d) — limited memory, no Hessian materialised
- Convergence: superlinear under standard assumptions (Byrd, Lu, Nocedal, Zhu 1995, Thm 3.2)

## Academic source
**Byrd, R. H., Lu, P., Nocedal, J., & Zhu, C. (1995).** "A limited memory algorithm for bound constrained optimization." *SIAM J. Sci. Comput.*, 16(5), 1190-1208. DOI: `10.1137/0916069`.

## C++ Interface (pybind11)
```cpp
// L-BFGS-B with two-loop recursion, Cauchy point, and box projection
std::vector<double> lbfgs_b(
    const double* x0, const double* lower, const double* upper, int d,
    std::function<double(const double*)> f,
    std::function<void(const double*, double*)> grad,
    int memory_m, int max_iter,
    double tol_grad, double tol_f, int max_line_search
);
```

## Memory budget
- Runtime RAM: <20 MB (d ≤ 2000, m ≤ 20 → ≤320 KB history)
- Disk: <2 MB
- Allocation: ring buffer of `std::vector<double>` for {s_i, y_i}; aligned 64-byte for two-loop dot products

## Performance target
- Python baseline: `scipy.optimize.minimize(method='L-BFGS-B')`
- Target: ≥4x faster
- Benchmark: d ∈ {50, 500, 2000}, Rosenbrock and ReLU-quadratic with bounds

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — `-Wall` through `-Werror -Wconversion`, no raw `new`/`delete` in two-loop hot path, ring-buffer history pre-allocated with `reserve(m)`, double accumulator for dot products, SIMD `_mm256_zeroupper()`, flush-to-zero on init, NaN/Inf entry checks, `noexcept` destructors, no `std::function` calls inside the two-loop (function pointers cached).

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_43.py` | Matches scipy L-BFGS-B within 1e-4 |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥4x faster than scipy |
| 5 | Edge cases | All-bounds-active / unconstrained / NaN / d=2000 pass |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- Strong-Wolfe line search (shared with META-44 BFGS, META-45 CG)

## Pipeline stage (non-conflict)
**Owns:** quasi-Newton bounded optimizer slot
**Alternative to:** META-44 full BFGS (unbounded, more memory), META-40 Newton (small d), META-04 coordinate ascent (1D-at-a-time)
**Coexists with:** META-54 GP-EI (HPO around it), META-50 Lookahead (different stage)

## Test plan
- Rosenbrock with bounds [−2, 2]² from (−1.2, 1.0): converges within 25 iterations
- All bounds active at optimum: returns projected gradient point
- Identity bounds + zero grad: returns x0 unchanged
- NaN in x0: raises `ValueError`
- d=2000 quadratic with random bounds: meets target time
