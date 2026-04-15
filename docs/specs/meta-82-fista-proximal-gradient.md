# META-82 — FISTA Proximal Gradient

## Overview
**Category:** Regularised optimiser (P8 regularisation block)
**Extension file:** `fista_proximal.cpp`
**Replaces/improves:** Vanilla proximal gradient (ISTA) for L1/elastic-net penalised weight learning in `learn_to_rank.py`
**Expected speedup:** ≥10x convergence rate over ISTA (O(1/t²) vs O(1/t))
**RAM:** <8 MB | **Disk:** <1 MB

## Algorithm

```
Input: smooth loss g(x), non-smooth penalty h(x), step η ≤ 1/L (Lipschitz of ∇g)
Output: x* = argmin g(x) + h(x)

x_0 ← initial weights
y_1 ← x_0
t_1 ← 1
for k = 1..max_iter:
    x_k ← prox_{η·h}( y_k − η · ∇g(y_k) )
    t_{k+1} ← (1 + sqrt(1 + 4·t_k²)) / 2
    y_{k+1} ← x_k + ((t_k − 1) / t_{k+1}) · (x_k − x_{k−1})
    if |F(x_k) − F(x_{k−1})| / |F(x_{k−1})| < tol: break
return x_k
```

- Paper momentum form: `y_{t+1} = x_{t+1} + ((t-1)/(t+2))·(x_{t+1} - x_t)` then `x_{t+1} = prox_{ηh}(y_t − η·∇g(y_t))`
- **Time complexity:** O(max_iter × cost(∇g + prox)), with O(1/t²) function-value convergence
- **Space complexity:** O(d) for x, y, x_prev
- **Convergence:** F(x_k) − F* ≤ 2L·‖x_0 − x*‖² / (k+1)²

## Academic source
Beck, A. and Teboulle, M., "A Fast Iterative Shrinkage-Thresholding Algorithm for Linear Inverse Problems", *SIAM Journal on Imaging Sciences*, 2(1):183–202, 2009. DOI 10.1137/080716542.

## C++ Interface (pybind11)

```cpp
// FISTA accelerated proximal gradient with arbitrary prox operator
std::vector<float> fista_minimise(
    const float* x0, int d,
    std::function<float(const float*, float*)> grad_g,   // returns g(x), fills grad
    std::function<void(const float*, float, float*)> prox_h, // prox_{η·h}(v) → out
    float lipschitz, int max_iter, float tol
);
```

## Memory Budget
- Runtime RAM: <8 MB (3 weight vectors x, y, x_prev + grad buffer)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(d)` per buffer, no per-iter alloc

## Performance Target
- Python baseline: ISTA loop with NumPy
- Target: ≥10x fewer iterations to ε-optimum than ISTA (theoretical O(1/t²) vs O(1/t))
- Benchmark: 3 sizes — d∈{100, 1000, 10000} with synthetic LASSO problem

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for reductions >100 elements. `t_k` momentum scalar uses `double`.

**Performance:** No `std::endl` loops. No `std::function` hot loops (callback OK at outer level only). No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

Adheres to `backend/extensions/CPP-RULES.md` in full.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_82.py` | Output matches scikit-learn `Lasso` within 1e-4 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `pytest backend/benchmarks/test_bench_fista.py` | ≥10x fewer iters than ISTA on 3 sizes |
| 5 | `pytest test_edges_meta_82.py` | Empty d=0, d=1, NaN init, η>1/L all handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `bench_extensions.py` regression | No slowdown vs prior commit |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- META-04 coord ascent (sibling weight optimiser, no shared state)
- pybind11 ≥ 2.10

## Pipeline stage non-conflict declaration
- **Owns:** L1/elastic-net regularised weight learning with Nesterov momentum
- **Alternative to:** ISTA, sub-gradient methods
- **Coexists with:** META-04 coordinate ascent (different optimiser family), all calibration metas (P9), all LR schedulers (P10)

## Test Plan
- Synthetic LASSO with known sparse solution: verify support recovery
- Compare iteration count to ISTA on identical problem — must show O(1/t²) advantage
- NaN gradient: verify raises ValueError before update
- Lipschitz overestimate (η too small): verify convergence still holds (slower)
- Single-coordinate (d=1) collapses to scalar prox-grad
