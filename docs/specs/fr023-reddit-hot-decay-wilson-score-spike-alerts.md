# FR-023 - Reddit Hot Decay, Wilson Score Confidence & Traffic Spike Alerts

## Confirmation

- `FR-023` is a real backlog item in `FEATURE-REQUESTS.md`.
- It is queued for `Phase 26`.
- This spec is written before implementation because the user explicitly requested the build blueprint in advance.
- Repo confirmed:
  - `FR-021` defines the value model with a `traffic_signal` slot fed by a flat 90-day normalized `SearchMetric` average — this is the one slot this FR improves;
  - `FR-016` explicitly defers traffic data from live ranking in its first pass — this FR must not touch `score_final`;
  - `FR-019` defines the `emit_operator_alert()` helper and the stable event type registry — this FR adds two new event types to it;
  - `FR-007` (link freshness) and `velocity.py` (half-life decay) already handle time-decay on link patterns and content activity — this FR must not add a third decay function to `score_final`;
  - no logarithmic time-decay normalization exists on the `traffic_signal` slot in FR-021 today;
  - no CTR confidence weighting exists anywhere in the codebase today;
  - no Hot-score-based spike alert exists — FR-019's `analytics.gsc_spike` is triggered by raw impression/click delta, which is a different and complementary check.

## Scope Statement

This FR has exactly three parts. Each part has a hard boundary.

| Part | What it does | Where it lives | What it must NOT do |
|---|---|---|---|
| 1. Reddit Hot decay | Replaces the flat 90-day normalization inside FR-021's `traffic_signal` computation | FR-021 value model only | Must not touch `score_final` in the main ranker |
| 2. Wilson Score | Displays a confidence-adjusted CTR in the FR-016 telemetry review UI | Display/diagnostics only | Must not feed into any score at any layer |
| 3. Hot-score spike alerts | Fires a new `analytics.hot_score_spike` alert when momentum rises sharply | FR-019 alert system only | Must not change ranking or suggestion ordering |

Nothing in this FR changes `score_final`, `score_link_freshness`, or any existing ranking weight.

## Current Repo Map

### FR-021 value model traffic_signal slot

- `backend/apps/knowledge_graph/services.py` (added by FR-021)
  - `traffic_signal` currently reads `SearchMetric` rows for the destination, computes a 90-day normalized average, and returns a bounded [0, 1] value.
  - Falls back to `0.5` when no `SearchMetric` rows exist.
  - This flat average is what FR-023 replaces with Reddit Hot decay normalization.

### FR-016 telemetry schema

- `backend/apps/analytics/models.py`
  - `SearchMetric` — daily coarse GSC/GA4 data per `ContentItem`:
    - `impressions`, `clicks`, `ctr`, `average_position`, `page_views`, `sessions`.
  - `SuggestionTelemetryDaily` (added by FR-016):
    - `date`, `suggestion_id`, `impressions`, `clicks`, `engaged_sessions`, `bounce_rate`, `scroll_depth_bucket`.
  - FR-016 review UI will show per-suggestion telemetry; Wilson Score is added there as a display field only.

### FR-019 alert system

- `backend/apps/notifications/services.py` (added by FR-019)
  - `emit_operator_alert()` — the canonical helper for creating `OperatorAlert` rows.
- Existing stable event types include `analytics.gsc_spike` and `analytics.gsc_spike_resolved`.
- Two new event types are added by this FR: `analytics.hot_score_spike` and `analytics.hot_score_spike_resolved`.

### Existing decay functions — must not be touched

- `backend/apps/pipeline/services/velocity.py`
  - uses a 21-day half-life logarithmic decay on content activity;
  - stored but not currently wired into `score_final`.
- `backend/apps/pipeline/services/link_freshness.py` (FR-007)
  - tracks link-pattern growth vs past window;
  - contributes to `score_link_freshness` in `score_final` via `link_freshness_ranking_weight`.

## Workflow Drift / Doc Mismatch Found During Inspection

- FR-021 spec specifies a flat 90-day normalized `traffic_signal`. This is a deliberate first-pass simplification that FR-023 is explicitly designed to improve. No mismatch — this improvement is expected.
- FR-016 spec says *"Do not let GA4 metrics directly change `score_final` in the first implementation pass."* FR-023 respects this fully: the Reddit Hot score feeds into the FR-021 value model pre-ranking slot only, never into `score_final`.
- FR-019's `analytics.gsc_spike` fires on raw impression/click deltas. FR-023's `analytics.hot_score_spike` fires on the Hot score momentum delta. They are complementary and use different math. No overlap.

## Source Summary

### External research used

- Reddit Hot ranking algorithm — original Haskell source and community documentation.
- Reddit Best comment ranking — Wilson Score confidence interval application.
- Evan Miller — "How Not To Sort By Average Rating" (Wilson Score reference article).

### Key facts extracted

**Reddit Hot formula:**

```
score = log10(max(abs(ups − downs), 1)) + submission_epoch_seconds / 45000
```

The key insight: every 10× increase in votes adds only 1 point. Time adds a fixed bonus per second. Combined effect: a page needs exponentially more engagement to stay "hot" as it ages.

Adapted for traffic (no downvotes, no submission epoch):

```
hot_score = log10(max(traffic_volume, 1)) − gravity × age_in_days
```

Where:
- `traffic_volume` = weighted combination of recent clicks and impressions.
- `gravity` = configurable decay rate (default: `0.05` per day).
- Age is measured from the most recent `SearchMetric` row date, not from content creation date.

This means a page needs 10× more traffic to maintain the same Hot score after `log10(10) / gravity = 20` days at the default gravity. Operators can tune gravity up (faster decay) or down (slower decay).

**Wilson Score lower bound:**

```
(p + z²/2n − z × sqrt(p(1−p)/n + z²/4n²)) / (1 + z²/n)
```

Where:
- `p` = observed CTR (clicks / impressions).
- `n` = total impressions.
- `z` = 1.96 for 95% confidence.

A page with 10 clicks on 10 impressions (100% CTR) gets a Wilson lower bound of ~0.72.
A page with 10 clicks on 10,000 impressions (0.1% CTR) gets a Wilson lower bound of ~0.0008.
This prevents low-sample outliers from looking like high-performers.

### What was clear

- Reddit Hot decay belongs in FR-021's `traffic_signal` slot only — it is a better normalization of the same data, not a new signal.
- Wilson Score belongs in the review UI only — it is a confidence label, not a ranking input.
- Hot-score spike detection is genuinely new. It fires on traffic *momentum* (rate of Hot score change), not on raw absolute volume. FR-019's existing `analytics.gsc_spike` fires on raw volume. They measure different things and do not conflict.
- Both Reddit Hot and Wilson Score are pure arithmetic. No ML dependency. No new infrastructure.

### What remained ambiguous

- Whether the gravity decay parameter should be per-content-type or site-wide.
- Whether the Hot score spike alert should link to the FR-022 health dashboard or the FR-016 telemetry review page.
- Whether Wilson Score should also be surfaced in the FR-022 health card diagnostics in a future pass.

## Problem Definition

Simple version first.

FR-021's `traffic_signal` uses a flat 90-day average. A page that was popular six months ago and dead today looks the same as a page that started picking up traffic this week. The linker cannot tell the difference.

The fix has three independent parts:

**Part 1:** Replace the flat average with Reddit Hot decay math. Recent traffic counts for more. Old traffic decays. The linker naturally favors pages that are gaining momentum right now.

**Part 2:** Show operators a confidence label next to CTR figures in the telemetry UI. "This 80% CTR is based on 5 impressions" is very different from "this 80% CTR is based on 50,000 impressions." Wilson Score makes that difference visible.

**Part 3:** Alert operators when a page's Hot score rises sharply — a different signal from raw impression spikes. A new page with 50 targeted clicks has a high Hot score relative to its age. The existing `analytics.gsc_spike` would not fire on 50 clicks. The new alert would.

---

## Part 1 — Reddit Hot Decay in FR-021 Value Model

### Scope

This part modifies exactly one function inside the FR-021 knowledge-graph service: the function that computes `traffic_signal` from `SearchMetric` rows.

No other file is touched by Part 1.

### Adapted formula

```python
import math

def compute_hot_traffic_signal(
    search_metrics: list[SearchMetric],
    *,
    clicks_weight: float = 1.0,
    impressions_weight: float = 0.05,
    gravity: float = 0.05,
    fallback: float = 0.5,
    site_hot_scores: list[float],  # pre-computed across all ContentItems for normalization
) -> float:
    """
    Replaces the flat 90-day average in the FR-021 traffic_signal slot.

    For each daily SearchMetric row:
        traffic_volume = clicks × clicks_weight + impressions × impressions_weight
        age_in_days = (today − row.date).days
        row_hot_score = log10(max(traffic_volume, 1)) − gravity × age_in_days

    Final raw hot score = sum of all row_hot_scores (recent days dominate).
    Normalized to [0, 1] using min-max across the full site distribution.
    Falls back to `fallback` (default 0.5) when no SearchMetric rows exist.
    """
```

### Why sum of row scores, not just most-recent row

Using the sum of daily row scores rewards pages that have had sustained recent traffic, not just a one-day spike. Each row contributes less as it ages. Old rows eventually contribute near zero at high gravity settings.

### Normalization

The raw hot score is not bounded naturally. It must be normalized site-wide before it enters the value model.

Method: min-max normalization across all `ContentItem` hot scores computed in the same pipeline run.

This is the same normalization pattern already used for PageRank in FR-006.

### New settings for this part

Add to `GET/PUT /api/settings/value-model/` (the settings API added by FR-021):

- `hot_decay_enabled` (bool, default: `true`)
  - When `false`, falls back to the original flat 90-day average. Allows instant rollback.
- `hot_gravity` (float, default: `0.05`)
  - Decay rate per day. Higher = faster decay. Range: `0.01` to `0.5`.
- `hot_clicks_weight` (float, default: `1.0`)
  - Relative weight of clicks vs impressions in traffic volume calculation.
- `hot_impressions_weight` (float, default: `0.05`)
  - Relative weight of impressions in traffic volume calculation.
- `hot_lookback_days` (int, default: `90`)
  - How many days of `SearchMetric` rows to include. Replaces the existing `traffic_lookback_days` field when Hot decay is enabled.

### Diagnostics added to `value_model_diagnostics`

Extend the `value_model_diagnostics` JSON already defined in FR-021:

```json
{
  "traffic_signal": 0.68,
  "traffic_data_source": "search_metric",
  "traffic_normalization": "hot_decay",
  "hot_gravity": 0.05,
  "hot_raw_score": 4.21,
  "hot_rows_used": 47,
  "hot_most_recent_row_date": "2026-03-27",
  "hot_fallback_used": false
}
```

When `hot_decay_enabled = false`, `traffic_normalization` is `"flat_90d_average"` and the hot-specific fields are absent.

### What does NOT change

- The `traffic_signal` weight in the value model (`w_traffic`) is unchanged.
- The value model formula is unchanged.
- The FR-021 pipeline integration point is unchanged.
- `score_final` in the main ranker is unchanged.
- FR-007 `score_link_freshness` is unchanged.
- `velocity.py` half-life decay is unchanged.

---

## Part 2 — Wilson Score in FR-016 Telemetry Review UI

### Scope

This part adds a display-only computed field to the FR-016 telemetry review UI.

It does not:
- write any new database column;
- feed into any score or ranking weight;
- change any existing model or API.

It does:
- compute Wilson Score lower bounds in the serializer or view layer;
- display them alongside raw CTR figures in the review UI.

### Formula implementation

```python
import math

def wilson_score_lower_bound(
    clicks: int,
    impressions: int,
    z: float = 1.96,  # 95% confidence
) -> float | None:
    """
    Returns the lower bound of the Wilson Score 95% confidence interval for CTR.
    Returns None when impressions == 0.
    """
    if impressions == 0:
        return None
    n = impressions
    p = clicks / n
    lower = (
        p + z**2 / (2 * n)
        - z * math.sqrt((p * (1 - p) / n) + z**2 / (4 * n**2))
    ) / (1 + z**2 / n)
    return max(lower, 0.0)
```

### Where it appears in the UI

On the FR-016 suggestion telemetry review panel, next to each CTR figure:

```
CTR: 12.4%   (Wilson 95% CI lower bound: 9.1%  |  n = 483 impressions)
CTR: 80.0%   (Wilson 95% CI lower bound: 28.4% |  n = 5 impressions — low confidence)
```

Show a plain-English confidence label:

| Impressions | Label |
|---|---|
| < 20 | `low confidence` |
| 20 – 99 | `moderate confidence` |
| 100 – 499 | `good confidence` |
| ≥ 500 | `high confidence` |

### API change

The `GET /api/analytics/telemetry/<suggestion_id>/` endpoint (added by FR-016) gains two computed read-only fields in its response:

```json
{
  "ctr": 0.124,
  "impressions": 483,
  "wilson_lower_bound": 0.091,
  "wilson_confidence_label": "good confidence"
}
```

These are computed on read, not stored. No migration needed.

### What does NOT change

- No model fields are added or changed.
- No ranking weight is added or changed.
- `score_final` is unchanged.
- FR-016's "no live ranking from telemetry in first pass" rule is fully respected.

---

## Part 3 — Hot-Score Spike Alerts in FR-019 Alert System

### Scope

This part adds two new stable event types to the FR-019 alert registry and a new periodic detection task.

It does not change ranking, suggestion ordering, or any score.

### How this differs from `analytics.gsc_spike`

| | `analytics.gsc_spike` (FR-019) | `analytics.hot_score_spike` (FR-023) |
|---|---|---|
| Trigger | Raw impressions or clicks delta above threshold | Hot score momentum — rate of change in the decay-adjusted score |
| Detects | Sudden volume jumps on any page | Pages gaining momentum relative to their age |
| Example it catches | A page going from 100 to 500 impressions | A new page with 50 targeted clicks — high Hot score for its age even if raw volume is modest |
| Example it misses | — | A page that always has 500 impressions (stable Hot score, no spike) |

They are complementary. Both should be enabled.

### New stable event types

Add to the FR-019 event type registry:

- `analytics.hot_score_spike`
- `analytics.hot_score_spike_resolved`

These names are stable from the moment they are shipped and must not be renamed.

### Detection logic

New Celery periodic task: `detect_hot_score_spikes`

Default schedule: daily (or after each analytics sync run).

Per-`ContentItem` algorithm:

1. Compute the current Hot score using the same formula as Part 1.
2. Compute the 7-day trailing average Hot score using the same formula over the 7-day window ending 8 days ago (avoids overlap with today's data).
3. Compute momentum: `delta = current_hot_score − trailing_average`.
4. Compute relative lift: `relative_lift = delta / max(trailing_average, 0.001)`.
5. If both thresholds are crossed:
   - `delta ≥ hot_spike_min_delta` (default: `1.5` log units)
   - `relative_lift ≥ hot_spike_min_relative_lift` (default: `0.5` = 50% increase)
6. Emit `analytics.hot_score_spike` via `emit_operator_alert()`.
7. If a previously-spiking item's hot score has fallen back below threshold: emit `analytics.hot_score_spike_resolved`.

### Alert payload

```json
{
  "event_type": "analytics.hot_score_spike",
  "severity": "warning",
  "title": "Traffic momentum spike detected",
  "message": "\"[Article Title]\" is gaining traffic momentum faster than usual. Consider reviewing it for internal link opportunities.",
  "related_route": "/review?content_item_id=<id>",
  "payload": {
    "content_item_id": 123,
    "content_type": "thread",
    "current_hot_score": 6.82,
    "trailing_average_hot_score": 4.21,
    "delta": 2.61,
    "relative_lift": 0.62,
    "most_recent_metric_date": "2026-03-27",
    "impressions_today": 412,
    "clicks_today": 51
  }
}
```

Dedupe key: `analytics.hot_score_spike:<content_item_id>:<date>`

Cooldown: 24 hours per item per day. A persistently-hot page fires once per day at most.

### Alert severity rules

| Relative lift | Severity |
|---|---|
| 50% – 99% | `warning` |
| ≥ 100% | `urgent` |

### New settings

Add to `GET/PUT /api/settings/health/` (the health settings API added by FR-022) or to a new `GET/PUT /api/settings/hot-spike-alerts/` endpoint if FR-022 is not yet implemented:

- `hot_spike_alerts_enabled` (bool, default: `true`)
- `hot_spike_min_delta` (float, default: `1.5`)
- `hot_spike_min_relative_lift` (float, default: `0.5`)
- `hot_spike_trailing_window_days` (int, default: `7`)
- `hot_spike_cooldown_hours` (int, default: `24`)

### What does NOT change

- Suggestion ranking is unchanged.
- `score_final` is unchanged.
- FR-019's existing `analytics.gsc_spike` logic is unchanged.
- The alert only points operators toward a page. It does not auto-approve or auto-inject any link.

---

## Settings UI

### Part 1 — additions to the FR-021 settings card

Add to the **Graph Candidate Generation & Value Scoring** settings card:

Under the traffic signal section:

- Toggle: **Use Reddit Hot decay for traffic signal** (on/off, default: on).
- Slider: **Gravity / decay rate** (0.01 – 0.5, default: 0.05). Help text: "Higher = older traffic fades faster."
- Slider: **Clicks weight** (0.1 – 5.0, default: 1.0).
- Slider: **Impressions weight** (0.01 – 1.0, default: 0.05). Help text: "Impressions count for less than clicks by default."
- Read-only: **Traffic normalization method**: "Hot decay (log10)" or "Flat 90-day average (fallback)".

### Part 2 — no new settings card

Wilson Score is display-only. No settings needed.

### Part 3 — spike alert settings

Add a new section **Traffic Momentum Spike Alerts** to the existing notification settings page (or the FR-022 health settings card):

- Toggle: **Enable Hot-score spike alerts** (on/off, default: on).
- Number field: **Minimum score delta** (default: 1.5).
- Number field: **Minimum relative lift %** (default: 50%).
- Number field: **Trailing window days** (default: 7).
- Number field: **Alert cooldown hours** (default: 24).

---

## Dependencies

| This FR requires | Why |
|---|---|
| FR-021 (Graph value model) | Part 1 modifies FR-021's `traffic_signal` computation |
| FR-016 (GA4 telemetry) | Part 2 adds Wilson display to FR-016's telemetry review panel |
| FR-019 (Operator alerts) | Part 3 uses `emit_operator_alert()` and the stable event type registry |

FR-022 (Health dashboard) is recommended but not required. Part 3 spike alert settings can live in the notification settings page until FR-022 is available.

---

## Test Plan

### Part 1 — Hot decay signal

- A page with high recent traffic and low old traffic scores higher than a page with the reverse pattern.
- Gravity `0.0` produces the same ranking as the original flat average (sanity check).
- High gravity (0.5) decays old traffic to near-zero after 10 days.
- Missing `SearchMetric` rows fall back to `0.5` exactly.
- `hot_decay_enabled = false` uses the old flat average and omits hot-specific diagnostics.
- Normalized output is bounded [0, 1].
- `value_model_diagnostics` contains all hot-specific fields when enabled.

### Part 2 — Wilson Score

- `wilson_score_lower_bound(10, 10)` returns ~0.72.
- `wilson_score_lower_bound(0, 0)` returns `None`.
- `wilson_score_lower_bound(1, 1000)` returns a very small positive number.
- API response includes `wilson_lower_bound` and `wilson_confidence_label`.
- Low-confidence label shows for impressions < 20.
- High-confidence label shows for impressions ≥ 500.
- Wilson fields do not appear in any scoring or ranking test — they are display-only.

### Part 3 — Spike alerts

- An item with a 60% relative Hot score lift fires a `warning` alert.
- An item with a 110% relative Hot score lift fires an `urgent` alert.
- Same item does not fire a second alert within cooldown window.
- An item whose score returns to baseline fires `analytics.hot_score_spike_resolved`.
- Dedupe key prevents duplicate rows for the same item on the same day.
- `hot_spike_alerts_enabled = false` disables the task without error.
- Existing `analytics.gsc_spike` logic is unmodified by this task.

---

## Acceptance Criteria

**Part 1:**
- The FR-021 value model `traffic_signal` uses Reddit Hot decay normalization by default.
- Operators can toggle back to the flat average with one switch.
- All decay parameters are configurable.
- Diagnostics show which normalization method was used per suggestion.

**Part 2:**
- Wilson Score lower bound and confidence label appear next to CTR in the FR-016 telemetry review UI.
- Wilson figures are computed on read, stored nowhere, and do not influence any score.

**Part 3:**
- `analytics.hot_score_spike` fires when a page's traffic momentum rises above threshold.
- `analytics.hot_score_spike_resolved` fires when the same page's momentum returns to baseline.
- Alerts are delivered via FR-019 bell center with correct severity, dedupe, and cooldown.
- Spike alert thresholds are configurable.
- FR-019's existing `analytics.gsc_spike` is unaffected.

---

## Out-of-Scope Follow-Up

- Feeding Hot score directly into `score_final` — belongs to FR-018 auto-tuning after telemetry matures.
- Wilson Score confidence gating on auto-tuning promotions — belongs to FR-018.
- Reddit "Best" comment ranking (Bayesian average for anchor text quality) — separate FR if needed.
- Per-content-type gravity tuning (different decay rate for threads vs posts) — Phase 27+ follow-up.
- Displaying Wilson Score in the FR-022 health card — out of scope for first pass.
