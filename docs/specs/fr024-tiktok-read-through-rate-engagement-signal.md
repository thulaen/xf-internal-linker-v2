# FR-024 - TikTok Read-Through Rate — Engagement Signal

## Confirmation

- `FR-024` is a real backlog item in `FEATURE-REQUESTS.md`.
- It is queued for `Phase 27`.
- This spec is written before implementation because the user explicitly requested the build blueprint in advance.
- Repo confirmed:
  - `SearchMetric` already stores `avg_engagement_time` (FloatField, seconds) and `bounce_rate` (FloatField, nullable) from GA4;
  - `ContentItem.distilled_text` already exists and contains cleaned body text suitable for word-count estimation;
  - FR-021 defines a five-signal value model (`relevance`, `traffic`, `freshness`, `authority`, `penalty`) in the pre-ranking pass;
  - no engagement quality signal exists in the value model or anywhere in the scoring pipeline today;
  - FR-016 also collects `avg_engagement_time_seconds` per suggestion but defers it from ranking;
  - this FR uses only page-level `SearchMetric` data, not FR-016 suggestion-level telemetry.

## Scope Statement

This FR adds exactly one thing: a sixth signal slot called `engagement_signal` to the FR-021 value model.

| What changes | Where |
|---|---|
| New `engagement_signal` computation | FR-021 value model service only |
| New fields in `value_model_diagnostics` | `Suggestion` JSON field only |
| New settings fields | `GET/PUT /api/settings/value-model/` only |
| New settings card controls | FR-021 settings card only |

**Hard boundaries — nothing else is touched:**

- `score_final` in the main ranker is not modified.
- FR-016 suggestion-level telemetry (`SuggestionTelemetryDaily`) is not read or used.
- FR-007 `score_link_freshness` is not modified.
- `velocity.py` is not modified.
- FR-023 `hot_decay` traffic signal computation is not modified.
- The existing five value model signals are not modified or reweighted by default.

## Current Repo Map

### FR-021 value model (the only modified file)

- `backend/apps/knowledge_graph/services.py` (added by FR-021)
  - current formula:
    ```
    value_score = (
        w_relevance   × relevance_signal
      + w_traffic     × traffic_signal
      + w_freshness   × freshness_signal
      + w_authority   × authority_signal
      - w_penalty     × penalty_signal
    )
    ```
  - `traffic_signal` is the slot replaced/augmented by FR-023 Part 1 (Reddit Hot decay).
  - `engagement_signal` is a new sixth additive slot introduced here.

### Data sources used by this FR

- `backend/apps/analytics/models.py`
  - `SearchMetric.avg_engagement_time` — average time on page in seconds, from GA4;
  - `SearchMetric.bounce_rate` — fraction of sessions where the user left without engaging, from GA4.
- `backend/apps/content/models.py`
  - `ContentItem.distilled_text` — cleaned body text, used for word-count estimation only.

### What is NOT used

- `SuggestionTelemetryDaily.avg_engagement_time_seconds` — deferred by FR-016.
- Any GA4 API call at pipeline time — all data is already in `SearchMetric`.

## Workflow Drift / Doc Mismatch Found During Inspection

- FR-021 spec defines five signals. The `value_model_diagnostics` JSON shape in that spec lists exactly five fields. This FR extends that shape by adding two new fields: `engagement_signal` and `read_through_rate_raw`. The FR-021 diagnostics shape is additive; this extension does not break it.
- `SearchMetric.avg_engagement_time` is already being fetched from GA4. It was never wired into scoring. This FR is the first consumer.

## Source Summary

### Concept source

TikTok's recommendation engine prioritises watch time and completion rate over like counts. Applied to content: a page that keeps readers engaged from top to bottom is higher quality than a page that users leave after three seconds, regardless of how many backlinks it has.

### Key insight adapted for internal linking

- An article that holds human attention all the way through is a better link destination than an SEO-stuffed page that users immediately bounce from.
- Read-Through Rate = `avg_engagement_time / estimated_read_time`. A value near 1.0 means people read the whole thing. A value near 0.0 means people leave immediately.
- Bounce rate is a complementary penalty: even if average engagement time looks reasonable, a high bounce rate means most users are leaving without engaging.

### What was clear

- `SearchMetric.avg_engagement_time` is already stored. No new data pipeline needed.
- Word count from `distilled_text` is a reliable estimated read time proxy. No NLP needed.
- The signal belongs in the FR-021 value model pre-ranking pass — same placement as `traffic_signal` and `freshness_signal`.
- FR-016's "no live ranking from suggestion telemetry" rule does not apply here because this FR uses page-level `SearchMetric`, which is a site-wide coarse signal already used elsewhere.

### What remained ambiguous

- Whether to use a rolling average of recent `SearchMetric` rows or just the most recent row. Spec uses a configurable rolling window (default: 30 days) to smooth noise.
- Whether estimated read time should use a fixed WPM constant or vary by content type. Spec uses a single configurable constant (default: 200 WPM) for simplicity.

## Problem Definition

Simple version first.

The FR-021 value model currently scores destination pages by how relevant they are, how much traffic they get, how fresh their links are, and how authoritative they are. It does not ask: do people actually read this page, or do they bounce straight back?

A page stuffed with keywords can have high relevance and high traffic. But if 90% of visitors leave in three seconds, it is a terrible link destination. The linker has no way to know this today.

Read-Through Rate solves this. It measures whether real human attention reaches the end of the page. Pages that hold attention get a higher `engagement_signal`. Pages with high bounce rates get penalised.

## Engagement Signal Formula

### Read-Through Rate

```python
def compute_read_through_rate(
    avg_engagement_time_seconds: float,
    word_count: int,
    words_per_minute: int = 200,
) -> float:
    """
    Estimates what fraction of the article a typical reader completes.

    estimated_read_time_seconds = (word_count / words_per_minute) × 60
    read_through_rate = avg_engagement_time_seconds / estimated_read_time_seconds

    Returns a raw ratio. Values above 1.0 mean users spend more time than
    the estimated read time (deep readers, re-readers, or tabbed browsing).
    """
    if word_count <= 0:
        return 0.5  # neutral fallback for empty or unprocessed content

    estimated_read_time_seconds = (word_count / words_per_minute) * 60

    if estimated_read_time_seconds <= 0:
        return 0.5

    return avg_engagement_time_seconds / estimated_read_time_seconds
```

### Bounce penalty

```python
def apply_bounce_penalty(
    read_through_rate: float,
    bounce_rate: float | None,
) -> float:
    """
    Penalises pages where most users leave without engaging.

    engagement_quality = read_through_rate × (1.0 - bounce_rate)

    If bounce_rate is None (not available), no penalty is applied.
    """
    if bounce_rate is None:
        return read_through_rate
    return read_through_rate * (1.0 - bounce_rate)
```

### Normalization to [0, 1]

```python
def normalize_engagement_signal(
    engagement_quality: float,
    site_engagement_scores: list[float],
    cap_ratio: float = 1.5,
) -> float:
    """
    Clamps and normalizes engagement_quality to [0, 1].

    Step 1: Cap at cap_ratio (default 1.5) to prevent extreme outliers
            from collapsing all other pages to near-zero.
    Step 2: Min-max normalize across the site distribution.

    Falls back to 0.5 (neutral) when site_engagement_scores is empty
    or when the page has no SearchMetric rows.
    """
```

### Rollup across multiple SearchMetric rows

`SearchMetric` stores one row per day per content item. This FR uses a rolling average over the most recent N days (default: 30) to smooth noise.

```python
def aggregate_engagement_metrics(
    search_metrics: list[SearchMetric],
    lookback_days: int = 30,
) -> tuple[float | None, float | None]:
    """
    Returns (avg_engagement_time_seconds, avg_bounce_rate) averaged
    across the most recent `lookback_days` SearchMetric rows.
    Returns (None, None) when no rows exist in the window.
    """
```

### Complete engagement_signal function

```python
def compute_engagement_signal(
    content_item: ContentItem,
    search_metrics: list[SearchMetric],
    site_engagement_scores: list[float],
    *,
    lookback_days: int = 30,
    words_per_minute: int = 200,
    cap_ratio: float = 1.5,
    fallback: float = 0.5,
) -> tuple[float, dict]:
    """
    Returns (engagement_signal, diagnostics_dict).

    engagement_signal is bounded [0, 1].
    diagnostics_dict contains all intermediate values for display.
    """
    avg_eng_time, avg_bounce = aggregate_engagement_metrics(
        search_metrics, lookback_days
    )

    if avg_eng_time is None:
        return fallback, {"engagement_fallback_used": True}

    word_count = len(content_item.distilled_text.split())
    rtr = compute_read_through_rate(avg_eng_time, word_count, words_per_minute)
    eq = apply_bounce_penalty(rtr, avg_bounce)
    signal = normalize_engagement_signal(eq, site_engagement_scores, cap_ratio)

    return signal, {
        "engagement_signal": signal,
        "read_through_rate_raw": rtr,
        "engagement_quality_raw": eq,
        "avg_engagement_time_seconds": avg_eng_time,
        "avg_bounce_rate": avg_bounce,
        "word_count": word_count,
        "estimated_read_time_seconds": (word_count / words_per_minute) * 60,
        "engagement_metric_rows_used": ...,
        "engagement_fallback_used": False,
    }
```

## Updated Value Model Formula

```
value_score = (
    w_relevance    × relevance_signal
  + w_traffic      × traffic_signal
  + w_freshness    × freshness_signal
  + w_authority    × authority_signal
  + w_engagement   × engagement_signal    ← new
  - w_penalty      × penalty_signal
)
```

Default weight: `w_engagement = 0.1`

The existing five weights do not change. The new signal is additive.

Because the formula now has five positive terms, the theoretical maximum unnormalized score increases slightly. The value model's output is already normalized before the main ranker sees it, so this does not affect `score_final` bounds.

## Settings API Changes

Extend `GET/PUT /api/settings/value-model/` with:

- `engagement_signal_enabled` (bool, default: `true`)
  - When `false`, `engagement_signal` returns the fallback value (0.5) and the slot has no effect.
- `w_engagement` (float, default: `0.1`)
  - Weight of the engagement signal in the value model formula.
- `engagement_lookback_days` (int, default: `30`)
  - How many days of `SearchMetric` rows to average.
- `engagement_words_per_minute` (int, default: `200`)
  - Reading speed used to estimate read time.
- `engagement_cap_ratio` (float, default: `1.5`)
  - Raw read-through rates above this value are clamped before normalization.
- `engagement_fallback_value` (float, default: `0.5`)
  - Value returned when no `SearchMetric` rows exist for a destination.

## Diagnostics Changes

Extend `value_model_diagnostics` JSON on `Suggestion` (already defined by FR-021) with:

```json
{
  "relevance_signal": 0.82,
  "traffic_signal": 0.68,
  "freshness_signal": 0.74,
  "authority_signal": 0.55,
  "engagement_signal": 0.71,
  "penalty_signal": 0.0,
  "weights": {
    "w_relevance": 0.4,
    "w_traffic": 0.3,
    "w_freshness": 0.1,
    "w_authority": 0.1,
    "w_engagement": 0.1,
    "w_penalty": 0.5
  },
  "value_score": 0.734,
  "read_through_rate_raw": 0.83,
  "engagement_quality_raw": 0.71,
  "avg_engagement_time_seconds": 148.2,
  "avg_bounce_rate": 0.14,
  "word_count": 1420,
  "estimated_read_time_seconds": 426.0,
  "engagement_metric_rows_used": 28,
  "engagement_fallback_used": false
}
```

## Settings UI

Add to the existing **Graph Candidate Generation & Value Scoring** settings card (added by FR-021):

Under a new sub-section: **Engagement Quality Signal (Read-Through Rate)**

- Toggle: **Enable engagement signal** (on/off, default: on).
- Slider: **Engagement weight** (0.0 – 0.5, default: 0.1).
- Number field: **Lookback window** (days, default: 30).
- Number field: **Reading speed** (WPM, default: 200). Help text: "Used to estimate how long each article takes to read."
- Number field: **Cap ratio** (default: 1.5). Help text: "Read-through rates above this are capped to prevent outliers."

## Review UI Changes

On the suggestion review detail panel, extend the value model breakdown to show:

- `Engagement signal`: score + confidence label.
- `Read-through rate`: raw ratio (e.g. "0.83 — readers typically reach 83% of this article").
- `Avg bounce rate`: percentage.
- `Avg engagement time`: seconds.
- `Estimated read time`: seconds.
- `Data rows used`: count.
- "No engagement data — using neutral fallback" when `engagement_fallback_used = true`.

## Dependencies

- FR-021 (Graph value model) — this FR modifies FR-021's value model service.
- No other FR dependencies.

## Test Plan

### Backend tests

- `compute_read_through_rate(300, 1000, 200)` returns `1.0` (300s ÷ 300s estimated).
- `compute_read_through_rate(60, 1000, 200)` returns `0.2`.
- `compute_read_through_rate(0, 0, 200)` returns fallback `0.5`.
- `apply_bounce_penalty(0.8, 0.5)` returns `0.4`.
- `apply_bounce_penalty(0.8, None)` returns `0.8` unchanged.
- Normalization output is bounded [0, 1] for any valid input.
- Rolling average correctly uses only rows within `lookback_days`.
- `engagement_signal_enabled = false` returns `0.5` and sets `engagement_fallback_used = True`.
- `value_model_diagnostics` contains all new fields.
- Existing five signal computations produce identical output before and after this FR.

### Frontend tests

- Settings card renders engagement sub-section with all controls.
- Review detail shows engagement breakdown correctly.
- "No engagement data" copy shows when fallback is used.

### Manual verification

- Run pipeline on content with known high and low engagement times.
- Confirm high-engagement destination pages surface higher in the pre-ranking pass.
- Confirm `value_model_diagnostics` populated on all new suggestions.
- Confirm `engagement_signal_enabled = false` produces `engagement_signal = 0.5` across the board.

## Acceptance Criteria

- `engagement_signal` is the sixth slot in the FR-021 value model.
- It is computed from `SearchMetric.avg_engagement_time` and `bounce_rate` only. No FR-016 suggestion-level data is used.
- Word count is estimated from `ContentItem.distilled_text`.
- Missing data falls back cleanly to 0.5.
- All parameters are configurable and documented in the settings card.
- Suggestion diagnostics show the full engagement breakdown.
- `score_final` in the main ranker is unchanged.

## Out-of-Scope Follow-Up

- Using FR-016 suggestion-level `avg_engagement_time_seconds` as input (belongs to FR-018 after telemetry matures).
- Per-content-type WPM calibration (short posts vs long guides).
- Scroll depth as a direct read-through proxy (FR-016 collects `scroll_50` as a boolean trigger, not a continuous depth).
- Dwell time anomaly detection for alerting (could be added to FR-023 Part 3 spike alerts later).
