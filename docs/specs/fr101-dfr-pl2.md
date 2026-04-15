# FR-101 - DFR PL2 (Poisson-Laplace 2)

## Overview
The Divergence-from-Randomness (DFR) family scores a term by how much its observed in-document frequency departs from a random baseline distribution. PL2 uses a Poisson model for term occurrence and a Laplace after-effect normalisation. It is parameter-free in the IDF sense (no `k₁`, no `b` to tune the same way as BM25), giving the auto-tuner an uncorrelated alternative to FR-011 / FR-099 / FR-100. Complements those signals by widening the LTR feature basis with a model that derives weights from information theory rather than empirical fitting.

## Academic source
**Amati, Gianni and van Rijsbergen, Cornelis Joost (2002).** "Probabilistic Models of Information Retrieval Based on Measuring the Divergence from Randomness." *ACM Transactions on Information Systems (TOIS)*, vol. 20, no. 4, pp. 357-389. DOI: `10.1145/582415.582416`.

## Formula
From Amati & van Rijsbergen (2002), Eq. 13 (PL2):

```
tfn(q,D) = tf(q,D) · log₂(1 + c·avgdl/|D|)              (length normalisation H2)

PL2(q,D) = (1 / (tfn + 1)) · [
  tfn · log₂(tfn / λ_q) + (λ_q + 1/(12·tfn) − tfn) · log₂(e) + 0.5·log₂(2π·tfn)
]

λ_q = F(q) / N

PL2(Q,D) = Σ_{q ∈ Q}  qtf(q,Q) · PL2(q,D)
```

Where:
- `tf(q,D)` = raw term frequency in `D`; `tfn` = length-normalised tf
- `|D|`, `avgdl` as before
- `c > 0` = length-normalisation parameter (default 7.0 per paper §6.3 for short queries; 1.0 for long queries)
- `F(q)` = total occurrences of `q` in the corpus, `N` = total documents
- `λ_q` = mean of the Poisson model = `F(q)/N`
- `qtf(q,Q)` = query term frequency (often 1)
- The bracketed expression is the Stirling-approximated `−log₂ P_Poisson(tfn ; λ_q)`

## Starting weight preset
```python
"dfr_pl2.enabled": "true",
"dfr_pl2.ranking_weight": "0.0",
"dfr_pl2.c": "7.0",
```

## C++ implementation
- File: `backend/extensions/dfr_pl2.cpp`
- Entry: `double dfr_pl2_score(const uint32_t* query_term_ids, int n, const DocStats& doc, const CorpusStats& corp, double c);`
- Complexity: `O(|Q|)` per (query, doc); per-term cost is constant-time after `log₂` and `1/x` (≤ 6 FP ops)
- Thread-safety: pure function
- SIMD: vectorised `log2` via `std::log2` + `#pragma omp simd reduction(+:score)`
- Builds against pybind11 like FR-099

## Python fallback
`backend/apps/pipeline/services/dfr_pl2.py::score_dfr_pl2(...)` — uses `math.log2` per term.

## Benchmark plan
| Candidates | C++ target | Python target |
|---|---|---|
| 10 | < 0.06 ms | < 0.6 ms |
| 100 | < 0.3 ms | < 6 ms |
| 500 | < 1.2 ms | < 30 ms |

## Diagnostics
- Raw PL2 score and per-term contributions
- C++ vs Python badge
- Length-normalised `tfn` for each query term
- Poisson mean `λ_q` per query term

## Edge cases & neutral fallback
- `tf = 0` for a query term → that term contributes 0
- `tfn = 0` (after normalisation) → that term contributes 0; avoids log of zero
- `|D| = 0` → 0.0, flag `empty_doc`
- `λ_q = 0` (term unseen in corpus) → that term contributes 0, flag `unseen_term`
- Missing corpus stats → neutral 0.5, flag `no_corpus_stats`
- NaN / Inf → 0.0, flag `nan_clamped`

## Minimum-data threshold
≥ 50 documents required so `λ_q` is statistically meaningful for typical query terms; below this returns neutral 0.5.

## Budget
Disk: <1 MB  ·  RAM: <5 MB

## Scope boundary vs existing signals
FR-101 does NOT duplicate FR-011 BM25 because PL2 is grounded in the divergence of the empirical tf from a Poisson baseline rather than a saturation-and-length curve; rankings disagree on rare terms in particular. It complements FR-018 by giving the auto-tuner a low-correlation feature drawn from information theory.

## Test plan bullets
- unit tests: zero overlap, single term, common-term-only, rare-term-only
- parity test: C++ vs Python within `1e-4` over 1000 random queries
- no-crash test on adversarial input (huge `tf`, `tfn → 0`)
- integration test: ranking unchanged when `ranking_weight = 0.0`
- monotonicity test: increasing `tf` for a fixed `|D|` should not decrease PL2
