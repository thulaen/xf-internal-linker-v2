# FR-075 - Watch-Time Completion Rate

## Confirmation

- **Backlog confirmed**: `FR-075 - Watch-Time Completion Rate` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No video completion or watch-time signal exists in the current ranker. The closest signal is `FR-024` (read-through rate), which measures scroll depth on text pages. FR-075 measures video completion ratio -- a fundamentally different engagement metric for video-containing pages.
- **Repo confirmed**: GA4 video event data (video_start, video_progress, video_complete) is available via the analytics sync pipeline.

## Source Summary

### Patent: US9098511B1 -- Watch-Time Completion Rate (Google/YouTube)

**Plain-English description of the patent:**

The patent describes ranking video content by the ratio of viewers who complete watching to those who start watching. Videos with high completion rates deliver on their promise -- viewers who started watching found the content valuable enough to finish.

**Repo-safe reading:**

The patent is YouTube-specific. This repo applies the concept to any page with embedded video using GA4 video events. The reusable core idea is:

- measure the ratio of video completions to video starts;
- high completion = satisfying video content;
- use as a quality signal for pages that contain video.

**What is adapted for this repo:**

- "watch time" maps to GA4 `video_progress` events (>85% = completion);
- "plays" maps to GA4 `video_start` events;
- pages without video default to neutral (0.5).

## Plain-English Summary

Simple version first.

When a page has a video embedded in it, do people actually watch the whole thing? If most viewers watch to the end, the video is probably good. If most viewers bail out early, the video is probably not delivering on its promise.

FR-075 measures this completion ratio. Pages with videos that people actually finish watching get a boost. Pages with videos that people abandon get a neutral or slightly negative signal.

Pages without video are unaffected -- they default to 0.5 (neutral).

## Problem Statement

Today the ranker has no awareness of video engagement quality. A page with a terrible video that 90% of viewers abandon scores the same as a page with an excellent video that 90% of viewers finish.

FR-075 closes this gap for pages containing embedded video content.

## Goals

FR-075 should:

- add a separate, explainable, bounded video completion signal;
- compute it from GA4 video events at index time;
- use Laplace smoothing to handle cold-start pages;
- default to neutral for pages without video;
- keep ranking impact additive, bounded, and off by default.

## Non-Goals

FR-075 does not:

- analyse video content or quality;
- change the read-through rate signal (FR-024);
- require video hosting or transcoding;
- implement production code in the spec pass.

## Math-Fidelity Note

### Signal definition

Let:

- `completions` = count of GA4 sessions where `video_progress > 0.85` for any video on the page
- `plays` = count of GA4 `video_start` events for any video on the page
- `alpha = 1` (Laplace smoothing constant)

**Laplace-smoothed completion rate:**

```text
completion_rate = (completions + alpha) / (plays + 2 * alpha)
```

Laplace smoothing ensures:

- a page with 0 completions and 0 plays scores `1/2 = 0.5` (neutral prior)
- a page with many completions converges to the true rate

**Final score:**

```text
score_watch_completion = completion_rate
```

Already bounded in `(0, 1)` by the Laplace formula.

**No-video fallback:**

```text
score_watch_completion = no_video_default    (default 0.5)
```

Used when:

- page has no embedded video;
- no GA4 video events exist for this page;
- feature is disabled.

### Why Laplace smoothing

Without smoothing, a page with 1 completion and 1 play scores `1.0` -- indistinguishable from a page with 10000 completions and 10000 plays. Laplace smoothing (`alpha = 1`) pulls small-sample pages toward the neutral prior of 0.5, letting the score converge to the true rate as data accumulates.

### Ranking hook

```text
score_completion_component =
  max(0.0, min(1.0, 2.0 * (score_watch_completion - 0.5)))
```

```text
score_final += watch_completion.ranking_weight * score_completion_component
```

Default: `ranking_weight = 0.0` -- diagnostics only until validated.

## Scope Boundary Versus Existing Signals

FR-075 must stay separate from:

- `FR-024` engagement read-through rate -- measures text scroll depth, not video completion.
- `FR-040` multimedia boost -- rewards the presence of multimedia, not its engagement quality.
- `FR-076` dwell-time profile match -- measures time-on-page patterns, not video-specific completion.

Hard rule: FR-075 must not modify any engagement metric used by FR-024 or FR-040.

## Inputs Required

- GA4 `video_start` events per page
- GA4 `video_progress` events per page (with progress percentage)
- GA4 `video_complete` events per page

## Settings And Feature-Flag Plan

### Operator-facing settings

Recommended keys (from `recommended_weights.py`):

- `watch_completion.enabled`
- `watch_completion.ranking_weight`
- `watch_completion.completion_threshold`
- `watch_completion.laplace_alpha`
- `watch_completion.no_video_default`

Defaults:

- `enabled = true`
- `ranking_weight = 0.02`
- `completion_threshold = 0.85`
- `laplace_alpha = 1`
- `no_video_default = 0.5`

## Diagnostics And Explainability Plan

Required fields:

- `score_watch_completion`
- `watch_completion_state` (`computed`, `neutral_feature_disabled`, `neutral_no_video`, `neutral_processing_error`)
- `total_plays` -- raw play count
- `total_completions` -- raw completion count
- `raw_completion_rate` -- unsmoothed rate
- `smoothed_completion_rate` -- Laplace-smoothed rate
- `has_video` -- boolean

Plain-English review helper text should say:

- `Watch-time completion rate measures what fraction of video viewers finish watching the embedded video.`
- `A high score means most viewers who start the video watch it to completion.`
- `Pages without video default to neutral and are unaffected.`

## Storage / Model / API Impact

### Content model

Add:

- `score_watch_completion: FloatField(default=0.5)`
- `watch_completion_diagnostics: JSONField(default=dict, blank=True)`

### PipelineRun snapshot

Add FR-075 settings and algorithm version to `PipelineRun.config_snapshot`.

### Backend API

Add:

- `GET /api/settings/watch-completion/`
- `PUT /api/settings/watch-completion/`

## Recommended Preset Integration

### `recommended_weights.py` entries (already forward-declared)

```python
"watch_completion.enabled": "true",
"watch_completion.ranking_weight": "0.02",
"watch_completion.completion_threshold": "0.85",
"watch_completion.laplace_alpha": "1",
"watch_completion.no_video_default": "0.5",
```

**Why these values:**

- `ranking_weight = 0.02` -- conservative. Video completion only applies to pages with video; limited corpus coverage.
- `completion_threshold = 0.85` -- 85% watched is the standard YouTube definition of "completed".
- `laplace_alpha = 1` -- standard Laplace prior; pulls low-sample pages toward 0.5.
- `no_video_default = 0.5` -- pages without video should not be penalized or boosted by this signal.
