# META-96 — Stochastic Weight Averaging (SWA)

## Overview
**Category:** Model averaging (P11 model averaging block)
**Extension file:** `swa.cpp`
**Replaces/improves:** Single-checkpoint final weights — SWA averages weights sampled along the optimisation trajectory, finding wider/flatter minima with better generalisation
**Expected speedup:** ≥6x over Python in-place EMA loop
**RAM:** <2x model size | **Disk:** <1 MB

## Algorithm

```
Input: training optimiser, swa_start_epoch, swa_lr (constant or cyclic),
       averaging frequency k_avg (every k_avg steps after swa_start)
State: w_SWA (running average), n_models counted, BN-running-stats buffer

Per-step:
  if epoch < swa_start_epoch:
      standard SGD step on w
      continue
  apply constant or cyclic LR (override base scheduler with swa_lr)
  if step % k_avg == 0:
      n_models    ← n_models + 1
      w_SWA       ← w_SWA  +  (w − w_SWA) / n_models      (running mean)

Equivalent batch form:
  w_SWA = (1/k) · Σ_{i=1..k} w_i        over k checkpoints sampled after warm-up

End-of-training:
  Re-estimate batch-norm running stats by one forward pass over training data
  with weights = w_SWA (BN params depend on activation stats which differ for w_SWA).
```

- **Time complexity:** O(d) per averaging step (d = parameter count)
- **Space complexity:** O(d) for w_SWA storage
- **Convergence:** Empirically improves test accuracy by 0.5–1.5 % on standard image benchmarks

## Academic source
Izmailov, P., Podoprikhin, D., Garipov, T., Vetrov, D. and Wilson, A. G., "Averaging Weights Leads to Wider Optima and Better Generalization", *Proceedings of the 34th Conference on Uncertainty in Artificial Intelligence (UAI)*, 2018.

## C++ Interface (pybind11)

```cpp
class SWA {
public:
    SWA(int param_count);
    void update(const float* w);          // O(d) running-mean step
    void get(float* w_swa_out) const;     // copy out current average
    int  n_models() const;
    void reset();
};

// Helper for BN re-estimation (caller still drives the forward pass)
void swa_reset_bn_stats(/* opaque BN layer handle */);
```

## Memory Budget
- Runtime RAM: ≤ 2× model parameter size (one buffer for w_SWA, plus caller's live w)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: single `std::vector<float>` of size d, reserved in constructor

## Performance Target
- Python baseline: in-place NumPy EMA `w_swa += (w - w_swa) / (n+1)`
- Target: ≥6x faster on d = 1e7 (SIMD vectorisation of running-mean update)
- Benchmark: 3 sizes — d ∈ {1e4, 1e6, 1e7}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback. SWA is single-thread; users serialise externally.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled. Validate param_count > 0; reject mismatched-size update calls.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on internal w_SWA buffer. Running-mean update vectorised: `w_SWA[i] += (w[i] − w_SWA[i]) / n`.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Use `double` accumulator path when n > 1e6 to avoid loss-of-significance in the running-mean denominator.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all. NaN in incoming w aborts the update with ValueError.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

Adheres to `backend/extensions/CPP-RULES.md` in full.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_96.py` | Average matches NumPy reference within 1e-6 after 1000 updates |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `pytest backend/benchmarks/test_bench_swa.py` | ≥6x speedup on 3 sizes |
| 5 | `pytest test_edges_meta_96.py` | d=1, n=0 (return zeros), NaN input rejected, very large n=1e9 stable |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | Generalisation | On synthetic noisy quadratic, w_SWA achieves lower test loss than final w |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- META-91 cosine warm restart (recommended cyclic LR for SWA sampling cadence)
- pybind11 ≥ 2.10

## Pipeline stage non-conflict declaration
- **Owns:** Running mean of trajectory weights via Welford-style online formula
- **Alternative to:** META-97 Polyak-Ruppert (different averaging convention), META-98 snapshot ensemble (averages predictions, not weights), META-99 deep ensembles (independent runs)
- **Coexists with:** All LR schedulers (consumes them), all P8 regularisers, all P9 calibrators

## Test Plan
- Constant w input over k updates: verify w_SWA = w exactly (Welford no-drift property)
- Linear-ramp w over k updates: verify w_SWA = mid-point
- Mismatched param_count: verify raises
- BN re-estimation API exists and is callable
- After 1e9 updates, single-precision drift bounded (use double accumulator path)
