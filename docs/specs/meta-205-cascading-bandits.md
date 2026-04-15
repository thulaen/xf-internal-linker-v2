# META-205 — Cascading Bandits

## Overview
**Category:** Contextual bandits (structured action: ordered top-K list with position-based click model)
**Extension file:** `cascading_bandits.cpp`
**Replaces/improves:** Correct click-attribution model for ordered internal-link lists — learns only from items the user actually examined (above the first click)
**Expected speedup:** ≥5x over Python per-round top-K UCB selection and update
**RAM:** <50 MB for n_items ≤ 10⁶ | **Disk:** <1 MB

## Algorithm

Kveton, Szepesvári, Wen, Ashkan extend multi-armed bandits to recommendation lists under the **cascade click model**: the user scans the list top-to-bottom and clicks at most once; all items above the clicked one are considered "examined" and all items below the clicked one (and all items in a list with no click) are treated as not observed.

```
Input: n_items, list size K, per-item attractiveness estimates w(i) ∈ [0,1],
       examination counts T(i), UCB parameter
Output: ordered list L_t = (a_1, …, a_K), click position C_t ∈ {1…K, ∞}

for each round t:
    # Paper action (UCB-CascadeUCB1):
    for each item i:
        U_t(i) = ŵ(i) + sqrt( 1.5·ln(t) / max(1, T(i)) )
    L_t ← top-K items by U_t (sorted descending)

    # Paper observation rule (cascade click model):
    show L_t; observe click position C_t (∞ if no click)

    # Paper update — only items examined (positions 1 … min(C_t, K)):
    for k = 1 … min(C_t, K):
        i = L_t[k]
        T(i) ← T(i) + 1
        ŵ(i) ← ŵ(i) + ((click at k ? 1 : 0) − ŵ(i)) / T(i)
    # Items at positions > C_t are NOT updated (not examined)
```

- **Time:** O(n_items + K·log K) per round for UCB + top-K via heap
- **Space:** O(n_items) for ŵ and T
- **Regret:** O(√(n_items·K·T·log T)) — Kveton et al. Theorem 3

## Academic Source
Kveton, B., Szepesvári, C., Wen, Z. & Ashkan, A. (2015). **"Cascading bandits: Learning to rank in the cascade model"**. *Proc. 32nd International Conference on Machine Learning (ICML)*, 767-776. [PMLR link](http://proceedings.mlr.press/v37/kveton15.html).

## C++ Interface (pybind11)

```cpp
// Compute top-K UCB items as an ordered list
void cascading_topk(
    const float* w_hat, const uint32_t* T_count,
    int n_items, int K, int t_round,
    int* list_out  // [K] in descending-UCB order
);
// Update attractiveness estimates from a single round's observation
void cascading_update(
    float* w_hat, uint32_t* T_count,
    const int* list_shown, int K,
    int click_position  // 1..K for click, -1 for no click
);
```

## Memory Budget
- Runtime RAM: <50 MB (n_items=10⁶ × 8 B for ŵ+T ≈ 8 MB; top-K heap negligible)
- Disk: <1 MB (.so/.pyd only)
- Allocation: caller-owned buffers; internal top-K uses stack-allocated `std::array` or small-`k` heap

## Performance Target
- Python baseline: NumPy per-item UCB + `np.argpartition` for top-K + manual update loop
- Target: ≥5x faster via branchless UCB, partial sort, and cache-friendly update walk
- Benchmark: 3 sizes — (n=1k, K=5), (n=10k, K=10), (n=10⁶, K=20)

## Pre-Implementation Safety Checklist

Follow `backend/extensions/CPP-RULES.md` in full. Key items:

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** Single-reader/single-writer update pattern; if parallelized, document atomic memory ordering on T_count and ŵ.

**Memory:** No raw `new`/`delete` in hot paths. RAII. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view`. No `[&]` capture beyond scope.

**Type safety:** Explicit `static_cast` for narrowing (T_count from `uint32_t` to `double`). Clamp ŵ to [0,1] after update. No signed/unsigned mismatch.

**SIMD:** `_mm256_zeroupper()` at AVX boundaries. `alignas(64)` on ŵ array. SIMD horizontal partial-sort for small K.

**Floating point:** Flush-to-zero on init. Guard against `T_count==0` before `1.0 / T_count`. Use `std::log` only for `t_round > 1`; for `t_round = 1` substitute a small positive constant. Double accumulator for incremental mean.

**Performance:** No `std::endl`, no `std::function`, no `dynamic_cast`. Top-K via `std::nth_element` or bounded heap.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all. Validate K ≤ n_items and click_position ∈ [-1, K].

**Build:** No cyclic includes. Static internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_205.py` | Matches NumPy reference within 1e-5 on ŵ and T_count |
| 3 | `ASAN=1 build + pytest` | Zero ASan/UBSan errors |
| 4 | `bench_extensions.py` | ≥5x faster than Python reference |
| 5 | `pytest test_edges_meta_205.py` | no-click (C=-1), click at position 1, click at K, K=1, K=n all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Optional: can be layered on top of META-203 LinUCB or META-204 LinTS to form **linear cascading bandits** (Zong et al. 2016) — not in scope here.

## Pipeline Stage & Non-Conflict

**Stage:** Final ordered-list selection for internal-link SERPs; top-level structure over the candidate pool.
**Owns:** Cascade click-model attribution and top-K UCB list selection.
**Alternative to:** Flat LinUCB (META-203) / LinTS (META-204) when the action is a single arm rather than an ordered list. If the action is inherently a list, **cascading bandits is the correct attribution model** and the flat bandits become incorrect.
**Coexists with:** META-203/204 as the per-item payoff model (combined as "cascading LinUCB/LinTS") — out of scope for this meta but forward-compatible.

## Test Plan
- No click (C=-1): verify all K items' T updated (all examined) and ŵ shifted toward 0
- Click at position 1: verify only first item updated toward 1
- Click at position K: verify all K items updated; positions 1..K−1 toward 0, position K toward 1
- K=1 degenerate: verify reduces to standard UCB1 with binary click
- K=n_items degenerate: verify full list shown each round
- Regret simulation: verify sublinear regret over T=10⁵ on a synthetic 1000-item problem
