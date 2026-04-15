# FR-158 — Sentence-Length Variance

## Overview
Posts that mix short and long sentences read more naturally than monotone walls of text. The standard deviation of sentence length is a strong proxy for rhythm and pacing — Crossley et al. found it among the top-5 readability features. Complements `fr157-part-of-speech-diversity` because POS entropy captures grammatical variety while sentence variance captures rhythmic variety.

## Academic source
Full citation: **Crossley, S. A., Skalicky, S., Dascalu, M., McNamara, D. S. & Kyle, K. (2019).** "Predicting text comprehension, processing, and familiarity in adult readers: New approaches to readability formulas." *Discourse Processes*, 56(7), 540-561. DOI: `10.1080/0163853X.2019.1646440`. Also covered in: Crossley, S. A. (2020). "Linguistic features in writing quality and development." *Readability Research: An Interdisciplinary Approach* (Routledge).

## Formula
Crossley et al. (2019), Equation 2, define sentence-length variance σ² and the derived dispersion ratio CV used as the ranker input:

```
μ_L  = (1 / N_sent) · Σ_i  L_i
σ²_L = (1 / N_sent) · Σ_i  (L_i − μ_L)²
CV   = σ_L / μ_L              (coefficient of variation)

where
  L_i    = token count of sentence i
  N_sent = number of sentences in d
```

The coefficient of variation `CV` is dimensionless; Crossley reports `CV` ≈ 0.45 for high-rated forum prose vs ≈ 0.20 for monotone low-quality prose.

## Starting weight preset
```python
"sent_variance.enabled": "true",
"sent_variance.ranking_weight": "0.0",
"sent_variance.target_cv": "0.45",
```

## C++ implementation
- File: `backend/extensions/sentence_variance.cpp`
- Entry: `double sentence_cv(const std::vector<uint16_t>& sentence_lengths)`
- Complexity: O(n) one-pass Welford's algorithm for mean + variance (numerically stable)
- Thread-safety: pure
- Builds via pybind11

## Python fallback
`backend/apps/pipeline/services/sentence_variance.py::compute_sentence_cv` using `statistics.pstdev`.

## Benchmark plan

| Size | Sentences | C++ target | Python target |
|---|---|---|---|
| Small | 10 | 0.005 ms | 0.05 ms |
| Medium | 100 | 0.04 ms | 0.5 ms |
| Large | 1,000 | 0.4 ms | 5 ms |

## Diagnostics
- Raw value "Sent CV: 0.42"
- Mean and stddev separately in debug payload
- C++/Python badge
- Fallback flag

## Edge cases & neutral fallback
- Single sentence → variance 0; CV undefined → neutral 0.5
- All sentences identical length → CV 0.0 → low score
- Mean = 0 (impossible if N_sent > 0) defensive divide-by-zero check
- Non-English unaffected (operates on token counts)

## Minimum-data threshold
At least 5 sentences required; below that return neutral 0.5.

## Budget
Disk: 0.02 MB  ·  RAM: 0.05 MB

## Scope boundary vs existing signals
No overlap with `fr157-part-of-speech-diversity` (POS distribution) or `fr156-cohesion-score-cohmetrix` (semantic continuity). Sentence variance is a structural rhythm metric only.

## Test plan bullets
- Unit: sentences [5,5,5,5,5] returns CV = 0.0
- Unit: sentences [3,15,7,22,4] returns CV ≈ 0.78
- Parity: C++ Welford vs Python statistics within 1e-9
- Edge: single sentence returns 0.5 with fallback flag
- Edge: zero-length sentence treated as 0 token count
- Integration: contributes only when enabled
- Regression: ranking unchanged when weight = 0.0
