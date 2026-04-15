# META-112 — Elliptical Slice Sampling (ESS)

## Overview
**Category:** MCMC weight posterior sampler (Gaussian-prior specialized)
**Extension file:** `elliptical_slice.cpp`
**Replaces/improves:** Generic MH/slice when prior is Gaussian and likelihood is expensive
**Expected speedup:** ≥5x over Python reference loop
**RAM:** <12 MB | **Disk:** <1 MB

## Algorithm

```
Input: Gaussian prior N(0, Σ), log-likelihood ℓ(w), initial w, n_samples
Output: chain {w_t} from posterior ∝ N(w; 0, Σ) · exp(ℓ(w))

for t = 1..n_samples:
    # sample ν ~ N(0, Σ), define ellipse w(θ) = w·cos(θ) + ν·sin(θ)
    ν ← N(0, Σ)
    log_y ← ℓ(w) + log(U(0,1))           # slice variable on log-likelihood
    θ ← U(0, 2π)
    (θ_min, θ_max) ← (θ - 2π, θ)
    loop:
        w' ← w·cos(θ) + ν·sin(θ)
        if ℓ(w') > log_y:
            break
        # shrink bracket toward 0
        if θ < 0: θ_min ← θ else: θ_max ← θ
        θ ← U(θ_min, θ_max)
    w ← w'
    append w to chain
```

- **Time complexity:** O(n_samples × avg_likelihood_evals)
- **Space complexity:** O(n_samples × d)
- **Convergence:** Exact (no MH step); tuning-free; ideal for Gaussian process models

## Academic Source
Murray I., Adams R.P., MacKay D.J.C. "Elliptical slice sampling." *Proceedings of AISTATS 2010* 9:541–548. URL: http://proceedings.mlr.press/v9/murray10a.html.

## C++ Interface (pybind11)

```cpp
// Elliptical slice sampler — prior Σ supplied via Cholesky factor L
std::vector<std::vector<float>> elliptical_slice_sample(
    const float* initial_w, int d,
    const float* prior_chol_L,            // Σ = L·Lᵀ
    std::function<float(const float*)> log_likelihood,
    int n_samples, uint64_t seed
);
```

## Memory Budget
- Runtime RAM: <12 MB (chain + L·ε buffer)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(n_samples)`

## Performance Target
- Python baseline: pure-python reference from Murray's paper
- Target: ≥5x faster
- Benchmark: 5k samples × d ∈ {10, 50, 200}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays. Vectorize the cos/sin combination.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Use `std::sincos` where available. Double accumulator for L·ε product reductions >100.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all. Verify L is lower-triangular and non-negative diagonal.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU. Seeded RNG.

See `backend/extensions/CPP-RULES.md` for full policy.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_112.py` | Posterior marginals match reference within 3% |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥3x faster than Python reference |
| 5 | `pytest test_edges_meta_112.py` | Diagonal Σ, rank-deficient L, ℓ=constant all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Requires pre-computed prior Cholesky factor L
- Coexists with GP kernels in downstream models

## Pipeline Stage Non-Conflict
**Owns:** Posterior sampling under Gaussian priors (no proposal tuning).
**Alternative to:** META-109 HMC when gradient is unavailable but prior is Gaussian.
**Coexists with:** META-106 MH, META-108 Slice — chosen via config flag.

## Test Plan
- Gaussian prior × Gaussian likelihood → closed-form posterior: mean within 2%, cov within 5%
- Constant likelihood: chain marginals match prior
- d=1, Σ=1: reduces to standard slice on Gaussian prior
- NaN likelihood: verify raises ValueError
