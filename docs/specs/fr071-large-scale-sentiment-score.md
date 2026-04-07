# FR-071 - Large-Scale Sentiment Score

## Confirmation

- **Backlog confirmed**: `FR-071 - Large-Scale Sentiment Score` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No sentiment or polarity signal exists in the current ranker. The closest existing signal is `score_semantic` (cosine similarity), which measures topical relevance, not emotional tone. FR-071 measures document-level sentiment polarity -- a fundamentally different axis.
- **Repo confirmed**: `ContentItem.distilled_text` already provides clean text suitable for lexicon-based sentiment analysis.

## Source Summary

### Patent: US7996210B2 -- Large-Scale Sentiment Analysis (Google)

**Plain-English description of the patent:**

The patent describes scoring documents by their overall sentiment polarity using lexical features. Documents are classified along a positive-negative spectrum. The system is designed to work at web scale using dictionary-based approaches rather than expensive ML models.

**Repo-safe reading:**

The patent covers web-scale sentiment analysis using lexical features. This repo applies the same principle at a site-local scope. The reusable core idea is:

- compute a sentiment polarity score for each page's text;
- prefer linking to neutral-to-positive pages;
- flag controversial or highly negative pages for operator review;
- keep it additive and bounded.

**What is directly supported by the patent:**

- document-level sentiment scoring from text features;
- mapping polarity to a bounded numeric score;
- using sentiment as a quality filter layer.

**What is adapted for this repo:**

- the patent describes a custom lexicon; this repo uses VADER (Valence Aware Dictionary and sEntiment Reasoner), a well-validated lexicon-based tool;
- compound scores are mapped from `[-1, +1]` to `[0, 1]` for consistency with the ranker's score range.

## Plain-English Summary

Simple version first.

Some pages have a positive, helpful tone. Some pages are negative, angry, or controversial.

FR-071 scores each destination page by its overall sentiment. Pages with neutral-to-positive tone score higher. Pages with strongly negative or controversial tone get flagged.

This is not about censoring opinions. It is about avoiding jarring tonal shifts when a reader follows an internal link from a neutral informational article to a strongly negative rant.

Think of it this way: `score_semantic` asks "is the destination on the right topic?" FR-071 asks "does the destination have an appropriate tone?"

## Problem Statement

Today the ranker has no awareness of sentiment or tone. It can suggest a link from a neutral product guide to a destination that is a scathing criticism of the product category, creating a jarring reader experience.

FR-071 closes this gap by providing a bounded sentiment polarity score per destination page.

## Goals

FR-071 should:

- add a separate, explainable, bounded sentiment score;
- compute it using VADER compound polarity on `distilled_text`;
- map the `[-1, +1]` VADER compound to a `[0, 1]` score;
- flag pages with `|compound| > controversy_threshold` for operator review;
- keep missing or insufficient text neutral at `0.5`;
- keep ranking impact additive, bounded, and off by default;
- fit the current Django + Celery + PostgreSQL + Angular architecture.

## Non-Goals

FR-071 does not:

- rewrite `ContentItem.distilled_text` or any embedding;
- change any existing signal logic;
- train a custom sentiment model;
- perform aspect-level or entity-level sentiment analysis;
- censor or remove content;
- implement production code in the spec pass.

## Math-Fidelity Note

### Signal definition

Let:

- `text` = destination page `distilled_text`
- `compound` = VADER compound polarity score for `text`, in `[-1, +1]`

**Mapped score:**

```text
score_sentiment = (compound + 1) / 2
```

This maps:

- `compound = -1.0` (maximally negative) -> `score = 0.0`
- `compound = 0.0` (neutral) -> `score = 0.5`
- `compound = +1.0` (maximally positive) -> `score = 1.0`

**Controversy flag:**

```text
is_controversial = (|compound| > controversy_threshold)
```

Default `controversy_threshold = 0.60`. Pages flagged as controversial appear with a warning icon in the review UI.

**Neutral fallback:**

```text
score_sentiment = 0.5
```

Used when:

- `distilled_text` is empty or below `min_text_chars`;
- VADER processing fails;
- feature is disabled.

### Why VADER

VADER is a rule-based lexicon tool optimised for social media text that:

- requires no training data or model files;
- runs in <1ms per document;
- handles negation, degree modifiers, and punctuation emphasis;
- produces a compound score in `[-1, +1]` that is well-calibrated.

It is deterministic, reproducible, and has zero RAM overhead beyond the lexicon (~2 MB).

### Ranking hook

```text
score_sentiment_component =
  max(0.0, min(1.0, 2.0 * (score_sentiment - 0.5)))
```

```text
score_final += sentiment_score.ranking_weight * score_sentiment_component
```

Default: `ranking_weight = 0.0` -- diagnostics only until validated.

## Scope Boundary Versus Existing Signals

FR-071 must stay separate from:

- `score_semantic`
  - semantic measures topical similarity via embeddings;
  - FR-071 measures emotional tone via lexical polarity;
  - orthogonal axes.

- `FR-081` contextual sentiment alignment
  - FR-081 compares sentiment between the source sentence and destination paragraph;
  - FR-071 computes absolute sentiment of the destination page alone;
  - FR-071 is a page-level property; FR-081 is a pair-level property.

- `FR-042` fact density
  - fact density measures informational richness;
  - FR-071 measures emotional valence;
  - completely different dimensions.

Hard rule: FR-071 must not mutate any token set, embedding, or text field used by any other signal.

## Inputs Required

FR-071 v1 can use only data already available in the pipeline:

- `ContentItem.distilled_text` -- already available at index time
- VADER lexicon -- bundled with the `vaderSentiment` Python package (no external dependency)

Explicitly disallowed FR-071 inputs in v1:

- embedding vectors
- analytics or telemetry data
- user reviews or comments

## Settings And Feature-Flag Plan

### Operator-facing settings

Recommended keys (from `recommended_weights.py`):

- `sentiment_score.enabled`
- `sentiment_score.ranking_weight`
- `sentiment_score.controversy_threshold`

Defaults:

- `enabled = true`
- `ranking_weight = 0.02`
- `controversy_threshold = 0.60`

Bounds:

- `0.0 <= ranking_weight <= 0.10`
- `0.30 <= controversy_threshold <= 0.90`

### Feature-flag behaviour

- `enabled = false` -> `score = 0.5`, state `neutral_feature_disabled`
- `enabled = true` and `ranking_weight = 0.0` -> compute and store diagnostics, no ranking impact

## Diagnostics And Explainability Plan

Add one new diagnostics object:

- `ContentItem.sentiment_diagnostics`

Required fields:

- `score_sentiment`
- `sentiment_state` (`computed`, `neutral_feature_disabled`, `neutral_text_too_short`, `neutral_processing_error`)
- `vader_compound` -- raw VADER compound score in `[-1, +1]`
- `vader_positive` -- VADER positive proportion
- `vader_negative` -- VADER negative proportion
- `vader_neutral` -- VADER neutral proportion
- `is_controversial` -- boolean flag
- `text_char_count` -- length of text analysed

Plain-English review helper text should say:

- `Sentiment score measures the overall emotional tone of this page's content.`
- `A high score means the page has positive or neutral tone. A low score means negative tone.`
- `Pages flagged as controversial have strong sentiment (positive or negative) above the threshold.`

## Storage / Model / API Impact

### Content model

Add:

- `score_sentiment: FloatField(default=0.5)`
- `sentiment_diagnostics: JSONField(default=dict, blank=True)`

### PipelineRun snapshot

Add FR-071 settings and algorithm version to `PipelineRun.config_snapshot`.

### Backend API

Add:

- `GET /api/settings/sentiment-score/`
- `PUT /api/settings/sentiment-score/`

### Review / admin / frontend

Add one new review row: `Sentiment Score`

Add one settings card:

- enabled toggle
- ranking weight slider
- controversy threshold slider

## Recommended Preset Integration

### `recommended_weights.py` entries (already forward-declared)

```python
"sentiment_score.enabled": "true",
"sentiment_score.ranking_weight": "0.02",
"sentiment_score.controversy_threshold": "0.60",
```

**Why these values:**

- `ranking_weight = 0.02` -- conservative. Sentiment is a soft quality signal, not a primary ranking factor.
- `controversy_threshold = 0.60` -- VADER compounds above 0.6 are strongly polarized. Flagging these gives operators visibility without being overly sensitive.
