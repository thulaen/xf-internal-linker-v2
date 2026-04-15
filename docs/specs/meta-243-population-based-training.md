# META-243 — Population-Based Training (PBT)

## Overview
**Category:** Hyperparameter optimisation
**Extension file:** `pbt.cpp`
**Replaces/improves:** Grid search / random search / Bayesian optimisation for HP tuning
**Expected speedup:** ≥3x wall-clock vs Bayesian HPO on equal compute (shared population)
**RAM:** <16 MB | **Disk:** <1 MB

## Algorithm

```
Input: N workers, each with (θ_i, h_i) = (weights, hyperparameters)
       fitness metric f, exploit fraction t, explore ratio r
Output: best (θ*, h*) after T generations

Initialise: each worker samples h_i from prior; train from scratch for s steps.

Repeat every s steps (paper, Algorithm 1):
  for worker i in parallel:
    train(θ_i, h_i) for s steps
    evaluate f_i = fitness(θ_i)

  exploit (paper, Section 3.1):
    rank workers by f_i
    if worker i is in bottom t fraction:
      pick worker j uniformly from top t fraction
      θ_i ← θ_j      # copy weights
      h_i ← h_j      # copy hyperparameters

  explore (paper, Section 3.1):
    perturb h_i:
      h_i ← h_j · uniform_choice({1/r, r})       # multiplicative
      OR
      h_i ← resample_from_prior(h_i)             # categorical

Terminate after T generations. Return argmax_i f_i.
```

- **Time complexity:** O(T · N · s · train_step_cost) distributed across N workers
- **Space complexity:** O(N · (|θ| + |h|)) across the whole fleet

## Academic Source
Jaderberg, M., Dalibard, V., Osindero, S., et al. "Population Based Training of Neural Networks." arXiv:1711.09846 (2017). https://arxiv.org/abs/1711.09846

## C++ Interface (pybind11)

```cpp
// Coordinator-side PBT step: compute exploit/explore decisions for a generation
struct PbtDecision {
    int   copy_from_worker;   // -1 if no copy
    std::vector<float> new_hparams;
};
std::vector<PbtDecision> pbt_step(
    const float* fitness_per_worker, int n_workers,
    const float* hparams_flat, int n_hparams_per_worker,
    float exploit_fraction,
    float perturb_ratio,
    const int* hparam_kinds,   // 0=continuous, 1=log, 2=categorical
    uint64_t seed
);
```

## Memory Budget
- Runtime RAM: <16 MB for decisions across N≤1024 workers (weights live in each worker process, not here)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(n_workers)`

## Performance Target
- Python baseline: Ray Tune PBT scheduler decision logic
- Target: ≥3x faster coordinator decisions; training cost dominates regardless
- Benchmark: N=16, 128, 1024 workers

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** The coordinator step itself is single threaded. Cross-worker training is orchestrated outside this extension.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. RAII only.

**Object lifetime:** Self-assignment safe. No dangling refs.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch.

**SIMD:** Not applicable to coordinator logic.

**Floating point:** Flush-to-zero on init. NaN fitness treated as worst. Log-scale perturb uses `std::exp2(log2(h) + log2(r) · ±1)`.

**Performance:** No `std::endl` loops. No `std::function` hot loops.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. No `printf(user_string)`. No TOCTOU. Seeded RNG is deterministic.

Full reference: `backend/extensions/CPP-RULES.md`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_243.py` | Decisions match Ray Tune PBT with same seed on toy fitness |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | Coordinator ≥3x faster than Ray Tune equivalent |
| 5 | `pytest test_edges_meta_243.py` | N=1, all equal fitness, NaN fitness handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Co-exists with META-242 (GL early stopping — can decide "done" per worker)
- Co-exists with META-244 (MAB HPO) and META-38 (successive-halving) as alternative HPO schedulers

## Pipeline Stage Non-Conflict
- **Owns:** exploit/explore decisions across a training population
- **Alternative to:** META-244 MAB HPO, META-38 successive-halving, Bayesian HPO
- **Coexists with:** META-242 GL early stopping (per-worker stopping)

## Test Plan
- Fitness 1..N, t=0.2: verify bottom 20% copy from top 20%
- All equal fitness: verify no copies and perturbations random
- N=1: verify no-op (no exploit possible)
- Deterministic seed: verify same decision sequence across runs
