# META-108 — Slice Sampler

## Overview
**Category:** MCMC weight posterior sampler (auxiliary-variable, tuning-free)
**Extension file:** `slice_sampling.cpp`
**Replaces/improves:** Manual proposal tuning in META-106; step-out procedure removes scale sensitivity
**Expected speedup:** ≥5x over Python step-out/shrinkage loop
**RAM:** <10 MB | **Disk:** <1 MB

## Algorithm

```
Input: unnormalized density p(w), initial w_0, step size ω, n_samples
Output: chain {w_t} approximating samples from p

w ← w_0
for t = 1..n_samples:
    # sample y ~ U(0, p(w)), then sample w' ~ U({w : p(w) ≥ y})
    log_y ← log p(w) + log(U(0,1))
    (L, R) ← step_out(w, ω, log_y)        # expand interval until both endpoints below log_y
    loop:
        w' ← U(L, R)
        if log p(w') ≥ log_y:
            break
        shrink (L, R) toward w            # replace side closest to w' with w'
    w ← w'
    append w to chain
```

- **Time complexity:** O(n_samples × avg_step_out_cost)
- **Space complexity:** O(n_samples × d)
- **Convergence:** Detailed balance via auxiliary slice variable; mixing robust to scale

## Academic Source
Neal R.M. "Slice sampling." *Annals of Statistics* 31(3):705–767, 2003. DOI: 10.1214/aos/1056562461.

## C++ Interface (pybind11)

```cpp
// Univariate slice sampler with step-out and shrinkage
std::vector<float> slice_sample(
    float initial_w,
    std::function<float(float)> log_density,
    float step_size, int max_step_out,
    int n_samples, uint64_t seed
);
```

## Memory Budget
- Runtime RAM: <10 MB
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(n_samples)`

## Performance Target
- Python baseline: step-out + shrinkage in pure Python
- Target: ≥5x faster
- Benchmark: 10k samples × density of 3 scales (σ ∈ {0.1, 1, 10})

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for reductions >100 elements. Use log-space for slice comparison.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all. `max_step_out` must be bounded to prevent runaway expansion.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU. Seeded RNG (xoshiro256** or PCG).

See `backend/extensions/CPP-RULES.md` for full policy.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_108.py` | KS distance vs reference < 0.05 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥3x faster than Python reference |
| 5 | `pytest test_edges_meta_108.py` | Heavy-tail, multi-modal, tiny scale all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (standalone univariate sampler; multivariate via coordinate-wise wrapper)

## Pipeline Stage Non-Conflict
**Owns:** Tuning-free univariate slice sampling.
**Alternative to:** META-106 MH (avoids proposal tuning).
**Coexists with:** META-107 Gibbs (slice can be the conditional sampler inside Gibbs).

## Test Plan
- N(0,1) target: marginal matches reference within 3%
- Bimodal Gaussian mix: verify both modes visited
- Heavy-tail (Cauchy): verify step-out does not exceed max_step_out cap
- NaN density: verify raises ValueError
