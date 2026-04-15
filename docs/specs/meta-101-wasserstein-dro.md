# META-101 — Wasserstein DRO

## Overview
**Category:** Robustness with geometric ambiguity (P12 robustness & sampling block)
**Extension file:** `wasserstein_dro.cpp`
**Replaces/improves:** ϕ-divergence DRO (META-100) for cases where geometric distance between examples (e.g. embedding space) is meaningful — Wasserstein ball protects against perturbations that move mass within the metric, not just reweight existing samples
**Expected speedup:** ≥3x over Python primal-dual loop
**RAM:** <16 MB | **Disk:** <1 MB

## Algorithm

```
Input: per-example losses ℓ_i(w) for i = 1..n, ground metric d(x_i, x_j),
       Wasserstein order p ∈ {1, 2}, radius ρ
Output: w* = argmin_w max_{Q : W_p(Q, P_train) ≤ ρ} E_Q[ℓ(w, x)]

Strong duality (Esfahani & Kuhn 2018, Theorem 4.2):
  max E_Q[ℓ] = inf_{λ ≥ 0} { λ·ρ^p + (1/n)·Σ_i sup_{x'} (ℓ_i(x') − λ·d(x_i, x')^p) }

For convex losses (or via approximation):
  inner sup over x' is solved analytically as
       φ_λ(x_i) = sup_{x'} (ℓ(x') − λ·d(x_i, x')^p)
  outer inf over λ is 1-D bisection.

Per outer SGD step (data-driven approximation):
  for i = 1..n:
      x'_i ← argmax_x' (ℓ_i(x') − λ·d(x_i, x')^p)        // local adversarial perturb
      ℓ̃_i  ← ℓ(x'_i)
  ∇_w L_W-DRO ≈ (1/n) Σ_i ∇_w ℓ̃_i
  bisect λ to enforce average perturbation cost ≈ ρ^p
```

- **Time complexity:** O(n · cost(inner sup) · log(1/tol)) per step
- **Space complexity:** O(n) for losses, perturbed examples
- **Convergence:** Convex when ℓ is convex in (w, x) and ground metric is Euclidean

## Academic source
Mohajerin Esfahani, P. and Kuhn, D., "Data-Driven Distributionally Robust Optimization Using the Wasserstein Metric: Performance Guarantees and Tractable Reformulations", *Mathematical Programming* (also SIAM Journal on Optimization treatment), 171:115–166, 2018.

## C++ Interface (pybind11)

```cpp
// 1-D dual: given losses + a perturbation-cost vector, find optimal λ via bisection
float wasserstein_dro_dual_lambda(
    const float* losses, const float* perturb_costs, int n,
    float rho, float p, float tol, int max_bisect
);

// Convenience: given perturbed losses (from caller's adversary) and costs, return
// re-weighted gradient combined with adversarial loss
void wasserstein_dro_grad(
    const float* losses, const float* perturb_costs, int n,
    const float* grads_nxd, int d,
    float rho, float p,
    float* grad_out, float* lambda_out
);
```

## Memory Budget
- Runtime RAM: <16 MB at n=1e5 (losses + perturb costs + bisection scratch + grad accumulator)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: pre-sized vectors; no per-iter alloc

## Performance Target
- Python baseline: NumPy + `scipy.optimize.brentq` for λ
- Target: ≥3x faster on n=1e4
- Benchmark: 3 sizes — n ∈ {1e3, 1e4, 1e5}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled. Validate p ∈ {1, 2} (extend later for general p), ρ > 0.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays. `pow` and reductions vectorised.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for cost reductions when n > 1e4. Bisection tolerance set in dual-variable space, not loss space.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all. ρ = 0 collapses to ERM (no perturbation). Bisection failure raises with diagnostic message.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

Adheres to `backend/extensions/CPP-RULES.md` in full.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_101.py` | λ matches scipy brentq within 1e-5 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `pytest backend/benchmarks/test_bench_wasserstein.py` | ≥3x speedup on 3 sizes |
| 5 | `pytest test_edges_meta_101.py` | ρ=0 (collapses to ERM), p=1 vs p=2, n=1, all-equal costs, NaN handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | Constraint | (1/n) Σ d(x_i, x'_i)^p ≤ ρ^p within 1e-4 |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- META-100 DRO (sibling robustness; complementary ambiguity definition)
- pybind11 ≥ 2.10

## Pipeline stage non-conflict declaration
- **Owns:** Wasserstein-ball DRO dual solve and gradient combiner
- **Alternative to:** META-100 ϕ-divergence DRO (Wasserstein is geometric, divergence is reweighting only)
- **Coexists with:** META-102 OHEM, META-103 reservoir, META-104 importance weighting, all P8/P9/P10/P11 metas

## Test Plan
- ρ = 0: verify λ → ∞, perturbation = 0, gradient = ERM gradient
- ρ → ∞: verify λ → 0, adversary unconstrained
- p = 1 vs p = 2 produce different λ on same losses
- Bisection converges in ≤ 60 iters for float precision
- Mean perturbation cost matches ρ^p within tolerance after solve
