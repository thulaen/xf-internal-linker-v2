# META-199 — Actor-Critic

## Overview
**Category:** Reinforcement learning (policy-gradient with learned value baseline)
**Extension file:** `actor_critic.cpp`
**Replaces/improves:** Variance-reduced alternative to META-198 REINFORCE; enables online (one-step) updates rather than end-of-episode
**Expected speedup:** ≥5x over Python per-step actor+critic update
**RAM:** <100 MB for actor |θ|≤10⁶ + critic |w|≤10⁶ | **Disk:** <1 MB

## Algorithm

Konda & Tsitsiklis actor-critic framework: the **critic** `V_w(s)` learns a state-value baseline via TD(0); the **actor** `π_θ(a|s)` uses the TD error δ as a low-variance estimate of the advantage.

```
Input: actor π_θ, critic V_w, rates α_θ (actor), α_w (critic), discount γ
Output: θ maximizing J(θ), w minimizing TD error

for each step (s, a, r, s'):
    # TD error / one-step advantage estimate:
    δ = r + γ · V_w(s') − V_w(s)      # (zero V_w(s') if terminal)

    # Critic update (TD(0) on value):
    w ← w + α_w · δ · ∇_w V_w(s)

    # Actor update (policy-gradient with δ as advantage):
    θ ← θ + α_θ · δ · ∇_θ log π_θ(a|s)
```

- **Time:** O(|θ| + |w|) per step
- **Space:** O(|θ| + |w|)
- **Variance:** Lower than REINFORCE due to bootstrapped baseline; biased if critic is imperfect

## Academic Source
Konda, V.R. & Tsitsiklis, J.N. (2000). **"Actor-critic algorithms"**. *Advances in Neural Information Processing Systems (NIPS)*, 12, 1008-1014. [NIPS proceedings](https://papers.nips.cc/paper/1786-actor-critic-algorithms).

## C++ Interface (pybind11)

```cpp
// Single-step TD error + actor/critic parameter updates
void actor_critic_step(
    float* theta, int d_theta,        // actor params
    float* w,     int d_w,            // critic params
    const float* grad_log_pi,         // [d_theta]
    const float* grad_V_s,            // [d_w]
    float V_s, float V_s_next,
    float r, float gamma,
    float alpha_theta, float alpha_w,
    bool terminal,
    float* delta_out                  // scalar TD error
);
```

## Memory Budget
- Runtime RAM: <100 MB (actor + critic gradient buffers)
- Disk: <1 MB (.so/.pyd)
- Allocation: caller-owned buffers; no internal heap

## Performance Target
- Python baseline: NumPy actor+critic per-step update
- Target: ≥5x faster via fused parameter updates
- Benchmark: 3 sizes — (d=64, d=64), (d=256, d=256), (d=1024, d=1024); 10⁶ steps each

## Pre-Implementation Safety Checklist

Follow `backend/extensions/CPP-RULES.md` in full. Key items:

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`, no `volatile`, no detached threads. Document atomic memory ordering.

**Memory:** No raw `new`/`delete` in hot paths. RAII only. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view`. No `[&]` capture beyond scope.

**Type safety:** Explicit `static_cast` for narrowing. No signed/unsigned mismatch. No strict aliasing.

**SIMD:** `_mm256_zeroupper()` at AVX boundaries. `alignas(64)` on θ and w buffers. Max 12 YMM.

**Floating point:** Flush-to-zero on init. NaN/Inf checks on r, γ, V_s, V_s_next, gradients. Double accumulator for gradient dot-products >100 elements.

**Performance:** No `std::endl`, no `std::function`, no `dynamic_cast` in hot loops.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all.

**Build:** No cyclic includes. Static internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_199.py` | Matches NumPy reference within 1e-5 |
| 3 | `ASAN=1 build + pytest` | Zero ASan/UBSan errors |
| 4 | `bench_extensions.py` | ≥5x faster than Python reference |
| 5 | `pytest test_edges_meta_199.py` | Terminal, zero reward, δ=0, large d all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (standalone update kernel; policy and value parameterization are caller's responsibility)

## Pipeline Stage & Non-Conflict

**Stage:** Post-click feedback loop; streaming (online) updates per interaction.
**Owns:** Fused TD-error-driven actor and critic parameter updates.
**Alternative to:** META-198 REINFORCE (Monte-Carlo; higher variance, no bootstrapping — cannot both be primary gradient estimator).
**Coexists with:** META-200 PPO (PPO is an actor-critic variant with clipped objective), META-196 Q-learning (different action-value vs state-value target — not both as primary critic).

## Test Plan
- Deterministic chain MDP: verify critic V_w converges to true V^π within 1e-3 in 10⁴ steps
- Terminal flag: verify `V_w(s')` zeroed in TD target
- δ=0 case: verify no parameter update
- Adversarial: NaN grad input → `ValueError`
- Large d=1024: verify throughput ≥500k steps/sec and no OOM
