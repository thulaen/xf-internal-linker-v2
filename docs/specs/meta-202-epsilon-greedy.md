# META-202 — ε-greedy Exploration

## Overview
**Category:** Reinforcement learning / bandits (exploration policy)
**Extension file:** `epsilon_greedy.cpp`
**Replaces/improves:** Baseline exploration primitive used by META-196 Q-learning, META-197 SARSA, and tabular contextual bandits
**Expected speedup:** ≥5x over Python branch + `np.argmax` per decision
**RAM:** <1 MB | **Disk:** <1 MB

## Algorithm

Watkins' minimal exploration rule: with probability ε pick a uniform random action; otherwise pick the greedy (argmax-Q) action. Despite its simplicity, ε-greedy is the default exploration baseline cited by virtually every RL paper.

```
Input: action-values Q(s, ·) ∈ ℝ^|A|, exploration rate ε ∈ [0,1], RNG
Output: action a

# Paper decision rule:
if Uniform(0,1) < ε:
    a ← Uniform({0, 1, …, |A|−1})      # explore
else:
    a ← argmax_a Q(s, a)                # exploit
```

Common schedules:
- Constant: `ε = 0.1`
- Linear decay: `ε_t = max(ε_min, ε_0 − k·t)`
- Exponential decay: `ε_t = ε_min + (ε_0 − ε_min)·exp(−λt)`

- **Time:** O(|A|) for the argmax (a single pass with ties broken at random)
- **Space:** O(1) auxiliary
- **Properties:** GLIE (Greedy in the Limit with Infinite Exploration) when ε → 0 appropriately

## Academic Source
Watkins, C.J.C.H. (1989). **"Learning from delayed rewards"** (Chapter 5). PhD thesis, University of Cambridge. [Institutional URL](https://www.cs.rhul.ac.uk/~chrisw/new_thesis.pdf). Later formalized in Watkins & Dayan (1992).

## C++ Interface (pybind11)

```cpp
// Single-state ε-greedy decision
int epsilon_greedy(
    const float* Q_row, int n_actions,
    float epsilon, uint64_t* rng_state
);
// Batched ε-greedy over N states
void epsilon_greedy_batch(
    const float* Q, int n_states, int n_actions,
    float epsilon, uint64_t* rng_state,
    int* actions_out
);
```

## Memory Budget
- Runtime RAM: <1 MB (no persistent state beyond RNG seed)
- Disk: <1 MB (.so/.pyd)
- Allocation: stack only; RNG state is an 8-byte `uint64_t` (xorshift/PCG)

## Performance Target
- Python baseline: `np.random.rand() < eps` + `np.argmax(Q)` per decision
- Target: ≥5x faster via vectorized SIMD argmax and fast PRNG (xoroshiro128+)
- Benchmark: 3 sizes — |A|=8, |A|=64, |A|=1024; 10⁷ decisions each

## Pre-Implementation Safety Checklist

Follow `backend/extensions/CPP-RULES.md` in full. Key items:

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`, no `volatile`. RNG state is per-thread (caller-owned) to avoid contention.

**Memory:** No raw `new`/`delete`. Stack only. Bounds-checked in debug.

**Object lifetime:** Self-assignment safe. No dangling `string_view`. No `[&]` capture beyond scope.

**Type safety:** Explicit `static_cast` for narrowing. No signed/unsigned mismatch. Validate ε∈[0,1].

**SIMD:** `_mm256_zeroupper()` at AVX boundaries. `alignas(64)` on Q buffer. SIMD horizontal-max with tie-breaking via index comparison.

**Floating point:** NaN/Inf checks on Q entries (skip or treat as −∞). No FP compare against NaN.

**Performance:** No `std::endl`, no `std::function`, no `dynamic_cast`. Do not use `std::uniform_real_distribution` in the hot loop — it is slow; use raw PRNG → `float`.

**Error handling:** Destructors `noexcept`. pybind11 catches all. Raise on |A|<=0.

**Build:** No cyclic includes. Static internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Caller-owned RNG state (no global seed write).

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_202.py` | Matches NumPy reference distributionally (χ² p>0.01) |
| 3 | `ASAN=1 build + pytest` | Zero ASan/UBSan errors |
| 4 | `bench_extensions.py` | ≥5x faster than Python reference |
| 5 | `pytest test_edges_meta_202.py` | ε=0 (always greedy), ε=1 (always random), ties, NaN Q all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks |
| 7 | `TSAN=1 build + pytest` | Zero races (per-thread RNG) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (standalone decision primitive; consumed by META-196, META-197, META-203, META-205)

## Pipeline Stage & Non-Conflict

**Stage:** Inner loop of every tabular/value-based learner that needs exploration.
**Owns:** ε-greedy decision rule and batched action selection.
**Alternative to:** Softmax/Boltzmann exploration, UCB (META-203), Thompson sampling (META-204) — ε-greedy is the baseline when simplicity matters.
**Coexists with:** All value-based methods (META-196/197). Not used by PPO (META-200) or DDPG (META-201), which sample from stochastic/noise-perturbed policies.

## Test Plan
- ε=0: verify always returns `argmax(Q)`
- ε=1: verify uniform distribution over actions within χ² tolerance over 10⁵ samples
- Tied Q values (all equal): verify output is uniform over tied actions
- Single action |A|=1: verify always returns 0
- NaN in Q row: verify deterministic fallback (skip NaN entries)
- Reproducibility: same seed → identical sequence of 10⁶ actions
