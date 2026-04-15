# FR-103 - DFR DPH (Hypergeometric, Parameter-Free)

## Overview
DPH is the parameter-free instance of the DFR family: no `c`, no `b`, no `k₁`. It uses a hypergeometric basic model (sampling-without-replacement view of term occurrence in a finite corpus) and a normalisation derived from the document's relative term-frequency. The lack of tuning knobs makes it the safest default fallback when the FR-018 auto-tuner has not yet converged. Complements FR-101 and FR-102 because DPH gives an out-of-the-box ranking baseline without operator intervention.

## Academic source
**Amati, Gianni; Ambrosi, Edgardo; Bianchi, Marco; Gaibisso, Carlo; Gambosi, Giorgio (2007).** "FUB, IASI-CNR and University of Tor Vergata at TREC 2007 Blog Track." *Sixteenth Text REtrieval Conference (TREC 2007 Notebook)*. NIST Special Publication 500-274. The DPH formula was first published in: **Amati (2006).** "Frequentist and Bayesian Approach to Information Retrieval." *Advances in Information Retrieval (ECIR 2006)*, LNCS 3936, pp. 13-24. DOI: `10.1007/11735106_3`.

## Formula
From Amati (2006), Eq. for DPH (also reproduced in FUB TREC 2007 §3.2):

```
norm(q,D) = (1 − f(q,D))²  /  (tf(q,D) + 1)

f(q,D) = tf(q,D) / |D|

DPH(q,D) = norm(q,D) · [
  tf(q,D) · log₂( (tf(q,D) · avgdl / |D|) · (N / F(q)) )
  + 0.5 · log₂( 2π · tf(q,D) · (1 − f(q,D)) )
]

DPH(Q,D) = Σ_{q ∈ Q}  qtf(q,Q) · DPH(q,D)
```

Where:
- `tf(q,D)` = term frequency in doc; `f(q,D)` = relative term frequency
- `|D|`, `avgdl` as before
- `F(q)` = total occurrences of `q` in corpus, `N` = total documents
- No tunable hyperparameters — all constants come from the hypergeometric derivation
- Stirling tail `0.5·log₂(2π·tf·(1−f))` corrects the binomial approximation

## Starting weight preset
```python
"dfr_dph.enabled": "true",
"dfr_dph.ranking_weight": "0.0",
# no other knobs - DPH is parameter-free by design
```

## C++ implementation
- File: `backend/extensions/dfr_dph.cpp`
- Entry: `double dfr_dph_score(const uint32_t* query_term_ids, int n, const DocStats& doc, const CorpusStats& corp);`
- Complexity: `O(|Q|)` per (query, doc); ~10 FP ops per term
- Thread-safety: pure function
- SIMD: `#pragma omp simd reduction(+:score)`
- Builds against pybind11 like FR-099

## Python fallback
`backend/apps/pipeline/services/dfr_dph.py::score_dfr_dph(...)`.

## Benchmark plan
| Candidates | C++ target | Python target |
|---|---|---|
| 10 | < 0.06 ms | < 0.6 ms |
| 100 | < 0.3 ms | < 6 ms |
| 500 | < 1.2 ms | < 30 ms |

## Diagnostics
- Raw DPH score and per-term contributions
- C++ vs Python badge
- `f(q,D)` per query term so operators can see which terms saturated the document
- Norm factor `(1−f)²/(tf+1)` per term

## Edge cases & neutral fallback
- `tf = 0` → term contributes 0
- `f = 1` (term is the entire document) → `norm = 0`, term contributes 0
- `tf = 1` and `f → 0` → Stirling tail dominates; clamped to 0 if log argument ≤ 0
- `F(q) = 0` (term unseen) → term contributes 0, flag `unseen_term`
- `|D| = 0` → 0.0, flag `empty_doc`
- Missing corpus stats → neutral 0.5, flag `no_corpus_stats`
- NaN / Inf → 0.0, flag `nan_clamped`

## Minimum-data threshold
≥ 50 documents before the hypergeometric mean is well-defined; below this returns neutral 0.5.

## Budget
Disk: <1 MB  ·  RAM: <5 MB

## Scope boundary vs existing signals
FR-103 does NOT duplicate FR-101 PL2 or FR-102 InL2 because DPH uses a hypergeometric (without-replacement) basic model rather than Poisson or `I(n)`, and has zero tunables. It complements FR-018 by being the safest "no-ops-yet" baseline DFR scorer.

## Test plan bullets
- unit tests: zero overlap, rare-term-only, common-term-only, single-term, all-tokens-are-q
- parity test: C++ vs Python within `1e-4`
- no-crash test on adversarial input (`tf = |D|`, `tf = 1`, huge `F(q)`)
- integration test: ranking unchanged when `ranking_weight = 0.0`
- parameter-free check: source code exposes no tunable knob
