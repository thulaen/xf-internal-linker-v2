# FR-087 - Reply Thread Depth Signal

## Confirmation

- **Backlog confirmed**: `FR-087 - Reply Thread Depth Signal` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No comment depth or discussion intensity signal exists in the current ranker. The closest signal is `FR-078` (community upvote velocity), which measures first-hour engagement speed. FR-087 measures the depth and structure of comment threads -- a fundamentally different engagement dimension.
- **Repo confirmed**: Comment/reply data can be derived from page metadata or analytics events.

## Source Summary

### Patent: US8954500B2 -- Reply Thread Depth Signal (Twitter)

**Plain-English description of the patent:**

The patent describes measuring content quality by the depth of reply/comment threads it generates. Content that provokes genuine discussion (deep, multi-level threads) is more valuable than content that receives only shallow reactions (single-level likes or shares).

**What is adapted for this repo:**

- "reply threads" maps to comment threads on pages (blog comments, forum replies, discussion sections);
- "depth" is the average nesting level of comment trees;
- deeper threads indicate genuine discussion, not just passive consumption.

## Plain-English Summary

Simple version first.

When a page generates deep comment threads -- where people reply to replies, and those replies get more replies -- it means the content provoked genuine discussion. Compare this to a page that gets a few top-level comments but no real conversation.

FR-087 measures this by computing the average depth of comment trees on each page. Deeper threads = more genuine discussion = higher quality signal.

## Problem Statement

Today the ranker has no awareness of discussion depth. A page with 100 shallow comments scores the same as a page with 20 comments that form deep, multi-level conversations.

FR-087 closes this gap by measuring the structural depth of comment threads.

## Goals

FR-087 should:

- add a separate, explainable, bounded reply depth signal;
- compute average comment tree depth per page;
- cap at a configurable maximum depth;
- keep pages without comments neutral at `0.5`;
- keep ranking impact additive, bounded, and off by default.

## Non-Goals

FR-087 does not:

- analyse comment content or quality;
- modify any engagement signal;
- implement production code in the spec pass.

## Math-Fidelity Note

### Signal definition

Let:

- `threads` = set of comment trees on the page
- `depth(thread)` = maximum nesting level of a comment tree (root = 1, reply to root = 2, etc.)
- `depth_cap` = maximum depth considered (default 5)

**Mean thread depth:**

```text
mean_depth = mean(depth(t) for t in threads)
```

**Capped and normalized score:**

```text
score_reply_depth = min(1.0, mean_depth / depth_cap)
```

This maps:

- `mean_depth = 0` (no threads) -> `score = 0.0`
- `mean_depth = depth_cap` (deep discussions) -> `score = 1.0`
- `mean_depth = 2.5` (moderate depth, cap = 5) -> `score = 0.5`

**Neutral centering:**

```text
score_final = 0.5 + 0.5 * score_reply_depth
```

**Neutral fallback:**

```text
score_reply_depth = 0.5
```

Used when:

- page has no comment section;
- page has comments disabled;
- feature is disabled.

### Ranking hook

```text
score_reply_component =
  max(0.0, min(1.0, 2.0 * (score_final - 0.5)))
```

```text
score_final += reply_depth.ranking_weight * score_reply_component
```

## Scope Boundary Versus Existing Signals

FR-087 must stay separate from:

- `FR-078` upvote velocity -- measures first-hour engagement speed, not thread depth.
- `FR-024` engagement -- measures read-through, not discussion depth.
- `FR-042` fact density -- measures information density, not discussion generation.

## Inputs Required

- Comment tree structure per page -- from page metadata or CMS
- Thread depth computation -- at index time

## Settings And Feature-Flag Plan

### Operator-facing settings

Recommended keys (from `recommended_weights.py`):

- `reply_depth.enabled`
- `reply_depth.ranking_weight`
- `reply_depth.depth_cap`

Defaults:

- `enabled = true`
- `ranking_weight = 0.02`
- `depth_cap = 5`

## Diagnostics And Explainability Plan

Required fields:

- `score_reply_depth`
- `reply_depth_state` (`computed`, `neutral_feature_disabled`, `neutral_no_comments`, `neutral_processing_error`)
- `thread_count` -- number of comment threads
- `mean_thread_depth` -- average depth
- `max_thread_depth` -- deepest thread
- `total_comments` -- total comment count

Plain-English review helper text should say:

- `Reply thread depth measures how deep the discussion goes in this page's comments.`
- `A high score means the content provokes genuine multi-level conversation.`
- `Pages without comments default to neutral.`

## Storage / Model / API Impact

### Content model

Add:

- `score_reply_depth: FloatField(default=0.5)`
- `reply_depth_diagnostics: JSONField(default=dict, blank=True)`

### Backend API

Add:

- `GET /api/settings/reply-depth/`
- `PUT /api/settings/reply-depth/`

## Recommended Preset Integration

### `recommended_weights.py` entries (already forward-declared)

```python
"reply_depth.enabled": "true",
"reply_depth.ranking_weight": "0.02",
"reply_depth.depth_cap": "5",
```
