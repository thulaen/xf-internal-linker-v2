# META-201 — Deep Deterministic Policy Gradient (DDPG)

## Overview
**Category:** Reinforcement learning (off-policy, deterministic continuous-action actor-critic)
**Extension file:** `ddpg.cpp`
**Replaces/improves:** Enables continuous-action control (e.g. continuous ranking-weight adjustments) where discrete Q-learning or stochastic policy gradients are unsuitable
**Expected speedup:** ≥5x over Python per-batch DDPG update
**RAM:** <500 MB for replay buffer (10⁶ transitions) + 4 networks | **Disk:** <1 MB

## Algorithm

Lillicrap et al.'s deterministic policy gradient with off-policy replay, target networks, and exploration noise. Extends Silver et al. (2014) DPG with deep networks, replay buffer, and Polyak-averaged targets.

```
Networks: actor μ_θ(s), critic Q_φ(s,a), targets μ_{θ'}, Q_{φ'}
Replay buffer D

# Deterministic policy:
a = μ_θ(s) + N_t      # N_t = exploration noise (OU or Gaussian)

for each gradient step:
    sample minibatch (s, a, r, s', done) ~ D
    # Critic TD update with target networks:
    y = r + γ·(1−done)·Q_{φ'}(s', μ_{θ'}(s'))
    L(φ) = E[(y − Q_φ(s,a))²];  φ ← φ − α_φ·∇L

    # Deterministic policy gradient (actor update):
    ∇_θ J ≈ E[ ∇_θ μ_θ(s) · ∇_a Q_φ(s,a) |_{a=μ_θ(s)} ]
    θ ← θ + α_θ·∇J

    # Polyak-averaged target networks:
    θ' ← τ·θ + (1−τ)·θ';   φ' ← τ·φ + (1−τ)·φ'
```

- **Time:** O(batch · (|θ|+|φ|)) per gradient step
- **Space:** O(buffer_capacity · transition_size) + 4 networks
- **Stability:** Requires target networks (τ≈0.005) and replay (decorrelates samples)

## Academic Source
Lillicrap, T.P., Hunt, J.J., Pritzel, A., Heess, N., Erez, T., Tassa, Y., Silver, D. & Wierstra, D. (2016). **"Continuous control with deep reinforcement learning"**. *International Conference on Learning Representations (ICLR)*. [arXiv:1509.02971](https://arxiv.org/abs/1509.02971).

## C++ Interface (pybind11)

```cpp
// Replay buffer (lock-free ring)
struct ReplayBuffer {
    void push(const float* s, const float* a, float r, const float* s_next, bool done);
    void sample_batch(int batch_size, /* out buffers */);
};
// Polyak averaging: target ← τ·source + (1−τ)·target
void polyak_update(float* target, const float* source, int d, float tau);
// TD target y = r + γ·(1−done)·Q_target
void ddpg_td_target(
    const float* r, const uint8_t* done, const float* q_target_next,
    int N, float gamma, float* y_out
);
```

## Memory Budget
- Runtime RAM: <500 MB (10⁶-entry replay buffer at ~400 B/transition ≈ 400 MB + networks)
- Disk: <1 MB (.so/.pyd only; networks serialized by caller)
- Allocation: pre-allocated ring buffer at construction; no per-step heap use

## Performance Target
- Python baseline: PyTorch DDPG critic+actor+target update
- Target: ≥5x faster for replay sampling and Polyak step (bottleneck is typically network forward/back — leave to framework; kernel owns buffer + updates)
- Benchmark: 3 sizes — buffer=10⁴, 10⁵, 10⁶; batch=256

## Pre-Implementation Safety Checklist

Follow `backend/extensions/CPP-RULES.md` in full. Key items:

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** Replay buffer is a producer/consumer; use `std::atomic` with documented memory ordering (`acquire`/`release`). No `std::recursive_mutex`. No `volatile`. Predicate-form waits.

**Memory:** No raw `new`/`delete` in hot paths. Pre-allocated ring buffer. RAII. `reserve()` before fills. Bounds checks in debug.

**Object lifetime:** Self-assignment safe. No dangling `string_view`. No `[&]` capture beyond scope.

**Type safety:** Explicit `static_cast` for narrowing. No signed/unsigned mismatch. No strict aliasing.

**SIMD:** `_mm256_zeroupper()` at AVX boundaries. `alignas(64)` on buffer rows and network params. Max 12 YMM.

**Floating point:** Flush-to-zero on init. NaN/Inf checks on r, γ, τ, q_target. Double accumulator for buffer-mean reductions >100 samples.

**Performance:** No `std::endl`, no `std::function`, no `dynamic_cast` in hot loops. Lock-free push via single-producer ring if possible.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all. τ∈(0,1], batch ≤ buffer size.

**Build:** No cyclic includes. Static internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_201.py` | Matches PyTorch reference within 1e-5 |
| 3 | `ASAN=1 build + pytest` | Zero ASan/UBSan errors |
| 4 | `bench_extensions.py` | ≥5x faster than Python replay/Polyak reference |
| 5 | `pytest test_edges_meta_201.py` | τ=0, τ=1, done=1, empty buffer, full buffer all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks |
| 7 | `TSAN=1 build + pytest` | Zero races in producer/consumer replay |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Optional: shares the Polyak averaging primitive with any future target-network method (e.g. TD3, SAC)

## Pipeline Stage & Non-Conflict

**Stage:** Continuous-action feedback loop (e.g. smooth weight steering based on CTR signal).
**Owns:** Replay buffer, Polyak averaging, TD-target computation.
**Alternative to:** META-200 PPO for on-policy continuous control; they target different regimes — DDPG off-policy deterministic, PPO on-policy stochastic. Cannot run both as primary controller.
**Coexists with:** META-196 Q-learning (discrete), META-202 ε-greedy (not used — DDPG uses additive noise instead).

## Test Plan
- Polyak τ=0: verify target unchanged
- Polyak τ=1: verify target = source
- TD target with done=1: verify y = r (no bootstrap)
- Replay buffer wrap-around: verify oldest entry evicted, sample uniform within valid entries
- Concurrent push/sample (TSAN): verify no races, no lost updates
- Pendulum-v1 smoke test: verify >150 reward after 10⁵ steps
