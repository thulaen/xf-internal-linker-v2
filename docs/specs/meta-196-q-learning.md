# META-196 — Q-learning

## Overview
**Category:** Reinforcement learning (off-policy TD control)
**Extension file:** `q_learning.cpp`
**Replaces/improves:** Static heuristic weight updates in adaptive ranker feedback loop
**Expected speedup:** ≥5x over Python tabular Q-learning loop
**RAM:** <50 MB for |S|×|A| ≤ 10⁵×32 | **Disk:** <1 MB

## Algorithm

Watkins & Dayan off-policy temporal-difference control. The agent learns the optimal action-value function `Q*(s,a)` regardless of the behavior policy, by bootstrapping on the greedy next-state value.

```
Input: learning rate α ∈ (0,1], discount γ ∈ [0,1), exploration ε
Output: Q(s,a) ≈ Q*(s,a)

Initialize Q(s,a) arbitrarily (zeros)
for each episode:
    observe s
    while s not terminal:
        a ← behavior policy (e.g. ε-greedy from Q)
        take action a, observe r, s'
        # Paper update rule (off-policy):
        Q(s,a) ← Q(s,a) + α·[r + γ·max_{a'} Q(s',a') − Q(s,a)]
        s ← s'
```

- **Time:** O(|A|) per step for `max_{a'}` lookup
- **Space:** O(|S|·|A|) tabular
- **Convergence:** Guaranteed to `Q*` under Robbins-Monro α schedule and all (s,a) visited infinitely often

## Academic Source
Watkins, C.J.C.H. & Dayan, P. (1992). **"Q-learning"**. *Machine Learning*, 8(3-4), 279-292. DOI: [10.1007/BF00992698](https://doi.org/10.1007/BF00992698).

## C++ Interface (pybind11)

```cpp
// Tabular Q-learning update
void q_learning_update(
    float* Q, int n_states, int n_actions,
    int s, int a, float r, int s_next,
    float alpha, float gamma, bool terminal
);
// Batched greedy action selection
void q_greedy_batch(
    const float* Q, int n_states, int n_actions,
    const int* states, int n, int* actions_out
);
```

## Memory Budget
- Runtime RAM: <50 MB (`|S|×|A|` float table; 10⁵·32·4B = 12.8 MB)
- Disk: <1 MB (.so/.pyd only; no model artifact in library)
- Allocation: caller-owned `float*` buffer, no internal `new`/`delete`

## Performance Target
- Python baseline: NumPy tabular update in Python loop (~2 µs/step)
- Target: ≥5x faster via cache-friendly row access and `std::max_element`
- Benchmark: 3 sizes — 10³×8, 10⁴×16, 10⁵×32 state-action tables; 10⁶ updates each

## Pre-Implementation Safety Checklist

Follow `backend/extensions/CPP-RULES.md` in full. Key items:

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`, no `volatile`, no detached threads. `condition_variable::wait()` predicate form. Atomics document memory ordering.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view`. No `[&]` capture beyond scope.

**Type safety:** Explicit `static_cast` for narrowing. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled.

**SIMD:** `_mm256_zeroupper()` at AVX boundaries. `alignas(64)` on hot arrays. Max 12 YMM.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks on α, γ, r. Double accumulator for reductions >100 elements.

**Performance:** No `std::endl`, no `std::function`, no `dynamic_cast` in hot loops.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace for internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_196.py` | Matches NumPy reference within 1e-5 |
| 3 | `ASAN=1 build + pytest` | Zero ASan/UBSan errors |
| 4 | `bench_extensions.py` | ≥5x faster than Python reference |
| 5 | `pytest test_edges_meta_196.py` | Terminal, α=0, γ=0, γ=1 all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (standalone tabular update kernel)

## Pipeline Stage & Non-Conflict

**Stage:** Post-click feedback loop (adaptive ranker outer loop).
**Owns:** Tabular action-value updates for discrete policy feedback.
**Alternative to:** META-197 SARSA (on-policy variant — cannot run both as primary learner simultaneously).
**Coexists with:** META-202 ε-greedy (used as behavior policy), META-04 coordinate ascent (offline weight tuning; different stage).

## Test Plan
- Deterministic gridworld 5×5: verify `Q` converges to known `Q*` within 10⁴ episodes (tolerance 1e-3)
- Single-state single-action: verify `Q ← r/(1−γ)` at fixed point
- Terminal flag: verify no bootstrap (`max_{a'}Q(s',a')` term zeroed)
- NaN reward: verify `ValueError` raised
- |S|×|A| = 10⁵×32: verify no OOM and throughput ≥500k updates/sec
