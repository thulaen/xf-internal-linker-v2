# META-164 — Information Bottleneck

## Overview
**Category:** Information-theoretic representation learner
**Extension file:** `info_bottleneck.cpp`
**Replaces/improves:** Ad-hoc feature compression in `feature_selection.py`; no existing IB implementation
**Expected speedup:** ≥6x over pure-Python Blahut-Arimoto loop
**RAM:** <100 MB | **Disk:** <1 MB

## Algorithm

```
Input: joint p(x,y), cluster count |T|, trade-off β > 0
Output: soft assignment p(t|x) minimising I(X;T) − β·I(T;Y)

Initialise p(t|x) randomly; compute p(t), p(y|t).
repeat until convergence of Lagrangian L_β:
    # self-consistent equations
    p(t|x) ∝ p(t) · exp(−β · D_KL( p(y|x) ‖ p(y|t) ))
    p(t)   = Σ_x p(x) · p(t|x)
    p(y|t) = (1/p(t)) · Σ_x p(y|x) · p(t|x) · p(x)
```

- **Time complexity:** O(iters · |X| · |T| · |Y|)
- **Space complexity:** O(|X|·|T| + |T|·|Y|)
- **Convergence:** Monotone decrease of L_β guaranteed (Blahut-Arimoto fixed-point)

## Academic Source
Tishby N., Pereira F., Bialek W., "The information bottleneck method," *Proc. 37th Annual Allerton Conf. on Communication, Control and Computing*, 1999. arXiv:physics/0004057. DOI: 10.48550/arXiv.physics/0004057

## C++ Interface (pybind11)

```cpp
// Soft IB clustering; returns p(t|x) as [|X| × |T|] row-major matrix
std::vector<float> information_bottleneck(
    const float* p_xy, int nx, int ny,
    int nt, float beta,
    int max_iters, float tol
);
```

## Memory Budget
- Runtime RAM: <100 MB for |X|=5k, |Y|=5k, |T|=64
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: three `std::vector<float>` matrices, `reserve()` up-front

## Performance Target
- Python baseline: Numpy Blahut-Arimoto loop
- Target: ≥6x faster for |X|=|Y|=2000, |T|=32
- Benchmark: |T| ∈ {8, 32, 128}, β ∈ {1, 5, 20}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. Arena/pool/RAII only. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. `log-sum-exp` trick in exp(−β·D_KL) to avoid overflow. Protect `log(0)` with ε.

**Performance:** No `std::endl` loops. No `std::function` hot loops. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. Scrub sensitive memory. No TOCTOU.

Full rules: see `backend/extensions/CPP-RULES.md`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_164.py` | Matches reference NumPy IB within 1e-3 on toy joint |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥6x faster than Python reference |
| 5 | `pytest test_edges_meta_164.py` | β=0, β→∞, |T|=1, |T|=|X| all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- META-163 (MI used for monitoring I(X;T), I(T;Y))

## Pipeline Stage Non-Conflict
- **Owns:** Soft probabilistic compression p(t|x) that preserves label-relevant info.
- **Alternative to:** PCA/autoencoder feature compression.
- **Coexists with:** Clustering metas (IB output can seed initial centroids).
- No conflict with the online ranker: IB runs offline on training telemetry only.

## Test Plan
- Exact toy joint (XOR of 2 bits): verify I(T;Y) saturates as β grows
- β=0: verify p(t|x) collapses to p(t)
- Large |T|: verify p(t|x) recovers near-identity when |T| ≥ |X|
- NaN inputs: verify raises ValueError
- Convergence monitor: L_β must be non-increasing across iterations
