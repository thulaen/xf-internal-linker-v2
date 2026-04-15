# FR-202 - Clickbait Classifier

## Overview
A clickbait headline withholds the answer or hooks the reader with a forward-reference, a numeric promise ("17 things you didn't know..."), or an exaggerated emotion. The Chakraborty et al. paper trained a 14-feature linear SVM on a labelled corpus of 32 K headlines achieving F1 = 0.93. This signal scores each candidate's title against the same 14 features and returns a `[0, 1]` clickbait probability. Used as a multiplicative penalty so clickbait threads rank below straight-shooter threads of the same topic.

## Academic source
**Chakraborty, Abhijnan; Paranjape, Bhargavi; Kakarla, Sourya; Ganguly, Niloy (2016).** "Stop Clickbait: Detecting and Preventing Clickbaits in Online News Media." *Proceedings of the 2016 IEEE/ACM International Conference on Advances in Social Networks Analysis and Mining (ASONAM 2016)*, pp. 9-16. DOI: `10.1109/ASONAM.2016.7752207`. The 14-feature set in §3 and the linear SVM with RBF baseline in §4 form the basis for this signal.

## Formula
For each title `t` extract a 14-dim feature vector `x(t)` (paper §3, Table 1):

| # | Feature | Definition |
|---|---|---|
| 1 | `len_words` | number of word tokens |
| 2 | `len_chars` | number of characters |
| 3 | `avg_word_len` | mean word length |
| 4 | `n_determiners` | count of {the, a, an, this, that, these, those} |
| 5 | `n_adverbs` | count of POS tag `RB*` |
| 6 | `n_cardinal_numbers` | count of POS tag `CD` |
| 7 | `n_fwd_ref_pronouns` | count of {this, these, that, those} used cataphorically |
| 8 | `n_superlatives` | count of POS tag `JJS`/`RBS` |
| 9 | `n_2nd_person` | count of {you, your, yours, yourself} |
| 10 | `n_punct` | total punctuation marks |
| 11 | `n_question_marks` | `?` count |
| 12 | `n_interjections` | count of POS tag `UH` |
| 13 | `n_hyperbolic` | matches against curated lexicon (amazing, shocking, …) |
| 14 | `ngram_match_score` | dot product with clickbait-bigram TF-IDF vector |

Linear SVM decision function (Eq. 2):
```
f(x) = wᵀ·x + b
clickbait_prob(t) = 1 / (1 + exp(−f(x)))            (Platt-scaled sigmoid)
clickbait_penalty(t) = max(0, clickbait_prob(t) − τ),   τ = 0.50
```

The trained `w ∈ ℝ¹⁴` and `b` are shipped as a pickled JSON blob (paper supplement).

## Starting weight preset
```python
"clickbait.enabled": "true",
"clickbait.ranking_weight": "0.0",
"clickbait.tau_decision": "0.50",
"clickbait.model_path": "models/clickbait_svm_v1.json",
"clickbait.hyperbolic_lexicon": "data/clickbait_hyperbolic.txt",
```

## C++ implementation
- File: `backend/extensions/clickbait_classifier.cpp`
- Entry: `double clickbait_score(const char* title, const SVMModel& model);`
- Complexity: `O(|t|)` tokenisation + `O(14)` linear SVM dot-product
- Thread-safety: model is read-only; tokeniser uses thread-local buffers
- POS tagger called via pybind11 to the spaCy small model (Python bridge OK because per-call cost dominated by tokenisation, not POS)
- Builds against pybind11

## Python fallback
`backend/apps/pipeline/services/clickbait.py::clickbait_score(...)` — full Python pipeline with `spacy` + `numpy` dot-product, used when extension unavailable.

## Benchmark plan
| Titles | C++ target | Python target |
|---|---|---|
| 100 | < 20 ms | < 200 ms |
| 1 K | < 200 ms | < 2 s |
| 10 K | < 2 s | < 20 s |

## Diagnostics
- Per-title 14-feature vector
- Raw `f(x)`, sigmoid `clickbait_prob`, and `clickbait_penalty`
- Top-3 contributing features per title (signed)
- Model checksum and version
- C++ vs Python badge

## Edge cases & neutral fallback
- Empty title → neutral `0.0`, flag `empty_title`
- Title `< 3` words → neutral `0.0`, flag `title_too_short`
- Non-English title (low ASCII ratio) → neutral `0.0`, flag `non_english`
- Hyperbolic lexicon missing → skip feature 13, re-balance via mean imputation
- NaN / Inf → `0.0`, flag `nan_clamped`

## Minimum-data threshold
`≥ 3` words in title before the score is trusted; below this returns neutral `0.0`.

## Budget
Disk: <500 KB (SVM weights + lexicon)  ·  RAM: <40 MB (spaCy small model loaded once per process)

## Scope boundary vs existing signals
FR-202 does NOT overlap with FR-052 readability matching (which targets reading-grade alignment, not clickbait detection) or FR-038 information-gain scoring (which is content-side, not title-side). It is distinct from FR-201 AstroTurf detection (which is account-level, not title-level).

## Test plan bullets
- unit tests: known clickbait headline (e.g. "You won't believe what happened next"), neutral headline
- parity test: C++ vs Python `f(x)` within `1e-4`
- regression test: legitimate listicles (e.g. "Top 10 PHP frameworks") get appropriate `≈ 0.4` not `≥ 0.8`
- integration test: ranking unchanged when `ranking_weight = 0.0`
- model-load test: corrupted SVM weights → falls back to neutral, logs `model_load_failed`
- POS-tagger fallback test: spaCy unavailable → simple regex POS approximation, flag `pos_fallback`
