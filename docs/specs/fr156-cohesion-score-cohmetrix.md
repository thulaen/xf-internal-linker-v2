# FR-156 — Cohesion Score (Coh-Metrix LSA)

## Overview
Coh-Metrix measures how well adjacent sentences "stick together" semantically. A destination whose paragraphs flow coherently is easier to read and earns more anchor click-through than a choppy one. We use the LSA-cosine variant which is the strongest single Coh-Metrix predictor of comprehension. Complements `fr155-discourse-connective-density` because connectives mark explicit links while cohesion captures implicit topical continuity.

## Academic source
Full citation: **Graesser, A. C., McNamara, D. S., Louwerse, M. M. & Cai, Z. (2004).** "Coh-Metrix: Analysis of text on cohesion and language." *Behavior Research Methods, Instruments, & Computers*, 36(2), 193-202. DOI: `10.3758/BF03195564`.

## Formula
Graesser et al. (2004), Equation 6 (LSA Adjacent Sentence Cohesion):

```
LSAcohesion(d) = (1 / (N_sent − 1)) · Σ_{i=1..N_sent−1}  cos(v_i, v_{i+1})

where
  v_i        = sum of LSA word vectors for content words in sentence i
  cos(a, b)  = (a · b) / (‖a‖ · ‖b‖)
  N_sent     = number of sentences in d
```

Coh-Metrix paper reports mean cohesion of 0.20 for narrative and 0.35 for expository text on the TASA corpus.

## Starting weight preset
```python
"cohesion.enabled": "true",
"cohesion.ranking_weight": "0.0",
"cohesion.embedding_dim": "300",
"cohesion.target_value": "0.30",
```

## C++ implementation
- File: `backend/extensions/cohesion.cpp`
- Entry: `double lsa_cohesion(const std::vector<std::vector<float>>& sentence_vecs)`
- Complexity: O(N_sent · d) where d = 300; O(n·300) total since vectors are precomputed
- Thread-safety: pure; relies on caller-supplied vectors
- SIMD: AVX2 dot-product on 8-float lanes; 30× over scalar
- Builds via pybind11

## Python fallback
`backend/apps/pipeline/services/cohesion.py::compute_lsa_cohesion` using `numpy` and the existing 300-dim sentence-embedding cache.

## Benchmark plan

| Size | Sentences | C++ target | Python target |
|---|---|---|---|
| Small | 10 | 0.02 ms | 0.5 ms |
| Medium | 100 | 0.18 ms | 4 ms |
| Large | 1,000 | 1.8 ms | 40 ms |

## Diagnostics
- Raw value "Cohesion: 0.31"
- C++/Python badge
- Fallback flag
- Debug fields: `min_pair_cosine`, `max_pair_cosine`, `n_sentence_pairs`

## Edge cases & neutral fallback
- Document with 1 sentence → no pairs → neutral 0.5
- Zero-norm vector (all stopwords) → skip pair, do not include in mean
- Non-English (no LSA model) → fallback to neutral 0.5
- Code-only post → skip signal

## Minimum-data threshold
At least 3 sentences required; below that return neutral 0.5.

## Budget
Disk: 0 MB (reuses existing embedding cache)  ·  RAM: 0.5 MB working buffer

## Scope boundary vs existing signals
Different from `fr011-field-aware-relevance-scoring` (query-doc match) and `fr156` ranks destination internal coherence, not query-relevance. No overlap with `fr029-gpu-embedding-pipeline-fp16` which produces document-level embeddings; this signal works on per-sentence vectors.

## Test plan bullets
- Unit: doc with two identical sentences returns ≈ 1.0
- Unit: doc with two orthogonal sentences returns ≈ 0.0
- Parity: C++ vs Python within 1e-5 (FP rounding tolerance)
- Edge: single-sentence doc returns neutral 0.5
- Edge: zero-norm sentence skipped, mean recomputed correctly
- Integration: signal contributes when enabled
- Regression: ranking unchanged when weight = 0.0
