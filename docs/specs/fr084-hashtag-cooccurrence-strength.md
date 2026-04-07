# FR-084 - Hashtag Co-occurrence Strength

## Confirmation

- **Backlog confirmed**: `FR-084 - Hashtag Co-occurrence Strength` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No tag co-occurrence or topic association signal exists in the current ranker. The closest signal is `score_keyword` (Jaccard on tokens), which measures word overlap. FR-084 measures the statistical strength of association between topic tags on source and destination pages using Pointwise Mutual Information (PMI) -- a fundamentally different measure.
- **Repo confirmed**: Page tags/categories are stored in `ContentItem` and available at pipeline time.

## Source Summary

### Patent: US10698945B2 -- Hashtag Co-occurrence Strength (Snap)

**Plain-English description of the patent:**

The patent describes measuring the strength of association between hashtags (topic tags) that co-occur on content. Tags that frequently appear together signal a strong topical relationship. PMI quantifies whether two tags appear together more often than chance would predict.

**What is adapted for this repo:**

- "hashtags" maps to page tags, categories, and topic labels from `ContentItem`;
- PMI is computed across the corpus between tags on source and destination pages;
- high PMI = strong topical association beyond random co-occurrence.

## Plain-English Summary

Simple version first.

Pages have topic tags. If the tags on the source page and the tags on the destination page frequently appear together across the corpus, those pages are topically related in a way that goes beyond simple word overlap.

FR-084 uses Pointwise Mutual Information (PMI) to measure this. PMI asks: "Do these tags appear together more often than random chance would predict?" A high PMI means the tags have a genuine association.

## Problem Statement

Today the ranker uses word overlap (Jaccard) and embedding similarity for topical matching. It does not use the explicit topic tag structure of pages. Two pages might have different words but share tags that the corpus shows are strongly associated.

FR-084 closes this gap with a tag-level association measure.

## Goals

FR-084 should:

- add a separate, explainable, bounded tag co-occurrence signal;
- compute PMI between source and destination page tags;
- use sigmoid to bound PMI into `[0, 1]`;
- keep pairs without tags neutral at `0.5`;
- keep ranking impact additive, bounded, and off by default.

## Non-Goals

FR-084 does not:

- modify page tags or create new tags;
- change keyword scoring or semantic similarity;
- implement production code in the spec pass.

## Math-Fidelity Note

### Signal definition

Let:

- `T_src` = set of topic tags on the source page
- `T_dst` = set of topic tags on the destination page
- `P(t)` = fraction of corpus pages containing tag `t`
- `P(t_src, t_dst)` = fraction of corpus pages containing both tags (co-occurrence fraction)
- `epsilon` = PMI smoothing constant (default 0.5)

**Pointwise Mutual Information per tag pair:**

```text
PMI(t_src, t_dst) = log2(P(t_src, t_dst) / (P(t_src) * P(t_dst)))
```

With smoothing:

```text
PMI_smooth(t_src, t_dst) = log2((P(t_src, t_dst) + epsilon/N) / ((P(t_src) + epsilon/N) * (P(t_dst) + epsilon/N)))
```

**Aggregate PMI across all tag pairs:**

```text
mean_pmi = mean(PMI_smooth(t_s, t_d) for t_s in T_src, t_d in T_dst)
```

**Bounded score via sigmoid:**

```text
score_hashtag_cooccurrence = sigmoid(mean_pmi) = 1 / (1 + exp(-mean_pmi))
```

This maps:

- `mean_pmi << 0` (tags negatively associated) -> `score ~ 0.0`
- `mean_pmi = 0` (tags independent) -> `score = 0.5`
- `mean_pmi >> 0` (tags strongly associated) -> `score ~ 1.0`

**Neutral fallback:**

```text
score_hashtag_cooccurrence = 0.5
```

Used when:

- either page has no tags;
- feature is disabled.

### Ranking hook

```text
score_hashtag_component =
  max(0.0, min(1.0, 2.0 * (score_hashtag_cooccurrence - 0.5)))
```

```text
score_final += hashtag_cooccurrence.ranking_weight * score_hashtag_component
```

## Scope Boundary Versus Existing Signals

FR-084 must stay separate from:

- `score_keyword` -- measures word-level overlap, not tag-level PMI.
- `score_semantic` -- measures embedding similarity, not explicit tag association.
- `FR-048` topical authority -- measures embedding-space cluster density, not tag co-occurrence.

## Inputs Required

- Page tags/categories from `ContentItem` -- already available at pipeline time
- Corpus-wide tag frequency counts -- computed at index time

## Settings And Feature-Flag Plan

### Operator-facing settings

Recommended keys (from `recommended_weights.py`):

- `hashtag_cooccurrence.enabled`
- `hashtag_cooccurrence.ranking_weight`
- `hashtag_cooccurrence.pmi_smoothing`

Defaults:

- `enabled = true`
- `ranking_weight = 0.02`
- `pmi_smoothing = 0.5`

## Diagnostics And Explainability Plan

Required fields:

- `score_hashtag_cooccurrence`
- `hashtag_cooccurrence_state` (`computed`, `neutral_feature_disabled`, `neutral_no_tags`, `neutral_processing_error`)
- `source_tags` -- list of source page tags
- `destination_tags` -- list of destination page tags
- `mean_pmi` -- average PMI across tag pairs
- `strongest_pair` -- tag pair with highest PMI
- `strongest_pmi` -- PMI value of strongest pair

Plain-English review helper text should say:

- `Hashtag co-occurrence measures how strongly the topic tags on the source and destination are associated across the corpus.`
- `A high score means these tags frequently appear together on other pages, suggesting genuine topical relevance.`

## Storage / Model / API Impact

### Suggestion model

Add:

- `score_hashtag_cooccurrence: FloatField(default=0.5)`
- `hashtag_cooccurrence_diagnostics: JSONField(default=dict, blank=True)`

Note: This is pair-specific (source tags x destination tags), so it lives on the Suggestion model.

### Backend API

Add:

- `GET /api/settings/hashtag-cooccurrence/`
- `PUT /api/settings/hashtag-cooccurrence/`

## Recommended Preset Integration

### `recommended_weights.py` entries (already forward-declared)

```python
"hashtag_cooccurrence.enabled": "true",
"hashtag_cooccurrence.ranking_weight": "0.02",
"hashtag_cooccurrence.pmi_smoothing": "0.5",
```
