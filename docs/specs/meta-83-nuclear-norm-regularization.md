# META-83 — Nuclear-Norm Regularisation

## Overview
**Category:** Low-rank regulariser (P8 regularisation block)
**Extension file:** `nuclear_norm_reg.cpp`
**Replaces/improves:** Unconstrained matrix factor learning in cross-feature interaction blocks; promotes low-rank weight matrices for memory and generalisation
**Expected speedup:** ≥4x over Python LAPACK SVD-prox loop
**RAM:** <120 MB | **Disk:** <1 MB

## Algorithm

```
Input: matrix W ∈ ℝ^{m×n}, regularisation λ > 0, step η
Output: low-rank W* = argmin g(W) + λ·‖W‖_*

Penalty:    ‖W‖_* = Σ_i σ_i(W)   (sum of singular values)
Prox op:    prox_{ηλ‖·‖_*}(M) = U · S_{ηλ}(Σ) · Vᵀ
            where M = UΣVᵀ, S_τ(σ) = max(σ − τ, 0)  (singular-value soft-threshold)

repeat:
    G ← ∇g(W)
    M ← W − η·G
    UΣVᵀ ← thinSVD(M)
    Σ' ← max(Σ − η·λ, 0)
    W  ← U · diag(Σ') · Vᵀ
until ‖W − W_prev‖_F < tol
```

- **Time complexity:** O(iter × min(m,n)·m·n) for thin SVD per step
- **Space complexity:** O(m·n + min(m,n)·(m+n)) for SVD factors
- **Convergence:** Same O(1/t²) when wrapped in FISTA (META-82) momentum

## Academic source
Fazel, M., Hindi, H. and Boyd, S., "A Rank Minimization Heuristic with Application to Minimum Order System Approximation", *Proceedings of the American Control Conference (ACC)*, 2001. DOI 10.1109/ACC.2001.945730.

## C++ Interface (pybind11)

```cpp
// Singular-value soft-threshold (nuclear-norm prox)
void nuclear_norm_prox(
    const float* M, int m, int n,
    float threshold,
    float* W_out,                 // m×n, prox_{τ‖·‖_*}(M)
    float* singular_values_out    // length min(m,n), post-threshold
);
```

## Memory Budget
- Runtime RAM: <120 MB at m=n=2048 (M, U, Σ, V, work buffers)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: pre-sized `std::vector<float>` work buffers, no per-iter alloc

## Performance Target
- Python baseline: NumPy `np.linalg.svd` + soft-threshold loop
- Target: ≥4x faster on m=n=512 (LAPACK direct call avoids Python boxing)
- Benchmark: 3 sizes — (m,n) ∈ {(64,64), (512,512), (2048,2048)}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills. SVD work buffers reused across calls.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for Frobenius reductions >100 elements. SVD via LAPACK `sgesdd` with workspace query.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all. LAPACK `info != 0` raises.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory. Link LAPACK once at module load.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

Adheres to `backend/extensions/CPP-RULES.md` in full.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror`; LAPACK linked |
| 2 | `pytest test_parity_meta_83.py` | Matches NumPy SVD-prox within 1e-4 Frobenius |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `pytest backend/benchmarks/test_bench_nuclear.py` | ≥4x speedup at 512×512 |
| 5 | `pytest test_edges_meta_83.py` | m=1, n=1, m=n, m≪n, all-zero, rank-1 inputs handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | Rank check | After convergence, numerical rank ≤ expected |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- LAPACK (system or OpenBLAS) for `sgesdd`/`dgesdd`
- META-82 FISTA for outer momentum loop (composable)

## Pipeline stage non-conflict declaration
- **Owns:** Singular-value soft-threshold prox operator for low-rank weight matrices
- **Alternative to:** Frobenius (L2) regularisation on factor matrices
- **Coexists with:** META-82 FISTA (outer optimiser), META-84 group LASSO (different penalty), calibration metas (P9), LR schedulers (P10)

## Test Plan
- Random rank-3 matrix + noise: verify recovered rank = 3 within tolerance
- λ = 0: verify W → M (no shrinkage)
- λ → ∞: verify W → 0
- Symmetric input: verify singular values match eigenvalue magnitudes
- 1×1 matrix degenerate case: returns max(M − ηλ, 0)
