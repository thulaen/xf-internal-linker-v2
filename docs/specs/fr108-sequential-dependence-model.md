# FR-108 - Sequential Dependence Model (SDM)

## Overview
Bag-of-words scorers ignore that adjacent query terms often form meaningful phrases. SDM frames retrieval as a Markov Random Field over query terms with three feature classes — single terms (`T`), ordered adjacent bigrams (`O`), and unordered windowed bigrams (`U`) — combined with fixed weights. It strictly generalises both unigram LM and exact-phrase match. Complements FR-008 phrase matching because SDM adds soft windowed-phrase scoring (matches a 2-term query within an 8-token window even if not contiguous).

## Academic source
**Metzler, Donald and Croft, W. Bruce (2005).** "A Markov Random Field Model for Term Dependencies." *Proceedings of the 28th Annual International ACM SIGIR Conference on Research and Development in Information Retrieval (SIGIR 2005)*, pp. 472-479. DOI: `10.1145/1076034.1076115`.

## Formula
From Metzler & Croft (2005), Eq. 5 (the SDM ranking function):

```
SDM(Q, D) = λ_T · Σ_{q ∈ Q}        log f_T(q, D)
          + λ_O · Σ_{q_i, q_{i+1}}  log f_O(q_i q_{i+1}, D)
          + λ_U · Σ_{q_i, q_{i+1}}  log f_U(q_i q_{i+1}, D)

f_T(q, D)         = (tf(q,D) + μ · p(q|C)) / (|D| + μ)            (Dirichlet LM)

f_O(q_i q_{i+1}, D) = (tf_#1(q_i q_{i+1}, D) + μ · p(#1|C)) / (|D| + μ)
                    (#1 = ordered adjacency, exact bigram in D)

f_U(q_i q_{i+1}, D) = (tf_#uwN(q_i q_{i+1}, D) + μ · p(#uwN|C)) / (|D| + μ)
                    (#uwN = unordered window of size N, default N = 8)
```

Where:
- `λ_T + λ_O + λ_U = 1`, paper §3.3 defaults: `λ_T = 0.85`, `λ_O = 0.10`, `λ_U = 0.05`
- `μ` = Dirichlet pseudo-count (default 2500, same as FR-105)
- `p(q|C)`, `p(#1|C)`, `p(#uwN|C)` = collection-frequency MLE for each feature
- `N = 8` is the standard SDM unordered-window size (paper §3.2)
- The sums over `(q_i, q_{i+1})` iterate adjacent query-term pairs only

## Starting weight preset
```python
"sdm.enabled": "true",
"sdm.ranking_weight": "0.0",
"sdm.lambda_T": "0.85",
"sdm.lambda_O": "0.10",
"sdm.lambda_U": "0.05",
"sdm.mu": "2500",
"sdm.uw_window": "8",
```

## C++ implementation
- File: `backend/extensions/sdm.cpp`
- Entry: `double sdm_score(const uint32_t* query_term_ids, int n, const PositionalDoc& doc, const CorpusStats& corp, double lambda_T, double lambda_O, double lambda_U, double mu, int uw_window);`
- Complexity: `O(|Q| + (|Q|−1) · |D|)` — `T` is `O(|Q|)`, `O` and `U` need a sliding-window scan over positions of each pair
- Thread-safety: pure function
- SIMD: positional intersection vectorised (see existing `scoring.cpp` posting-merge utilities)
- Builds against pybind11 like FR-099

## Python fallback
`backend/apps/pipeline/services/sdm.py::score_sdm(...)`.

## Benchmark plan
| Candidates | C++ target | Python target |
|---|---|---|
| 10 | < 0.5 ms | < 5 ms |
| 100 | < 3 ms | < 30 ms |
| 500 | < 12 ms | < 150 ms |

## Diagnostics
- Per-component score (`T`, `O`, `U`) and the three λ values
- C++ vs Python badge
- Number of `#1` and `#uw8` matches per pair
- Effective `μ` and `N`

## Edge cases & neutral fallback
- `|Q| = 1` → only `T` component contributes; no warning, this is correct behaviour
- `|D| = 0` → 0.0, flag `empty_doc`
- No positional data → fall back to LM-only (`T` component); flag `no_positions`
- Sum `λ_T + λ_O + λ_U ≠ 1` → renormalise and flag `lambda_renormalised`
- Missing corpus stats → neutral 0.5, flag `no_corpus_stats`
- NaN / Inf → 0.0, flag `nan_clamped`

## Minimum-data threshold
Corpus ≥ 100 docs and document has positional data; below this returns neutral 0.5.

## Budget
Disk: <2 MB  ·  RAM: <20 MB (positional postings + bigram cache)

## Scope boundary vs existing signals
FR-108 does NOT duplicate FR-008 phrase matching because FR-008 is a binary phrase-hit signal while SDM is a continuous MRF score combining unigrams, ordered bigrams, and windowed bigrams. It does not duplicate FR-105 LM because SDM strictly generalises LM (`λ_T = 1` recovers LM exactly).

## Test plan bullets
- unit tests: `|Q| = 1`, `|Q| = 2`, longer queries, repeated terms
- parity test: C++ vs Python within `1e-4`
- limit check: `λ_T = 1, λ_O = λ_U = 0` reduces to FR-105 stage-1 LM
- no-crash test on adversarial input (`uw_window = 0`, `μ = 0`)
- integration test: ranking unchanged when `ranking_weight = 0.0`
