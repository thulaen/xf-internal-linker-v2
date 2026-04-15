# META-95 — Step Decay with Plateau Detection

## Overview
**Category:** Learning-rate scheduler (P10 LR schedulers block)
**Extension file:** `step_decay_plateau.cpp`
**Replaces/improves:** Constant LR or fixed-schedule decay; reactive plateau detection drops LR when validation NDCG stops improving — robust to dataset-dependent epoch counts
**Expected speedup:** N/A — convergence robustness; CPU work negligible
**RAM:** <1 KB | **Disk:** <1 MB

## Algorithm

```
Input:
  η_0  initial LR
  γ    decay factor (e.g. 0.1)
  patience  steps to wait without improvement before dropping
  cooldown  steps to wait after a drop before resuming patience
  threshold improvement threshold ε (relative or absolute)
  min_lr    lower clip (default 0)
  mode      'min' (val_loss) or 'max' (val_NDCG)
  Optional fallback: exponential step every step_size epochs

State:
  η_current, best_metric, num_bad_steps, cooldown_remaining

Per-validation-step:
  if cooldown_remaining > 0:
      cooldown_remaining ← cooldown_remaining − 1
      return                                            // skip patience
  if metric_improves(metric, best_metric, threshold, mode):
      best_metric    ← metric
      num_bad_steps ← 0
  else:
      num_bad_steps ← num_bad_steps + 1
      if num_bad_steps ≥ patience:
          η_current        ← max(η_current · γ, min_lr)
          num_bad_steps    ← 0
          cooldown_remaining ← cooldown
```

- **Time complexity:** O(1) per validation step
- **Space complexity:** O(1)
- **Convergence:** Used in ResNet (ICCV 2015) — typical schedule γ = 0.1 every 30 epochs, or plateau-driven for unknown training durations

## Academic source
He, K., Zhang, X., Ren, S. and Sun, J., "Deep Residual Learning for Image Recognition", *IEEE International Conference on Computer Vision (ICCV)*, 2015 — step-decay LR schedule used and described in Section 3.4 / 4.1.

## C++ Interface (pybind11)

```cpp
enum class PlateauMode { Min, Max };

class StepDecayPlateau {
public:
    StepDecayPlateau(float eta_0, float gamma, int patience, int cooldown,
                     float threshold, float min_lr, PlateauMode mode);
    float step(float val_metric);   // call once per validation; returns current LR
    void  reset();
    int   bad_steps() const;
    float current_lr() const;
};

// Optional non-reactive variant: exponential step every `step_size` epochs
class StepDecayFixed {
public:
    StepDecayFixed(float eta_0, float gamma, int step_size);
    float step();
    void  reset();
};
```

## Memory Budget
- Runtime RAM: <1 KB
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: zero per-step

## Performance Target
- Python baseline: `torch.optim.lr_scheduler.ReduceLROnPlateau`
- Target: parity within 1e-7
- Benchmark: 3 sizes — 100, 10000, 1000000 sequential `step()` calls

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback. Single-thread.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled. Validate 0 < γ < 1, patience ≥ 1, cooldown ≥ 0, η_0 > min_lr ≥ 0.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays. Scalar arithmetic — no vectorisation needed.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks (NaN val_metric counts as no improvement). Threshold compared in mode-specific direction.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all. NaN val_metric handled gracefully (treated as no improvement, not a crash).

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

Adheres to `backend/extensions/CPP-RULES.md` in full.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_95.py` | LR sequence matches PyTorch `ReduceLROnPlateau` exactly |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `pytest backend/benchmarks/test_bench_step_decay.py` | <100 ns per `step()` on 3 sizes |
| 5 | `pytest test_edges_meta_95.py` | NaN metric, patience=1, cooldown=0, min_lr clip, mode=min/max all handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | Drop count | Sequence with K plateaus produces exactly K LR drops |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- pybind11 ≥ 2.10
- No external deps

## Pipeline stage non-conflict declaration
- **Owns:** Plateau-detected step decay + optional fixed-step exponential decay
- **Alternative to:** META-91 cosine, META-92 1-cycle, META-93 transformer warmup, META-94 polynomial decay
- **Coexists with:** All P8 regularisers, all P9 calibrators; do not stack with another LR scheduler

## Test Plan
- Constant improving metric: verify LR never drops
- Constant worsening metric: verify drop after exactly `patience` steps
- After drop: verify cooldown blocks the next `cooldown` steps from triggering
- min_lr clip: verify LR cannot drop below floor after many plateaus
- NaN metric: verify treated as no improvement, no crash
