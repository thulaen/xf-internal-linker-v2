# FR-148 — Space-Saving Top-k Anchor Tracker

## Overview
Forum link suggestions need to know the *top-k most frequent* anchor texts in the corpus so the diversity guard (FR-045) can detect over-reuse. Sketches like Count-Min (FR-146) estimate frequency for *queried* items but cannot enumerate the top-k without scanning all possible items. Space-Saving keeps exactly k counters and provides deterministic top-k tracking with bounded memory. FR-148 complements FR-045 by maintaining a persistent, low-RAM list of the most-used anchors across the corpus, updated in O(1) per insertion.

## Academic source
Metwally, A., Agrawal, D., and El-Abbadi, A. "Efficient computation of frequent and top-k elements in data streams." *Proceedings of the 10th International Conference on Database Theory (ICDT '05)*, pp. 398–412, 2005. DOI: 10.1007/978-3-540-30570-5_27.

## Formula
Maintain a set of `k` counters `T = { (e_1, c_1, ε_1), …, (e_k, c_k, ε_k) }` where `e_i` is the monitored item, `c_i` is its estimated count, and `ε_i` is the maximum possible overestimation of `c_i`.

**Update** (insert item `x`):
```
If x ∈ T:                              // x already monitored
  c_x ← c_x + 1
Else if |T| < k:                        // capacity available
  T ← T ∪ { (x, 1, 0) }
Else:                                   // replace the min-counter element
  (e_min, c_min, ε_min) = argmin_{(e,c,ε) ∈ T}  c
  T ← T \ { (e_min, c_min, ε_min) }
  T ← T ∪ { (x, c_min + 1, c_min) }    // new ε = old min count
```

**Top-k query:** sort `T` by `c_i` descending; the largest `c_i − ε_i` are guaranteed top-k.

**Error guarantee:** for any item `x` with true frequency `f(x)`,
```
f(x) ≤ ĉ(x) ≤ f(x) + ε_x ≤ f(x) + N/k
```

where `N` = total number of insertions. So with `k = ⌈ 1/ε ⌉`, every item with frequency `≥ ε · N` is guaranteed to be in `T` and its count is within `ε · N` of true.

## Starting weight preset
```python
"space_saving.enabled": "true",
"space_saving.ranking_weight": "0.0",
"space_saving.k_counters": "1000",
"space_saving.report_top_n": "100",
"space_saving.guarantee_threshold_epsilon": "0.001",
```

## C++ implementation
- File: `backend/extensions/space_saving.cpp`
- Entry: `void ss_update(SpaceSavingState* state, uint64_t item_hash, const char* item_str)`, `std::vector<TopKEntry> ss_top_k(const SpaceSavingState* state, int n)`
- Complexity: O(1) amortised per update using the Stream-Summary data structure (linked list of buckets, each bucket holds items with same count). Naive O(log k) using a min-heap also acceptable.
- Thread-safety: per-instance state; updates need a single mutex (the data structure is not lock-free). Memory: O(k) entries × (8B hash + variable string + 4B count + 4B error) ≈ 50 bytes/entry, so 50 KB at k=1000.

## Python fallback
`backend/apps/pipeline/services/space_saving.py::SpaceSaving` (mirrors `bounter.HashTable` and Stream-Summary reference).

## Benchmark plan
| n updates | Python (ms) | C++ target (ms) | Speedup |
|---|---|---|---|
| 10,000 | 18 | <2 | ≥9x |
| 1,000,000 | 1,900 | <180 | ≥11x |
| 100,000,000 | 195,000 | <17,000 | ≥11x |

## Diagnostics
UI: ranked list "Top-100 anchors with estimated frequency and guaranteed-frequency lower bound". Debug fields: `top_k_entries[].item`, `top_k_entries[].count`, `top_k_entries[].error_epsilon`, `top_k_entries[].guaranteed_min_count`, `total_insertions_N`, `k_counters_used`, `min_counter_value`.

## Edge cases & neutral fallback
Empty state → empty top-k. k=0 → ValueError. Tie-breaking when multiple counters share min value: any can be evicted (deterministic by hash for reproducibility). After eviction, item still re-monitored if it appears again (will start at new min + 1). String storage: variable-length anchors require careful memory management — use an arena allocator. Item identity by hash, not string equality (collisions theoretically possible at 64-bit).

## Minimum-data threshold
After N ≥ 100·k insertions, top-k results are stable and reliable.

## Budget
Disk: ~50 KB per Space-Saving state at k=1000 ·  RAM: ~50 KB; arena holds strings (additional ~50 KB at typical anchor lengths)

## Scope boundary vs existing signals
FR-045 (anchor diversity guard) checks anchors used per-page; FR-148 tracks corpus-wide top-k anchors that feed into FR-045's reuse penalty. FR-146/FR-147 (Count-Min/Count-Sketch) estimate frequency of *queried* items but cannot enumerate top-k without scanning. FR-150 (Lossy Counting) tracks all items above a frequency threshold; FR-148 tracks exactly k items regardless of threshold.

## Test plan bullets
- Insert Zipfian distribution → top-10 results match exact Counter top-10.
- Insert uniform distribution with > k distinct items → top-k results have high error_epsilon (expected).
- Item with frequency > N/k always in T → guaranteed by paper.
- k = 1 → only the most-recently-inserted item monitored at any time (degenerate).
- Empty insertion → empty top-k.
- Persistence: serialise Stream-Summary, deserialise, continue.
- Compare to exact Counter on stream of 1M items: top-100 overlap ≥ 95%.
- Concurrent updates with mutex produce same result as sequential.
