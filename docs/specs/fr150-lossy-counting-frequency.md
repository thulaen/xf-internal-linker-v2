# FR-150 — Lossy Counting Frequency Sketch

## Overview
Lossy Counting is a deterministic frequency-counting algorithm with explicit, provable error bounds — unlike randomised sketches (Count-Min, Count-Sketch), Lossy Counting *guarantees* every item with frequency `> ε·N` is reported, with at most `ε·N` overestimation, no probability of failure. FR-150 complements the randomised sketches by providing a *deterministic* top-frequency tracker for cases where probabilistic guarantees are insufficient (e.g., compliance-style anchor-reuse audits, or operator-facing reports that must not miss any heavy hitter).

## Academic source
Manku, G. S. and Motwani, R. "Approximate frequency counts over data streams." *Proceedings of the 28th International Conference on Very Large Data Bases (VLDB '02)*, pp. 346–357, 2002. URL: https://www.vldb.org/conf/2002/S10P03.pdf. DOI: 10.1016/B978-155860869-6/50038-X.

## Formula
Stream of `N` items processed in *buckets* of width `w = ⌈ 1/ε ⌉`. Bucket boundary `b_current = ⌈ N / w ⌉`. Maintain a data structure `D` of triples `(e, f, Δ)` where `e` is an item, `f` is its observed frequency since first added, and `Δ` is the maximum possible underestimation (the bucket count when `e` was added).

**Insertion** (item `x`):
```
If (x, f, Δ) ∈ D:
  f ← f + 1
Else:
  D ← D ∪ { (x, 1, b_current − 1) }
```

**Pruning** (at every bucket boundary, i.e., when `N mod w == 0`):
```
For each (e, f, Δ) ∈ D:
  If f + Δ ≤ b_current:
    D ← D \ { (e, f, Δ) }
```

**Output** (request top items above frequency threshold `s`):
```
Return all (e, f, Δ) ∈ D such that f ≥ (s − ε) · N
```

**Guarantees:**
- No item with true frequency ≥ `s·N` is omitted.
- No reported item has true frequency < `(s − ε)·N`.
- Every reported `f` satisfies `f ≤ true_count(e) ≤ f + ε·N`.

Memory bound: at most `(1/ε) · log(ε·N)` entries, far smaller than naive Counter for skewed streams.

## Starting weight preset
```python
"lossy_counting.enabled": "true",
"lossy_counting.ranking_weight": "0.0",
"lossy_counting.epsilon": "0.001",
"lossy_counting.support_threshold_s": "0.005",
"lossy_counting.bucket_width_w": "auto",
```

## C++ implementation
- File: `backend/extensions/lossy_counting.cpp`
- Entry: `void lc_update(LossyCountingState* state, uint64_t item_hash, const char* item_str)`, `std::vector<FrequentEntry> lc_query(const LossyCountingState* state, double s)`
- Complexity: O(1) amortised per update (hash table). O(|D|) for pruning at bucket boundaries; total pruning work is O(N · log(ε·N) / w) = O(N · ε · log(ε·N)).
- Thread-safety: per-instance state; concurrent updates need mutex on the hash table. Memory: O((1/ε) · log(ε·N)) entries × ~40 bytes (hash + count + delta + string ptr) ≈ 200 KB at ε=0.001 and N=10⁶.

## Python fallback
`backend/apps/pipeline/services/lossy_counting.py::LossyCounting` (mirrors `lossy_counting` PyPI reference).

## Benchmark plan
| n updates | Python (ms) | C++ target (ms) | Speedup |
|---|---|---|---|
| 10,000 | 28 | <3 | ≥9x |
| 1,000,000 | 3,200 | <280 | ≥11x |
| 100,000,000 | 350,000 | <30,000 | ≥11x |

## Diagnostics
UI: ranked list "All anchors with estimated frequency ≥ 0.5% of corpus, with guaranteed-frequency lower bound". Debug fields: `entries_in_D`, `bucket_width_w`, `current_bucket_b`, `total_insertions_N`, `epsilon`, `support_threshold_s`, `theoretical_max_entries`.

## Edge cases & neutral fallback
Empty stream → empty output. ε = 0 → bucket width infinite → no pruning ever (degenerates to exact Counter). ε ≥ 1 → bucket width 1 → every item pruned immediately (no entries retained). Pruning must run *before* query for guarantees to hold. NaN / null input → skip with state flag. Items must be hashable; strings stored in an arena allocator to control fragmentation.

## Minimum-data threshold
After N ≥ 1/ε insertions, the first bucket boundary triggers; below this, no pruning has happened and all observed items are retained.

## Budget
Disk: ~200 KB at ε=0.001 and N=10⁶ ·  RAM: ~200 KB (entries × 40 B); strings stored in arena (~200 KB additional)

## Scope boundary vs existing signals
FR-148 (Space-Saving) tracks exactly k items regardless of frequency; FR-150 tracks all items above a frequency threshold (variable count). FR-146 (Count-Min) gives probabilistic bounds; FR-150 gives deterministic bounds. FR-150 is preferred for operator-facing reports requiring "every heavy hitter included" guarantees; FR-148 is preferred when memory must be strictly bounded.

## Test plan bullets
- Insert Zipfian distribution → all true heavy hitters above s·N are reported.
- Insert uniform distribution → very few entries retained after pruning.
- Pruning produces no false negatives (compare to exact Counter).
- Reported frequencies satisfy `true_count ≤ reported_f + ε·N` always.
- Empty stream → empty output.
- ε = 0 raises ValueError.
- Persistence: serialise hash table + Δ values, deserialise, continue.
- Concurrent atomic updates produce same result as sequential.
