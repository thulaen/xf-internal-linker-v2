# META-140 — DropConnect

## Overview
**Category:** Regularisation / noise
**Extension file:** `dropconnect.cpp`
**Replaces/improves:** Dropout on activations when dropping weight connections yields stronger ensembling
**Expected speedup:** ≥3x over Python numpy mask
**RAM:** <30 MB | **Disk:** <1 MB

## Algorithm

```
Input: weight matrix W ∈ ℝ^{m×n}, keep probability p
Output: masked W̃

Rule (Wan et al., ICML 2013):
    M ~ Bernoulli(p) elementwise on W                   (per forward pass)
    W̃ = M ⊙ W / p                     (inverted scaling keeps expectation E[W̃] = W)
```

- **Time complexity:** O(m·n) per forward pass
- **Space complexity:** O(m·n) for mask (can be regenerated)
- **Convergence:** Equivalent in expectation to a Gaussian noise input when combined with activation

## C++ Interface (pybind11)

```cpp
// DropConnect — apply Bernoulli mask to weight matrix, inverted scaling
void dropconnect_mask(
    float* W_out,
    const float* W_in,
    int m, int n,
    float keep_prob, uint64_t rng_seed
);
```

## Memory Budget
- Runtime RAM: <30 MB (output matrix + RNG state)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: caller-owned

## Performance Target
- Python baseline: `np.random.binomial` + multiply
- Target: ≥3x faster via fast RNG + AVX2 multiply
- Benchmark: m·n ∈ {1024², 4096², 16384²}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` — see `backend/extensions/CPP-RULES.md`.

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for reductions >100 elements. keep_prob ∈ (0,1] enforced — error on 0 or >1.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_140.py` | Distribution E[W̃]=W within 2 sigma |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥3x faster than numpy baseline |
| 5 | `pytest test_edges_meta_140.py` | keep_prob=1 (no-op), keep_prob=1e-6, m=n=1 all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (self-contained PRNG)

## Pipeline Stage Non-Conflict
- **Owns:** Weight-level Bernoulli masking
- **Alternative to:** Standard Dropout (activation-level), META-141 (stochastic depth) — mutually exclusive per layer
- **Coexists with:** All optimizers META-128..135, META-136 label smoothing

## Test Plan
- keep_prob=1: W̃ = W bit-exact
- Over many seeds: empirical E[W̃] matches W within 2 sigma
- Zero W row: stays zero regardless of mask
- Large matrix 16384² finishes within benchmark budget
