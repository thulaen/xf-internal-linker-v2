# FR-058 - N-gram Writing Quality Prediction

## Confirmation

- **Backlog confirmed**: `FR-058 - N-gram Writing Quality Prediction` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No writing-quality or linguistic-quality signal exists in the current ranker. The closest existing signal is fact density (FR-042), which counts factual claims. FR-058 measures *how well the text is written* using n-gram language model perplexity — a fundamentally different axis. A page can be fact-dense but poorly written, or fact-sparse but linguistically polished.
- **Repo confirmed**: `ContentItem.distilled_text` is available for all pages. N-gram extraction and frequency counting operate on raw text with no external dependencies.

## Current Repo Map

### Scoring already available

- `backend/apps/pipeline/services/ranker.py`
  - `score_fact_density` (FR-042) — measures factual claim density.
  - `score_information_gain` (FR-038) — measures vocabulary novelty.
  - No signal currently measures *writing quality patterns* — whether the text reads naturally or appears auto-generated, spun, or poorly composed.

- `backend/apps/pipeline/services/text_tokens.py`
  - `tokenize_text(text)` — returns normalized tokens. FR-058 needs raw text (not just token sets) because n-gram order matters.

### Source data already available at pipeline time

- `backend/apps/content/models.py`
  - `ContentItem` stores `distilled_text` for all pages in the site corpus.
  - The full corpus is available at index time for training the n-gram language model.

### Storage and settings patterns already available

- `backend/apps/suggestions/models.py` — separate `FloatField` + `JSONField` per feature signal.
- `backend/apps/core/views.py` — per-feature settings endpoints pattern.
- `backend/apps/suggestions/views.py` — `PipelineRun.config_snapshot` pattern.

## Source Summary

### Patent: US9767157B2 — Predicting Site Quality

**Plain-English description of the patent:**

The patent describes Google's Panda quality scoring system. It uses various signals — including linguistic quality indicators derived from n-gram language model analysis — to predict whether a page is high-quality editorial content or low-quality auto-generated/thin content. Pages that match the statistical patterns of known high-quality text score well; pages that deviate (unusual n-gram frequencies, repetitive patterns, unnatural phrase constructions) score poorly.

**Repo-safe reading:**

The patent uses a large-scale ML pipeline with many signals. This repo isolates the n-gram language model component: build a reference language model from the site's known-good pages, then score each page by how well it fits that model. The reusable core idea is:

- natural, well-written text follows predictable n-gram frequency patterns;
- auto-generated, spun, or thin content has unusual n-gram distributions (too repetitive, too random, or statistically unlikely phrase patterns);
- perplexity under a Kneser-Ney smoothed n-gram language model measures this deviation;
- lower perplexity = text fits the model better = higher writing quality.

**What is directly supported by the patent:**

- using n-gram frequency patterns as a quality signal;
- building a reference model from known-good content;
- scoring pages by deviation from expected linguistic patterns.

**What is adapted for this repo:**

- the "known-good" reference corpus is the site's own pages (self-referential quality baseline);
- the patent uses a mix of signals; this repo isolates the n-gram perplexity component;
- scoring is at the page level, cached at index time.

## Plain-English Summary

Simple version first.

Well-written text follows predictable patterns. When you read a naturally written article, the phrases flow in ways that match how English normally works. Auto-generated text, spun articles, and thin content break these patterns — the phrases are awkward, repetitive, or statistically unlikely.

FR-058 builds a statistical model of how "normal good writing" looks on this site by analyzing n-gram patterns (2-to-5-word sequences) across all pages. Then it scores each page by how well it fits that model.

A page with natural writing gets low perplexity (the model is not surprised by the text). A page with weird, robotic, or spun text gets high perplexity (the model is confused by the text).

This is different from fact density (which counts factual claims regardless of writing quality) and from information gain (which measures novelty regardless of how the text reads). FR-058 asks "does this page read like naturally written content?"

## Problem Statement

Today the ranker measures what content says (topic, facts, novelty) but not how *well* it is written. A destination page with auto-generated filler text that happens to be on-topic scores the same as a carefully authored article on the same topic.

This means the ranker can recommend thin, poorly written pages as long as they hit the right keywords and topic vectors. The reader who follows the link gets content that technically matches but is unpleasant or unhelpful to read.

FR-058 closes this gap with an n-gram-based writing quality score.

## Goals

FR-058 should:

- add a separate, explainable, bounded writing-quality signal;
- build a Kneser-Ney smoothed n-gram language model (2-to-5-grams) from the site corpus;
- score each page by its perplexity under this model;
- map perplexity to a bounded score where lower perplexity = higher quality;
- keep pages with too little text neutral at `0.5`;
- build the model once at index time and score pages in batch;
- keep ranking impact additive, bounded, and off by default;
- fit the current Django + Celery + PostgreSQL + Angular architecture.

## Non-Goals

FR-058 does not:

- rewrite `ContentItem.distilled_text`, `ContentItem.title`, or any embedding;
- change `score_semantic`, `score_keyword`, or the core ranker weighted sum;
- change FR-006 through FR-057 logic;
- replace fact density (FR-042) or information gain (FR-038) — they measure different things;
- implement neural language models — it uses deterministic n-gram statistics;
- implement real-time scoring — quality is computed at index time;
- use analytics, reviewer feedback, or any live query data;
- implement production code in the spec pass.

## Math-Fidelity Note

### Kneser-Ney smoothed n-gram language model

Let:

- `max_n` = maximum n-gram order (default 5, models use n=2,3,4,5)
- `d` = Kneser-Ney discount parameter (default 0.75)
- `C(w_1 ... w_n)` = count of n-gram `w_1 ... w_n` in the training corpus
- `N_{1+}(* w_n)` = number of unique contexts in which `w_n` appears as the last token (continuation count)
- `N_{1+}(w_1 ... w_{n-1} *)` = number of unique tokens following the prefix `w_1 ... w_{n-1}`

**Kneser-Ney probability (highest-order n-gram):**

```text
P_KN(w_n | w_1 ... w_{n-1}) =
  max(C(w_1 ... w_n) - d, 0) / C(w_1 ... w_{n-1})
  + lambda(w_1 ... w_{n-1}) * P_KN(w_n | w_2 ... w_{n-1})
```

where the backoff weight is:

```text
lambda(w_1 ... w_{n-1}) =
  (d / C(w_1 ... w_{n-1})) * N_{1+}(w_1 ... w_{n-1} *)
```

**Lower-order Kneser-Ney (continuation probability):**

```text
P_KN(w_n | w_2 ... w_{n-1}) =
  max(N_{1+}(* w_2 ... w_n) - d, 0) / N_{1+}(* w_2 ... w_{n-1} *)
  + lambda(w_2 ... w_{n-1}) * P_KN(w_n | w_3 ... w_{n-1})
```

**Base case (unigram continuation):**

```text
P_KN(w) = N_{1+}(* w) / N_{1+}(* *)
```

This recursion builds a smooth probability estimate that backs off from 5-grams to 4-grams to 3-grams to bigrams to unigrams, using continuation counts at lower orders.

### Perplexity computation

Let:

- `text` = the destination page's `distilled_text` as a token sequence of length `L`
- `w_1, w_2, ..., w_L` = the token sequence

**Log-probability of the text:**

```text
log_prob = sum( log2(P_KN(w_i | w_{i-n+1} ... w_{i-1})) for i in 1..L )
```

**Perplexity:**

```text
perplexity = 2^(-log_prob / L)
```

Lower perplexity = the model is less surprised = the text follows expected patterns = higher quality writing.

### Signal definition

Let:

- `PP` = perplexity of the destination page
- `PP_baseline` = `baseline_perplexity` setting (default 200.0) — the perplexity at which the score becomes neutral (0.5). Calibrated empirically from the site's corpus distribution.

**Quality ratio:**

```text
quality_ratio = min(1.0, PP_baseline / max(PP, 1.0))
```

This maps:

- `PP << PP_baseline` (much lower perplexity than baseline) -> `quality_ratio` near 1.0
- `PP == PP_baseline` (perplexity at baseline) -> `quality_ratio = 1.0` (capped)
- `PP >> PP_baseline` (much higher perplexity) -> `quality_ratio` approaches 0

**Bounded score:**

```text
score_ngram_quality = 0.5 * (1.0 + quality_ratio)
```

This maps:

- excellent writing (PP=50, baseline=200) -> `quality_ratio = 1.0`, `score = 1.0`
- average writing (PP=200, baseline=200) -> `quality_ratio = 1.0`, `score = 1.0`
- poor writing (PP=600, baseline=200) -> `quality_ratio = 0.33`, `score = 0.67`
- terrible writing (PP=2000, baseline=200) -> `quality_ratio = 0.10`, `score = 0.55`

**Neutral fallback:**

```text
score_ngram_quality = 0.5
```

Used when:

- page has fewer than 50 tokens (too short for reliable perplexity);
- n-gram model is not yet trained;
- feature is disabled.

### Why Kneser-Ney smoothing is the right approach

Kneser-Ney is the gold standard for n-gram language model smoothing. It handles unseen n-grams gracefully through the continuation count mechanism: instead of raw frequency at lower orders, it uses the number of unique contexts a word appeared in. This prevents common words from dominating the backoff distribution and gives a more accurate quality estimate. Modified Kneser-Ney is the algorithm used in KenLM, SRILM, and every production language model toolkit.

### Ranking hook

Add one centered additive component to the existing ranker:

```text
score_ngram_quality_component =
  max(0.0, min(1.0, 2.0 * (score_ngram_quality - 0.5)))
```

```text
score_final += ngram_quality.ranking_weight * score_ngram_quality_component
```

Default: `ranking_weight = 0.0` — diagnostics run silently with no ranking impact until an operator validates the signal.

## Scope Boundary Versus Existing Signals

FR-058 must stay separate from:

- `score_fact_density` (FR-042)
  - fact density counts factual claims in the content;
  - FR-058 measures how naturally the text is written;
  - a page can be fact-dense but poorly written, or well-written with few explicit facts.

- `score_information_gain` (FR-038)
  - information gain measures vocabulary novelty;
  - FR-058 measures linguistic naturalness;
  - novel content can be well-written or poorly written.

- `score_semantic`
  - semantic measures topical similarity;
  - FR-058 measures writing quality;
  - a page can be on-topic but badly written.

- `score_readability_match` (FR-052)
  - readability measures difficulty level (grade level);
  - FR-058 measures naturalness of phrase patterns;
  - a page can be at grade 8 (easy) but still sound robotic, or at grade 14 (hard) but beautifully written.

Hard rule: FR-058 must not mutate any token set, embedding, or text field used by any other signal.

## Inputs Required

FR-058 v1 needs:

- site corpus `distilled_text` — for training the n-gram language model (all pages at index time)
- destination `distilled_text` — for scoring each page at index time
- the n-gram model file — built once, stored on disk, loaded at scoring time

Explicitly disallowed FR-058 inputs in v1:

- external reference corpora (the model is site-self-referential)
- embedding vectors
- analytics or telemetry data
- any data not available at index time

## Settings And Feature-Flag Plan

### Operator-facing settings

Persist through `AppSetting`.

Recommended keys:

- `ngram_quality.enabled`
- `ngram_quality.ranking_weight`
- `ngram_quality.max_n`
- `ngram_quality.kn_discount`
- `ngram_quality.baseline_perplexity`

Defaults:

- `enabled = true`
- `ranking_weight = 0.03`
- `max_n = 5`
- `kn_discount = 0.75`
- `baseline_perplexity = 200.0`

Bounds:

- `0.0 <= ranking_weight <= 0.10`
- `2 <= max_n <= 7`
- `0.0 < kn_discount < 1.0`
- `50.0 <= baseline_perplexity <= 1000.0`

### Feature-flag behavior

- `enabled = false`
  - skip quality computation entirely
  - store `score_ngram_quality = 0.5`
  - store `ngram_quality_state = neutral_feature_disabled`
- `enabled = true` and `ranking_weight = 0.0`
  - compute quality scores and store diagnostics
  - do not change ranking order

## Diagnostics And Explainability Plan

Add one new diagnostics object:

- `Suggestion.ngram_quality_diagnostics`

Required fields:

- `score_ngram_quality`
- `ngram_quality_state`
  - `computed`
  - `neutral_feature_disabled`
  - `neutral_text_too_short`
  - `neutral_model_not_trained`
  - `neutral_processing_error`
- `perplexity` — raw perplexity of the destination page
- `quality_ratio` — `PP_baseline / PP`
- `token_count` — number of tokens scored
- `baseline_perplexity_setting` — baseline used for this computation
- `max_n_setting` — maximum n-gram order used
- `corpus_size` — number of pages in the training corpus
- `sample_high_perplexity_ngrams` — up to 3 n-grams with the highest surprise (most unusual phrases)
- `sample_low_perplexity_ngrams` — up to 3 n-grams with the lowest surprise (most natural phrases)

Plain-English review helper text should say:

- `N-gram quality means this page is written in natural, well-structured language that matches the site's editorial standard.`
- `A high score means the text reads naturally. A low score may indicate auto-generated, spun, or poorly composed content.`
- `Neutral means the page had too little text to score reliably, or the feature is disabled.`

## Storage / Model / API Impact

### Suggestion model

Add:

- `score_ngram_quality: FloatField(default=0.5)`
- `ngram_quality_diagnostics: JSONField(default=dict, blank=True)`

### Content model

Add:

- `ContentItem.ngram_perplexity: FloatField(null=True, blank=True)`

Reason:

- perplexity is a stable per-page property computed at index time;
- caching it avoids recomputing at suggestion time.

### N-gram model storage

- model file stored on disk: `~200 MB` for a site with 50K-100K pages and 5-gram coverage
- model can be discarded after scoring and rebuilt from corpus on demand
- model file path configurable via settings

### PipelineRun snapshot

Add FR-058 settings and algorithm version to `PipelineRun.config_snapshot`.

### Backend API

Add:

- `GET /api/settings/ngram-quality/`
- `PUT /api/settings/ngram-quality/`
- `POST /api/settings/ngram-quality/rebuild-model/` — triggers re-training of the n-gram model from the current corpus

### Review / admin / frontend

Add one new review row:

- `Writing Quality`

Add one small diagnostics block:

- perplexity value and quality ratio
- sample high-surprise and low-surprise n-grams
- neutral reason when fallback was used

Add one settings card:

- enabled toggle
- ranking weight slider
- max n-gram order input
- Kneser-Ney discount input
- baseline perplexity input

## Backend Service Touch Points

Implementation files for the later code pass:

- `backend/apps/pipeline/services/ngram_quality.py` — new service file (model training, scoring)
- `backend/apps/pipeline/services/ranker.py` — add FR-058 additive hook
- `backend/apps/pipeline/services/pipeline.py` — read cached perplexity at suggestion time
- `backend/apps/content/models.py` — add `ngram_perplexity` field
- `backend/apps/suggestions/models.py` — add two new fields on Suggestion
- `backend/apps/suggestions/serializers.py` — expose new fields
- `backend/apps/suggestions/views.py` — snapshot FR-058 settings
- `backend/apps/suggestions/admin.py` — expose new fields
- `backend/apps/suggestions/migrations/<new migration>`
- `backend/apps/content/migrations/<new migration>`
- `backend/apps/core/views.py` — add settings endpoints
- `backend/apps/api/urls.py` — wire new settings endpoints
- `backend/apps/pipeline/tests.py` — FR-058 unit tests
- `backend/extensions/ngramqual.cpp` — C++ extension for batch n-gram extraction and perplexity computation
- `frontend/src/app/review/suggestion-detail-dialog.component.ts`
- `frontend/src/app/review/suggestion-detail-dialog.component.html`
- `frontend/src/app/settings/silo-settings.service.ts`
- `frontend/src/app/settings/settings.component.ts`
- `frontend/src/app/settings/settings.component.html`

Modules that must stay untouched in the FR-058 implementation pass:

- `backend/apps/graph/models.py` — no new graph edges
- `backend/apps/pipeline/services/phrase_matching.py`
- `backend/apps/pipeline/services/learned_anchor.py`
- `backend/apps/pipeline/services/information_gain.py`
- `backend/apps/pipeline/services/fact_density.py` (FR-042) — must remain independent

## Test Plan

### 1. N-gram model training

- corpus of known-good pages produces a valid model
- model file size is within expected bounds (~200 MB for 50K pages)
- model loads correctly and produces valid probabilities

### 2. Perplexity computation

- well-written natural text -> low perplexity (below baseline)
- random word salad -> high perplexity (above baseline)
- repeated single phrase 100 times -> moderate-to-low perplexity (repetitive but predictable)

### 3. Quality score mapping

- PP=50, baseline=200 -> `score = 1.0`
- PP=200, baseline=200 -> `score = 1.0`
- PP=600, baseline=200 -> `score = 0.67`
- PP=2000, baseline=200 -> `score = 0.55`

### 4. Neutral fallback cases

- text shorter than 50 tokens -> `score = 0.5`, state `neutral_text_too_short`
- model not trained -> `score = 0.5`, state `neutral_model_not_trained`
- feature disabled -> `score = 0.5`, state `neutral_feature_disabled`

### 5. Ranking off by default

- `ranking_weight = 0.0` -> final score ordering unchanged

### 6. Bounded score

- score is always in `[0.5, 1.0]` regardless of input

### 7. Isolation from other signals

- changing FR-042 fact density does not affect `score_ngram_quality`
- changing FR-038 information gain does not affect `score_ngram_quality`
- perplexity is stored on ContentItem but never modifies `distilled_text` or embeddings

### 8. Serializer and frontend contract

- `score_ngram_quality` and `ngram_quality_diagnostics` appear in suggestion detail API response
- review dialog renders the `Writing Quality` row
- settings page loads and saves FR-058 settings

### 9. Snapshot coverage

- `PipelineRun.config_snapshot` includes FR-058 settings and algorithm version

## Rollout Plan

### Step 1 — model training

- build n-gram model from site corpus
- verify model size and loading performance
- inspect perplexity distribution across all pages

### Step 2 — diagnostics only

- implement FR-058 scoring with `ranking_weight = 0.0`
- calibrate `baseline_perplexity` from the corpus distribution (median or 75th percentile)
- verify that low-perplexity pages are genuinely well-written
- verify that high-perplexity pages are genuinely low-quality

### Step 3 — operator review

- inspect `sample_high_perplexity_ngrams` to confirm they represent genuinely unusual phrases
- confirm the model does not penalize legitimate domain-specific jargon unfairly

### Step 4 — optional small ranking enablement

- only after operator verification passes
- recommended first live weight: `0.02` to `0.04`

## Risk List

- the self-referential model trains on the site's own content, so if most pages are low quality, the model's baseline is low quality — mitigated by the operator-tunable `baseline_perplexity` and the sample n-gram diagnostics;
- domain-specific jargon and technical terms may increase perplexity even on well-written pages — mitigated by training the model on the site's own corpus (jargon becomes expected);
- very short pages produce unreliable perplexity estimates — mitigated by the 50-token minimum threshold;
- the n-gram model file (~200 MB) adds storage overhead — it can be rebuilt on demand and discarded after scoring;
- non-English content or mixed-language pages will produce high perplexity under an English-dominant model — operators should inspect language distribution before enabling.

## Recommended Preset Integration

### `recommended_weights.py` entries (already added — forward-declared)

```python
"ngram_quality.enabled": "true",
"ngram_quality.ranking_weight": "0.03",
"ngram_quality.max_n": "5",
"ngram_quality.kn_discount": "0.75",
"ngram_quality.baseline_perplexity": "200.0",
```

**Why these values:**

- `enabled = true` — run diagnostics silently from day one.
- `ranking_weight = 0.03` — moderate quality signal. Writing quality is meaningful but should not overpower relevance. Raise to `0.05` after confirming the model discriminates well.
- `max_n = 5` — 5-grams capture phrase-level patterns (sentence fragments). Higher n-grams are sparse and add noise.
- `kn_discount = 0.75` — standard Kneser-Ney discount used in SRILM and KenLM.
- `baseline_perplexity = 200.0` — typical for a medium-sized specialized corpus. Adjust after inspecting the site's actual perplexity distribution.

### Migration note

A new data migration is needed to upsert these keys into the existing `WeightPreset` record where `is_system=True` and `name='Recommended'`.

## Out Of Scope

- neural language model quality scoring (GPT-based perplexity)
- external reference corpus training (Common Crawl, Wikipedia)
- per-section quality scoring (intro vs body vs conclusion)
- grammar checking or spell checking as quality signals
- readability interaction (quality and readability are independent axes)
- any dependency on analytics or telemetry data
- any modification to stored text or embeddings
