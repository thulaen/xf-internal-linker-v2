# META-131 — Mirror Descent (Offline)

## Overview
**Category:** Advanced gradient optimizer
**Extension file:** `mirror_descent.cpp`
**Replaces/improves:** Projected gradient for weights constrained to a simplex (e.g. convex combinations of rerankers)
**Expected speedup:** ≥3x over Python reference with explicit log/exp
**RAM:** <5 MB | **Disk:** <1 MB

## Algorithm

```
Input: weights w ∈ Δ^{d-1} (simplex), gradient g_t, learning rate η
Mirror map: ψ(w) = Σ w_i · log w_i            (negative entropy)
Bregman divergence: D_ψ(w, w_t) = Σ w_i · log(w_i / w_{t,i})
Output: updated weights w_{t+1}

Update rule (Nemirovski & Yudin 1983):
    w_{t+1} = argmin_{w ∈ Δ} ( η · ⟨g_t, w⟩ + D_ψ(w, w_t) )

For entropy regularizer ψ = negative entropy, the closed form is the
exponentiated gradient (EG) update:
    w_{t+1,i} = w_{t,i} · exp(−η · g_{t,i}) / Z
    Z = Σ_j w_{t,j} · exp(−η · g_{t,j})
```

- **Time complexity:** O(d) per step
- **Space complexity:** O(d)
- **Convergence:** O(√(log d / T)) regret on simplex — dimension-logarithmic (vs √d for Euclidean GD)

## C++ Interface (pybind11)

```cpp
// Mirror descent step on the probability simplex (EG form)
void mirror_descent_step(
    float* weights, int d,
    const float* gradient,
    float learning_rate
);
```

## Memory Budget
- Runtime RAM: <5 MB (w + scratch buffer)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: in-place; one stack-sized scratch for log-sum-exp

## Performance Target
- Python baseline: numpy `w * np.exp(−η*g)` then normalise
- Target: ≥3x faster via fast vectorised `exp` and log-sum-exp trick
- Benchmark: d ∈ {32, 512, 8192}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` — see `backend/extensions/CPP-RULES.md`.

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for reductions >100 elements. Use log-sum-exp stable normalisation to prevent overflow when η·g large.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_131.py` | Output matches numpy EG reference within 1e-5 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥3x faster than numpy baseline |
| 5 | `pytest test_edges_meta_131.py` | w at vertex, η=0, huge η·g, NaN grad all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (self-contained)

## Pipeline Stage Non-Conflict
- **Owns:** Simplex-constrained weight update via negative-entropy Bregman
- **Alternative to:** META-128, META-129, META-130, META-133, META-134 — mutually exclusive
- **Coexists with:** META-04 coord ascent (unconstrained phase), META-146 Fourier features (feature prep)

## Test Plan
- Uniform init + constant positive gradient: verify weight mass concentrates on smallest index
- Simplex feasibility invariant: Σw_i = 1 every step within 1e-6
- η=0: weights unchanged
- Gradient with Inf: verify raises ValueError
