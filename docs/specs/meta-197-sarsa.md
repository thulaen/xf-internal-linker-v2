# META-197 — SARSA

## Overview
**Category:** Reinforcement learning (on-policy TD control)
**Extension file:** `sarsa.cpp`
**Replaces/improves:** Conservative on-policy alternative to META-196 Q-learning for risk-sensitive click feedback
**Expected speedup:** ≥5x over Python tabular SARSA loop
**RAM:** <50 MB for |S|×|A| ≤ 10⁵×32 | **Disk:** <1 MB

## Algorithm

Rummery & Niranjan on-policy temporal-difference control. Unlike Q-learning, the update uses the value of the action actually taken next under the current policy (hence the name SARSA: state-action-reward-state-action tuple).

```
Input: learning rate α, discount γ, policy π (e.g. ε-greedy from Q)
Output: Q(s,a) ≈ Q^π(s,a)

Initialize Q arbitrarily (zeros)
for each episode:
    observe s; choose a ~ π(·|s)
    while s not terminal:
        take action a, observe r, s'
        choose a' ~ π(·|s')
        # Paper update rule (on-policy, uses actual next action):
        Q(s,a) ← Q(s,a) + α·[r + γ·Q(s',a') − Q(s,a)]
        s ← s'; a ← a'
```

- **Time:** O(1) per step (no `max` over actions)
- **Space:** O(|S|·|A|) tabular
- **Convergence:** Converges to `Q^π` for the policy π that is followed; with GLIE exploration, converges to `Q*`

## Academic Source
Rummery, G.A. & Niranjan, M. (1994). **"On-line Q-learning using connectionist systems"**. *Cambridge University Engineering Department Technical Report* CUED/F-INFENG/TR 166. [Institutional URL](https://www.cs.cam.ac.uk/techreports/).

## C++ Interface (pybind11)

```cpp
// Tabular SARSA update (on-policy; requires a_next)
void sarsa_update(
    float* Q, int n_states, int n_actions,
    int s, int a, float r, int s_next, int a_next,
    float alpha, float gamma, bool terminal
);
// Batched on-policy rollout update
void sarsa_rollout(
    float* Q, int n_states, int n_actions,
    const int* s_seq, const int* a_seq, const float* r_seq,
    int T, float alpha, float gamma
);
```

## Memory Budget
- Runtime RAM: <50 MB (same 10⁵·32·4B table as META-196)
- Disk: <1 MB (.so/.pyd only)
- Allocation: caller-owned buffers, no internal `new`/`delete`

## Performance Target
- Python baseline: NumPy tabular SARSA in Python loop
- Target: ≥5x faster — simpler than Q-learning (no `max`), so should be at parity or faster
- Benchmark: 3 sizes — 10³×8, 10⁴×16, 10⁵×32 tables; 10⁶ transitions each

## Pre-Implementation Safety Checklist

Follow `backend/extensions/CPP-RULES.md` in full. Key items:

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`, no `volatile`, no detached threads. Predicate-form waits. Document atomic memory ordering.

**Memory:** No raw `new`/`delete` in hot paths. RAII only. `reserve()` before known-size fills. Bounds checks in debug.

**Object lifetime:** Self-assignment safe. No dangling `string_view`. No `[&]` capture beyond scope.

**Type safety:** Explicit `static_cast` for narrowing. No signed/unsigned mismatch. All switch cases handled.

**SIMD:** `_mm256_zeroupper()` at AVX boundaries. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf checks on α, γ, r. Double accumulator for long reductions.

**Performance:** No `std::endl`, no `std::function`, no `dynamic_cast` in hot loops.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all.

**Build:** No cyclic includes. Static internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_197.py` | Matches NumPy reference within 1e-5 |
| 3 | `ASAN=1 build + pytest` | Zero ASan/UBSan errors |
| 4 | `bench_extensions.py` | ≥5x faster than Python reference |
| 5 | `pytest test_edges_meta_197.py` | Terminal, α=0, γ=0, γ=1 all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (standalone tabular update kernel)

## Pipeline Stage & Non-Conflict

**Stage:** Post-click feedback loop (adaptive ranker outer loop).
**Owns:** On-policy tabular action-value updates for conservative learners.
**Alternative to:** META-196 Q-learning (off-policy; cannot run both as primary learner simultaneously).
**Coexists with:** META-202 ε-greedy (behavior policy), META-04 coordinate ascent (offline tuning).

## Test Plan
- Cliff-walking gridworld: verify SARSA learns a safer path than Q-learning under ε-greedy
- Deterministic chain MDP: verify convergence to `Q^π` within 10⁴ episodes
- Terminal flag: verify no bootstrap at episode end
- NaN reward: verify `ValueError` raised
- Greedy policy (ε=0): verify equivalence to on-policy evaluation
