# FR-153 — Nominalization Density

## Overview
Heavy nominalization ("the implementation of the configuration" instead of "configure it") signals abstract, dense prose that often disengages forum readers and earns fewer click-throughs as a link destination. A simple ratio of derived nouns (`-tion`, `-ment`, `-ance`, `-ity`, `-ness`) per finite clause gives a robust readability prior. Complements `fr158-sentence-length-variance` because nominalization affects vocabulary choice while sentence variance affects rhythm.

## Academic source
Full citation: **Halliday, M. A. K. (1985).** *An Introduction to Functional Grammar*. London: Edward Arnold. Chapter 10, "Grammatical Metaphor", pp. 319-345. Republished by Routledge, 4th ed. (2014). DOI: `10.4324/9780203431269`.

## Formula
Halliday (1985) defines grammatical-metaphor density as nominalised-process counts per ranking clause. Operationalised as:

```
NomDensity(d) = N_nom(d) / N_clause(d)

where
  N_nom(d)    = #{ tokens whose lemma matches suffix set
                  S = {-tion, -sion, -ment, -ance, -ence,
                       -ity, -ness, -ship, -hood, -ism, -al} }
  N_clause(d) = #{ finite clauses in d }
```

Halliday reports densities of 0.5-0.8 nominalisations per clause in scientific writing vs. 0.05-0.15 in casual conversation; forum posts target the lower band.

## Starting weight preset
```python
"nominalization.enabled": "true",
"nominalization.ranking_weight": "0.0",
"nominalization.target_density": "0.15",
"nominalization.penalty_above": "0.50",
```

## C++ implementation
- File: `backend/extensions/nominalization.cpp`
- Entry: `double nominalization_density(const std::vector<Token>& tokens)`
- Complexity: O(n·k) where k = average suffix-set size (constant ≤ 11); effectively O(n)
- Thread-safety: pure; uses constexpr `std::array` of suffixes for branchless matching
- SIMD: AVX2 string compare on 16-byte aligned suffix slots when available
- Builds via pybind11

## Python fallback
`backend/apps/pipeline/services/nominalization.py::compute_nominalization_density` using a precompiled regex of the suffix set against `token.lemma_`.

## Benchmark plan

| Size | Tokens | C++ target | Python target |
|---|---|---|---|
| Small | 200 | 0.06 ms | 2 ms |
| Medium | 2,000 | 0.5 ms | 18 ms |
| Large | 20,000 | 5 ms | 180 ms |

## Diagnostics
- Raw density value (e.g. "Nom: 0.22 / clause")
- C++/Python badge
- Fallback flag
- Debug fields: `n_nominalizations`, `n_clauses`, `top_5_nominalizations`

## Edge cases & neutral fallback
- Document with zero clauses → neutral 0.5
- False-positive lemmas like "nation", "season" filtered via stop-suffix list
- Code blocks and `<pre>` excluded
- Non-English posts → skip signal, fallback flag set

## Minimum-data threshold
At least 5 finite clauses required; below that return neutral 0.5.

## Budget
Disk: 0.3 MB  ·  RAM: 0.6 MB

## Scope boundary vs existing signals
Distinct from `fr152-passive-voice-ratio` (verbal voice) and `fr157-part-of-speech-diversity` (entropy across all POS tags). Nominalization density is a targeted noun-derivation count, not a global POS distribution measure.

## Test plan bullets
- Unit: doc with "implementation, configuration, deployment" in one clause returns 3.0
- Unit: doc "we configured it" returns 0.0
- Parity: C++ vs Python on 1,000 forum posts within 1e-6
- Edge: stop-suffix list correctly filters "nation", "season", "reason"
- Edge: empty doc returns 0.5 with fallback flag
- Integration: contributes to ranker only when `enabled=true`
- Regression: ranking unchanged when weight = 0.0
