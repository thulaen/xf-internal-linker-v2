# META-204 — LinTS (Linear Thompson Sampling)

## Overview
**Category:** Contextual bandits (linear payoff, Bayesian posterior-sampling exploration)
**Extension file:** `lints.cpp`
**Replaces/improves:** Bayesian alternative to META-203 LinUCB; often empirically stronger on real click data due to randomized exploration
**Expected speedup:** ≥5x over Python multivariate-Gaussian sample + argmax per decision
**RAM:** <200 MB for |A|≤1024 arms × d≤64 | **Disk:** <1 MB

## Algorithm

Agrawal & Goyal's Thompson-sampling variant for linear contextual bandits. Maintain a Gaussian posterior over each arm's parameter `θ_a`; at each round draw a sample from the posterior and pick the arm with the highest sampled predicted reward.

```
Input: per-arm A_a = I_d + Σ x_a x_a^T, b_a = Σ x_a r, prior variance v² (Agrawal-Goyal v = R·sqrt(d·ln(t/δ)/ε))
Output: chosen arm a_t

for each round t:
    observe contexts x_{t,a}
    for each arm a:
        μ_a = A_a^{-1} · b_a
        Σ_a = v² · A_a^{-1}
        # Paper posterior sample:
        θ̃_a ~ N( μ_a, Σ_a )
        # Paper score:
        s_{t,a} = x_{t,a}^T · θ̃_a

    # Paper decision rule:
    a_t = argmax_a s_{t,a}

    observe reward r_t
    A_{a_t} ← A_{a_t} + x_{t,a_t}·x_{t,a_t}^T
    b_{a_t} ← b_{a_t} + r_t · x_{t,a_t}
```

- **Time:** O(|A| · d²) per round; sample via `θ̃ = μ + v·L·z`, L = Cholesky(A^{-1}), z ~ N(0, I_d)
- **Space:** O(|A| · d²) for `A_a`, `L_a`
- **Regret:** O(d·√(T·log T)·log(T/δ)) — Agrawal-Goyal Theorem 1

## Academic Source
Agrawal, S. & Goyal, N. (2013). **"Thompson sampling for contextual bandits with linear payoffs"**. *Proc. 30th International Conference on Machine Learning (ICML)*, 127-135. [PMLR link](http://proceedings.mlr.press/v28/agrawal13.html).

## C++ Interface (pybind11)

```cpp
// Draw posterior sample θ̃ = μ + v·L·z with cached Cholesky L of A_inv
void lints_sample_theta(
    const float* mu, const float* L_A_inv,   // [d], [d,d] lower-triangular
    int d, float v, uint64_t* rng_state,
    float* theta_tilde_out                    // [d]
);
// Batched decision across |A| arms
int lints_choose(
    const float* mu_stack, const float* L_stack,
    const float* x_stack, int n_arms, int d,
    float v, uint64_t* rng_state
);
// Incremental Cholesky update (rank-1) after posterior update
void cholesky_rank1_update(float* L, const float* x, int d);
```

## Memory Budget
- Runtime RAM: <200 MB (stacked μ_a, L_a for |A|=1024, d=64)
- Disk: <1 MB (.so/.pyd only)
- Allocation: caller-owned stacked buffers; no internal heap in hot loop

## Performance Target
- Python baseline: `numpy.random.multivariate_normal` + per-arm argmax
- Target: ≥5x faster via cached Cholesky and reusable Gaussian samples
- Benchmark: 3 sizes — (|A|=16, d=8), (|A|=128, d=32), (|A|=1024, d=64)

## Pre-Implementation Safety Checklist

Follow `backend/extensions/CPP-RULES.md` in full. Key items:

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** Per-arm updates independent and parallelizable. Per-thread RNG state (caller-owned) to avoid contention.

**Memory:** No raw `new`/`delete` in hot paths. RAII. `reserve()` before known-size fills. Bounds-checked in debug.

**Object lifetime:** Self-assignment safe. No dangling `string_view`. No `[&]` capture beyond scope.

**Type safety:** Explicit `static_cast` for narrowing. No signed/unsigned mismatch. No strict aliasing.

**SIMD:** `_mm256_zeroupper()` at AVX boundaries. `alignas(64)` on μ, L rows. Max 12 YMM.

**Floating point:** Flush-to-zero on init. NaN/Inf checks on x, r, v. Maintain positive-definiteness of L via rank-1 update (not full refactor). Double accumulator for quadratic forms >100 elements.

**Performance:** No `std::endl`, no `std::function`, no `dynamic_cast`. Gaussian samples via Box-Muller or Ziggurat — not `std::normal_distribution` in hot loop.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all. Validate v>0.

**Build:** No cyclic includes. Static internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Per-thread RNG (no global seed write). Scrub sensitive memory.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_204.py` | Mean + covariance of samples match NumPy reference within 1e-3 over 10⁵ draws |
| 3 | `ASAN=1 build + pytest` | Zero ASan/UBSan errors |
| 4 | `bench_extensions.py` | ≥5x faster than Python reference |
| 5 | `pytest test_edges_meta_204.py` | v=0 (collapses to greedy), d=1, ill-conditioned A, tied scores all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks |
| 7 | `TSAN=1 build + pytest` | Zero races (per-thread RNG) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Shares Cholesky rank-1 update primitive with potential future Bayesian methods.

## Pipeline Stage & Non-Conflict

**Stage:** Link-candidate selection with contextual features (same slot as META-203 LinUCB).
**Owns:** Per-arm Bayesian posterior sampling and argmax decision.
**Alternative to:** META-203 LinUCB on the same linear-payoff problem — exactly one should be active per deployment.
**Coexists with:** META-205 Cascading bandits (top-level structure), META-202 ε-greedy (not used — Thompson sampling is itself the exploration mechanism).

## Test Plan
- v=0 (no exploration): verify collapses to ridge-regression greedy (equivalent to LinUCB α=0)
- Large v (heavy exploration): verify near-uniform arm selection
- Sample statistics: verify empirical mean of θ̃ converges to A^{-1}·b and covariance to v²·A^{-1}
- Cholesky rank-1 update: verify L_new·L_new^T = A^{-1}_new within 1e-5
- Ill-conditioned A: verify ridge term keeps posterior sampling stable
- Regret vs LinUCB on a synthetic bandit: verify both sublinear over T=10⁴
