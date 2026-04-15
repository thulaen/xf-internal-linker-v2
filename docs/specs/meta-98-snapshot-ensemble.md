# META-98 — Snapshot Ensemble

## Overview
**Category:** Prediction-level ensemble (P11 model averaging block)
**Extension file:** `snapshot_ensemble.cpp`
**Replaces/improves:** Single-checkpoint inference — snapshot ensembles capture diverse minima during one training run via cosine-annealing warm restarts (META-91), then average their predictions
**Expected speedup:** ≥4x over Python ensemble-loop boilerplate (per query, prediction averaging is the bottleneck)
**RAM:** <K · model size | **Disk:** K snapshots, sized by model

## Algorithm

```
Input: training driven by cosine-annealing-with-warm-restarts schedule,
       K = number of cycles to ensemble (e.g. last K of M)

Snapshot capture:
  At each cosine-annealing minimum (end of cycle i), save weights w_i to disk.
  Continue training: warm restart bumps LR back to η_max for cycle i+1.

Inference (per query):
  for k = 1..K:
      load w_k (or keep in memory)
      p_k(y | x) ← model(w_k, x)
  P_ensemble(y | x) = (1/K) · Σ_{k=1..K} p_k(y | x)

Equivalent: average logits before softmax for marginally better calibration.
```

- **Time complexity:** O(K) inference cost per query
- **Space complexity:** O(K · d) on disk; in-memory K snapshots if cached
- **Convergence:** Empirically improves accuracy ~0.5–1.5 % over single model with no extra training cost

## Academic source
Huang, G., Li, Y., Pleiss, G., Liu, Z., Hopcroft, J. E. and Weinberger, K. Q., "Snapshot Ensembles: Train 1, Get M for Free", *International Conference on Learning Representations (ICLR)*, 2017.

## C++ Interface (pybind11)

```cpp
// Average K probability vectors element-wise (vectorised)
void snapshot_avg_probs(
    const float* probs_KxN, int K, int N,    // K snapshots × N classes (or candidates)
    float* probs_out                           // length N
);

// Average K logit vectors then softmax (alternative)
void snapshot_avg_logits_softmax(
    const float* logits_KxN, int K, int N,
    float* probs_out
);

// On-disk snapshot manager (file paths only — caller does I/O)
struct SnapshotManager {
    void   add(const std::string& path);
    size_t size() const;
    void   clear();
};
```

## Memory Budget
- Runtime RAM: <K · model size in worst case (cached) — typically only top-K probability vectors for averaging
- Disk: K · model size; suggested K ∈ {3, 5, 10}
- Allocation: pre-sized output buffer; no per-query alloc

## Performance Target
- Python baseline: NumPy `np.mean(probs_stack, axis=0)` plus Python loop overhead
- Target: ≥4x faster on K=5, N=10000
- Benchmark: 3 sizes — (K, N) ∈ {(3, 100), (5, 10000), (10, 100000)}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled. Validate K ≥ 1, N ≥ 1.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays. Per-class accumulation vectorised across snapshots.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for the mean when K · N > 1e6. Numerically stable softmax with max-subtract for `snapshot_avg_logits_softmax`.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`. Snapshot file I/O is the caller's responsibility (we never block on disk inside hot loops).

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all. K=0 raises.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU on snapshot file paths (caller responsibility).

Adheres to `backend/extensions/CPP-RULES.md` in full.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_98.py` | Output matches NumPy `mean` within 1e-6 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `pytest backend/benchmarks/test_bench_snapshot.py` | ≥4x speedup on 3 sizes |
| 5 | `pytest test_edges_meta_98.py` | K=1 (returns input), K=2, N=1, NaN snapshot, identical snapshots all handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | Diversity check | Synthetic snapshots from different cosine-min restart points produce lower ensemble error than any single snapshot |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- META-91 cosine warm restart (provides the cycle-end trigger)
- pybind11 ≥ 2.10

## Pipeline stage non-conflict declaration
- **Owns:** Probability and logit averaging across K snapshots taken at cosine-annealing minima
- **Alternative to:** META-96 SWA (averages weights, not predictions), META-99 deep ensembles (independent training runs), META-97 Polyak-Ruppert
- **Coexists with:** All LR schedulers (consumes META-91), all P8 regularisers, all P9 calibrators (apply calibration after ensemble averaging)

## Test Plan
- K identical snapshots: verify ensemble probs == single snapshot exactly
- K = 1: verify pass-through
- Probability inputs that don't sum to 1: verify still produces a valid simplex output
- Logit + softmax variant: verify numerically equivalent to `softmax(mean(logits))`, more stable than `mean(softmax(logits))` for extreme logits
- N = 1: verify scalar averaging works
