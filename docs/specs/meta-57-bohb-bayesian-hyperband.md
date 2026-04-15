# META-57 — BOHB (Bayesian Optimisation + Hyperband)

## Overview
**Category:** Bayesian-HPO + multi-fidelity bandit hybrid
**Extension file:** `bohb.cpp`
**Replaces/improves:** META-58 Hyperband (random sampling) and META-55 TPE (no fidelity awareness); BOHB combines TPE within each budget level with Hyperband across budgets — best-of-both
**Expected speedup:** ≥5x over `hpbandster` BOHB Python step
**RAM:** <128 MB | **Disk:** <2 MB

## Algorithm
```
Input: budget [r_min, r_max], reduction factor η (typ. 3), TPE quantile γ (typ. 0.15)
Output: best (config, budget) over total budget

s_max = ⌊log_η(r_max / r_min)⌋
B = (s_max + 1) · r_max                                # total budget per outer loop

for s = s_max..0:
    n = ⌈ B/r_max · η^s / (s+1) ⌉                      # initial #configs
    r = r_max · η^(−s)                                 # initial budget per config

    # Sample configs: TPE if enough history, else random (Falkner 2018 §3.2):
    if |H_b| ≥ |H_b| > N_min for any budget b:
        configs ← TPE_sample(n, γ, history at largest filled budget)
    else:
        configs ← random_sample(n)

    # Successive halving (Hyperband inner loop, Li 2017):
    for i = 0..s:
        n_i = ⌊n · η^(−i)⌋
        r_i = r · η^i
        evaluate {f(c, r_i)} for c ∈ configs           # evaluate on budget r_i
        configs ← top n_i / η configs by performance
```
- Time complexity: O(s_max² · n_max · r_max)
- Space complexity: O(total_evals · d) for per-budget history
- Convergence: Falkner 2018 Thm 3.1 — strong-anytime + asymptotic-optimal performance

## Academic source
**Falkner, S., Klein, A., & Hutter, F. (2018).** "BOHB: Robust and Efficient Hyperparameter Optimization at Scale." *International Conference on Machine Learning* (ICML), 80, 1437-1446. URL: `https://proceedings.mlr.press/v80/falkner18a.html`. arXiv: `1807.01774`.

## C++ Interface (pybind11)
```cpp
// BOHB outer loop: Hyperband bracket schedule + TPE sampling per budget
struct BOHBResult {
    std::vector<double> config_best;
    double y_best;
    double budget_best;
    std::vector<std::tuple<std::vector<double>, double, double>> trace;   // (config, budget, y)
};

BOHBResult bohb(
    std::function<double(const double*, double)> objective,    // (config, budget) → loss
    int d, const double* lower, const double* upper,
    double r_min, double r_max, double eta,
    double gamma, int n_min,
    int total_outer_loops, int random_seed
);
```

## Memory budget
- Runtime RAM: <128 MB (per-budget TPE history dominates)
- Disk: <2 MB
- Allocation: per-budget `std::vector<History>`; reserved at construction

## Performance target
- Python baseline: `hpbandster.optimizers.BOHB`
- Target: ≥5x faster per outer loop
- Benchmark: 6D Hartmann, 20D feedforward NN HPO

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — `-Wall` through `-Werror`, no raw `new`/`delete` in TPE inner, no `std::recursive_mutex`, SIMD AVX2 with `_mm256_zeroupper()`, flush-to-zero on init, NaN/Inf entry checks on objective, `noexcept` destructors, η > 1, γ ∈ (0, 0.5], r_min > 0 guards, deterministic seeding, no `std::function` in TPE inner density evaluation.

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_57.py` | Best-config rank matches `hpbandster` within tolerance |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥5x faster than hpbandster |
| 5 | Edge cases | r_min = r_max (no halving) / first bracket (no TPE history) / NaN pass |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- META-55 TPE (inner sampler)
- META-58 Hyperband (outer schedule)

## Pipeline stage (non-conflict)
**Owns:** multi-fidelity Bayesian-HPO slot
**Alternative to:** META-54 GP-EI, META-55 TPE, META-56 SMAC, META-58 Hyperband, META-59 GP-UCB
**Coexists with:** META-46–53 (HPO targets via budget = epochs)

## Test plan
- 6D Hartmann with synthetic budget = noise_scale: BOHB beats Hyperband on simple regret
- First bracket with no history: falls back to random sampling
- r_min = r_max: degenerates to TPE (no halving brackets)
- NaN in objective: raises `ValueError`
- 20D NN HPO: meets target time
