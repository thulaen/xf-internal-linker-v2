# FR-081 - Contextual Sentiment Alignment

## Confirmation

- **Backlog confirmed**: `FR-081 - Contextual Sentiment Alignment` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No tonal consistency or sentiment-matching signal exists in the current ranker. The closest signal is FR-071 (large-scale sentiment score), which measures absolute destination sentiment. FR-081 measures the tonal match between source context and destination opening -- a pair-level property, not a page-level one.
- **Repo confirmed**: `ContentItem.distilled_text` is already available at pipeline time for both source and destination.

## Source Summary

### Patent: US20150286627A1 -- Contextual Sentiment Alignment (Google)

**Plain-English description of the patent:**

The patent describes scoring the tonal consistency between a user's current context and a candidate document. A jarring tonal shift (from positive to negative) creates a poor user experience. Tonal alignment between source and destination improves perceived link quality.

**What is adapted for this repo:**

- "source context" maps to the VADER sentiment of the source sentence surrounding the link insertion point;
- "destination tone" maps to the VADER sentiment of the destination page's first paragraph;
- the score measures how closely these two sentiments match.

## Plain-English Summary

Simple version first.

When a reader is in the middle of a positive, helpful paragraph and clicks a link, they expect the destination to have a similar tone. If the link drops them into a negative rant, it feels jarring.

FR-081 measures this tonal alignment. If the source sentence is positive and the destination opening is also positive, the score is high. If they are mismatched, the score is lower.

This is different from FR-071 (absolute sentiment) because FR-081 cares about the *match*, not the absolute value.

## Problem Statement

Today the ranker can suggest links that create jarring tonal shifts -- a positive source context linking to a negative destination, or vice versa.

FR-081 closes this gap by measuring sentiment alignment between the link's context and the destination's opening.

## Goals

FR-081 should:

- add a separate, explainable, bounded sentiment alignment signal;
- compute VADER sentiment for both the source insertion context and the destination's first paragraph;
- score the closeness of the two sentiments;
- keep pairs with insufficient text neutral at `0.5`;
- keep ranking impact additive, bounded, and off by default.

## Non-Goals

FR-081 does not:

- modify FR-071 (absolute sentiment score);
- train a custom sentiment model;
- implement production code in the spec pass.

## Math-Fidelity Note

### Signal definition

Let:

- `c_src` = VADER compound score of the source sentence context (the sentence where the link is inserted), in `[-1, +1]`
- `c_dst` = VADER compound score of the destination page's first paragraph, in `[-1, +1]`

**Tonal alignment score:**

```text
score_sentiment_alignment = 1 - |c_src - c_dst| / 2
```

This maps:

- `|c_src - c_dst| = 0` (perfect tonal match) -> `score = 1.0`
- `|c_src - c_dst| = 1` (moderate mismatch) -> `score = 0.5`
- `|c_src - c_dst| = 2` (maximum mismatch: +1 vs. -1) -> `score = 0.0`

**Neutral centering:**

```text
score_final = 0.5 + 0.5 * score_sentiment_alignment
```

Maps to `[0.5, 1.0]` so mismatched tones are neutral, not actively penalizing.

**Neutral fallback:**

```text
score_sentiment_alignment = 0.5
```

Used when:

- source sentence text is too short for VADER analysis;
- destination has no first paragraph;
- feature is disabled.

### Ranking hook

```text
score_alignment_component =
  max(0.0, min(1.0, 2.0 * (score_final - 0.5)))
```

```text
score_final += sentiment_alignment.ranking_weight * score_alignment_component
```

## Scope Boundary Versus Existing Signals

FR-081 must stay separate from:

- `FR-071` sentiment score -- measures absolute destination sentiment, not source-destination match.
- `score_semantic` -- measures topical similarity, not tonal similarity.
- `FR-043` semantic drift penalty -- measures topic drift, not sentiment drift.

## Inputs Required

- Source sentence text at link insertion point -- from pipeline context
- Destination page first paragraph -- from `ContentItem.distilled_text`

## Settings And Feature-Flag Plan

### Operator-facing settings

Recommended keys (from `recommended_weights.py`):

- `sentiment_alignment.enabled`
- `sentiment_alignment.ranking_weight`

Defaults:

- `enabled = true`
- `ranking_weight = 0.02`

## Diagnostics And Explainability Plan

Required fields:

- `score_sentiment_alignment`
- `sentiment_alignment_state` (`computed`, `neutral_feature_disabled`, `neutral_text_too_short`, `neutral_processing_error`)
- `source_vader_compound` -- VADER compound for source sentence
- `destination_vader_compound` -- VADER compound for destination first paragraph
- `compound_difference` -- absolute difference

Plain-English review helper text should say:

- `Contextual sentiment alignment measures whether the tone around the link matches the destination's opening tone.`
- `A high score means smooth tonal transitions. A low score means a jarring shift in sentiment.`

## Storage / Model / API Impact

### Suggestion model

Add:

- `score_sentiment_alignment: FloatField(default=0.5)`
- `sentiment_alignment_diagnostics: JSONField(default=dict, blank=True)`

Note: This is pair-specific (source sentence x destination), so it lives on the Suggestion model.

### Backend API

Add:

- `GET /api/settings/sentiment-alignment/`
- `PUT /api/settings/sentiment-alignment/`

## Recommended Preset Integration

### `recommended_weights.py` entries (already forward-declared)

```python
"sentiment_alignment.enabled": "true",
"sentiment_alignment.ranking_weight": "0.02",
```
