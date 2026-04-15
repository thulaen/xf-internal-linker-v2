# META-117 — Black-Box Variational Inference (BBVI)

## Overview
**Category:** Variational posterior approximator (score-function gradient)
**Extension file:** `bbvi.cpp`
**Replaces/improves:** Model-specific VI when ELBO gradient is hard to derive analytically
**Expected speedup:** ≥4x over Python Monte-Carlo ELBO gradient
**RAM:** <25 MB | **Disk:** <1 MB

## Algorithm

```
Input: variational family q(z;λ), joint p(x,z), n_MC samples per iter, step γ_t
Output: λ maximizing ELBO

for t = 1..n_iters:
    draw z_s ~ q(z;λ) for s = 1..S
    # ∇_λ L = E_q[∇_λ log q(z;λ) · (log p(x,z) − log q(z;λ))]  — score-function estimator
    compute g_hat = (1/S) Σ_s ∇_λ log q(z_s;λ) · (log p(x,z_s) − log q(z_s;λ))
    # variance reduction: subtract control variate (Rao-Blackwellized baseline)
    λ ← λ + γ_t · g_hat
return λ
```

- **Time complexity:** O(n_iters × S × (log_q_cost + log_p_cost))
- **Space complexity:** O(|λ|)
- **Convergence:** Stochastic gradient ascent on ELBO; variance depends on score estimator quality

## Academic Source
Ranganath R., Gerrish S., Blei D.M. "Black Box Variational Inference." *Proceedings of AISTATS 2014*, pp. 814–822. URL: http://proceedings.mlr.press/v33/ranganath14.html.

## C++ Interface (pybind11)

```cpp
// BBVI with Adam-style adaptive step
std::vector<float> bbvi(
    const float* initial_lambda, int lambda_dim,
    std::function<void(const float*, int, float*)> sample_q,       // z ~ q
    std::function<float(const float*, const float*)> log_q,        // log q(z;λ)
    std::function<float(const float*)> log_p_joint,
    std::function<void(const float*, const float*, float*)> grad_log_q,
    int n_mc_samples, int n_iters, float lr, uint64_t seed
);
```

## Memory Budget
- Runtime RAM: <25 MB (λ + MC sample buffer + grad accumulator)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve`

## Performance Target
- Python baseline: PyTorch/TensorFlow Probability BBVI
- Target: ≥4x faster
- Benchmark: S ∈ {10, 50, 200} MC samples × n_iters=5k × λ_dim ∈ {10, 100}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on gradient buffer.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks on λ and log_p. Double accumulator for MC average. Gradient clipping to prevent runaway.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU. Seeded RNG.

See `backend/extensions/CPP-RULES.md` for full policy.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_117.py` | Final ELBO within 1% of Edward/TFP reference |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥3x faster than TFP reference |
| 5 | `pytest test_edges_meta_117.py` | S=1, zero-variance q, degenerate joint handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Caller supplies `sample_q`, `log_q`, `log_p_joint`, `grad_log_q`

## Pipeline Stage Non-Conflict
**Owns:** General-purpose VI without model-specific derivation.
**Alternative to:** META-114 mean-field VI, META-118 reparam VI (score-fn vs. pathwise).
**Coexists with:** All VI families — selected by `vi.estimator = score`.

## Test Plan
- Toy Gaussian posterior: λ converges to truth within 2%
- Variance of estimator decreases with S
- S=1 unstable but bounded: no NaN
- Log-q NaN: verify raises ValueError
