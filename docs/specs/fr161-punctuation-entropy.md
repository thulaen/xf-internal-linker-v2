# FR-161 — Punctuation Entropy

## Overview
Posts that mix periods, commas, question marks, semicolons, and parentheses tend to be more carefully written than ones with a single punctuation type (e.g. all periods or all exclamation marks). Shannon entropy over the punctuation distribution is a cheap stylometric prior used in authorship attribution and quality scoring. Complements `fr157-part-of-speech-diversity` because POS entropy measures content-word variety while punctuation entropy measures structural variety.

## Academic source
Full citation: **Shannon, C. E. (1948).** "A Mathematical Theory of Communication." *The Bell System Technical Journal*, 27(3), 379-423. DOI: `10.1002/j.1538-7305.1948.tb01338.x`. Stylometric application: **Stamatatos, E. (2009).** "A Survey of Modern Authorship Attribution Methods." *Journal of the American Society for Information Science and Technology*, 60(3), 538-556. DOI: `10.1002/asi.21001`, §3.1.

## Formula
Stamatatos (2009) §3.1 applies Shannon's classic formula (Shannon 1948, Theorem 2) over the punctuation symbol distribution:

```
PunctEntropy(d) = − Σ_{p ∈ P}  q_p · log_2(q_p)

where
  P   = punctuation inventory { . , ; : ! ? - — ( ) " ' / }
  q_p = N_p(d) / N_punct(d)  = relative frequency of punctuation p
  N_punct(d) = total punctuation tokens in d
```

Theoretical maximum H_max = log_2(13) ≈ 3.70. Stamatatos reports natural English averages 2.0-2.6 bits.

## Starting weight preset
```python
"punct_entropy.enabled": "true",
"punct_entropy.ranking_weight": "0.0",
"punct_entropy.target_entropy": "2.3",
```

## C++ implementation
- File: `backend/extensions/punct_entropy.cpp`
- Entry: `double punct_entropy(const std::string_view& raw_text)`
- Complexity: O(n) over raw bytes; lookup table of size 256 maps each byte to punct-class (0-12) or skip
- Thread-safety: pure; lookup table is constexpr
- SIMD: AVX2 byte-class counting via `_mm256_shuffle_epi8`
- Builds via pybind11

## Python fallback
`backend/apps/pipeline/services/punct_entropy.py::compute_punct_entropy` using `collections.Counter` over filtered punctuation chars.

## Benchmark plan

| Size | Bytes | C++ target | Python target |
|---|---|---|---|
| Small | 1 KB | 0.005 ms | 0.2 ms |
| Medium | 10 KB | 0.04 ms | 1.8 ms |
| Large | 100 KB | 0.4 ms | 18 ms |

## Diagnostics
- Raw value "Punct H: 2.31 bits"
- C++/Python badge
- Fallback flag
- Debug fields: `top_3_punct`, `n_unique_punct`, `dominant_share`

## Edge cases & neutral fallback
- Doc with no punctuation → entropy 0 → fallback flag, neutral 0.5
- Doc with only one type (e.g. all periods) → entropy 0
- Code blocks excluded (operator chars would inflate entropy)
- Unicode dashes (— …) handled via UTF-8 NFC normalisation upstream

## Minimum-data threshold
At least 20 punctuation tokens required; below that return neutral 0.5.

## Budget
Disk: 0.01 MB  ·  RAM: 0.05 MB

## Scope boundary vs existing signals
Distinct from `fr157-part-of-speech-diversity` (content-word POS) and `fr155-discourse-connective-density` (lexical connectives). Punctuation entropy is the only signal that examines purely non-alphabetic tokens.

## Test plan bullets
- Unit: doc with 5 punct types in equal counts returns log_2(5) ≈ 2.32
- Unit: doc with all periods returns 0.0
- Parity: C++ vs Python within 1e-6
- Edge: empty doc returns 0.5 with fallback flag
- Edge: code-block punctuation excluded correctly
- Integration: contributes only when enabled
- Regression: ranking unchanged when weight = 0.0
