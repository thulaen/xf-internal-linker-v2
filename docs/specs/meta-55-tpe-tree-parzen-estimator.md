# META-55 — Tree-structured Parzen Estimator (TPE)

## Overview
**Category:** Bayesian-HPO (density-ratio surrogate, scales to high-d, supports conditional spaces)
**Extension file:** `tpe_estimator.cpp`
**Replaces/improves:** META-54 GP-EI for high-dimensional or conditional/categorical spaces where O(T³) GP cubic cost is prohibitive
**Expected speedup:** ≥8x over Optuna `TPESampler.sample` Python step
**RAM:** <64 MB | **Disk:** <1 MB

## Algorithm
```
Input: history H = {(x_i, y_i)}_{i=1..T}, quantile γ ∈ (0, 0.5] (typ. 0.15), n_candidates (typ. 24)
Output: x_{T+1} = next config to evaluate

# Split history (Bergstra 2011 §3):
y* ← γ-quantile of {y_i}
ℓ(x) ← parametric Parzen density of {x_i : y_i < y*}    # "good" set
g(x) ← parametric Parzen density of {x_i : y_i ≥ y*}    # "bad" set

# Sample n_candidates from ℓ:
{x̃_j}_{j=1..n_candidates} ← sample(ℓ)

# Acquire by maximising density ratio (Bergstra 2011 eq. 11):
EI(x) ∝ ℓ(x) / g(x)
x_{T+1} ← argmax_j  ℓ(x̃_j) / g(x̃_j)
```
- Time complexity: O(T · n_candidates · d) per acquisition
- Space complexity: O(T · d) — store all history; no covariance matrix
- Convergence: empirical; Bergstra 2011 §6 — TPE matches GP-EI on hyper-DBN, exceeds random search

## Academic source
**Bergstra, J., Bardenet, R., Bengio, Y., & Kégl, B. (2011).** "Algorithms for Hyper-Parameter Optimization." *Advances in Neural Information Processing Systems* (NIPS), 24, 2546-2554. URL: `https://papers.nips.cc/paper_files/paper/2011/hash/86e8f7ab32cfd12577bc2619bc635690`.

## C++ Interface (pybind11)
```cpp
// TPE acquisition step: split history by gamma, fit Parzen ℓ and g, sample, return argmax ℓ/g
struct TPEResult {
    std::vector<double> x_next;
    double ei_score;
};

TPEResult tpe_step(
    const double* X_history, const double* y_history, int T, int d,
    const double* lower, const double* upper,
    double gamma, int n_candidates,
    int random_seed
);
```

## Memory budget
- Runtime RAM: <64 MB (T ≤ 1000, d ≤ 50)
- Disk: <1 MB
- Allocation: aligned 64-byte buffers for X_history copy; per-call scratch reserved at construction

## Performance target
- Python baseline: Optuna `TPESampler` Python sampling
- Target: ≥8x faster per acquisition
- Benchmark: T ∈ {50, 200, 1000}, d ∈ {5, 20, 50}

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — `-Wall` through `-Werror`, no raw `new`/`delete`, SIMD AVX2 for Gaussian density evaluations with `_mm256_zeroupper()`, flush-to-zero on init, NaN/Inf entry checks on y_history, `noexcept` destructors, γ ∈ (0, 0.5] guard, n_candidates ≥ 1 guard, deterministic seeding for reproducibility, no `std::function` in inner density loop.

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_55.py` | EI rank order matches Optuna within 1e-4 |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥8x faster than Optuna CPU |
| 5 | Edge cases | T < n_init / all-y-equal / NaN in y / T=1000 pass |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- None (standalone surrogate sampler)

## Pipeline stage (non-conflict)
**Owns:** Bayesian-HPO surrogate slot for high-d / categorical
**Alternative to:** META-54 GP-EI, META-56 SMAC, META-57 BOHB, META-58 Hyperband, META-59 GP-UCB
**Coexists with:** META-57 BOHB (TPE is the BO inside BOHB), all META-46–53 (HPO targets)

## Test plan
- 2D Branin: TPE finds global min within 100 evals
- 50D random objective: ratio-acquisition outperforms random sampling
- All y equal (no signal): degenerates gracefully to uniform sample
- NaN in y_history: raises `ValueError`
- T=1000, d=50: meets target time
