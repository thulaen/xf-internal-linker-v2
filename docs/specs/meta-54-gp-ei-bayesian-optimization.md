# META-54 — Gaussian Process with Expected Improvement (GP-EI)

## Overview
**Category:** Bayesian-HPO (surrogate-model-based black-box optimizer)
**Extension file:** `gp_ei_bo.cpp`
**Replaces/improves:** META-46–53 random-search HPO; GP-EI builds a probabilistic surrogate of the objective and chooses the next x by maximising Expected Improvement
**Expected speedup:** ≥10x over scikit-optimize `gp_minimize` per BO iteration (Cholesky + EI in C++)
**RAM:** <128 MB | **Disk:** <2 MB

## Algorithm
```
Input: domain X ⊂ ℝ^d, prior GP with kernel k (Matérn-5/2 default), n_init random points, total budget T
Output: x* ≈ argmin f(x)

# Initialisation
{x_i, y_i}_{i=1..n_init} ← random_sample(X), evaluate f
f* ← min_i y_i

for t = n_init + 1..T:
    # Posterior at any x (Močkus 1974; Rasmussen 2006 Ch. 2):
    # μ(x)   = k(x,X)·(K + σ_n²I)⁻¹·y
    # σ²(x)  = k(x,x) − k(x,X)·(K + σ_n²I)⁻¹·k(X,x)
    # Acquisition (Jones, Schonlau, Welch 1998 eq. 15):
    Z(x)   = (f* − μ(x) − ξ) / σ(x),  ξ = exploration constant (typ. 0.01)
    EI(x)  = (f* − μ(x) − ξ) · Φ(Z) + σ(x) · φ(Z)        if σ(x) > 0
    EI(x)  = 0                                            if σ(x) = 0

    x_t ← argmax_{x ∈ X} EI(x)                          # multi-start L-BFGS-B inner solve
    y_t ← f(x_t); f* ← min(f*, y_t)
    Append (x_t, y_t); refit kernel hyperparameters via marginal log-likelihood
```
- Time complexity: O(T³) for Cholesky on K + O(T · acquisition_inner_iters)
- Space complexity: O(T²) for K matrix + O(T·d) for X
- Convergence: Bull 2011 — for Matérn-ν kernel, simple regret = O(T^(−ν/d) · (log T)^α)

## Academic source
**Močkus, J. (1974).** "On Bayesian methods for seeking the extremum." *Optimization Techniques IFIP Technical Conf.*, 400-404. Springer LNCS 27.
**Jones, D. R., Schonlau, M., & Welch, W. J. (1998).** "Efficient global optimization of expensive black-box functions." *Journal of Global Optimization*, 13(4), 455-492. DOI: `10.1023/A:1008306431147`.
**Rasmussen, C. E., & Williams, C. K. I. (2006).** *Gaussian Processes for Machine Learning.* MIT Press, ISBN: `978-0-262-18253-9`.

## C++ Interface (pybind11)
```cpp
// GP-EI BO loop with Cholesky-based posterior and L-BFGS-B inner acquisition
struct BOResult {
    std::vector<double> x_best;
    double y_best;
    std::vector<std::vector<double>> trace;
};

BOResult gp_ei_bo(
    std::function<double(const double*)> objective,
    int d, const double* lower, const double* upper,
    int n_init, int total_budget,
    const char* kernel,        // "matern52" | "matern32" | "rbf"
    double xi,                 // exploration
    int random_seed
);
```

## Memory budget
- Runtime RAM: <128 MB (T ≤ 200, d ≤ 20 → 200×200 K = 320 KB; multi-start scratch dominates)
- Disk: <2 MB
- Allocation: aligned 64-byte K matrix; pre-reserved per-iteration scratch; no per-iteration heap churn

## Performance target
- Python baseline: scikit-optimize `gp_minimize`
- Target: ≥10x faster per BO iteration
- Benchmark: 6D Hartmann, 2D Branin, 10D Levy — T = 50, 100, 200

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — `-Wall` through `-Werror -Wconversion`, no raw `new`/`delete`, SIMD GEMM/Cholesky with `_mm256_zeroupper()`, flush-to-zero on init, double accumulator for K matrix entries, NaN/Inf entry checks on objective evaluations, `noexcept` destructors, jitter (1e-8·I) added to K for numerical PSD, no `std::function` in inner Cholesky/triangular solve.

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_54.py` | EI value matches scikit-optimize within 1e-4 |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥10x faster per iter than scikit-optimize |
| 5 | Edge cases | Singular K (jitter handled) / NaN in y / T=200 pass |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- META-43 L-BFGS-B for inner acquisition optimisation
- META-12 / inline Cholesky factorisation
- META-59 GP-UCB shares posterior code (μ, σ²)

## Pipeline stage (non-conflict)
**Owns:** Bayesian-HPO surrogate slot
**Alternative to:** META-55 TPE, META-56 SMAC, META-57 BOHB, META-58 Hyperband, META-59 GP-UCB
**Coexists with:** META-04 coordinate ascent (inner optimizer), META-43 L-BFGS-B (acquisition inner solve), all META-46–53 (HPO targets)

## Test plan
- 2D Branin: finds global min within 25 evaluations (Jones 1998 reproduction)
- 6D Hartmann: simple regret ≤ 0.05 within 100 evals
- Identity objective f(x) = 0: GP collapses correctly, EI = 0 everywhere after first eval
- NaN in y_t: raises `ValueError`
- T=200, d=10: meets target time
