# FR-113 - Ordered Span Proximity (Büttcher–Clarke–Lushman)

## Overview
MinSpan (FR-112) doesn't care about query-term order. But "running shoes" matched as "shoes running" is weaker evidence than the in-order match. Ordered Span Proximity walks the document, accumulates an in-order span score whenever query terms appear in their query-order, and decays the contribution by the gap distance. Strong on titles and headings where exact phrasing matters. Complements FR-112 because MinSpan is order-free and FR-113 is order-aware; the two together cover both regimes.

## Academic source
**Büttcher, Stefan; Clarke, Charles L. A.; Lushman, Brad (2006).** "Term Proximity Scoring for Ad-Hoc Retrieval on Very Large Text Collections." *Proceedings of the 29th Annual International ACM SIGIR Conference on Research and Development in Information Retrieval (SIGIR 2006)*, pp. 621-622. DOI: `10.1145/1148170.1148285`. (Full method described in Büttcher's PhD thesis: "Multi-User File System Search," University of Waterloo, 2007.)

## Formula
From Büttcher, Clarke, Lushman (2006), Eq. 1 (proximity contribution of an adjacent ordered pair `(t_i, t_{i+1})`):

```
acc(t_i, t_{i+1}, D) = Σ_{(p_i, p_{i+1}) : 1 ≤ p_{i+1} − p_i, ordered}  IDF(t_i) · IDF(t_{i+1}) / (p_{i+1} − p_i)²

ordered_span(Q, D) = Σ_{i = 1..|Q|−1}  acc(t_i, t_{i+1}, D)

score_OSP(Q, D) = log( 1 + ordered_span(Q, D) )
```

Where:
- `t_i` = i-th term of `Q` in query order
- `(p_i, p_{i+1})` = a pair of positions in `D` such that `t_i` occurs at `p_i`, `t_{i+1}` occurs at `p_{i+1}`, and `p_{i+1} > p_i` (strictly ordered)
- `IDF(t)` = `log( (N + 1) / df(t) )` (paper §2)
- `1 / (p_{i+1} − p_i)²` decays with squared distance — same kernel as FR-111 but only counted in-order
- `log(1 + ·)` keeps the score numerically tame for high-density passages

## Starting weight preset
```python
"osp.enabled": "true",
"osp.ranking_weight": "0.0",
"osp.distance_decay": "inverse_square",
"osp.idf_weighted": "true",
```

## C++ implementation
- File: `backend/extensions/osp.cpp`
- Entry: `double osp_score(const uint32_t* query_term_ids, int n, const PositionalDoc& doc, const CorpusStats& corp);`
- Complexity: `O(|D| · |Q|)` worst case via two-pointer scan over consecutive query-term posting pairs; typical anchor query gives `O(|D|)`
- Thread-safety: pure function
- SIMD: `1/d²` precomputed table for `d ∈ [1, 1024]`; `log1p` vectorised
- Builds against pybind11 like FR-099

## Python fallback
`backend/apps/pipeline/services/osp.py::score_osp(...)`.

## Benchmark plan
| Candidates | C++ target | Python target |
|---|---|---|
| 10 | < 0.1 ms | < 1 ms |
| 100 | < 0.5 ms | < 5 ms |
| 500 | < 2.5 ms | < 25 ms |

## Diagnostics
- Per-pair `acc(t_i, t_{i+1})` contributions
- C++ vs Python badge
- Number of ordered pair occurrences found
- Whether any pair contributed (otherwise score = 0)

## Edge cases & neutral fallback
- `|Q| = 1` → no consecutive pairs; score = 0
- `Q ∩ D = ∅` → 0.0
- All occurrences out of order → 0.0; flag `no_ordered_pairs`
- `|D| = 0` → 0.0, flag `empty_doc`
- No positional data → neutral 0.5, flag `no_positions`
- Missing corpus stats (no IDF) → uniform IDF = 1, flag `no_idf_uniform`
- NaN / Inf → 0.0, flag `nan_clamped`

## Minimum-data threshold
Document with positional data and `|Q| ≥ 2`; corpus ≥ 10 docs for IDF. Below this, returns neutral 0.5.

## Budget
Disk: <1 MB  ·  RAM: <10 MB

## Scope boundary vs existing signals
FR-113 does NOT duplicate FR-112 MinSpan because MinSpan is order-free; FR-113 only counts ordered pairs. It does not duplicate FR-111 BM25TP because BM25TP sums all unordered pairs and bolts onto a BM25 base, whereas FR-113 is a standalone IDF-weighted ordered-pair score.

## Test plan bullets
- unit tests: `|Q| = 1`, exact-order match, reverse-order (score = 0), interleaved
- parity test: C++ vs Python within `1e-4`
- order sensitivity: swapping two adjacent query terms changes the score
- monotonicity: closer ordered pairs strictly increase score
- no-crash test on adversarial input (`df = 0` for some term, `|D|` huge)
- integration test: ranking unchanged when `ranking_weight = 0.0`
