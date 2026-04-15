# FR-159 — Yule's K (Lexical Concentration)

## Overview
Yule's K is a length-independent measure of how concentrated vocabulary is on a few word forms. Low-K destinations use varied vocabulary (rich content); high-K destinations repeat the same words endlessly (filler, spam). It is one of the oldest and most stable lexical-richness measures. Complements `fr160-mtld-lexical-diversity` because Yule's K is concentration-based and MTLD is window-based; the two are weakly correlated.

## Academic source
Full citation: **Yule, G. U. (1944).** *The Statistical Study of Literary Vocabulary*. Cambridge University Press, Cambridge. Chapter 2, "Vocabulary as a Statistical Universe", pp. 7-65. Reprinted (2014). DOI: `10.1017/CBO9781107415324.003`.

## Formula
Yule (1944), Equation 2.4, defines K from the frequency spectrum:

```
K = 10⁴ · (M_2 − M_1) / M_1²

where
  M_1   = Σ_i  i · V_i   = total tokens N
  M_2   = Σ_i  i² · V_i
  V_i   = number of distinct word types occurring exactly i times
```

K is independent of text length (proved in Yule 1944 §2.3). Typical English values: 80-120 for varied prose, > 200 for repetitive content.

## Starting weight preset
```python
"yule_k.enabled": "true",
"yule_k.ranking_weight": "0.0",
"yule_k.target_max": "150.0",
"yule_k.penalty_above": "250.0",
```

## C++ implementation
- File: `backend/extensions/yule_k.cpp`
- Entry: `double yule_k(const std::vector<uint32_t>& token_ids)`
- Complexity: O(n + V) where V = unique types; uses `absl::flat_hash_map` for type counts then iterates frequency-of-frequencies
- Thread-safety: pure
- Builds via pybind11

## Python fallback
`backend/apps/pipeline/services/yule_k.py::compute_yule_k` using `collections.Counter` twice (types then frequency-of-frequencies).

## Benchmark plan

| Size | Tokens | C++ target | Python target |
|---|---|---|---|
| Small | 200 | 0.05 ms | 0.4 ms |
| Medium | 2,000 | 0.4 ms | 4 ms |
| Large | 20,000 | 4 ms | 45 ms |

## Diagnostics
- Raw value "Yule K: 95.4"
- C++/Python badge
- Fallback flag
- Debug fields: `n_tokens`, `n_types`, `top_5_repeated_words`

## Edge cases & neutral fallback
- Empty doc → neutral 0.5
- Single-token doc → K = 0
- All-unique-tokens doc → K = 0 (no repetition); maps to high quality
- Stopwords removed before computation (improves discriminative power per Yule §3)
- Numeric token IDs from canonical lemmatised form; case-insensitive

## Minimum-data threshold
At least 50 content tokens after stopword removal; below that return neutral 0.5.

## Budget
Disk: 0.05 MB  ·  RAM: 1.0 MB (hash map for large docs)

## Scope boundary vs existing signals
Distinct from `fr160-mtld-lexical-diversity` (window-based diversity) and `fr161-punctuation-entropy` (non-lexical). K is a frequency-spectrum concentration metric — independent in design and intent.

## Test plan bullets
- Unit: doc with all unique tokens returns K = 0
- Unit: doc "the the the the the" returns K = 10⁴ · (25−5)/25 = 8000
- Parity: C++ vs Python within 1e-6
- Edge: empty doc returns 0.5 with fallback flag
- Edge: single token returns 0 cleanly (no NaN)
- Integration: contributes only when enabled
- Regression: ranking unchanged when weight = 0.0
