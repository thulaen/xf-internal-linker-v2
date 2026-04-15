# META-244 — Multi-Armed Bandit Hyperparameter Optimisation

## Overview
**Category:** Hyperparameter optimisation
**Extension file:** `mab_hpo.cpp`
**Replaces/improves:** Pure random search; complements (does not replace) META-38 successive-halving
**Expected speedup:** ≥4x sample efficiency vs random search at the same budget
**RAM:** <8 MB | **Disk:** <1 MB

## Algorithm

```
Input: K hyperparameter configurations (arms), total budget B resource units,
       pull-cost per arm, UCB exploration constant c

State per arm k:
  n_k    = number of pulls so far
  s_k    = running mean reward (e.g. val accuracy)
  N_total = Σ n_k

UCB1 arm selection (paper builds on Auer 2002):
  a_t = argmax_k ( s_k + c · √(ln N_total / n_k) )
        (if n_k == 0, select arm k first)

Successive-elimination via bandit (Jamieson & Talwalkar, Section 3):
  maintain active set A
  pull a_t for r_t resource increments
  observe reward (e.g. validation loss at new cum-budget)
  update s_k, n_k
  remove arm k from A if its upper conf bound < best lower conf bound

Distinct from META-38 (pure successive-halving):
  META-38 allocates uniformly within a bracket then halves.
  META-244 uses UCB / lower-confidence bound to choose arms dynamically.
```

- **Time complexity:** O(B) bandit decisions; training cost dominates
- **Space complexity:** O(K)

## Academic Source
Jamieson, K., and Talwalkar, A. "Non-stochastic best arm identification and hyperparameter optimization." Proceedings of the 19th International Conference on Artificial Intelligence and Statistics (AISTATS 2016), pp. 240–248. https://proceedings.mlr.press/v51/jamieson16.html

## C++ Interface (pybind11)

```cpp
// Stateful bandit controller
struct MABState {
    std::vector<int>   n_pulls;
    std::vector<float> mean_reward;
    std::vector<bool>  active;
    float              c_ucb;
};
MABState mab_make(int k_arms, float c_ucb);
int  mab_next_arm(MABState& s);
void mab_observe(MABState& s, int arm, float reward);
void mab_prune(MABState& s, float conf_z);
```

## Memory Budget
- Runtime RAM: <8 MB (state for K≤10k arms)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(k_arms)`

## Performance Target
- Python baseline: loop in Python with `numpy.argmax`
- Target: ≥4x lower decision overhead per step
- Benchmark: K=16, 256, 1024 arms, B=10000 pulls

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** Controller is single threaded; external workers call with a mutex.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. RAII only.

**Object lifetime:** Self-assignment safe. No dangling refs.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch.

**SIMD:** Not typically useful at this K scale; keep scalar.

**Floating point:** Flush-to-zero on init. NaN reward treated as −∞. UCB divisor clamped `max(n_k, 1)`.

**Performance:** No `std::endl` loops. No `std::function` hot loops.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. No `printf(user_string)`. No TOCTOU.

Full reference: `backend/extensions/CPP-RULES.md`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_244.py` | Arm-selection matches Python UCB1 reference exactly with seed |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥4x faster than NumPy reference |
| 5 | `pytest test_edges_meta_244.py` | Single arm, all rewards equal, NaN rewards handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if caller serialises access) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Standalone controller
- Coexists (does NOT replace) META-38 successive-halving — both are HPO schedulers with different strategies

## Pipeline Stage Non-Conflict
- **Owns:** UCB-style arm selection and confidence-bound pruning
- **Alternative to:** Random search, Bayesian HPO
- **Coexists with:** META-38 (successive-halving uses uniform allocation then elimination); META-243 PBT (different HPO paradigm)

## Test Plan
- Two arms, one clearly better: verify best arm pulled asymptotically ≥90%
- All arms equal: verify approximately uniform pulls
- K = 1: verify always returns arm 0
- Pruning threshold very strict: verify does not remove all arms
