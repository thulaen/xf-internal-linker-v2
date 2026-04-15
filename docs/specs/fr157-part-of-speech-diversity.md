# FR-157 — Part-of-Speech Diversity Entropy

## Overview
A destination that uses a balanced mix of nouns, verbs, adjectives, and adverbs reads more naturally than one dominated by one POS class (e.g. all nouns = catalog page; all verbs = command list). Shannon entropy over the POS-tag distribution gives a single-number quality prior. Complements `fr159-yule-k-lexical-concentration` because Yule's K measures word-form diversity while POS entropy measures grammatical diversity.

## Academic source
Full citation: **Biber, D. (1988).** *Variation across Speech and Writing*. Cambridge University Press, Cambridge. ISBN: 978-0-521-32294-7. Chapter 4, "Methodology", pp. 73-101. DOI: `10.1017/CBO9780511621024`.

## Formula
Biber (1988), Table 4.1, defines POS variation as Shannon entropy over the tag distribution:

```
POSEntropy(d) = − Σ_{t ∈ T}  p_t · log_2(p_t)

where
  T   = POS-tag inventory (Penn Treebank, 36 tags)
  p_t = N_t(d) / N_token(d)  = relative frequency of tag t
  N_t(d)     = count of tokens tagged t in d
  N_token(d) = total tagged tokens in d
```

Theoretical maximum H_max = log_2(36) ≈ 5.17. Biber reports natural English averages 3.8-4.4.

## Starting weight preset
```python
"pos_diversity.enabled": "true",
"pos_diversity.ranking_weight": "0.0",
"pos_diversity.target_entropy": "4.0",
```

## C++ implementation
- File: `backend/extensions/pos_entropy.cpp`
- Entry: `double pos_entropy(const std::vector<uint8_t>& tag_ids, size_t n_tags)`
- Complexity: O(n + k) where k = 36 tags; one pass to count, one over tag table to sum
- Thread-safety: pure
- SIMD: histogram counting via 4 interleaved accumulators (avoids data dependency)
- Builds via pybind11

## Python fallback
`backend/apps/pipeline/services/pos_entropy.py::compute_pos_entropy` using `collections.Counter` + `math.log2`.

## Benchmark plan

| Size | Tokens | C++ target | Python target |
|---|---|---|---|
| Small | 200 | 0.04 ms | 0.6 ms |
| Medium | 2,000 | 0.3 ms | 5 ms |
| Large | 20,000 | 3 ms | 50 ms |

## Diagnostics
- Raw entropy "POS H: 4.12 bits"
- C++/Python badge
- Fallback flag
- Debug fields: `top_3_tags`, `n_unique_tags`, `dominant_tag_share`

## Edge cases & neutral fallback
- Empty doc → neutral 0.5
- Single-tag doc (e.g. all nouns) → entropy 0.0 → maps to penalty
- Non-English / no POS tagger → fallback to neutral 0.5
- Tag IDs ≥ 36 ignored (defensive)

## Minimum-data threshold
At least 30 tagged tokens required; below that return neutral 0.5.

## Budget
Disk: 0.05 MB  ·  RAM: 0.2 MB

## Scope boundary vs existing signals
Different from `fr153-nominalization-density` (specific noun derivations) and `fr152-passive-voice-ratio` (specific verb construction). POS entropy is a global tag-distribution measure, not a class-specific count.

## Test plan bullets
- Unit: balanced POS doc returns entropy ≈ 4.0
- Unit: all-nouns doc returns entropy 0.0
- Parity: C++ vs Python within 1e-6
- Edge: single-tag input returns 0.0 cleanly
- Edge: empty input returns 0.5 with fallback flag
- Integration: contributes only when enabled
- Regression: ranking unchanged when weight = 0.0
