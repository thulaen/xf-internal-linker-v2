# FR-110 - Full Dependence Model (FDM)

## Overview
SDM (FR-108) only scores adjacent query-term pairs `(q_i, q_{i+1})`. The Full Dependence Model adds all-pairs and all-subsets: any non-empty subset of query terms contributes both an ordered (`#1`) and an unordered (`#uw`) feature. This catches long-distance co-occurrence missed by SDM (e.g. "running" and "shoes" matching in a paragraph that also contains "marathon" between them). Complements FR-108 because FDM is the strict superset of SDM's pair set.

## Academic source
**Metzler, Donald and Croft, W. Bruce (2005).** "A Markov Random Field Model for Term Dependencies." *Proceedings of the 28th Annual International ACM SIGIR Conference on Research and Development in Information Retrieval (SIGIR 2005)*, pp. 472-479. DOI: `10.1145/1076034.1076115`. (FDM is the variant in §3.3 alongside SDM; both are MRF instantiations.)

## Formula
From Metzler & Croft (2005), Eq. 5 generalised to all subsets (FDM, paper §3.3):

```
FDM(Q, D) = λ_T · Σ_{q ∈ Q}              log f_T(q, D)
          + λ_O · Σ_{S ∈ subsets(Q), |S|≥2}  log f_O(S, D)
          + λ_U · Σ_{S ∈ subsets(Q), |S|≥2}  log f_U(S, D)

f_T(q, D) = (tf(q,D) + μ · p(q|C)) / (|D| + μ)

f_O(S, D) = (tf_#1(S, D) + μ · p(#1S|C)) / (|D| + μ)
            (#1S = the terms of S in their query order, contiguous in D)

f_U(S, D) = (tf_#uwN(S, D) + μ · p(#uwS|C)) / (|D| + μ)
            (#uwN = all terms of S within a window of size N · |S|)
```

Where:
- `λ_T + λ_O + λ_U = 1`, paper §3.3 defaults: `λ_T = 0.80`, `λ_O = 0.10`, `λ_U = 0.10`
- `μ = 2500` (Dirichlet pseudo-count)
- `N = 4` is the per-term FDM window multiplier (paper §3.2; window grows with subset size)
- The subset sums grow as `2^|Q| − |Q| − 1`, so an upper-bound `|Q| ≤ K_max` is enforced (default `K_max = 6`; longer queries fall back to SDM)

## Starting weight preset
```python
"fdm.enabled": "true",
"fdm.ranking_weight": "0.0",
"fdm.lambda_T": "0.80",
"fdm.lambda_O": "0.10",
"fdm.lambda_U": "0.10",
"fdm.mu": "2500",
"fdm.uw_window_per_term": "4",
"fdm.max_query_len": "6",
```

## C++ implementation
- File: `backend/extensions/fdm.cpp`
- Entry: `double fdm_score(const uint32_t* query_term_ids, int n, const PositionalDoc& doc, const CorpusStats& corp, double lambda_T, double lambda_O, double lambda_U, double mu, int uw_per_term, int max_q);`
- Complexity: `O((2^|Q|) · |D|)` worst case; bounded by `K_max`. For `|Q| ≤ 6`: ≤ 63 subsets · `|D|` ops
- Thread-safety: pure function
- SIMD: positional intersection vectorised; subset enumeration uses bit-mask iteration
- Builds against pybind11 like FR-108

## Python fallback
`backend/apps/pipeline/services/fdm.py::score_fdm(...)`.

## Benchmark plan
| Candidates | C++ target | Python target |
|---|---|---|
| 10 (Q=4) | < 1 ms | < 10 ms |
| 100 (Q=4) | < 5 ms | < 50 ms |
| 500 (Q=4) | < 25 ms | < 250 ms |

## Diagnostics
- Per-component score (`T`, `O`, `U`)
- Per-subset contribution top-5 (so operator can see "Tokyo Marathon training" caught a 3-term match)
- C++ vs Python badge
- Whether `|Q| > K_max` triggered SDM fallback

## Edge cases & neutral fallback
- `|Q| = 1` → only `T` contributes
- `|Q| > K_max` → fall back to SDM, flag `truncated_to_sdm`
- `|D| = 0` → 0.0, flag `empty_doc`
- No positional data → fall back to LM-only, flag `no_positions`
- λ-sum ≠ 1 → renormalise, flag `lambda_renormalised`
- Missing corpus stats → neutral 0.5, flag `no_corpus_stats`
- NaN / Inf → 0.0, flag `nan_clamped`

## Minimum-data threshold
Corpus ≥ 100 docs and document has positional data; below this returns neutral 0.5.

## Budget
Disk: <2 MB  ·  RAM: <25 MB (subset bitmask cache + positional postings)

## Scope boundary vs existing signals
FR-110 does NOT duplicate FR-108 SDM because FDM scores all subsets (`2^|Q|`) while SDM only scores adjacent pairs. It does not duplicate FR-109 WSDM because FDM uses global `λ` (like SDM) but expands to all subsets; WSDM uses per-pair learned `λ`. The two are orthogonal axes and could combine into "weighted FDM" later.

## Test plan bullets
- unit tests: `|Q| = 1, 2, 3, 6, 7` (the last to confirm SDM fallback)
- parity test: C++ vs Python within `1e-4`
- limit check: `|Q| = 2` reduces FDM to SDM exactly
- subset enumeration test: bit-mask iteration covers all `2^|Q|−|Q|−1` non-singleton subsets without double-count
- no-crash test on adversarial input (`|Q| = K_max`, all-same-term query)
- integration test: ranking unchanged when `ranking_weight = 0.0`
