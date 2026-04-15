# FR-105 - Two-Stage Language Model Smoothing

## Overview
Single-stage Dirichlet or Jelinek-Mercer smoothing forces one parameter to handle two distinct tasks: estimating an unseen-term probability and matching the query style. The Two-Stage LM separates them: stage-1 Dirichlet smoothing absorbs corpus mass to estimate the document model `p(w|D)`, then stage-2 Jelinek-Mercer smoothing mixes that with a query-background model `p(w|U)`. Complements FR-011 / FR-099 by adding a probabilistic-LM scorer with explicit per-stage explainability.

## Academic source
**Zhai, ChengXiang and Lafferty, John (2002).** "Two-Stage Language Models for Information Retrieval." *Proceedings of the 25th Annual International ACM SIGIR Conference on Research and Development in Information Retrieval (SIGIR 2002)*, pp. 49-56. DOI: `10.1145/564376.564387`. (Companion CIKM 2002 paper "A Study of Smoothing Methods for Language Models Applied to Ad Hoc Information Retrieval", DOI: `10.1145/584792.584854`.)

## Formula
From Zhai & Lafferty (2002), Eq. 5 (two-stage smoothed document model):

```
p(w | D) = (tf(w,D) + μ · p(w|C)) / (|D| + μ)              (stage 1: Dirichlet)

p(w | D, U) = (1 − λ) · p(w|D) + λ · p(w|U)                (stage 2: JM mixing)

score(Q, D) = Σ_{w ∈ Q}  qtf(w,Q) · log p(w | D, U)
```

Where:
- `tf(w,D)`, `|D|`, `qtf(w,Q)` as before
- `p(w|C) = cf(w) / |C|` = collection model (corpus frequency / total tokens)
- `p(w|U)` = query-background model — for ad-hoc retrieval often = `p(w|C)` if no separate query log
- `μ > 0` = Dirichlet pseudo-count (default 2500 per paper §5.2)
- `λ ∈ [0, 1]` = Jelinek-Mercer mix weight (default 0.7 for short queries, 0.3 for long queries per paper Table 2)

The two-stage view says: `μ` is set by the corpus (long docs need less corpus mass), `λ` is set by query style (verbose queries need more background absorption).

## Starting weight preset
```python
"two_stage_lm.enabled": "true",
"two_stage_lm.ranking_weight": "0.0",
"two_stage_lm.mu": "2500",
"two_stage_lm.lambda_jm": "0.7",
```

## C++ implementation
- File: `backend/extensions/two_stage_lm.cpp`
- Entry: `double two_stage_lm_score(const uint32_t* query_term_ids, int n, const DocStats& doc, const CorpusStats& corp, double mu, double lambda_jm);`
- Complexity: `O(|Q|)` per (query, doc); per-term cost is one log + four FP ops
- Thread-safety: pure function
- SIMD: `#pragma omp simd reduction(+:score)`
- Builds against pybind11 like FR-099

## Python fallback
`backend/apps/pipeline/services/two_stage_lm.py::score_two_stage_lm(...)`.

## Benchmark plan
| Candidates | C++ target | Python target |
|---|---|---|
| 10 | < 0.05 ms | < 0.5 ms |
| 100 | < 0.2 ms | < 5 ms |
| 500 | < 1 ms | < 25 ms |

## Diagnostics
- Raw log-likelihood score
- C++ vs Python badge
- Per-term `p(w|D)` (stage-1) and final `p(w|D,U)` (stage-2)
- Effective `μ` and `λ` (after any auto-update)

## Edge cases & neutral fallback
- `tf(w,D) = 0` and `p(w|C) = 0` → log-arg ≤ 0; clamped at log(1e-20) and flagged `floor_clamped`
- `|D| = 0` → 0.0, flag `empty_doc`
- `μ = 0` → reduces to JM-only; not an error but flagged `mu_zero`
- Missing corpus stats → neutral 0.5, flag `no_corpus_stats`
- NaN / Inf → 0.0, flag `nan_clamped`

## Minimum-data threshold
≥ 100 documents so the collection model `p(w|C)` is meaningful; below this returns neutral 0.5.

## Budget
Disk: <2 MB  ·  RAM: <10 MB (collection-frequency table)

## Scope boundary vs existing signals
FR-105 does NOT duplicate FR-011 / FR-099 / FR-100 because it is a probabilistic LM scorer (sum of log probabilities), not a saturation-and-IDF heuristic. It complements FR-018 by giving the auto-tuner a feature that decomposes naturally into Dirichlet (`μ`) and JM (`λ`) tuning axes.

## Test plan bullets
- unit tests: zero overlap, common term only, rare term only, varying `μ`, varying `λ`
- parity test: C++ vs Python within `1e-4`
- limit checks: as `μ → 0` reduces to JM smoothing; as `μ → ∞` reduces to background only
- no-crash test on adversarial input (`p(w|C) = 0`, huge `μ`)
- integration test: ranking unchanged when `ranking_weight = 0.0`
