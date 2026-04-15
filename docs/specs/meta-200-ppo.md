# META-200 — Proximal Policy Optimization (PPO)

## Overview
**Category:** Reinforcement learning (trust-region policy-gradient, clipped surrogate)
**Extension file:** `ppo.cpp`
**Replaces/improves:** Stable, sample-efficient alternative to REINFORCE and vanilla Actor-Critic; the de-facto deep-RL default
**Expected speedup:** ≥5x over Python per-minibatch surrogate+clip computation
**RAM:** <200 MB for rollout buffer + two policy networks | **Disk:** <1 MB

## Algorithm

Schulman et al.'s clipped-surrogate objective: limit the per-step policy update by clipping the importance-sampling ratio between new and old policies. This preserves the monotonic-improvement intuition of TRPO with first-order optimization only.

```
Input: old policy π_{θ_old}, advantages Â_t, clip ε (typically 0.2), epochs K
Output: new policy π_θ

# Importance ratio:
r_t(θ) = π_θ(a_t|s_t) / π_{θ_old}(a_t|s_t)

# Paper clipped surrogate objective (maximize):
L(θ) = E[ min( r_t(θ)·Â_t , clip(r_t(θ), 1−ε, 1+ε)·Â_t ) ]

for epoch = 1..K:
    for each minibatch of rollout:
        compute r_t(θ) and Â_t (e.g. GAE)
        θ ← θ + α · ∇_θ L(θ)
```

- **Time:** O(K · N · d) per rollout of N transitions, d policy params
- **Space:** O(N) rollout buffer + O(d) gradient
- **Stability:** Clip prevents destructive updates; monotonic improvement empirically observed

## Academic Source
Schulman, J., Wolski, F., Dhariwal, P., Radford, A. & Klimov, O. (2017). **"Proximal policy optimization algorithms"**. arXiv preprint. [arXiv:1707.06347](https://arxiv.org/abs/1707.06347).

## C++ Interface (pybind11)

```cpp
// Per-sample clipped surrogate loss and gradient
void ppo_clip_loss(
    const float* log_probs_new,   // [N]
    const float* log_probs_old,   // [N]
    const float* advantages,      // [N]
    int N, float clip_eps,
    float* loss_per_sample,       // [N]
    float* ratio_out              // [N] (diagnostic)
);
// Generalized Advantage Estimation (Schulman 2016, used with PPO)
void compute_gae(
    const float* rewards, const float* values,
    const uint8_t* dones, int T,
    float gamma, float lambda,
    float* advantages_out, float* returns_out
);
```

## Memory Budget
- Runtime RAM: <200 MB (rollout N≤10⁵ + 2× policy params d≤10⁶)
- Disk: <1 MB (.so/.pyd)
- Allocation: caller-owned buffers; no internal heap

## Performance Target
- Python baseline: PyTorch/NumPy vectorized PPO loss
- Target: ≥5x faster via fused exp/clip/min and SIMD horizontal ops
- Benchmark: 3 sizes — N=1024, N=10k, N=100k rollouts

## Pre-Implementation Safety Checklist

Follow `backend/extensions/CPP-RULES.md` in full. Key items:

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`, no `volatile`, no detached threads. Document atomic memory ordering.

**Memory:** No raw `new`/`delete` in hot paths. RAII only. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view`. No `[&]` capture beyond scope.

**Type safety:** Explicit `static_cast` for narrowing. No signed/unsigned mismatch. No strict aliasing.

**SIMD:** `_mm256_zeroupper()` at AVX boundaries. `alignas(64)` on rollout buffers. Max 12 YMM.

**Floating point:** Flush-to-zero on init. NaN/Inf checks on log-probs, advantages, ε. Clamp ratio to safe range before `std::min`. Double accumulator for mean-loss reductions >100 samples.

**Performance:** No `std::endl`, no `std::function`, no `dynamic_cast` in hot loops. Use `std::fma` where beneficial.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all. Validate clip_eps ∈ (0, 1).

**Build:** No cyclic includes. Static internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_200.py` | Matches PyTorch reference within 1e-5 |
| 3 | `ASAN=1 build + pytest` | Zero ASan/UBSan errors |
| 4 | `bench_extensions.py` | ≥5x faster than PyTorch CPU reference |
| 5 | `pytest test_edges_meta_200.py` | ε=0, ratio=1, zero-advantage, large-N all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Optional: uses META-198 REINFORCE gradient primitive; reuses GAE helper

## Pipeline Stage & Non-Conflict

**Stage:** Post-click feedback loop; batched off-line epochs over a rollout buffer.
**Owns:** Clipped-surrogate PPO loss, ratio computation, GAE.
**Alternative to:** META-198 REINFORCE and META-199 Actor-Critic as the primary policy-gradient engine (only one should be the active learner at a time).
**Coexists with:** META-202 ε-greedy (not used — PPO samples from the stochastic policy directly), META-04 coordinate ascent (offline).

## Test Plan
- Ratio r=1 (θ==θ_old): verify loss = −Â (unclipped branch)
- Ratio r>1+ε with positive Â: verify clip branch active and gradient zeroed
- Ratio r<1−ε with negative Â: verify clip branch active
- Zero advantage: verify loss=0 and gradient=0
- GAE with γ=0, λ=0: verify advantages = rewards − values (one-step)
- Large rollout N=10⁵: verify throughput ≥10 MSamples/sec and no OOM
