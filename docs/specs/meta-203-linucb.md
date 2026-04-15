# META-203 — LinUCB (Linear Contextual Bandit with UCB)

## Overview
**Category:** Contextual bandits (linear payoff, upper-confidence-bound exploration)
**Extension file:** `linucb.cpp`
**Replaces/improves:** Click-rate exploration for per-link contextual selection (features: link class, suggested weight, publisher signal, etc.)
**Expected speedup:** ≥5x over Python `np.linalg.solve` + score loop per decision
**RAM:** <200 MB for |A|≤1024 arms × d≤64 features | **Disk:** <1 MB

## Algorithm

Li, Chu, Langford, Schapire model each arm `a` as having a linear expected payoff `E[r|x,a] = x_a^T · θ_a*`. Per arm, maintain a ridge-regression sufficient statistic and pick the arm with the highest **upper confidence bound** on the predicted reward.

```
Input: per-arm design matrix A_a = I_d + Σ x_a x_a^T, vector b_a = Σ x_a r_a, tuning α
Output: chosen arm a_t

for each round t:
    observe context x_{t,a} ∈ ℝ^d for each arm a
    for each arm a:
        θ̂_a = A_a^{-1} · b_a
        # Paper score (mean + UCB confidence term):
        p_{t,a} = x_{t,a}^T · θ̂_a + α · sqrt( x_{t,a}^T · A_a^{-1} · x_{t,a} )

    # Paper decision rule:
    a_t = argmax_a p_{t,a}

    observe reward r_t
    A_{a_t} ← A_{a_t} + x_{t,a_t} · x_{t,a_t}^T
    b_{a_t} ← b_{a_t} + r_t · x_{t,a_t}
```

- **Time:** O(|A| · d²) per round using cached A_a^{-1} (Sherman-Morrison rank-1 update)
- **Space:** O(|A| · d²) for per-arm `A_a` (and optionally its inverse)
- **Regret:** O(√(T·d·log T)) under Li et al. Theorem 1

## Academic Source
Li, L., Chu, W., Langford, J. & Schapire, R.E. (2010). **"A contextual-bandit approach to personalized news article recommendation"**. *Proc. 19th International Conference on World Wide Web (WWW)*, 661-670. DOI: [10.1145/1772690.1772758](https://doi.org/10.1145/1772690.1772758).

## C++ Interface (pybind11)

```cpp
// Sherman-Morrison rank-1 update of cached inverse A⁻¹ after observing x
void sherman_morrison_update(float* A_inv, const float* x, int d);
// Score a single arm: mean + α·sqrt(x^T A^{-1} x)
float linucb_score(
    const float* A_inv, const float* b, const float* x,
    int d, float alpha
);
// Batched decision across |A| arms
int linucb_choose(
    const float* A_inv_stack,   // [|A|, d, d]
    const float* b_stack,       // [|A|, d]
    const float* x_stack,       // [|A|, d]
    int n_arms, int d, float alpha
);
```

## Memory Budget
- Runtime RAM: <200 MB (|A|=1024 arms × 64·64·4 B ≈ 16 MB for A_inv; plus b, x, θ̂)
- Disk: <1 MB (.so/.pyd only; A_a and b_a serialized by caller)
- Allocation: caller-owned stacked buffers; no internal heap

## Performance Target
- Python baseline: NumPy `solve` + manual confidence bound per arm
- Target: ≥5x faster via cached A⁻¹ (Sherman-Morrison) and SIMD dot/quadratic-form
- Benchmark: 3 sizes — (|A|=16, d=8), (|A|=128, d=32), (|A|=1024, d=64)

## Pre-Implementation Safety Checklist

Follow `backend/extensions/CPP-RULES.md` in full. Key items:

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`, no `volatile`, no detached threads. Per-arm updates are independent and parallelizable; document atomic memory ordering if shared.

**Memory:** No raw `new`/`delete` in hot paths. RAII. `reserve()` before known-size fills. Bounds-checked in debug.

**Object lifetime:** Self-assignment safe. No dangling `string_view`. No `[&]` capture beyond scope.

**Type safety:** Explicit `static_cast` for narrowing. No signed/unsigned mismatch. No strict aliasing.

**SIMD:** `_mm256_zeroupper()` at AVX boundaries. `alignas(64)` on `A_inv` rows, `b`, `x`. Max 12 YMM.

**Floating point:** Flush-to-zero on init. NaN/Inf checks on x, r, α. **Symmetrize A_inv after Sherman-Morrison** (guard against drift). Double accumulator for `x^T A^{-1} x` quadratic form (mandatory — sqrt of it must be non-negative).

**Performance:** No `std::endl`, no `std::function`, no `dynamic_cast`. Avoid full `d×d` inverse recomputation in the hot loop.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all. Clamp `x^T A^{-1} x` to ≥0 before sqrt.

**Build:** No cyclic includes. Static internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_203.py` | Matches NumPy reference within 1e-5 |
| 3 | `ASAN=1 build + pytest` | Zero ASan/UBSan errors |
| 4 | `bench_extensions.py` | ≥5x faster than Python reference |
| 5 | `pytest test_edges_meta_203.py` | α=0 (pure greedy), d=1, ill-conditioned A, zero x all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (standalone per-arm linear bandit kernel)

## Pipeline Stage & Non-Conflict

**Stage:** Link-candidate selection with contextual features (inner loop of the ranker when budget allows exploration).
**Owns:** Linear UCB per-arm score and Sherman-Morrison sufficient-statistic update.
**Alternative to:** META-204 LinTS (Thompson sampling) on the same linear-payoff problem — pick one per deployment.
**Coexists with:** META-205 Cascading bandits (layered on top when the action is an ordered list), META-202 ε-greedy (not used — UCB replaces it).

## Test Plan
- d=1 scalar arm: verify score = θ̂ + α·sqrt(1/A) matches closed form
- α=0: verify decision collapses to ridge-regression greedy
- Ill-conditioned A (near-singular): verify ridge regularization prevents NaN
- Zero context x=0: verify score = α·0 = 0
- Regret vs LinTS on a synthetic linear bandit: verify both sublinear over T=10⁴
- |A|=1024, d=64: verify decision latency <1 ms
