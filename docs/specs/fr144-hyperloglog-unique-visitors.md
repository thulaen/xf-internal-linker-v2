# FR-144 — HyperLogLog Unique Visitor Count

## Overview
Counting unique visitors to a forum page seems trivial — just store a set — but at scale, exact set storage costs gigabytes per page. HyperLogLog estimates the cardinality of any set with relative error `~1.04/√m` using only a few KB regardless of input size. FR-144 gives the ranker a per-page "audience size" signal that complements FR-072 (trending velocity) and FR-074 (influence score) without requiring exact-count storage. The classic HLL has a known bias for small cardinalities; FR-145 fixes this.

## Academic source
Flajolet, P., Fusy, É., Gandouet, O., and Meunier, F. "HyperLogLog: the analysis of a near-optimal cardinality estimation algorithm." *Proceedings of the 2007 International Conference on Analysis of Algorithms (AOFA '07)*, Discrete Mathematics and Theoretical Computer Science Proceedings AH, pp. 137–156, 2007. DOI: 10.46298/dmtcs.3545.

## Formula
Initialise `m = 2^p` registers `M[0], …, M[m−1]`, all zero. For each item `x` to insert:

```
h(x) = 64-bit hash
First p bits → register index j ∈ [0, m)
Remaining bits → w
ρ(w) = position of leftmost 1-bit in w (1-indexed)
M[j] ← max(M[j], ρ(w))
```

Cardinality estimate (raw):

```
E = α_m · m² · ( Σ_{j=0..m−1} 2^{−M[j]} )^{−1}
```

where the bias-correction constant is

```
α_m = 0.7213 / (1 + 1.079/m)    for m ≥ 128
α_16 = 0.673
α_32 = 0.697
α_64 = 0.709
```

Range correction (the original HLL):

```
n̂ = E                          if E > (5/2) · m       (large range)
n̂ = m · ln(m / V)              if E ≤ (5/2) · m and V > 0   (small range, V = #zero registers)
n̂ = 2^{32} · ln(2^{32}/(2^{32}−E))   if E > (1/30) · 2^{32}  (saturation)
```

Standard error: `σ ≈ 1.04 / √m`. At p = 12 (m = 4096), σ ≈ 1.6%; at p = 14, σ ≈ 0.81%.

## Starting weight preset
```python
"hyperloglog.enabled": "true",
"hyperloglog.ranking_weight": "0.0",
"hyperloglog.precision_p": "12",
"hyperloglog.hash_function": "xxhash64",
"hyperloglog.min_estimated_cardinality": "10",
```

## C++ implementation
- File: `backend/extensions/hyperloglog.cpp`
- Entry: `void hll_add(uint8_t* registers, int p, uint64_t hash)` plus `double hll_estimate(const uint8_t* registers, int p)`
- Complexity: O(1) per insertion; O(m) for estimate.
- Thread-safety: per-page registers; updates use atomic max if shared. SIMD: estimate's `Σ 2^{−M[j]}` vectorisable across 16-wide register chunks. Memory: m bytes per page (4 KB at p=12).

## Python fallback
`backend/apps/pipeline/services/hyperloglog.py::HyperLogLog` (mirrors `datasketch.HyperLogLog`).

## Benchmark plan
| n insertions | Python (ms) | C++ target (ms) | Speedup |
|---|---|---|---|
| 1,000 | 6 | <1 | ≥6x |
| 1,000,000 | 5,500 | <500 | ≥11x |
| 100,000,000 | 580,000 | <50,000 | ≥11x |

## Diagnostics
UI: numeric "≈ 1.2M unique visitors (±19K)". Debug fields: `cardinality_estimate`, `relative_error_pct`, `precision_p`, `register_count_m`, `nonzero_register_count`, `max_register_value`, `range_correction_used`.

## Edge cases & neutral fallback
Empty registers → estimate = 0. All registers max → saturation correction applied. Hash collisions inevitable for n > 2^64; impossibly rare. NaN/empty input items → skip with state flag. Range corrections must be applied (otherwise small-cardinality estimates are biased high). Use 64-bit hash to extend saturation point beyond 2^32.

## Minimum-data threshold
At least 10 estimated items before reporting. Below this, the small-range correction is unstable; report neutral.

## Budget
Disk: m bytes/page = 4 KB at p=12, persistent ·  RAM: <100 MB total for 25,000 pages

## Scope boundary vs existing signals
FR-072 (trending velocity) is a *rate* signal, not a unique-count signal. FR-074 (influence score) is graph-based, not visitor-based. FR-145 (HLL++) is the bias-corrected successor with better small-cardinality accuracy. FR-148 (Space-Saving) tracks top-k items, not cardinality. FR-144 is the canonical "how many distinct visitors?" signal.

## Test plan bullets
- Insert 1M unique IDs at p=12 → estimate within ±2% of 1M.
- Insert same 100 IDs 10,000 times each → estimate ≈ 100 (deduplication works).
- Empty registers → estimate exactly 0.
- Cardinality 1 → small-range correction returns ≈ 1.
- Compare to exact set count for n ≤ 1,000: relative error < 1.04/√4096.
- Merge two HLLs (max per register) → cardinality of union.
- Persistence: serialise registers, deserialise, continue inserting.
- xxhash64 input → register distribution near-uniform across `[0, m)`.
