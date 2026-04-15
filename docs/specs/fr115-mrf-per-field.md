# FR-115 - Markov Random Field Per-Field Ranking

## Overview
SDM (FR-108) and FDM (FR-110) score the document as one bag of positions; field-aware BM25 (FR-011) scores per-field but ignores term dependence. Per-Field MRF combines both: each field (title, body, anchor text, headings) has its own SDM, with field-specific `λ_T,f`, `λ_O,f`, `λ_U,f` and field-specific Dirichlet `μ_f`. The per-field scores are linearly combined with field weights `w_f`. Critical for forum data where the post title and OP body are far more salient than reply bodies. Complements FR-011 because FR-011 is field-aware-BM25 only; FR-115 is field-aware-with-term-dependence.

## Academic source
**Huston, Samuel and Croft, W. Bruce (2014).** "A Comparison of Retrieval Models using Term Dependencies." *Proceedings of the 23rd ACM International Conference on Information and Knowledge Management (CIKM 2014)*, pp. 111-120. DOI: `10.1145/2661829.2661888`. (Companion to **Huston & Croft, SIGIR 2013** "Parameters Learned in the Comparison of Retrieval Models Using Term Dependencies," DOI: `10.1145/2484028.2484157`, where the per-field MRF is formalised in §3.)

## Formula
From Huston & Croft (2013), §3.2 (Per-Field Sequential Dependence Model):

```
For each field f ∈ F = {title, body, anchor, heading}:

  f_T,f(q, D)   = (tf_f(q, D) + μ_f · p(q | C_f)) / (|D_f| + μ_f)
  f_O,f(b, D)   = (tf_f,#1(b, D) + μ_f · p(b_#1 | C_f)) / (|D_f| + μ_f)
  f_U,f(b, D)   = (tf_f,#uwN(b, D) + μ_f · p(b_#uw | C_f)) / (|D_f| + μ_f)

  SDM_f(Q, D) = λ_T,f · Σ_{q ∈ Q}        log f_T,f(q, D)
              + λ_O,f · Σ_{q_i, q_{i+1}} log f_O,f(q_i q_{i+1}, D)
              + λ_U,f · Σ_{q_i, q_{i+1}} log f_U,f(q_i q_{i+1}, D)

PF-MRF(Q, D) = Σ_{f ∈ F}  w_f · SDM_f(Q, D)
```

Where:
- Each field `f` has its own document length `|D_f|`, posting list, collection model `p(·|C_f)`, and Dirichlet pseudo-count `μ_f`
- `λ_T,f + λ_O,f + λ_U,f = 1` per field; paper Table 3 gives field-specific defaults (title fields favour higher `λ_O`)
- `w_f ≥ 0` and `Σ w_f = 1`; paper §4 default for web data: `w_title = 0.4, w_body = 0.4, w_anchor = 0.15, w_heading = 0.05`
- Per-field `μ_f`: paper §4 sets `μ_title = 100, μ_body = 2500, μ_anchor = 500, μ_heading = 200`

## Starting weight preset
```python
"mrf_per_field.enabled": "true",
"mrf_per_field.ranking_weight": "0.0",
"mrf_per_field.fields": "title,body,anchor,heading",
"mrf_per_field.w_title": "0.4",
"mrf_per_field.w_body": "0.4",
"mrf_per_field.w_anchor": "0.15",
"mrf_per_field.w_heading": "0.05",
"mrf_per_field.lambda_T_title": "0.80",
"mrf_per_field.lambda_O_title": "0.15",
"mrf_per_field.lambda_U_title": "0.05",
"mrf_per_field.lambda_T_body": "0.85",
"mrf_per_field.lambda_O_body": "0.10",
"mrf_per_field.lambda_U_body": "0.05",
"mrf_per_field.mu_title": "100",
"mrf_per_field.mu_body": "2500",
"mrf_per_field.mu_anchor": "500",
"mrf_per_field.mu_heading": "200",
"mrf_per_field.uw_window": "8",
```

## C++ implementation
- File: `backend/extensions/mrf_per_field.cpp`
- Entry: `double mrf_per_field_score(const uint32_t* query_term_ids, int n, const FieldedPositionalDoc& doc, const PerFieldCorpusStats& corp, const PerFieldMrfCoeffs& coeffs);`
- Complexity: `O(F · (|Q| + (|Q|−1) · |D_f|))` where `F = number of fields`; reuses per-field positional postings already maintained for FR-011
- Thread-safety: pure function; per-field SDM evaluations are independent and OpenMP-parallel
- SIMD: same vectorisation as FR-108 SDM, applied per field
- Builds against pybind11 like FR-099

## Python fallback
`backend/apps/pipeline/services/mrf_per_field.py::score_mrf_per_field(...)`.

## Benchmark plan
| Candidates | C++ target | Python target |
|---|---|---|
| 10 | < 1 ms | < 10 ms |
| 100 | < 6 ms | < 60 ms |
| 500 | < 25 ms | < 300 ms |

(Per-field cost dominates; numbers assume `F = 4`.)

## Diagnostics
- Per-field SDM score and the field weight `w_f`
- Per-field `(λ_T, λ_O, λ_U)` and `μ_f`
- C++ vs Python badge
- Which fields contributed the most to the final score
- Per-component (`T`, `O`, `U`) breakdown per field

## Edge cases & neutral fallback
- Field absent from document (`|D_f| = 0`) → that field's SDM = 0; weight is renormalised across remaining fields, flag `field_missing`
- All fields missing → 0.0, flag `empty_doc`
- λ-sum per field ≠ 1 → renormalise per field, flag `lambda_renormalised`
- `Σ w_f ≠ 1` → renormalise, flag `w_renormalised`
- No positional data for a field → that field falls back to LM-only (`λ_T = 1` for that field), flag `no_positions_field:<f>`
- Missing per-field corpus stats → that field uses uniform `p(·|C_f) = 1/|C|`, flag `no_field_corpus_stats:<f>`
- NaN / Inf → 0.0, flag `nan_clamped`

## Minimum-data threshold
Per-field corpus stats require ≥ 50 documents with that field populated; below this the field is dropped and weight renormalised across remaining fields.

## Budget
Disk: <2 MB  ·  RAM: <25 MB (per-field positional postings + per-field collection-frequency tables)

## Scope boundary vs existing signals
FR-115 does NOT duplicate FR-011 field-aware BM25 because FR-011 has no term-dependence (`λ_O = λ_U = 0` implicitly); FR-115 is FR-108 SDM applied per field. It does not duplicate FR-108 SDM because SDM scores the unified document; FR-115 maintains a separate SDM per field with field-specific `λ` and `μ`.

## Test plan bullets
- unit tests: single-field document, all-fields-equal-content, missing-field handling
- parity test: C++ vs Python within `1e-4`
- limit checks: `w_body = 1` and other `w_f = 0` should reduce to FR-108 SDM on body field
- field-renormalisation test: dropping the title field rebalances weights across remaining fields and the score sum stays consistent
- no-crash test on adversarial input (every field empty, single-token field)
- integration test: ranking unchanged when `ranking_weight = 0.0`
