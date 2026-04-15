# FR-160 — MTLD (Measure of Textual Lexical Diversity)

## Overview
MTLD measures how long a text can run before its type-token-ratio (TTR) drops below a fixed threshold (default 0.72). Unlike raw TTR, MTLD is robust to text length — McCarthy & Jarvis showed it stays stable from 100-2000 tokens. It is a strong destination-quality prior for forum posts of varied length. Complements `fr159-yule-k-lexical-concentration` because Yule's K is concentration-based (frequency spectrum) and MTLD is sequence-based (TTR walk).

## Academic source
Full citation: **McCarthy, P. M. & Jarvis, S. (2010).** "MTLD, vocd-D, and HD-D: A validation study of sophisticated approaches to lexical diversity assessment." *Behavior Research Methods*, 42(2), 381-392. DOI: `10.3758/BRM.42.2.381`.

## Formula
McCarthy & Jarvis (2010), §2.2, define MTLD as the average number of tokens per "factor" — a factor ends when running TTR falls to threshold τ = 0.72:

```
forward_factors = walk left→right; each time TTR drops to τ, increment factor
                  count and reset; partial last factor weighted by
                  (1 − TTR_partial) / (1 − τ)
MTLD_forward    = N / forward_factors

reverse_factors = same walk right→left
MTLD_reverse    = N / reverse_factors

MTLD = (MTLD_forward + MTLD_reverse) / 2
```

Higher MTLD = more lexical diversity. McCarthy & Jarvis report 80-110 for student essays and 60-80 for repetitive prose.

## Starting weight preset
```python
"mtld.enabled": "true",
"mtld.ranking_weight": "0.0",
"mtld.ttr_threshold": "0.72",
"mtld.target_min": "60.0",
```

## C++ implementation
- File: `backend/extensions/mtld.cpp`
- Entry: `double mtld(const std::vector<uint32_t>& token_ids, double ttr_threshold = 0.72)`
- Complexity: O(n) with rolling hashset insertions; both forward and reverse passes
- Thread-safety: pure; uses thread-local scratch hashset
- Builds via pybind11

## Python fallback
`backend/apps/pipeline/services/mtld.py::compute_mtld` using set + integer counters.

## Benchmark plan

| Size | Tokens | C++ target | Python target |
|---|---|---|---|
| Small | 200 | 0.07 ms | 0.8 ms |
| Medium | 2,000 | 0.6 ms | 7 ms |
| Large | 20,000 | 6 ms | 70 ms |

## Diagnostics
- Raw value "MTLD: 78.4"
- Forward and reverse values shown separately in debug
- C++/Python badge
- Fallback flag
- Debug fields: `n_factors_forward`, `n_factors_reverse`, `partial_weight`

## Edge cases & neutral fallback
- Document shorter than 50 tokens → MTLD undefined → neutral 0.5
- Document where TTR never drops to 0.72 (rare, only first 20 tokens) → MTLD = N (max diversity)
- Stopwords kept (per McCarthy & Jarvis recommendation §3.1)
- Tokens lowercased and lemmatised before running

## Minimum-data threshold
At least 50 tokens required (below this MTLD is unstable per McCarthy & Jarvis §4.3).

## Budget
Disk: 0.05 MB  ·  RAM: 0.6 MB (hashset for large docs)

## Scope boundary vs existing signals
Distinct from `fr159-yule-k-lexical-concentration` (frequency-spectrum based) and `fr157-part-of-speech-diversity` (POS-tag entropy). MTLD is a sequential-walk TTR metric only.

## Test plan bullets
- Unit: 200 unique tokens → MTLD = 200 (TTR never drops)
- Unit: alternating "a b a b a b ..." token stream → low MTLD
- Parity: C++ vs Python within 1e-6
- Edge: 49-token doc returns 0.5 with fallback flag
- Edge: TTR drops at exactly the threshold handled correctly
- Integration: contributes only when enabled
- Regression: ranking unchanged when weight = 0.0
