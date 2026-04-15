# META-56 — SMAC (Sequential Model-based Algorithm Configuration)

## Overview
**Category:** Bayesian-HPO (Random-Forest surrogate + EI acquisition; supports mixed continuous/categorical/conditional spaces)
**Extension file:** `smac.cpp`
**Replaces/improves:** META-54 GP-EI for spaces with categorical, integer, or conditional (tree-structured) hyperparameters where Gaussian Processes assume continuous geometry
**Expected speedup:** ≥6x over `smac3` Python per BO iteration
**RAM:** <128 MB | **Disk:** <2 MB

## Algorithm
```
Input: history H = {(θ_i, y_i)}_{i=1..T}, RF surrogate hyperparams (n_trees, max_depth)
Output: θ_{T+1} = next configuration

# 1. Fit Random-Forest surrogate (Hutter 2011 §3.2):
RF ← train_rf(H, n_trees=10, min_samples_leaf=3)
For each leaf, compute mean μ_leaf and variance σ²_leaf of y values

# 2. Predict mean and variance for any θ (Hutter 2014 eq. 3):
μ̂(θ)  = (1/n_trees) · Σ_t  μ_{leaf_t(θ)}
σ̂²(θ) = (1/n_trees) · Σ_t  (σ²_{leaf_t(θ)} + μ²_{leaf_t(θ)})  −  μ̂(θ)²

# 3. EI acquisition (Jones 1998):
y* = min_i y_i
Z(θ) = (y* − μ̂(θ)) / σ̂(θ)
EI(θ) = (y* − μ̂(θ))·Φ(Z) + σ̂(θ)·φ(Z)

# 4. Local search + random sample candidates, return argmax EI:
θ_{T+1} ← argmax_{θ ∈ candidates} EI(θ)
```
- Time complexity: O(T · log T) for RF fit + O(n_candidates · n_trees · max_depth) for acquisition
- Space complexity: O(T · d) history + O(n_trees · n_leaves) RF
- Convergence: Hutter, Hoos, Leyton-Brown 2011 §5 — empirically robust on AClib benchmark suite

## Academic source
**Hutter, F., Hoos, H. H., & Leyton-Brown, K. (2011).** "Sequential model-based optimization for general algorithm configuration." *Learning and Intelligent Optimization* (LION 5), Lecture Notes in Computer Science, vol 6683, pp. 507-523. DOI: `10.1007/978-3-642-25566-3_40`.

## C++ Interface (pybind11)
```cpp
// SMAC step: fit RF surrogate, predict (mu, sigma^2) for candidates, return EI-max
struct SMACResult {
    std::vector<double> theta_next;
    double ei_score;
};

SMACResult smac_step(
    const double* X_history, const double* y_history, int T, int d,
    const double* lower, const double* upper,
    const int* is_categorical,            // 1 if dimension is categorical
    int n_trees, int max_depth,
    int n_candidates, int random_seed
);
```

## Memory budget
- Runtime RAM: <128 MB (T ≤ 1000, n_trees = 10, d ≤ 100)
- Disk: <2 MB
- Allocation: aligned tree node arrays; per-tree split buffer reserved at construction

## Performance target
- Python baseline: `smac3` BO iteration
- Target: ≥6x faster per iter
- Benchmark: T ∈ {50, 200, 1000}, mixed cat+continuous d=20

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — `-Wall` through `-Werror`, no raw `new`/`delete`, no `std::recursive_mutex` in tree fit, SIMD AVX2 for Gaussian CDF approximation with `_mm256_zeroupper()`, flush-to-zero on init, NaN/Inf entry checks on y, `noexcept` destructors, n_trees ≥ 1, max_depth ≥ 1 guards, categorical handling tested explicitly, no `std::function` in tree-traversal hot path.

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_56.py` | EI ranking matches `smac3` within 1e-3 (RF non-determinism tolerated) |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥6x faster than smac3 |
| 5 | Edge cases | All-categorical / all-continuous / NaN / T=1000 pass |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races (RF training may be threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- META-12 / standalone Random Forest (or split-finding helper if META-RF exists)

## Pipeline stage (non-conflict)
**Owns:** Bayesian-HPO surrogate slot for mixed/categorical
**Alternative to:** META-54 GP-EI, META-55 TPE, META-57 BOHB, META-58 Hyperband, META-59 GP-UCB
**Coexists with:** META-57 BOHB, all META-46–53 (HPO targets)

## Test plan
- Mixed cat+continuous synthetic: SMAC outperforms GP on categorical-heavy domain
- All-continuous: matches GP-EI ranking within tolerance
- Categorical-only: tree splits handle cat dimensions correctly (verify via instrumentation)
- NaN in y: raises `ValueError`
- T=1000, d=20: meets target time
