# FR-088 - Save/Bookmark Rate

## Confirmation

- **Backlog confirmed**: `FR-088 - Save/Bookmark Rate` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No save rate, bookmark rate, or intent-to-return signal exists in the current ranker. The closest signal is `FR-024` (engagement read-through rate), which measures in-session engagement. FR-088 measures a different behavioural signal -- the fraction of viewers who save the page for later, indicating high perceived value.
- **Repo confirmed**: GA4 bookmark/save events are available via the analytics sync pipeline.

## Source Summary

### Patent: US9256680B2 -- Save/Bookmark Rate (Pinterest)

**Plain-English description of the patent:**

The patent describes using the save/pin/bookmark rate as a quality signal for content. When users save content to revisit later, it indicates they found it valuable enough to return to -- a stronger signal than a passive view. The save rate (saves divided by views) is a normalized measure of intent-to-return.

**What is adapted for this repo:**

- "saves" maps to GA4 `bookmark_event` or equivalent save/pin interactions;
- "views" maps to GA4 `page_view` events;
- Laplace smoothing is applied to handle cold-start pages.

## Plain-English Summary

Simple version first.

When someone saves or bookmarks a page, they are saying "I want to come back to this." That is a stronger signal than just viewing a page -- it means the reader found genuine lasting value.

FR-088 measures the save/bookmark rate: what fraction of viewers save the page. Pages with high save rates have demonstrated intent-to-return value.

## Problem Statement

Today the ranker measures in-session engagement (read-through, dwell time) but not intent-to-return behaviour. A page that many people save for later reference is clearly valuable, but the ranker cannot distinguish it from a page that gets the same number of views but no saves.

FR-088 closes this gap with a normalized save/bookmark rate.

## Goals

FR-088 should:

- add a separate, explainable, bounded save rate signal;
- compute saves / (views + smoothing constant);
- use Laplace-style smoothing to handle pages with few views;
- keep pages without save data neutral at `0.5`;
- keep ranking impact additive, bounded, and off by default.

## Non-Goals

FR-088 does not:

- track individual users' bookmark lists;
- modify any engagement signal;
- implement production code in the spec pass.

## Math-Fidelity Note

### Signal definition

Let:

- `saves` = count of GA4 `bookmark_event` (or equivalent save/pin) events for this page
- `views` = count of GA4 `page_view` events for this page
- `alpha` = Laplace denominator smoothing (default 10)

**Smoothed save rate:**

```text
save_rate = saves / (views + alpha)
```

The `alpha` denominator prevents division by zero and pulls low-view pages toward zero (conservative prior).

**Normalized score:**

```text
score_bookmark_rate = min(1.0, save_rate / max_save_rate)
```

Where `max_save_rate` is the corpus-wide maximum save rate (used for normalization).

**Neutral centering:**

```text
score_final = 0.5 + 0.5 * score_bookmark_rate
```

**Neutral fallback:**

```text
score_bookmark_rate = 0.5
```

Used when:

- page has no GA4 save events tracked;
- views below minimum threshold;
- feature is disabled.

### Ranking hook

```text
score_bookmark_component =
  max(0.0, min(1.0, 2.0 * (score_final - 0.5)))
```

```text
score_final += bookmark_rate.ranking_weight * score_bookmark_component
```

## Scope Boundary Versus Existing Signals

FR-088 must stay separate from:

- `FR-024` engagement read-through -- measures in-session behaviour, not intent-to-return.
- `FR-076` dwell-time profile -- measures time-on-page, not save behaviour.
- `FR-075` watch-time completion -- measures video completion, not page saving.

## Inputs Required

- GA4 `bookmark_event` counts per page -- from existing analytics sync
- GA4 `page_view` counts per page -- already available

## Settings And Feature-Flag Plan

### Operator-facing settings

Recommended keys (from `recommended_weights.py`):

- `bookmark_rate.enabled`
- `bookmark_rate.ranking_weight`
- `bookmark_rate.laplace_denominator`

Defaults:

- `enabled = true`
- `ranking_weight = 0.02`
- `laplace_denominator = 10`

## Diagnostics And Explainability Plan

Required fields:

- `score_bookmark_rate`
- `bookmark_rate_state` (`computed`, `neutral_feature_disabled`, `neutral_no_save_data`, `neutral_processing_error`)
- `save_count` -- raw save events
- `view_count` -- raw page views
- `raw_save_rate` -- unsmoothed saves/views
- `smoothed_save_rate` -- with Laplace denominator

Plain-English review helper text should say:

- `Save/bookmark rate measures what fraction of visitors save this page for later.`
- `A high score means visitors find this page valuable enough to return to.`

## Storage / Model / API Impact

### Content model

Add:

- `score_bookmark_rate: FloatField(default=0.5)`
- `bookmark_rate_diagnostics: JSONField(default=dict, blank=True)`

### Backend API

Add:

- `GET /api/settings/bookmark-rate/`
- `PUT /api/settings/bookmark-rate/`

## Recommended Preset Integration

### `recommended_weights.py` entries (already forward-declared)

```python
"bookmark_rate.enabled": "true",
"bookmark_rate.ranking_weight": "0.02",
"bookmark_rate.laplace_denominator": "10",
```
