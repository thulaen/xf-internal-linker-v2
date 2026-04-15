# META-114 — Mean-Field Variational Inference

## Overview
**Category:** Variational posterior approximator (factorized)
**Extension file:** `mean_field_vi.cpp`
**Replaces/improves:** MCMC posterior when point estimate or fast approximation suffices
**Expected speedup:** ≥6x over Python CAVI loop (pure-C++ coordinate updates)
**RAM:** <15 MB | **Disk:** <1 MB

## Algorithm

```
Input: factorized family q(z) = Π q_i(z_i), joint p(x,z), data x
Output: variational params λ minimizing KL(q || p(·|x))

# maximize ELBO L(q) = E_q[log p(x,z)] − E_q[log q(z)] under factorized q(z) = Π q_i(z_i)
initialize λ
repeat:
    for i = 1..d:
        # coordinate update: q_i*(z_i) ∝ exp(E_{q_{-i}}[log p(x, z)])
        λ_i ← closed_form_update(λ_{-i}, x)
    compute ELBO
until |ΔELBO| < tol
return λ
```

- **Time complexity:** O(epochs × d × coord_update_cost)
- **Space complexity:** O(d × params_per_factor)
- **Convergence:** ELBO monotonically non-decreasing; converges to local optimum of non-convex ELBO

## Academic Source
Beal M.J. *Variational Algorithms for Approximate Bayesian Inference.* Ph.D. thesis, Gatsby Computational Neuroscience Unit, University College London, 2003. URL: https://www.cse.buffalo.edu/faculty/mbeal/thesis/.

## C++ Interface (pybind11)

```cpp
// Coordinate Ascent Variational Inference (CAVI)
std::vector<float> mean_field_vi(
    const float* initial_lambda, int d, int params_per_factor,
    std::function<void(int, const float*, float*)> coord_update,
    std::function<float(const float*)> elbo_fn,
    int max_epochs, float tol
);
```

## Memory Budget
- Runtime RAM: <15 MB (λ + per-factor working buffers)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve`

## Performance Target
- Python baseline: per-coordinate update in numpy
- Target: ≥6x faster
- Benchmark: 200 epochs × d ∈ {10, 100, 1000}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on λ buffer.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for ELBO. Monotonic check: fail fast if ELBO decreases by more than numerical tol.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

See `backend/extensions/CPP-RULES.md` for full policy.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_114.py` | Variational params match scikit reference within 1% |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥4x faster than Python reference |
| 5 | `pytest test_edges_meta_114.py` | d=1, no data, degenerate init all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (caller supplies coord_update)

## Pipeline Stage Non-Conflict
**Owns:** Fast factorized posterior approximation.
**Alternative to:** META-106..110 MCMC when speed > accuracy.
**Coexists with:** META-115 EP, META-117 BBVI — selected by `vi.family` config.

## Test Plan
- Conjugate Gaussian–Gaussian: λ matches closed-form posterior
- ELBO monotonicity: 100 random inits all increase
- d=1 degenerate: verify convergence in ≤10 epochs
- NaN coord update: verify raises ValueError
