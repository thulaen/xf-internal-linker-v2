# META-58 — Hyperband

## Overview
**Category:** Multi-fidelity bandit HPO (random sampling + successive halving)
**Extension file:** `hyperband.cpp`
**Replaces/improves:** Random search HPO; Hyperband adaptively allocates more budget to promising configurations and aggressively prunes losers
**Expected speedup:** ≥6x over `keras-tuner` Hyperband Python loop overhead
**RAM:** <32 MB | **Disk:** <1 MB

## Algorithm
```
Input: max budget per config R, reduction factor η (typ. 3)
Output: best config

s_max = ⌊log_η(R / r_min)⌋                            # number of brackets, Li 2017 §3
B = (s_max + 1) · R                                    # total budget per bracket suite

for s = s_max..0:
    # Allocate within bracket s:
    n   = ⌈ B/R · η^s / (s + 1) ⌉                     # initial #configs (Li 2017 alg. 1)
    r   = R · η^(−s)                                   # initial budget per config

    configs ← random_sample(n)

    # Successive halving:
    for i = 0..s:
        n_i = ⌊ n · η^(−i) ⌋
        r_i = r · η^i
        L = { f(c, r_i) : c ∈ configs }
        configs ← top_k(configs, k = ⌊n_i / η⌋, key = L)

    keep best config seen at any (c, r)
```
- Time complexity: per outer suite O((s_max+1) · B) — provably optimal up to log factors (Li 2017 Thm 3)
- Space complexity: O(n_max · d) for current bracket only
- Convergence: Li 2017 Thm 3 — total budget O(log² R) more than oracle

## Academic source
**Li, L., Jamieson, K., DeSalvo, G., Rostamizadeh, A., & Talwalkar, A. (2017).** "Hyperband: A novel bandit-based approach to hyperparameter optimization." *Journal of Machine Learning Research*, 18(185), 1-52. URL: `https://www.jmlr.org/papers/v18/16-558.html`. arXiv: `1603.06560`.

## C++ Interface (pybind11)
```cpp
// Hyperband: random sample + successive halving across log_eta(R/r_min) brackets
struct HyperbandResult {
    std::vector<double> config_best;
    double y_best;
    double budget_best;
    int total_evals;
};

HyperbandResult hyperband(
    std::function<double(const double*, double)> objective,    // (config, budget) → loss
    int d, const double* lower, const double* upper,
    double R, double r_min, double eta,
    int n_outer_loops, int random_seed
);
```

## Memory budget
- Runtime RAM: <32 MB (n_max ≤ 200, d ≤ 50)
- Disk: <1 MB
- Allocation: ring buffer for current bracket configs; reserved at construction

## Performance target
- Python baseline: keras-tuner Hyperband loop overhead (excluding objective time)
- Target: ≥6x faster per outer loop
- Benchmark: synthetic budget-monotonic objective, 6D and 20D, η ∈ {3, 4}

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — `-Wall` through `-Werror`, no raw `new`/`delete` in halving inner, sort uses `std::sort` with stable comparator (no `std::function` callable closures), SIMD not required (control plane), flush-to-zero on init, NaN/Inf entry checks on objective output, `noexcept` destructors, η > 1, R > r_min > 0 guards, deterministic seeding for reproducibility.

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_58.py` | Bracket schedule matches Li 2017 Tab. 1 exactly |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥6x faster than keras-tuner |
| 5 | Edge cases | s_max = 0 / R = r_min / NaN / n_outer_loops = 1 pass |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- None (random sampling only — TPE-augmented variant is META-57 BOHB)

## Pipeline stage (non-conflict)
**Owns:** multi-fidelity bandit HPO slot
**Alternative to:** META-54 GP-EI, META-55 TPE, META-56 SMAC, META-57 BOHB, META-59 GP-UCB
**Coexists with:** META-57 BOHB (BOHB uses Hyperband schedule), META-46–53 (HPO targets)

## Test plan
- Reproduce Li 2017 Tab. 1 bracket schedule for R=81, η=3 exactly
- Synthetic monotone-in-budget objective: Hyperband finds optimum within 4 outer loops
- s_max = 0: degenerates to random search
- NaN in objective: raises `ValueError`
- 20D, 4 outer loops: meets target time
