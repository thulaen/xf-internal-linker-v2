# META-147 — Feature Hashing Trick

## Overview
**Category:** Feature engineering
**Extension file:** `hashing_trick.cpp`
**Replaces/improves:** One-hot encoding for high-cardinality categorical or sparse text features
**Expected speedup:** ≥5x over sklearn `HashingVectorizer`
**RAM:** <20 MB | **Disk:** <1 MB

## Algorithm

```
Input: sparse categorical tokens (id_i, weight_i), hash table size J
Output: dense (or sparse) feature vector φ_h(x) ∈ ℝ^J

Rule (Weinberger et al., ICML 2009):
    two independent hash functions:
        h : token → {0,...,J-1}
        ξ : token → {−1, +1}
    φ_h(x)_j = Σ_{i : h(i) = j} ξ(i) · x_i

Signed hash gives unbiased inner-product preservation:
    E[⟨φ_h(x), φ_h(y)⟩] = ⟨x, y⟩
```

- **Time complexity:** O(nnz) where nnz is number of non-zero input tokens
- **Space complexity:** O(J) output
- **Convergence:** Unbiased; variance O(‖x‖² · ‖y‖² / J)

## C++ Interface (pybind11)

```cpp
// Hashed feature vector using MurmurHash3 for h and ξ
void hashing_trick(
    float* phi_out, int J,
    const uint64_t* token_ids, const float* weights, int nnz,
    uint32_t hash_seed
);
```

## Memory Budget
- Runtime RAM: <20 MB (dense output for J up to 2²²)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: caller-owned

## Performance Target
- Python baseline: sklearn `HashingVectorizer`
- Target: ≥5x faster via MurmurHash3 SIMD + signed accumulate
- Benchmark: nnz ∈ {1000, 100000, 1000000}, J=2²⁰

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` — see `backend/extensions/CPP-RULES.md`.

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled. Require J power-of-two or document modulo cost.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for reductions >100 elements. Hash must be stable across runs (documented seed).

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU. Hash seed exposed so caller controls per-deployment salt.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_147.py` | Matches sklearn HashingVectorizer with same seed within 1e-6 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥5x faster than sklearn |
| 5 | `pytest test_edges_meta_147.py` | nnz=0, all collisions, J=1, duplicate ids all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- MurmurHash3 (bundled, header-only)

## Pipeline Stage Non-Conflict
- **Owns:** Hash-based dense projection of sparse categorical tokens
- **Alternative to:** META-148 (target encoding), META-149 (count encoding), META-150 (LOO target) — mutually exclusive per categorical column
- **Coexists with:** META-143..146 numerical encoders; optimizers META-128..135

## Test Plan
- Inner product preservation: ⟨φ_h(x), φ_h(y)⟩ ≈ ⟨x, y⟩ on average
- Determinism: same seed, same tokens, same output
- Collision isolation: handled without crash
- nnz=0: returns zero vector
