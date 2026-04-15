# META-146 — Fourier Random Features (RFF)

## Overview
**Category:** Feature engineering
**Extension file:** `fourier_rff.cpp`
**Replaces/improves:** Kernel ridge / kernel SVM in ranker feature prep — linear model on RFF ≈ RBF-kernel model
**Expected speedup:** ≥4x over sklearn `RBFSampler`
**RAM:** <80 MB | **Disk:** <1 MB

## Algorithm

```
Input: X ∈ ℝ^{N×d}, number of features D, kernel bandwidth σ
State: ω_i ~ p(ω) = N(0, σ⁻² I) for i=1..D, b_i ~ U(0, 2π)
Output: z(X) ∈ ℝ^{N×D}

Rule (Rahimi & Recht, NIPS 2007):
    z(x) = √(2/D) · [cos(ω_1ᵀ x + b_1), ..., cos(ω_Dᵀ x + b_D)]

Approximation property:
    E[z(x)ᵀ z(y)] = k(x − y) = exp(−‖x−y‖² / (2σ²))     (RBF kernel)
```

- **Time complexity:** O(N · d · D) for the projection
- **Space complexity:** O(D · d) for ω cache + O(N · D) output
- **Convergence:** Uniform approximation error O(1/√D) on any compact set

## C++ Interface (pybind11)

```cpp
// Fit: sample and store ω, b
void fourier_rff_fit(
    float* omega_out,     // (D, d)
    float* bias_out,      // (D,)
    int d, int D, float sigma, uint64_t rng_seed
);

// Transform
void fourier_rff_transform(
    float* Z_out,         // (N, D)
    const float* X, int N, int d,
    const float* omega, const float* bias, int D
);
```

## Memory Budget
- Runtime RAM: <80 MB (ω + output for N=50k, D=1024, d=64)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: caller-owned

## Performance Target
- Python baseline: sklearn `RBFSampler`
- Target: ≥4x faster via BLAS gemm + vector cos
- Benchmark: N=10000, d=64, D ∈ {256, 1024, 4096}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` — see `backend/extensions/CPP-RULES.md`.

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for reductions >100 elements. Guard σ > 0; vectorised cos with range reduction to avoid precision loss.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_146.py` | E[z(x)ᵀz(y)] matches RBF kernel within 0.05 for D=4096 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥4x faster than sklearn RBFSampler |
| 5 | `pytest test_edges_meta_146.py` | N=1, d=1, D=1 all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- BLAS (for ω X^T) optional; fallback in pure C++

## Pipeline Stage Non-Conflict
- **Owns:** Random cosine projection with stored ω, b
- **Alternative to:** META-143 (polynomial), META-144 (B-spline), META-145 (natural cubic) — mutually exclusive per feature bundle
- **Coexists with:** META-147..150 categorical encoders; optimizers META-128..135

## Test Plan
- Equal inputs x=y: z(x)ᵀz(x) → 1 as D grows (RBF kernel at origin = 1)
- Fit/transform determinism with fixed seed
- σ=0: raises ValueError
- Many-D large-N benchmark completes within RAM budget
