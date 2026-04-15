# FR-178 — Pointwise Mutual Information (PMI)

## Overview
PMI quantifies how much more often two terms (or a term and a topic, or a host-anchor pair) co-occur than they would by chance under independence. PMI > 0 ⇒ terms attract; PMI = 0 ⇒ independent; PMI < 0 ⇒ repel. For an internal-linker, PMI between an anchor phrase and a candidate destination's title gives a cheap collocation prior. Foundational for FR-179 (NPMI, the bounded variant) and FR-180 (LLR, the significance-tested variant). Complements `fr011-field-aware-relevance-scoring` (per-document BM25) by being a *corpus-wide association* signal.

## Academic source
Church, K. W. and Hanks, P. "Word association norms, mutual information, and lexicography." *Computational Linguistics*, 16(1), pp. 22–29, 1990. URL: https://aclanthology.org/J90-1003/. ACL Anthology citation: `J90-1003`. Earlier related work: Fano, R. M. *Transmission of Information* (MIT Press, 1961), where the pointwise version of mutual information is defined.

## Formula
From Church & Hanks (1990), Eq. 1 — PMI between two events `x` and `y` (commonly word co-occurrences in a window of size `W`):

```
PMI(x, y) = log( P(x, y) / ( P(x) · P(y) ) )

where, with sliding window of size W:
  P(x)    = count(x) / N                   (unigram prob)
  P(y)    = count(y) / N
  P(x, y) = count(x, y) / N                (joint count in same window)
  N       = total positions / windows in the corpus
```

Equivalent form on raw counts (with `N` as window count):

```
PMI(x, y) = log( N · count(x, y) / ( count(x) · count(y) ) )
```

Range: `PMI ∈ ( −∞, +∞ )`. Maximum at perfect co-occurrence (`P(x,y) = min(P(x), P(y))`); negative for anti-correlation; undefined when either marginal is zero.

## Starting weight preset
```python
"pmi.enabled": "true",
"pmi.ranking_weight": "0.0",
"pmi.window_size_W": "10",
"pmi.log_base": "2",
"pmi.smoothing_epsilon": "0.5",
```

## C++ implementation
- File: `backend/extensions/pmi.cpp`
- Entry: `double pmi(uint64_t count_xy, uint64_t count_x, uint64_t count_y, uint64_t total_n)`
- Complexity: O(1) per pair given precomputed counts; O(N · W) to build co-occurrence sketch
- Thread-safety: pure function on counts; sketch building uses lock-free counters
- Builds via pybind11; SIMD log via vectorised polynomial when computing many pairs

## Python fallback
`backend/apps/pipeline/services/pmi.py::compute_pmi` using `math.log2((c_xy * N) / (c_x * c_y))` with smoothing.

## Benchmark plan

| Size | pairs evaluated | C++ target | Python target |
|---|---|---|---|
| Small | 1,000 | 0.005 ms | 0.5 ms |
| Medium | 100,000 | 0.4 ms | 50 ms |
| Large | 10,000,000 | 30 ms | 4,500 ms |

## Diagnostics
- PMI value rendered as "PMI: 4.2 bits"
- Per-pair count breakdown `(count_xy, count_x, count_y, N)`
- C++/Python badge
- Debug fields: `window_size_W`, `joint_count`, `marginal_x`, `marginal_y`, `total_windows`, `log_base`

## Edge cases & neutral fallback
- `count(x, y) = 0` ⇒ PMI = −∞ ⇒ apply add-ε smoothing (default ε = 0.5 per Hutchins/Church) so PMI is finite
- `count(x) = 0` or `count(y) = 0` ⇒ undefined ⇒ neutral 0.5 with fallback flag (term unseen)
- Low-count pairs (count_xy < 5) are unstable — flag in diagnostics; consider FR-180 LLR for significance testing
- Window size: PMI is sensitive to `W`; typical values 5–10 for syntax-flavoured association, 100+ for topical
- Self-co-occurrence (`x = y`): `PMI(x, x) = log(1/P(x)) = surprisal(x)` — still well-defined

## Minimum-data threshold
Need `count(x) ≥ 5` and `count(y) ≥ 5` and `count(x, y) ≥ 3` for stable PMI; otherwise fall back to neutral.

## Budget
Disk: depends on co-occurrence sketch (~50 MB for 100k vocab × top-pairs) · RAM: same sketch in lookup form

## Scope boundary vs existing signals
Distinct from `fr179-normalized-pmi` (NPMI is bounded `[−1, +1]`) and `fr180-log-likelihood-ratio-term-association` (LLR adds significance test). Distinct from `fr011-field-aware-relevance-scoring` (per-document scorer). PMI is the raw, unbounded base case for the association-signal family.

## Test plan bullets
- Unit: perfectly co-occurring pair `count_xy = count_x = count_y` ⇒ PMI = `log₂(N/count_x)`
- Unit: independent pair `count_xy ≈ count_x · count_y / N` ⇒ PMI ≈ 0
- Parity: C++ vs Python within 1e-6 on 1,000 pairs
- Edge: zero joint count uses smoothing, no `log(0)` crash
- Edge: zero marginal returns 0.5 with fallback
- Integration: deterministic across runs given fixed sketch
- Regression: top-50 ranking unchanged when weight = 0.0
