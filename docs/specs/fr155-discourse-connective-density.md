# FR-155 — Discourse Connective Density

## Overview
Explicit discourse connectives ("however", "therefore", "for example", "in addition") signal that a passage explains, contrasts, or exemplifies — exactly the kind of structured prose that makes a strong link destination. Counting connectives per sentence gives a cheap structural-quality prior. Complements `fr156-cohesion-score-cohmetrix` because connectives mark explicit relations while cohesion measures latent semantic continuity.

## Academic source
Full citation: **Pitler, E. & Nenkova, A. (2008).** "Revisiting Readability: A Unified Framework for Predicting Text Quality." *Proceedings of the 2008 Conference on Empirical Methods in Natural Language Processing (EMNLP)*, pp. 186-195. ACL Anthology: `D08-1020`. DOI: `10.3115/1613715.1613742`.

## Formula
Pitler & Nenkova (2008), Equation 3, define discourse-connective density as the ratio of identified connective tokens to sentence count, weighted by the connective-relation prior `w(c)` learned from PDTB:

```
ConnDensity(d) = (1 / N_sent(d)) · Σ_{c ∈ d}  w(c) · 1[c ∈ C]

where
  C       = PDTB v2 connective inventory (≈ 100 entries)
  w(c)    = corpus-prior weight for connective c (default 1.0)
  N_sent(d) = sentence count of d
```

Pitler & Nenkova report a Pearson r=0.48 between this density and human readability ratings on the WSJ corpus.

## Starting weight preset
```python
"discourse_conn.enabled": "true",
"discourse_conn.ranking_weight": "0.0",
"discourse_conn.target_per_sentence": "0.6",
```

## C++ implementation
- File: `backend/extensions/discourse_connectives.cpp`
- Entry: `double connective_density(const std::vector<std::string_view>& tokens, const ConnLexicon& lex)`
- Complexity: O(n) via Aho-Corasick over the PDTB connective inventory (handles multi-word "for example", "in other words")
- Thread-safety: shared const automaton
- Builds via pybind11

## Python fallback
`backend/apps/pipeline/services/discourse_connectives.py::compute_connective_density` using a precompiled trie over the PDTB inventory.

## Benchmark plan

| Size | Tokens | C++ target | Python target |
|---|---|---|---|
| Small | 200 | 0.08 ms | 1.5 ms |
| Medium | 2,000 | 0.5 ms | 11 ms |
| Large | 20,000 | 5 ms | 100 ms |

## Diagnostics
- Raw value "Connectives/sent: 0.74"
- C++/Python badge
- Fallback flag
- Debug fields: `top_5_connectives`, `n_connectives`, `n_sentences`

## Edge cases & neutral fallback
- Document with one sentence → density = N_conn (capped at 5.0)
- Empty document → neutral 0.5
- Non-English → skip, fallback flag
- Connective inside a code block excluded

## Minimum-data threshold
At least 3 sentences required; below that return neutral 0.5.

## Budget
Disk: 0.1 MB  ·  RAM: 0.4 MB

## Scope boundary vs existing signals
Distinct from `fr154-hedging-language-density` (epistemic stance) and `fr157-part-of-speech-diversity` (POS distribution). Connective density is a closed-class lexical count for discourse markers only.

## Test plan bullets
- Unit: "However, this works. Therefore, that fails." returns 2/2 = 1.0
- Unit: "This works. That fails." returns 0/2 = 0.0
- Parity: C++ vs Python within 1e-6
- Edge: single-sentence doc handled without divide-by-zero
- Edge: PDTB inventory loaded from JSON, hot-swappable
- Integration: contributes when enabled
- Regression: ranking unchanged when weight = 0.0
