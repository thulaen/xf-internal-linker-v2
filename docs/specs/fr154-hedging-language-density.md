# FR-154 — Hedging Language Density

## Overview
Hedging words ("might", "perhaps", "it appears that", "to some extent") signal author uncertainty. Forum destinations packed with hedges are weaker authorities for an internal link than confident, declarative answers. A simple density score lets the ranker prefer assertive content. Complements `fr007-link-freshness-authority` because freshness measures recency while hedging density measures confidence.

## Academic source
Full citation: **Hyland, K. (1998).** *Hedging in Scientific Research Articles*. Pragmatics & Beyond New Series 54, John Benjamins, Amsterdam. ISBN: 978-90-272-5072-6. DOI: `10.1075/pbns.54`.

## Formula
Hyland (1998), Chapter 5, defines hedging density as the count of hedge tokens normalised per 1,000 words:

```
HedgeDensity(d) = 1000 · N_hedge(d) / N_token(d)

where
  N_hedge(d)  = #{ tokens or n-grams in d that match the
                  Hyland hedge lexicon H (≈ 250 entries:
                  modal verbs, epistemic adverbs, adjectives,
                  approximators, indirectness markers) }
  N_token(d)  = total non-stopword tokens in d
```

Hyland reports 18.0 hedges per 1,000 words as the corpus mean for biology research articles; forum prose averages 8-12.

## Starting weight preset
```python
"hedging.enabled": "true",
"hedging.ranking_weight": "0.0",
"hedging.target_per_1k": "10.0",
"hedging.penalty_above": "25.0",
```

## C++ implementation
- File: `backend/extensions/hedging.cpp`
- Entry: `double hedge_density(const std::vector<std::string_view>& tokens, const HedgeLexicon& lex)`
- Complexity: O(n) using a precompiled Aho-Corasick automaton over the 250-entry lexicon (multi-word hedges supported)
- Thread-safety: lexicon is const-shared; matching state is per-call
- Builds via pybind11

## Python fallback
`backend/apps/pipeline/services/hedging.py::compute_hedge_density` using `pyahocorasick`.

## Benchmark plan

| Size | Tokens | C++ target | Python target |
|---|---|---|---|
| Small | 200 | 0.08 ms | 1.2 ms |
| Medium | 2,000 | 0.6 ms | 9 ms |
| Large | 20,000 | 6 ms | 95 ms |

## Diagnostics
- Raw value "Hedges/1k: 12.4"
- C++/Python badge
- Fallback flag
- Debug fields: `top_3_hedge_phrases`, `n_hedges`, `n_tokens`

## Edge cases & neutral fallback
- Empty doc → neutral 0.5
- All-hedges doc (rare) → score capped at 100/1k
- Non-English → skip, fallback flag
- Quoted text in `<blockquote>` excluded so quoted hedges don't penalise the host

## Minimum-data threshold
At least 50 non-stopword tokens required; below that return neutral 0.5.

## Budget
Disk: 0.4 MB (lexicon)  ·  RAM: 1.2 MB (Aho-Corasick states)

## Scope boundary vs existing signals
Independent of `fr155-discourse-connective-density` (rhetorical glue) and `fr156-cohesion-score-cohmetrix` (semantic coherence). Hedging is purely an epistemic-stance lexical count.

## Test plan bullets
- Unit: doc "It might possibly be the case that perhaps..." returns ≥ 4 hedges
- Unit: doc "The cause is X." returns 0 hedges
- Parity: C++ vs Python within 1e-6 across 1,000 forum posts
- Edge: empty doc returns neutral 0.5
- Edge: lexicon update reload without restart
- Integration: contributes only when enabled
- Regression: ranking unchanged when weight = 0.0
