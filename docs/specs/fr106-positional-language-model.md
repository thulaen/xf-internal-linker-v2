# FR-106 - Positional Language Model

## Overview
Standard LM and BM25 scorers ignore where in the document the query terms appear. The Positional Language Model (PLM) builds a per-position language model by spreading each term's occurrence to neighbouring positions through a kernel (Gaussian, triangle, or cosine). The document score is the maximum (or aggregated) per-position score across the document. Forum posts open with a topic summary; PLM rewards documents where query terms cluster in those high-value opening positions. Complements FR-105 because PLM extends LM scoring with positional structure that FR-105 cannot see.

## Academic source
**Lv, Yuanhua and Zhai, ChengXiang (2009).** "Positional Language Models for Information Retrieval." *Proceedings of the 32nd International ACM SIGIR Conference on Research and Development in Information Retrieval (SIGIR 2009)*, pp. 299-306. DOI: `10.1145/1571941.1572005`.

## Formula
From Lv & Zhai (2009), Eqs. 4-7 (Gaussian kernel + Dirichlet smoothing):

```
k(i, j) = exp( − (i − j)² / (2 · σ²) )                           (Gaussian kernel)

c'(w, i) = Σ_{j=1..|D|}  c(w, j) · k(i, j)                       (propagated count)

Z(i) = Σ_{w'} c'(w', i)                                          (normaliser)

p(w | D, i) = (c'(w, i) + μ · p(w|C)) / (Z(i) + μ)               (Dirichlet at position i)

PLM_BestPos(Q, D) = max_{i = 1..|D|}  Σ_{w ∈ Q}  qtf(w,Q) · log p(w | D, i)
```

Where:
- `c(w, j)` = 1 if token at position `j` is `w`, else 0
- `i, j` = positions in `D`, indexed 1..|D|
- `σ > 0` = Gaussian kernel bandwidth (default 50 per paper §4.2 Table 1)
- `μ > 0` = Dirichlet pseudo-count (default 2500)
- `p(w|C) = cf(w) / |C|`
- `PLM_BestPos` = score using best-position aggregation; alternatives in the paper include MultiPosition and MeanPosition

## Starting weight preset
```python
"plm.enabled": "true",
"plm.ranking_weight": "0.0",
"plm.kernel": "gaussian",
"plm.sigma": "50",
"plm.mu": "2500",
"plm.aggregation": "best_pos",
```

## C++ implementation
- File: `backend/extensions/plm.cpp`
- Entry: `double plm_score(const uint32_t* query_term_ids, int n, const PositionalDoc& doc, const CorpusStats& corp, double sigma, double mu, AggregationMode mode);`
- Complexity: `O(|Q| · |D| · P)` where `P` is the kernel support window (truncated at `4σ` ≈ 200 positions); reuses positional posting lists already built for FR-008 phrase matching
- Thread-safety: pure function
- SIMD: kernel `exp` precomputed in a lookup table; per-position sum vectorised
- Builds against pybind11 like FR-099

## Python fallback
`backend/apps/pipeline/services/plm.py::score_plm(...)`.

## Benchmark plan
| Candidates | C++ target | Python target |
|---|---|---|
| 10 | < 0.5 ms | < 5 ms |
| 100 | < 3 ms | < 50 ms |
| 500 | < 15 ms | < 250 ms |

(Higher targets reflect `O(|D|·P)` per-doc cost.)

## Diagnostics
- Raw PLM score and per-term contribution at the winning position
- C++ vs Python badge
- Best position `i*` (where the maximum was attained)
- Effective kernel `σ` and aggregation mode

## Edge cases & neutral fallback
- `|D| = 0` → 0.0, flag `empty_doc`
- No positional data available → neutral 0.5, flag `no_positions`
- Single-position document (`|D| = 1`) → kernel reduces to delta; PLM = LM at that position
- All query terms absent → score = corpus-only contribution
- Missing corpus stats → neutral 0.5, flag `no_corpus_stats`
- NaN / Inf → 0.0, flag `nan_clamped`

## Minimum-data threshold
Document must have ≥ 5 tokens with positional data, and corpus ≥ 100 docs; below this returns neutral 0.5.

## Budget
Disk: <3 MB  ·  RAM: <15 MB (positional posting cache + kernel LUT)

## Scope boundary vs existing signals
FR-106 does NOT duplicate FR-105 because PLM is a per-position model with explicit positional kernels; FR-105 is position-agnostic. It does not duplicate FR-008 phrase matching because PLM scores soft proximity at every position rather than binary phrase hits.

## Test plan bullets
- unit tests: empty doc, single token, query terms clustered vs spread out
- parity test: C++ vs Python within `1e-4`
- kernel sanity: Gaussian symmetric around `i`; triangle linear decay
- best-position monotonicity: clustering query terms in one window should not lower score
- no-crash test on adversarial input (`σ = 0`, `|D|` very large)
- integration test: ranking unchanged when `ranking_weight = 0.0`
