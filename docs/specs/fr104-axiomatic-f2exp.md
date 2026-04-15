# FR-104 - Axiomatic F2EXP Retrieval

## Overview
Axiomatic Retrieval defines a small set of formal constraints (TFC1, TFC2, TFC3, TDC, LNC1, LNC2, TF-LNC) that every reasonable retrieval function should satisfy, then derives scoring functions provably meeting them. F2EXP is the exponential length-normalised variant — it is robust against adversarial term-weighting because the axioms exclude pathological behaviour by construction. Complements FR-099 / FR-100 / FR-101 by being grounded in principle rather than empirical fit; it acts as a sanity floor in the LTR ensemble.

## Academic source
**Fang, Hui and Zhai, ChengXiang (2006).** "Semantic Term Matching in Axiomatic Approaches to Information Retrieval." *Proceedings of the 29th Annual International ACM SIGIR Conference on Research and Development in Information Retrieval (SIGIR 2006)*, pp. 115-122. DOI: `10.1145/1148170.1148193`. (F2EXP defined in their earlier paper: **Fang, Tao, Zhai (2004).** "A Formal Study of Information Retrieval Heuristics," *SIGIR 2004*, DOI: `10.1145/1008992.1009004`.)

## Formula
F2EXP from Fang & Zhai (2004), Table 4, modified-IDF version:

```
F2EXP(Q, D) = Σ_{q ∈ Q ∩ D}  qtf(q,Q) · ( N / df(q) )^k  ·  (tf(q,D)) / (tf(q,D) + s + s · |D| / avgdl)
```

Where:
- `Q ∩ D` = query terms present in document
- `qtf(q,Q)` = query term frequency
- `tf(q,D)`, `df(q)`, `|D|`, `avgdl`, `N` as before
- `k > 0` = IDF exponent (default 0.35 per paper §4.2 Table 2)
- `s ∈ (0, 1)` = length-normalisation parameter (default 0.5 per paper §4.2 Table 2)

The `(N/df(q))^k` factor is the axiomatic IDF and `(tf)/(tf + s + s·|D|/avgdl)` is the length-normalised tf saturation; together they satisfy TFC1 (rewards term-frequency increase), TFC3 (rewards rare terms), LNC1 (penalises length increase from non-query terms), and TF-LNC (joint constraint).

## Starting weight preset
```python
"axiomatic_f2exp.enabled": "true",
"axiomatic_f2exp.ranking_weight": "0.0",
"axiomatic_f2exp.k": "0.35",
"axiomatic_f2exp.s": "0.5",
```

## C++ implementation
- File: `backend/extensions/axiomatic_f2exp.cpp`
- Entry: `double f2exp_score(const uint32_t* query_term_ids, int n, const DocStats& doc, const CorpusStats& corp, double k, double s);`
- Complexity: `O(|Q|)` per (query, doc); single `std::pow(N/df, k)` per term (precomputable per-term)
- Thread-safety: pure function
- SIMD: `#pragma omp simd reduction(+:score)`; `std::pow` vectorised by the compiler with `-ffast-math`
- Builds against pybind11 like FR-099

## Python fallback
`backend/apps/pipeline/services/axiomatic_f2exp.py::score_f2exp(...)`.

## Benchmark plan
| Candidates | C++ target | Python target |
|---|---|---|
| 10 | < 0.06 ms | < 0.6 ms |
| 100 | < 0.3 ms | < 6 ms |
| 500 | < 1.5 ms | < 30 ms |

## Diagnostics
- Raw F2EXP score and per-term contributions
- C++ vs Python badge
- Per-term IDF factor `(N/df)^k`
- Length-normalised tf factor

## Edge cases & neutral fallback
- `Q ∩ D = ∅` → score = 0.0
- `df(q) = 0` (term unseen in corpus) → IDF factor undefined, term contributes 0, flag `unseen_term`
- `df(q) > N` (corruption) → IDF clamped at 0, flag `idf_clamped`
- `|D| = 0` → 0.0, flag `empty_doc`
- Missing corpus stats → neutral 0.5, flag `no_corpus_stats`
- NaN / Inf → 0.0, flag `nan_clamped`

## Minimum-data threshold
≥ 20 documents so `N/df` is non-trivial; below this returns neutral 0.5.

## Budget
Disk: <1 MB  ·  RAM: <5 MB

## Scope boundary vs existing signals
FR-104 does NOT duplicate FR-099, FR-100, FR-101, FR-102, or FR-103 because F2EXP is an axiomatic derivation: the IDF is `(N/df)^k` (power, not log) and the length factor is `tf + s(1+|D|/avgdl)` (additive, not multiplicative). Provably satisfies retrieval axioms that BM25 and DFR violate in extremes.

## Test plan bullets
- unit tests: zero overlap, single term, varying length, varying `df`
- parity test: C++ vs Python within `1e-4`
- axiom checks (paper §3): TFC1, TFC3, LNC1, TF-LNC verified by construction
- no-crash test on adversarial input (`df = 0`, huge `tf`)
- integration test: ranking unchanged when `ranking_weight = 0.0`
