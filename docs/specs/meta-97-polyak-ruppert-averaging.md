# META-97 — Polyak-Ruppert Averaging

## Overview
**Category:** Iterate averaging (P11 model averaging block)
**Extension file:** `polyak_ruppert.cpp`
**Replaces/improves:** Final-iterate SGD output — Polyak-Ruppert averaging asymptotically achieves the Cramér-Rao lower bound (statistically optimal among unbiased estimators) for stochastic optimisation
**Expected speedup:** ≥6x over Python in-place running average
**RAM:** <2x model size | **Disk:** <1 MB

## Algorithm

```
Input: stream of SGD iterates w_1, w_2, …, w_T
Output: averaged iterate w̄_T

Online running mean:
  w̄_t = ((t − 1)/t) · w̄_{t−1}  +  (1/t) · w_t
       = w̄_{t−1}  +  (w_t − w̄_{t−1}) / t           (Welford form)

Closed form:
  w̄_T = (1/T) · Σ_{s=1..T} w_s

Optional tail-averaging variant (Jain et al., common in practice):
  Discard first burn-in B iterates, average the remaining T − B:
  w̄_T = (1/(T − B)) · Σ_{s=B+1..T} w_s
```

- **Time complexity:** O(d) per averaging step
- **Space complexity:** O(d) for w̄_t
- **Convergence:** With learning rate η_t = O(t^(-α)) for α ∈ (1/2, 1), w̄_T achieves the optimal asymptotic variance (paper Theorems 1–2)

## Academic source
Polyak, B. T. and Juditsky, A. B., "Acceleration of Stochastic Approximation by Averaging", *SIAM Journal on Control and Optimization*, 30(4):838–855, 1992.

## C++ Interface (pybind11)

```cpp
class PolyakRuppert {
public:
    PolyakRuppert(int param_count, int burn_in = 0);
    void update(const float* w);          // O(d) Welford running mean (skips while t ≤ burn_in)
    void get(float* w_avg_out) const;
    int  steps_counted() const;           // = max(0, t - burn_in)
    void reset();
};
```

## Memory Budget
- Runtime RAM: ≤ 2× model parameter size
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: single `std::vector<float>` of size d, reserved in constructor

## Performance Target
- Python baseline: in-place NumPy `w_avg = ((t-1)*w_avg + w) / t`
- Target: ≥6x faster on d = 1e7 (SIMD vectorisation)
- Benchmark: 3 sizes — d ∈ {1e4, 1e6, 1e7}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback. Single-thread.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled. Validate param_count > 0, burn_in ≥ 0; reject mismatched-size update.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on internal w_avg buffer. Welford update vectorised.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator path for steps > 1e6 to control round-off in the running mean denominator.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all. NaN in incoming w aborts the update with ValueError.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

Adheres to `backend/extensions/CPP-RULES.md` in full.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_97.py` | Average matches NumPy reference within 1e-6 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `pytest backend/benchmarks/test_bench_polyak.py` | ≥6x speedup on 3 sizes |
| 5 | `pytest test_edges_meta_97.py` | d=1, burn_in ≥ T (no averaging), burn_in=0, NaN input handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | Variance check | On synthetic stochastic-quadratic problem, averaged iterate variance is O(1/T) (statistical efficiency) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- pybind11 ≥ 2.10
- No external deps

## Pipeline stage non-conflict declaration
- **Owns:** Pure running mean of all (or post-burn-in) iterates with Welford update
- **Alternative to:** META-96 SWA (selectively samples after warm-up with override LR), META-98 snapshot ensemble (predictions, not weights), META-99 deep ensembles (independent runs)
- **Coexists with:** All LR schedulers, all P8 regularisers, all P9 calibrators

## Test Plan
- Constant w stream: verify w̄_T = w exactly
- Linear-ramp w: verify w̄_T = mid-point analytically
- burn_in = 5, T = 10: verify only iterates 6..10 averaged
- burn_in ≥ T: verify get() returns zeros (or last w if user prefers — document policy)
- After 1e9 iters, drift bounded (double accumulator)
