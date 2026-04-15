# FR-152 — Passive-Voice Ratio

## Overview
Forum threads written in heavy passive voice ("the post was edited", "the thread was closed") tend to read as bureaucratic, less engaging, and less suitable as link destinations than active-voice prose. Measuring the passive-voice fraction of a candidate destination gives the ranker a cheap stylistic prior on writing quality. Complements `fr156-cohesion-score-cohmetrix` because cohesion measures inter-sentence coupling while passive ratio measures intra-sentence agency.

## Academic source
Full citation: **Hundt, M. & Mair, C. (2004).** "Agile and uptight genres: The corpus-based approach to language change in progress." *International Journal of Corpus Linguistics*, 4(2), 221-242. DOI: `10.1075/ijcl.4.2.02hun`.

## Formula
From Hundt & Mair (2004), Section 3, the passive-voice ratio for a document is computed as the count of finite passive constructions normalised by the total number of finite verbal clauses:

```
PassiveRatio(d) = N_passive(d) / N_finite(d)

where
  N_passive(d) = #{ (aux, vbn) : aux ∈ {be, get} ∧ vbn ∈ past-participle }
  N_finite(d)  = total finite verb clauses in d
```

A neutral baseline of 0.20 is reported across written English registers; values above 0.40 mark dense bureaucratic style.

## Starting weight preset
```python
"passive_voice.enabled": "true",
"passive_voice.ranking_weight": "0.0",
"passive_voice.target_ratio": "0.20",
"passive_voice.penalty_above": "0.40",
```

## C++ implementation
- File: `backend/extensions/passive_voice.cpp`
- Entry: `double passive_voice_ratio(const std::vector<Token>& tokens)`
- Complexity: O(n) over tokens; single pass with a 2-token sliding window
- Thread-safety: pure function on input slice; no shared state
- Builds via pybind11; uses precomputed POS-tag enum (no Python re-tokenisation)

## Python fallback
`backend/apps/pipeline/services/passive_voice.py::compute_passive_ratio` using spaCy's `tag_` field to detect `VBN` preceded by `be/get` aux.

## Benchmark plan

| Size | Tokens | C++ target | Python target |
|---|---|---|---|
| Small | 200 | 0.05 ms | 1.5 ms |
| Medium | 2,000 | 0.4 ms | 12 ms |
| Large | 20,000 | 4 ms | 120 ms |

## Diagnostics
- Raw passive ratio in suggestion detail UI (e.g. "Passive: 0.18")
- C++/Python badge
- Fallback flag when POS tags missing
- Debug fields: `n_passive`, `n_finite`, `aux_lemma_breakdown`

## Edge cases & neutral fallback
- Document with zero finite verbs → neutral 0.5, fallback flag set
- Single-sentence destinations < 5 tokens → skip signal
- Imperatives ("post your reply") miscounted as zero verbs → tolerated
- Quoted text inside `<blockquote>` excluded from numerator and denominator

## Minimum-data threshold
Need at least 10 finite verbal clauses before signal contributes; otherwise fall back to neutral 0.5.

## Budget
Disk: 0.2 MB  ·  RAM: 0.5 MB

## Scope boundary vs existing signals
Does not duplicate `fr011-field-aware-relevance-scoring` (lexical match) or `fr034-link-context-quality-audit` (anchor surroundings). Passive ratio is a destination-side stylometric prior, not a query-document or anchor-window measure.

## Test plan bullets
- Unit: synthetic doc "X was edited by Y" returns 1.0
- Unit: synthetic doc "Y edited X" returns 0.0
- Parity: C++ vs Python on 1,000 forum posts within 1e-6
- Edge: empty doc returns 0.5 with fallback flag
- Edge: doc with only nominal sentences returns 0.5
- Integration: signal contributes after weight tune; deterministic across runs
- Regression: top-50 ranking unchanged when weight = 0.0
