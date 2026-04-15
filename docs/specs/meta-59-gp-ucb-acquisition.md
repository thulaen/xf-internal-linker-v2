# META-59 — GP-UCB (Gaussian Process Upper Confidence Bound)

## Overview
**Category:** Bayesian-HPO (GP surrogate + UCB acquisition with theoretical regret bounds)
**Extension file:** `gp_ucb.cpp`
**Replaces/improves:** META-54 GP-EI's heuristic exploration parameter ξ; GP-UCB's β_t schedule provides a sublinear regret guarantee independent of horizon T
**Expected speedup:** ≥10x over scikit-optimize `gp_minimize` per BO iteration with custom UCB
**RAM:** <128 MB | **Disk:** <2 MB

## Algorithm
```
Input: domain X ⊂ ℝ^d, prior GP with kernel k, n_init random points, total budget T,
       confidence schedule β_t (Srinivas 2010 Thm 1: β_t = 2·log(|X|·t²·π²/(6δ)) for finite X;
       continuous variant in Thm 2)
Output: x* ≈ argmin f(x)

{x_i, y_i}_{i=1..n_init} ← random_sample(X), evaluate f

for t = n_init + 1..T:
    # Posterior μ_t(x), σ_t(x) via Cholesky on K + σ_n²I
    # UCB acquisition (Srinivas 2010 eq. 1):
    UCB_t(x) = μ_t(x) − √β_t · σ_t(x)               # for minimisation; maximisation flips sign

    x_t ← argmin_{x ∈ X} UCB_t(x)                    # multi-start L-BFGS-B inner
    y_t ← f(x_t)
    Append (x_t, y_t); refit kernel hyperparameters via marginal log-likelihood
```
- Time complexity: O(T³) for Cholesky on K + O(T · acquisition_inner)
- Space complexity: O(T²) K matrix + O(T·d) X
- Regret: Srinivas 2010 Thm 2 — cumulative regret R_T = O*(√(T·β_T·γ_T)), where γ_T is maximum information gain (γ_T = O((log T)^{d+1}) for RBF kernel)

## Academic source
**Srinivas, N., Krause, A., Kakade, S. M., & Seeger, M. (2010).** "Gaussian Process Optimization in the Bandit Setting: No Regret and Experimental Design." *International Conference on Machine Learning* (ICML), 1015-1022. URL: `https://icml.cc/Conferences/2010/papers/422.pdf`. arXiv: `0912.3995`.

## C++ Interface (pybind11)
```cpp
// GP-UCB BO loop with Cholesky-based posterior and adaptive beta_t schedule
struct UCBResult {
    std::vector<double> x_best;
    double y_best;
    std::vector<std::vector<double>> trace;
};

UCBResult gp_ucb_bo(
    std::function<double(const double*)> objective,
    int d, const double* lower, const double* upper,
    int n_init, int total_budget,
    const char* kernel,         // "matern52" | "matern32" | "rbf"
    double delta,               // confidence level (1 - delta)
    int random_seed
);
```

## Memory budget
- Runtime RAM: <128 MB (T ≤ 200, d ≤ 20)
- Disk: <2 MB
- Allocation: aligned 64-byte K matrix; pre-reserved per-iteration scratch; no per-iteration heap churn

## Performance target
- Python baseline: scikit-optimize with custom UCB acquisition
- Target: ≥10x faster per BO iteration
- Benchmark: 6D Hartmann, 2D Branin, 10D Levy — T ∈ {50, 100, 200}

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — `-Wall` through `-Werror -Wconversion`, no raw `new`/`delete`, SIMD GEMM/Cholesky with `_mm256_zeroupper()`, flush-to-zero on init, double accumulator for K matrix entries and posterior mean/variance, NaN/Inf entry checks on y, `noexcept` destructors, jitter (1e-8·I) on K for PSD, β_t > 0 guard, no `std::function` in inner Cholesky/triangular solve, posterior code shared with META-54 to avoid divergence.

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_59.py` | Posterior μ, σ² match GPy reference within 1e-4 |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥10x faster per iter than scikit-optimize |
| 5 | Edge cases | Singular K (jitter handled) / β_1 path / NaN / T=200 pass |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- META-54 GP-EI (shared posterior μ, σ² code path — UCB only changes acquisition)
- META-43 L-BFGS-B for inner acquisition optimisation
- META-12 / inline Cholesky factorisation

## Pipeline stage (non-conflict)
**Owns:** Bayesian-HPO surrogate slot with regret-bounded acquisition
**Alternative to:** META-54 GP-EI, META-55 TPE, META-56 SMAC, META-57 BOHB, META-58 Hyperband
**Coexists with:** META-43 L-BFGS-B (inner acquisition), all META-46–53 (HPO targets)

## Test plan
- 2D Branin: cumulative regret matches Srinivas 2010 sublinear curve
- 6D Hartmann: simple regret ≤ 0.05 within 100 evals
- β_1 first-step path: numerically valid (no log(0))
- Singular K: jitter restores PSD
- NaN in y: raises `ValueError`
- T=200, d=10: meets target time
