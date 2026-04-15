# META-103 — Reservoir Sampling (Algorithm R)

## Overview
**Category:** Streaming sampling (P12 robustness & sampling block)
**Extension file:** `reservoir_sampling.cpp`
**Replaces/improves:** "Read entire stream into RAM then sample" — reservoir keeps a uniformly-random k-sample over an unbounded stream in O(k) memory; useful for online training-set sub-sampling, random NDCG audit picks, sampled diagnostics
**Expected speedup:** ≥10x over Python `random.sample` on full materialised list
**RAM:** O(k) | **Disk:** <1 MB

## Algorithm

```
Input: stream of items, target sample size k
State: reservoir[0..k-1], items_seen t (1-indexed)

Algorithm R (Vitter 1985):
  for first k items:
      reservoir[t-1] ← item
  for each subsequent item (t = k+1, k+2, …):
      j ← uniform_int(1, t)
      if j ≤ k:
          reservoir[j-1] ← item    // overwrite uniformly-random slot

Equivalent: item t is kept in the k-sample with probability k/t (exactly).

Variant — Algorithm L (faster for large t):
  Skip a geometric number of items between considerations of replacement,
  reducing expected RNG calls from O(N) to O(k · log(N/k)).
```

- **Time complexity:** O(N) for Algorithm R; O(k · log(N/k)) for Algorithm L
- **Space complexity:** O(k) reservoir
- **Convergence:** Each item has exact probability k/N of being in the final sample (uniform)

## Academic source
Vitter, J. S., "Random Sampling with a Reservoir", *ACM Transactions on Mathematical Software (TOMS)*, 11(1):37–57, 1985. DOI 10.1145/3147.3165.

## C++ Interface (pybind11)

```cpp
// Algorithm R streaming reservoir
template<typename T>
class Reservoir {
public:
    explicit Reservoir(size_t k, uint64_t rng_seed);
    void   add(const T& item);     // O(1) amortised
    void   add_int_id(int64_t id); // common case: sampling integer record IDs
    std::vector<T> sample() const; // copy out current reservoir
    size_t size() const;           // = min(k, items_seen)
    void   reset();
};

// Standalone helper for the int-ID case
std::vector<int64_t> reservoir_sample_int(
    const int64_t* stream, size_t N,
    size_t k, uint64_t rng_seed
);
```

## Memory Budget
- Runtime RAM: O(k) for reservoir + tiny RNG state (xoshiro256** keeps 256 bits)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: reservoir vector reserved at construction

## Performance Target
- Python baseline: `random.sample(full_list, k)` (requires materialising full list)
- Target: ≥10x faster on N=1e7, k=1000 (single pass, no list materialisation)
- Benchmark: 3 sizes — N ∈ {1e4, 1e6, 1e8} with k=1000

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback. Reservoir is single-thread; fan-in via merge of per-thread reservoirs (weighted combination) is the user's responsibility.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch (use `size_t` for k and t consistently). No strict aliasing violation. All switch cases handled. Validate k ≥ 1.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays. Per-item path is scalar (RNG-bound).

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. RNG uses 64-bit integer (xoshiro256** PRNG); avoids float-precision pitfalls. Algorithm L geometric skip uses `log` in `double`.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`. Use modulo-bias-free uniform_int via Lemire's method.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all. k = 0 raises. Stream length 0 returns empty reservoir.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU. RNG seeded from caller (deterministic) — never from `std::random_device` silently.

Adheres to `backend/extensions/CPP-RULES.md` in full.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_103.py` | Same seed → same sample as Python reference impl |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `pytest backend/benchmarks/test_bench_reservoir.py` | ≥10x speedup on 3 sizes |
| 5 | `pytest test_edges_meta_103.py` | N=0 (empty), N<k (returns all), N=k, N=k+1, k=1 handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | Uniformity test | Over 10000 trials with N=1000, k=10, χ² test passes (p > 0.01) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- pybind11 ≥ 2.10
- No external deps; embed xoshiro256** PRNG

## Pipeline stage non-conflict declaration
- **Owns:** Streaming uniform k-sample (Algorithm R + Algorithm L variants)
- **Alternative to:** Materialise-then-sample (uses unbounded RAM)
- **Coexists with:** META-102 OHEM (different selection criterion — loss-based vs uniform), META-104 importance weighting (probability-weighted, not uniform), META-105 stratified k-fold; all P8/P9/P10/P11 metas

## Test Plan
- N < k: returns all N items
- N = k: returns the first k items in order
- Same seed twice: identical reservoir
- χ² uniformity over many runs: each item appears in sample at rate k/N within tolerance
- Algorithm L geometric skip produces same statistical distribution as Algorithm R
