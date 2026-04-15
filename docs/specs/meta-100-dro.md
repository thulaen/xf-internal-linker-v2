# META-100 — Distributionally Robust Optimisation (DRO)

## Overview
**Category:** Robustness (P12 robustness & sampling block)
**Extension file:** `dro.cpp`
**Replaces/improves:** ERM (empirical-risk minimisation) — DRO optimises worst-case loss over a neighbourhood of the empirical distribution, providing protection against tail subgroups (rare query types, minority sections)
**Expected speedup:** ≥4x over Python primal-dual loop
**RAM:** <8 MB | **Disk:** <1 MB

## Algorithm

```
Input: per-example losses ℓ_i(w) for i = 1..n, ambiguity set Ω parameterised by ρ
       Ω = { Q ∈ Δ^{n−1} : D(Q ‖ P_train) ≤ ρ }    where D is a divergence (KL, χ²)
Output: w* = argmin_w max_{Q ∈ Ω} E_Q[ℓ(w, x)]

Inner max (per outer w step) — example with KL constraint:
  Q*_i = exp(ℓ_i(w) / η) / Σ_j exp(ℓ_j(w) / η)
  pick η > 0 so that KL(Q* ‖ P) = ρ                 (1-D bisection on η)

Outer min: standard SGD/Adam with re-weighted gradient
  ∇_w L_DRO(w) = Σ_i Q*_i · ∇_w ℓ_i(w)

Special case (CVaR): max-of-α-tail is recovered with χ² uncertainty + appropriate ρ
```

- **Time complexity:** Outer SGD step O(n · cost(∇ℓ)), inner solve O(n · log(1/tol)) via bisection
- **Space complexity:** O(n) for per-example losses and Q*
- **Convergence:** Stochastic gradient descent on the DRO objective; convex when ℓ is convex in w

## Academic source
Ben-Tal, A., El Ghaoui, L. and Nemirovski, A., *Robust Optimization*, Princeton University Press, 2009. (Foundational text; Chapter 14 develops the DRO framework specifically.)

## C++ Interface (pybind11)

```cpp
enum class DROAmbiguity { KL, ChiSquared };

// Inner solver: given losses, return tilted distribution Q*
std::vector<float> dro_inner_solve(
    const float* losses, int n,
    DROAmbiguity ambig, float rho,
    float tol = 1e-6f, int max_bisect = 60
);

// Convenience: compute DRO-reweighted gradient (caller supplies per-example grads)
void dro_reweighted_gradient(
    const float* losses, int n,
    const float* grads_nxd, int d,
    DROAmbiguity ambig, float rho,
    float* grad_out
);
```

## Memory Budget
- Runtime RAM: <8 MB at n=1e5 (losses + Q* + bisection scratch); independent of d for inner solve
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: pre-sized vectors; no per-iter alloc inside bisection

## Performance Target
- Python baseline: NumPy primal-dual loop with `scipy.optimize.brentq` for η
- Target: ≥4x faster on n=1e5 (in-place exp + bisection without Python overhead)
- Benchmark: 3 sizes — n ∈ {1e3, 1e4, 1e5}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled. Validate ρ > 0 and finite, n ≥ 1, d ≥ 1.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays. exp/log vectorised in inner exponential-tilt computation.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Numerically stable softmax (subtract max loss before `exp`) inside inner solve. Double accumulator for partition function `Σ exp`.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`. Bisection step count bounded (max_bisect default 60 — sufficient for float precision).

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all. ρ = 0 returns uniform Q (no tilting). ρ = ∞ returns one-hot at argmax loss.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

Adheres to `backend/extensions/CPP-RULES.md` in full.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_100.py` | Q* matches Python brentq+softmax reference within 1e-5 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `pytest backend/benchmarks/test_bench_dro.py` | ≥4x speedup on 3 sizes |
| 5 | `pytest test_edges_meta_100.py` | n=1, ρ=0 (uniform Q), ρ→∞ (one-hot), all-equal losses, NaN handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | KL constraint | Resulting KL(Q* ‖ P) = ρ within 1e-5 |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- pybind11 ≥ 2.10
- No external deps

## Pipeline stage non-conflict declaration
- **Owns:** ϕ-divergence-ball DRO inner solve and gradient reweighting
- **Alternative to:** ERM (uniform 1/n weighting), META-101 Wasserstein-DRO (geometry-aware ambiguity)
- **Coexists with:** META-102 OHEM (different reweighting heuristic), META-103 reservoir, META-104 importance weighting; all P8 regularisers, P9 calibrators, P10 schedulers, P11 averagers

## Test Plan
- ρ = 0: verify Q* = uniform 1/n
- ρ → ∞: verify Q* concentrates on argmax loss
- All losses equal: verify Q* = uniform regardless of ρ (KL = 0 trivially achievable)
- KL recovered: post-fit KL(Q* ‖ uniform) = ρ within tolerance
- Reweighted gradient = uniform gradient when ρ = 0
