# META-198 — REINFORCE (Monte-Carlo Policy Gradient)

## Overview
**Category:** Reinforcement learning (policy-gradient; likelihood ratio)
**Extension file:** `reinforce.cpp`
**Replaces/improves:** Parameterized policy optimization for continuous/large action spaces where tabular Q-learning cannot scale
**Expected speedup:** ≥5x over Python per-trajectory gradient accumulation
**RAM:** <50 MB for θ with ≤10⁶ params | **Disk:** <1 MB

## Algorithm

Williams' likelihood-ratio policy gradient: use Monte-Carlo return `G_t` to estimate the expected-return gradient and take stochastic gradient ascent on policy parameters θ.

```
Input: policy π_θ(a|s), learning rate α, discount γ
Output: θ maximizing J(θ) = E_τ[Σ_t γ^t·r_t]

# Paper gradient (likelihood-ratio form):
∇J(θ) = E_τ[ Σ_t ∇_θ log π_θ(a_t|s_t) · G_t ]

for each episode:
    rollout trajectory τ = (s_0,a_0,r_0, …, s_T)
    for t = 0..T-1:
        G_t = Σ_{k=t}^{T-1} γ^{k-t}·r_k
        # Per-step update:
        θ_{t+1} = θ_t + α · ∇_θ log π_θ(a_t|s_t) · G_t
```

- **Time:** O(T · |θ|) per episode
- **Space:** O(|θ|) plus O(T) trajectory buffer
- **Variance:** High; typically reduced by baseline `b(s)` (optional, disabled by default)

## Academic Source
Williams, R.J. (1992). **"Simple statistical gradient-following algorithms for connectionist reinforcement learning"**. *Machine Learning*, 8(3-4), 229-256. DOI: [10.1007/BF00992696](https://doi.org/10.1007/BF00992696).

## C++ Interface (pybind11)

```cpp
// Monte-Carlo return computation
void compute_returns(
    const float* rewards, int T, float gamma, float* returns_out
);
// Likelihood-ratio policy gradient accumulator (softmax/Gaussian head)
void reinforce_grad_accum(
    const float* log_prob_grads,  // [T, d]
    const float* returns,         // [T]
    int T, int d,
    float* grad_out               // [d], in/out accumulator
);
```

## Memory Budget
- Runtime RAM: <50 MB (gradient buffer `d` floats + trajectory `T` floats)
- Disk: <1 MB (.so/.pyd)
- Allocation: caller-owned buffers; no internal `new`/`delete`

## Performance Target
- Python baseline: NumPy vectorized gradient accumulation per trajectory
- Target: ≥5x faster via fused multiply-add and cache-friendly stride
- Benchmark: 3 sizes — (T=100, d=64), (T=500, d=256), (T=1000, d=1024)

## Pre-Implementation Safety Checklist

Follow `backend/extensions/CPP-RULES.md` in full. Key items:

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`, no `volatile`, no detached threads. Document atomic memory ordering.

**Memory:** No raw `new`/`delete` in hot paths. RAII only. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view`. No `[&]` capture beyond scope.

**Type safety:** Explicit `static_cast` for narrowing. No signed/unsigned mismatch. No strict aliasing.

**SIMD:** `_mm256_zeroupper()` at AVX boundaries. `alignas(64)` on gradient buffers. Max 12 YMM.

**Floating point:** Flush-to-zero on init. NaN/Inf checks on rewards, γ, α. Double accumulator for return sums and gradient reductions >100 elements (mandatory — policy gradient is variance-sensitive).

**Performance:** No `std::endl`, no `std::function`, no `dynamic_cast` in hot loops. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all.

**Build:** No cyclic includes. Static internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_198.py` | Matches NumPy reference within 1e-5 |
| 3 | `ASAN=1 build + pytest` | Zero ASan/UBSan errors |
| 4 | `bench_extensions.py` | ≥5x faster than Python reference |
| 5 | `pytest test_edges_meta_198.py` | T=1, γ=0, γ=1, zero rewards all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (standalone gradient kernel; policy parameterization is caller's responsibility)

## Pipeline Stage & Non-Conflict

**Stage:** Post-click feedback loop with parameterized policy (e.g. softmax over ranking features).
**Owns:** Monte-Carlo likelihood-ratio gradient assembly.
**Alternative to:** META-199 Actor-Critic (bootstrapped variance-reduced alternative — cannot both be primary gradient estimator).
**Coexists with:** META-200 PPO (PPO uses REINFORCE-style gradient as a building block), META-04 coordinate ascent.

## Test Plan
- Bandit with 2 arms (T=1): verify gradient direction matches closed form
- Discount γ=0: verify only immediate reward contributes to `G_t`
- Zero rewards: verify gradient is exactly zero
- Known Gaussian policy: verify gradient norm matches analytic expectation within 3σ Monte Carlo
- Large T=1000, d=1024: verify throughput and no OOM
