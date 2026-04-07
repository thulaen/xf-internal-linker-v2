# FR-085 - Content Format Preference Signal

## Confirmation

- **Backlog confirmed**: `FR-085 - Content Format Preference Signal` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No format affinity or content-type matching signal exists in the current ranker. The closest signal is `FR-040` (multimedia boost), which rewards the presence of multimedia. FR-085 measures whether the destination's format matches what the source page's audience prefers -- a fundamentally different axis.
- **Repo confirmed**: GA4 event data with content format metadata is available via the analytics sync pipeline.

## Source Summary

### Patent: US20190050433A1 -- Content Format Preference Signal (Snap)

**Plain-English description of the patent:**

The patent describes scoring content by format affinity -- matching the content format (text-heavy, image-heavy, video-heavy) to the user's demonstrated preference. Users who engage primarily with text content prefer text-heavy destinations; users who engage primarily with video prefer video-heavy destinations.

**What is adapted for this repo:**

- "user preference" maps to the dominant content format consumed by the source page's audience (derived from GA4 event types);
- "format match" checks whether the destination page's format matches this audience preference;
- a match scores high; a mismatch scores with a configurable penalty.

## Plain-English Summary

Simple version first.

Readers who spend time on text-heavy articles prefer more text. Readers who spend time watching videos prefer more video. If a source page attracts text readers, linking to a video-heavy destination may not serve them well.

FR-085 matches the format preference of the source page's audience with the destination page's dominant format. A match gets a full score. A mismatch gets a reduced score.

## Problem Statement

Today the ranker has no awareness of content format alignment. It can link a long-form text article (whose readers prefer text) to a destination that is primarily a video gallery, creating a format mismatch.

FR-085 closes this gap with a simple format affinity check.

## Goals

FR-085 should:

- add a separate, explainable, bounded format preference signal;
- classify pages into dominant format categories (text/image/video);
- score format match between source audience preference and destination format;
- keep ranking impact additive, bounded, and off by default.

## Non-Goals

FR-085 does not:

- modify FR-040 (multimedia boost);
- analyse content quality within any format;
- implement production code in the spec pass.

## Math-Fidelity Note

### Signal definition

Let:

- `format_src` = dominant format consumed by the source page's audience, determined by GA4 event types (scroll = text, image_click = image, video_start = video)
- `format_dst` = dominant format of the destination page (classified at index time from content analysis)
- `mismatch_penalty` = configurable penalty for format mismatch (default 0.50)

**Score:**

```text
If format_src == format_dst:
    score_format_preference = 1.0
Else:
    score_format_preference = mismatch_penalty
```

**Neutral centering:**

```text
score_final = 0.5 + 0.5 * score_format_preference
```

This maps:

- format match -> `score = 1.0`
- format mismatch -> `score = 0.75` (with default penalty 0.50)

**Neutral fallback:**

```text
score_format_preference = 0.5
```

Used when:

- source page has insufficient GA4 data to determine audience format preference;
- destination page cannot be classified;
- feature is disabled.

### Ranking hook

```text
score_format_component =
  max(0.0, min(1.0, 2.0 * (score_final - 0.5)))
```

```text
score_final += format_preference.ranking_weight * score_format_component
```

## Scope Boundary Versus Existing Signals

FR-085 must stay separate from:

- `FR-040` multimedia boost -- rewards presence of multimedia, not format-audience alignment.
- `FR-075` watch-time completion -- measures video completion quality, not format matching.
- `FR-076` dwell-time profile -- measures time-on-page, not content format.

## Inputs Required

- GA4 event types per page (scroll, image_click, video_start) -- from existing analytics sync
- Page format classification -- derived from content analysis at index time

## Settings And Feature-Flag Plan

### Operator-facing settings

Recommended keys (from `recommended_weights.py`):

- `format_preference.enabled`
- `format_preference.ranking_weight`
- `format_preference.mismatch_penalty`

Defaults:

- `enabled = true`
- `ranking_weight = 0.02`
- `mismatch_penalty = 0.50`

## Diagnostics And Explainability Plan

Required fields:

- `score_format_preference`
- `format_preference_state` (`computed`, `neutral_feature_disabled`, `neutral_insufficient_data`, `neutral_processing_error`)
- `source_audience_format` -- dominant format of source audience
- `destination_format` -- classified format of destination
- `is_match` -- boolean

Plain-English review helper text should say:

- `Format preference measures whether the destination's content format matches what the source page's audience prefers.`
- `A high score means format alignment. A lower score means the audience may prefer a different format.`

## Storage / Model / API Impact

### Suggestion model

Add:

- `score_format_preference: FloatField(default=0.5)`
- `format_preference_diagnostics: JSONField(default=dict, blank=True)`

### Backend API

Add:

- `GET /api/settings/format-preference/`
- `PUT /api/settings/format-preference/`

## Recommended Preset Integration

### `recommended_weights.py` entries (already forward-declared)

```python
"format_preference.enabled": "true",
"format_preference.ranking_weight": "0.02",
"format_preference.mismatch_penalty": "0.50",
```
