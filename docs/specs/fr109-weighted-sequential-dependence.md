# FR-109 - Weighted Sequential Dependence Model (WSDM)

## Overview
SDM (FR-108) uses one global `λ_T`, `λ_O`, `λ_U`. Real queries vary: in some "Tokyo Marathon training plan" the bigram "Tokyo Marathon" is far more salient than the bigram "Marathon training". WSDM replaces the three global `λ` with per-feature weights driven by simple importance features (term IDF, query log popularity, Wikipedia presence). The auto-tuner can learn which term pairs deserve the proximity bonus. Complements FR-108 as a per-pair refinement and complements FR-018 because the per-feature-weight regression is exactly the kind of small linear-model problem the auto-tuner already handles.

## Academic source
**Bendersky, Michael; Metzler, Donald; Croft, W. Bruce (2010).** "Learning Concept Importance Using a Weighted Dependence Model." *Proceedings of the Third ACM International Conference on Web Search and Data Mining (WSDM 2010)*, pp. 31-40. DOI: `10.1145/1718487.1718492`.

## Formula
From Bendersky, Metzler, Croft (2010), Eq. 1 (weighted sequential dependence):

```
WSDM(Q, D) = Σ_{q ∈ Q}        w_T(q)        · log f_T(q, D)
           + Σ_{q_i, q_{i+1}} w_O(q_i q_{i+1}) · log f_O(q_i q_{i+1}, D)
           + Σ_{q_i, q_{i+1}} w_U(q_i q_{i+1}) · log f_U(q_i q_{i+1}, D)

w_T(q)        = Σ_φ  λ_T,φ · φ(q)         (linear combination of term importance features)
w_O(b)        = Σ_φ  λ_O,φ · φ(b)         (same for ordered bigram b)
w_U(b)        = Σ_φ  λ_U,φ · φ(b)         (same for unordered bigram b)
```

Where:
- `f_T`, `f_O`, `f_U` are the same Dirichlet-smoothed feature scores as in SDM (FR-108)
- `φ(·)` are concept-importance features. Paper §4.1 uses (with their numeric defaults):
  - `φ_idf(q) = log( (N + 1) / df(q) )`
  - `φ_qlogcf(q) = log( 1 + qf_QueryLog(q) )`
  - `φ_wiki(q) = log( 1 + qf_Wikipedia(q) )`
  - constant bias `1`
- `λ_T,φ`, `λ_O,φ`, `λ_U,φ` are learned coefficients (paper Table 4); for our cold start, default to SDM equivalence: `λ_T,bias = 0.85`, `λ_O,bias = 0.10`, `λ_U,bias = 0.05`, all other `λ = 0`

## Starting weight preset
```python
"wsdm.enabled": "true",
"wsdm.ranking_weight": "0.0",
"wsdm.lambda_T_bias": "0.85",
"wsdm.lambda_O_bias": "0.10",
"wsdm.lambda_U_bias": "0.05",
"wsdm.lambda_T_idf": "0.0",
"wsdm.lambda_O_idf": "0.0",
"wsdm.lambda_U_idf": "0.0",
"wsdm.mu": "2500",
"wsdm.uw_window": "8",
```

## C++ implementation
- File: `backend/extensions/wsdm.cpp`
- Entry: `double wsdm_score(const uint32_t* query_term_ids, int n, const PositionalDoc& doc, const CorpusStats& corp, const WsdmCoeffs& coeffs);`
- Complexity: `O(|Q|·F + (|Q|−1)·F + (|Q|−1)·|D|)` where `F` = number of importance features (small constant ~4); dominated by the `|D|` proximity scan
- Thread-safety: pure function
- SIMD: `#pragma omp simd reduction(+:score)` over feature vector dot-products
- Builds against pybind11; reuses `sdm.cpp` proximity primitives

## Python fallback
`backend/apps/pipeline/services/wsdm.py::score_wsdm(...)`.

## Benchmark plan
| Candidates | C++ target | Python target |
|---|---|---|
| 10 | < 0.6 ms | < 6 ms |
| 100 | < 3.5 ms | < 35 ms |
| 500 | < 14 ms | < 175 ms |

## Diagnostics
- Per-component score (`T`, `O`, `U`)
- Per-pair learned weight values
- C++ vs Python badge
- Which features fired for each weight (e.g. "Tokyo Marathon: idf=4.2, wiki=8.1")

## Edge cases & neutral fallback
- All `λ` zero → reduces to SDM with `λ_T = λ_O = λ_U = 0`; ranking falls back to constant
- Missing concept feature (e.g. no Wikipedia data) → that feature contributes 0
- Negative learned weight → clipped at 0 to keep monotonicity, flag `weight_clipped`
- `|D| = 0` → 0.0, flag `empty_doc`
- Missing corpus stats → neutral 0.5, flag `no_corpus_stats`
- NaN / Inf → 0.0, flag `nan_clamped`

## Minimum-data threshold
Same as SDM (corpus ≥ 100 docs, positional data); plus at least one active concept feature with non-zero learned weight, otherwise reduce silently to FR-108 SDM defaults.

## Budget
Disk: <2 MB  ·  RAM: <20 MB

## Scope boundary vs existing signals
FR-109 does NOT duplicate FR-108 SDM because the `λ` are per-pair (a function of importance features), not global. It complements FR-018 because the per-feature `λ` coefficients are themselves learnable; the auto-tuner can regress them from observed CTR.

## Test plan bullets
- unit tests: zero coefficients (constant score), single-feature, multi-feature
- parity test: C++ vs Python within `1e-4`
- limit check: `λ_T_bias = 0.85, λ_O_bias = 0.10, λ_U_bias = 0.05`, others zero, exactly recovers SDM
- no-crash test on adversarial input (negative `λ`, missing feature)
- integration test: ranking unchanged when `ranking_weight = 0.0`
