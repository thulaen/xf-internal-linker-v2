# FR-016 - GA4 + Matomo Suggestion Attribution & User-Behavior Telemetry

## Confirmation

- `FR-016` is a real backlog item in `FEATURE-REQUESTS.md`.
- It is queued for `Phase 19`.
- This spec is being written early because the user explicitly asked for the real blueprint before implementation.
- Repo confirmed: the analytics app exists, but it only stores coarse content-level `GSC` / `GA4` numbers today. There is no suggestion-level attribution, no algorithm-version behavior tracking, and no telemetry charts tied to suggestion performance.
- **Matomo update (2026-04-01):** Matomo is now installed on-premise at `matomo.goldmidi.com`. Tracking code is live on XenForo and WordPress. FR-016 collects from **two parallel sources**: GA4 (cloud, sampled at scale) and Matomo (on-premise, unsampled, full cardinality). Both feed the same `SuggestionTelemetryDaily` model via a `telemetry_source` field. Matomo fills the cardinality gap where GA4 buckets low-volume suggestions into `(other)`.

## Current Repo Map

### Existing analytics storage

- `backend/apps/analytics/models.py`
  - `SearchMetric` stores daily `gsc` or `ga4` metrics by `ContentItem`.
  - `ImpactReport` stores before/after comparisons for applied suggestions.
- Problem:
  - current analytics storage is content-level, not suggestion-level;
  - there is no `suggestion_id`, `pipeline_run_id`, or `algorithm_version` in analytics rows;
  - there is no per-link impression/click funnel.

### Existing suggestion and version context

- `backend/apps/suggestions/models.py`
  - `Suggestion` already holds host, destination, anchor, review status, and pipeline run references.
  - `PipelineRun.config_snapshot` already exists and is the right place to freeze algorithm settings.
- `backend/apps/pipeline/services/algorithm_versions.py`
  - already stores dated algorithm version metadata for weighted authority runs.

### Existing analytics UI

- `frontend/src/app/analytics/analytics.component.ts`
- `frontend/src/app/analytics/analytics.component.html`
  - analytics page exists only as a placeholder.

### Existing settings and jobs plumbing

- `backend/apps/core/models.py`
  - `AppSetting` is the existing settings store.
- `backend/apps/core/views.py`
  - existing settings APIs live here.
- `backend/apps/pipeline/tasks.py`
  - shows the current Celery task pattern used for long-running jobs.

### Important repo constraint

- The app does not auto-write links into XenForo or WordPress today.
- Reviewers manually apply approved suggestions.
- That means `FR-016` must define a safe way to attribute behavior to an applied suggestion without changing canonical URLs or breaking existing content.

## Workflow Drift / Doc Mismatch Found During Inspection

- `SearchMetric` says it stores `GA4` data, but it is too coarse for suggestion attribution.
- The analytics page is not built yet, so charts for telemetry do not exist.
- There is no live-site instrumentation layer in this repo today for:
  - seeing when a suggestion-generated link is shown;
  - seeing when that exact link is clicked;
  - carrying that attribution onto the destination page.
- Existing docs mention `GA4` and impact reporting in broad terms, but there is no exact event schema, no sync design, and no attribution design yet.

## Source Summary

### Source documents actually read

- Official `GA4` event / custom-parameter guidance
- Official `GA4` Measurement Protocol guidance
- Official `GA4` Data API schema guidance
- Existing repo analytics models and placeholder analytics UI

### Concepts used from the sources

- `GA4` supports custom events with custom parameters.
- `GA4` supports aggregated reporting across dimensions and metrics such as:
  - `sessions`
  - `engagedSessions`
  - engagement time / user engagement duration
  - `bounceRate`
  - `eventCount`
  - device category
  - channel grouping
  - country / region
- `GA4` is good at tracking behavior and engagement.
- `GA4` is not enough by itself to safely rewrite ranking in real time.

### What was clear

- `GA4` is the right first-party behavior source for:
  - link clicks;
  - sessions;
  - engagement time;
  - device/channel segmentation;
  - coarse geography.
- `GA4` can support version-vs-version behavior comparisons if attribution fields are sent consistently.

### What remained ambiguous

- `GA4` standard page-view reporting does not automatically know which internal link suggestion caused the visit.
- Attribution across page navigation needs a repo-specific bridge.
- Precise location should not be used.
- Raw user-level exports are not needed for this phase and create unnecessary privacy and regression risk.

## Telemetry-Fidelity Note

Simple version first.

This phase is about teaching the app to watch what people do.
It is not about letting the app change ranking yet.

### Directly supported by the product

- send custom events into `GA4`;
- attach custom parameters to those events;
- pull back aggregated metrics by date, device, channel, and geography.

### Adapted for this repo

- Use repo-specific event names for suggestion behavior.
- Use first-party DOM attributes plus a small browser session bridge for attribution.
- Use coarse geography only.
- Store local daily aggregates, not raw per-user event rows.
- Keep telemetry additive and fully optional.

### Alternatives considered

1. Add query-string attribution tokens to internal URLs.
2. Route clicks through a redirect endpoint.
3. Keep canonical URLs unchanged, stamp safe DOM metadata on instrumented links, and carry attribution in browser session storage.

### Chosen interpretation

- Choose option 3.
- Reason:
  - it avoids SEO-risky query-string pollution;
  - it avoids redirect latency and canonical confusion;
  - it keeps attribution local to first-party site code;
  - it lets unsupported manual links fail safely into neutral unattributed reporting.

## Problem Definition

Simple version first.

Right now the app can suggest a link, but it cannot tell whether real people saw it, clicked it, stayed on the destination, or came back later.

`FR-016` adds a behavior-tracking layer so the app can later learn from real usage.

Technical definition:

- define a stable `GA4` event schema for suggestion-generated internal links;
- attribute impressions, clicks, and destination engagement back to:
  - the exact suggestion;
  - the exact pipeline run;
  - the exact dated algorithm version;
- store local daily aggregates for reporting and later learning;
- add charts that explain which suggestions and algorithm versions perform well;
- keep all live ranking behavior unchanged in this phase.

## Phase Boundary and Non-Goals

`FR-016` must stay separate from:

- delayed search reward from `GSC` (`FR-017`)
- automatic weight tuning and model promotion (`FR-018`)
- direct ranking changes in `score_final`
- precise location tracking
- raw user replay tools
- redirect-based attribution
- query-string URL tagging for internal links
- any requirement that every manually applied link must be attributable

## Chosen Attribution Model

### Attribution prerequisites

Strong attribution only works when the live rendered link carries first-party metadata.

Supported mode:

- a site integration renders instrumented internal links with metadata attributes.

Unsupported mode:

- a reviewer pastes a plain link with no metadata.
- behavior remains unattributed and must stay neutral.

### Required link metadata on the rendered `<a>`

Recommended DOM attributes:

- `data-xfil-schema="fr016_v1"`
- `data-xfil-suggestion-id="<uuid>"`
- `data-xfil-pipeline-run-id="<uuid>"`
- `data-xfil-algorithm-key="<string>"`
- `data-xfil-algorithm-version-date="YYYY-MM-DD"`
- `data-xfil-algorithm-version-slug="YYYY_MM_DD"`
- `data-xfil-destination-id="<int>"`
- `data-xfil-destination-type="<thread|resource|wp_post|wp_page>"`
- `data-xfil-host-id="<int>"`
- `data-xfil-host-type="<...>"`
- `data-xfil-source-label="<xenforo|wordpress>"`
- `data-xfil-same-silo="<0|1>"`
- `data-xfil-link-position-bucket="<first_quartile|upper_middle|lower_middle|last_quartile|unknown>"`
- `data-xfil-anchor-hash="<short_hash>"`
- `data-xfil-anchor-length="<int>"`

Important:

- do not put raw anchor text into DOM attributes for telemetry;
- use a stable short hash plus length instead;
- raw anchor text already exists in the app database.

### Site-side browser bridge

When an instrumented link is clicked:

- client JS reads the `data-xfil-*` payload;
- client JS sends the click event to `GA4`;
- client JS stores a short-lived attribution payload in `sessionStorage`;
- payload is keyed by destination path plus a timestamp;
- payload TTL should default to `30` minutes.

When the destination page loads:

- client JS checks same-origin referrer and `sessionStorage`;
- if a valid recent attribution payload matches the destination path:
  - emit attributed destination-view behavior events;
  - keep attribution available for the rest of the session window.

### Why session storage is chosen

- it keeps canonical URLs clean;
- it avoids redirect wrappers;
- it keeps the attribution bridge local and low-risk;
- it fails safe when not available.

## Chosen Event Schema

### Event schema version

- schema name: `fr016_v1`
- this value must be attached to every custom event as `xfil_schema`

### Custom events emitted

#### 1. `suggestion_link_impression`

Fire when:

- an instrumented suggestion-generated link is at least `50%` visible for `1000ms`;
- once per page view per unique `suggestion_id`.

Purpose:

- measure “people had a real chance to see this link”.

#### 2. `suggestion_link_click`

Fire when:

- an instrumented link is activated by:
  - left click;
  - middle click;
  - keyboard activation.

Purpose:

- measure click-through from the host page.

#### 3. `suggestion_destination_view`

Fire when:

- a destination page is loaded after a valid attributed suggestion click in the active browser session.

Purpose:

- prove the suggestion click actually led to a destination landing.

#### 4. `suggestion_destination_engaged`

Fire when:

- an attributed destination visit becomes meaningfully engaged.

Default engaged rule:

- first of:
  - `10` focused seconds;
  - `50%` scroll depth;
  - a marked conversion event.

Purpose:

- separate empty clicks from useful visits.

#### 5. `suggestion_destination_conversion`

Fire when:

- the site records a business-defined conversion during an attributed destination session.

Purpose:

- support later high-value outcome learning.

### Derived metrics not emitted as custom events

Do not emit a custom bounce event.

Instead derive bounce-like outcomes from daily aggregates:

- `bounce_sessions = sessions - engaged_sessions`
- `bounce_rate = bounce_sessions / sessions`

Reason:

- unload/pagehide bounce events are easy to lose and create noisy regressions.

## Required Event Parameters

### Common parameters on every custom event

- `xfil_schema`
- `suggestion_id`
- `pipeline_run_id`
- `algorithm_key`
- `algorithm_version_date`
- `algorithm_version_slug`
- `destination_content_id`
- `destination_content_type`
- `host_content_id`
- `host_content_type`
- `source_label`
- `same_silo`
- `link_position_bucket`
- `anchor_hash`
- `anchor_length`

### Extra parameters by event

#### `suggestion_link_impression`

- `host_page_type`
- `viewport_bucket`

#### `suggestion_link_click`

- `click_kind`
  - `left`
  - `middle`
  - `keyboard`
- `open_in_new_tab`

#### `suggestion_destination_view`

- `landing_depth`
  - default `1`

#### `suggestion_destination_engaged`

- `engagement_trigger`
  - `focused_10s`
  - `scroll_50`
  - `conversion`

#### `suggestion_destination_conversion`

- `conversion_name`

### Parameters intentionally excluded

- no raw anchor text
- no full page title
- no email, username, or user ID
- no precise coordinates
- no postcode / zip code
- no query-string mutation on internal destination URLs

## Local Data Model Required

### Keep current models intact

Do not overload `SearchMetric` for suggestion attribution.

Reason:

- `SearchMetric` is content-level and too coarse;
- changing its meaning would create migration confusion and regression risk.

### New model: `SuggestionTelemetryDaily`

Add to `backend/apps/analytics/models.py`:

- `date: DateField(db_index=True)`
- `telemetry_source: CharField(choices=["ga4", "matomo"], db_index=True)` — which analytics platform this row came from
- `suggestion: ForeignKey("suggestions.Suggestion", null=True, blank=True, on_delete=models.CASCADE)`
- `destination: ForeignKey("content.ContentItem", related_name="telemetry_as_destination", on_delete=models.CASCADE)`
- `host: ForeignKey("content.ContentItem", related_name="telemetry_as_host", on_delete=models.CASCADE)`
- `algorithm_key: CharField`
- `algorithm_version_date: DateField`
- `algorithm_version_slug: CharField`
- `event_schema: CharField`
- `device_category: CharField(blank=True)`
- `default_channel_group: CharField(blank=True)`
- `source_medium: CharField(blank=True)`
- `country: CharField(blank=True)`
- `region: CharField(blank=True)`
- `source_label: CharField(blank=True)`
- `same_silo: BooleanField(null=True)`
- `impressions: IntegerField(default=0)`
- `clicks: IntegerField(default=0)`
- `destination_views: IntegerField(default=0)`
- `engaged_sessions: IntegerField(default=0)`
- `conversions: IntegerField(default=0)`
- `sessions: IntegerField(default=0)`
- `bounce_sessions: IntegerField(default=0)`
- `avg_engagement_time_seconds: FloatField(default=0.0)`
- `total_engagement_time_seconds: FloatField(default=0.0)`
- `event_count: IntegerField(default=0)`
- `is_attributed: BooleanField(default=True)`
- `last_synced_at: DateTimeField(auto_now=True)`

Recommended uniqueness:

- `date`
- `telemetry_source`
- `suggestion`
- `algorithm_version_slug`
- `device_category`
- `default_channel_group`
- `source_medium`
- `country`
- `region`
- `is_attributed`

Recommended indexes:

- `Index(fields=["algorithm_version_slug", "date"])`
- `Index(fields=["telemetry_source", "date"])`
- `Index(fields=["suggestion", "-date"])`
- `Index(fields=["destination", "-date"])`
- `Index(fields=["device_category", "date"])`
- `Index(fields=["default_channel_group", "date"])`

### New model: `TelemetryCoverageDaily`

Purpose:

- measure telemetry quality, not content performance.

Fields:

- `date`
- `event_schema`
- `source_label`
- `algorithm_version_slug`
- `expected_instrumented_links`
- `observed_impression_links`
- `observed_click_links`
- `attributed_destination_sessions`
- `unattributed_destination_sessions`
- `duplicate_event_drops`
- `missing_metadata_events`
- `delayed_rows_rewritten`
- `coverage_state`
  - `healthy`
  - `partial`
  - `degraded`

### New model: `AnalyticsSyncRun`

Purpose:

- record each analytics import / restatement run for any source.

Fields:

- `source: CharField(choices=["ga4", "matomo", "gsc"])` — which platform this run imported from
- `started_at`
- `completed_at`
- `status`
- `lookback_days`
- `rows_read`
- `rows_written`
- `rows_updated`
- `error_message`

## Settings, Defaults, Bounds, and Validation

### Settings storage

Persist through `AppSetting` in category `analytics`.

**GA4 keys:**

- `analytics.ga4_behavior_enabled`
- `analytics.ga4_property_id`
- `analytics.ga4_measurement_id`
- `analytics.ga4_api_secret`
- `analytics.ga4_sync_enabled`
- `analytics.ga4_sync_lookback_days`

**Matomo keys:**

- `analytics.matomo_enabled` — master on/off for Matomo collection
- `analytics.matomo_url` — base URL of the Matomo instance (e.g. `https://matomo.goldmidi.com`)
- `analytics.matomo_site_id_xenforo` — Matomo site ID for the XenForo forum
- `analytics.matomo_site_id_wordpress` — Matomo site ID for WordPress (if separate)
- `analytics.matomo_token_auth` — Matomo API token (stored encrypted, never returned in plain text)
- `analytics.matomo_sync_enabled`
- `analytics.matomo_sync_lookback_days`

**Shared telemetry keys:**

- `analytics.telemetry_event_schema`
- `analytics.telemetry_geo_granularity`
- `analytics.telemetry_retention_days`
- `analytics.telemetry_impression_visible_ratio`
- `analytics.telemetry_impression_min_ms`
- `analytics.telemetry_engaged_min_seconds`

### Defaults

- `ga4_behavior_enabled = false`
- `ga4_sync_enabled = false`
- `ga4_sync_lookback_days = 7`
- `matomo_enabled = false`
- `matomo_sync_enabled = false`
- `matomo_sync_lookback_days = 7`
- `telemetry_event_schema = "fr016_v1"`
- `telemetry_geo_granularity = "country"`
- `telemetry_retention_days = 400`
- `telemetry_impression_visible_ratio = 0.5`
- `telemetry_impression_min_ms = 1000`
- `telemetry_engaged_min_seconds = 10`

### Bounds

- `1 <= ga4_sync_lookback_days <= 30`
- `1 <= matomo_sync_lookback_days <= 30`
- `telemetry_geo_granularity` in:
  - `none`
  - `country`
  - `country_region`
- `1 <= telemetry_retention_days <= 800`
- `0.25 <= telemetry_impression_visible_ratio <= 1.0`
- `250 <= telemetry_impression_min_ms <= 5000`
- `5 <= telemetry_engaged_min_seconds <= 60`

### Validation rules

- secrets must never be returned in plain text from public settings APIs;
- region storage is allowed only when geo granularity is `country_region`;
- if telemetry is disabled, sync jobs must not run;
- missing property or secret must block sync and return a clear validation error;
- changing settings must not change ranking, review state, or historical snapshots.

## Data Collection and Sync Shape

### Collection paths (two parallel sources)

**GA4 path:**

1. live site renders instrumented link markup with `data-xfil-*` attributes
2. browser emits GA4 custom events (`suggestion_link_impression`, `suggestion_link_click`, etc.)
3. scheduled backend sync pulls aggregated rows from GA4 Data API
4. backend writes `SuggestionTelemetryDaily` rows with `telemetry_source = "ga4"`
5. analytics UI charts read local aggregates only

**Matomo path:**

1. same instrumented link markup triggers a parallel Matomo custom event via the Matomo JS tracker
2. Matomo stores the raw event on-premise at `matomo.goldmidi.com` — unsampled, full cardinality
3. scheduled backend sync calls the Matomo Reporting API (`Actions.getPageUrls`, `Events.getCategory`)
4. backend writes `SuggestionTelemetryDaily` rows with `telemetry_source = "matomo"`
5. same analytics UI charts read both sources; charts can filter by `telemetry_source`

**Why both:**

- GA4 is the primary source for device/channel/geographic segmentation
- Matomo is the primary source for per-suggestion click accuracy — GA4 buckets low-volume `suggestion_id` values into `(other)` at scale; Matomo has no cardinality limit
- FR-018 auto-tuning prefers Matomo click data when available because it is unsampled

### Sync cadence

**GA4:**

- hourly restatement for the last `2` days
- daily catch-up for the last `7` days
- reason: GA4 data arrives late and recent rows need safe rewrites

**Matomo:**

- hourly sync for the last `1` day (Matomo data is available immediately, no processing delay)
- daily catch-up for the last `7` days

### Pull granularity

Pull daily aggregates grouped by:

- `date`
- `telemetry_source`
- `suggestion_id`
- `algorithm_version_slug`
- `device_category`
- `default_channel_group`
- `country`
- `region`

If `suggestion_id` is unavailable:

- write an unattributed row with `is_attributed = false`
- never map that row to a random suggestion

## Charts and Dashboard Requirements

### Analytics page goal

Simple version first.

The charts should answer:

- Are people seeing the links?
- Are they clicking?
- Are they staying?
- Which algorithm version is doing better?
- Which segments are weird or broken?

### Required charts

#### 1. Suggestion Funnel chart

Show:

- impressions
- clicks
- destination views
- engaged sessions
- conversions

Slice by:

- date range
- algorithm version
- source label

#### 2. Daily trend line chart

Show by day:

- clicks
- CTR
- engaged sessions
- average engagement time

Compare:

- champion vs earlier versions

#### 3. Top suggestions bar chart

Rank by:

- click-through rate
- total clicks
- engaged-session rate

#### 4. Algorithm version comparison chart

Show per version:

- impressions
- CTR
- engaged-session rate
- conversion rate
- average engagement time

#### 5. Device split stacked bar chart

Show:

- desktop / mobile / tablet

Metrics:

- clicks
- engaged sessions
- CTR

#### 6. Channel split bar chart

Show:

- direct
- organic search
- referral
- email
- other available grouped channels

#### 7. Geography table or heatmap

Show only coarse geography:

- country
- optional region when enabled

Metrics:

- sessions
- engaged sessions
- CTR

#### 8. Telemetry health chart

Show:

- attributed session rate
- missing metadata rate
- duplicate event drop rate
- delayed rewrite count

### Charts intentionally out of scope

- no session replay
- no per-user drilldown
- no exact live-user map

## API, Admin, Review, and UI Impact

### Backend API

Add read APIs under analytics:

- `GET /api/analytics/telemetry/overview/`
- `GET /api/analytics/telemetry/funnel/`
- `GET /api/analytics/telemetry/by-version/`
- `GET /api/analytics/telemetry/top-suggestions/`
- `GET /api/analytics/telemetry/by-device/`
- `GET /api/analytics/telemetry/by-channel/`
- `GET /api/analytics/telemetry/by-geo/`
- `GET /api/analytics/telemetry/coverage/`

Add settings APIs:

- `GET /api/settings/analytics/ga4/`
- `PUT /api/settings/analytics/ga4/`

Add sync trigger:

- `POST /api/analytics/telemetry/ga4-sync/`

### Admin

Expose:

- `SuggestionTelemetryDaily`
- `TelemetryCoverageDaily`
- `AnalyticsSyncRun`

### Review UI

Add later-friendly helper text, not ranking changes:

- show whether a suggestion has telemetry attribution capability:
  - `instrumented`
  - `plain_manual`
  - `unknown`

Optional helper action:

- `Copy Instrumented Markup`

Important:

- this does not auto-apply the link;
- it only helps supported integrations preserve attribution metadata safely.

### Analytics UI

Likely touched:

- `frontend/src/app/analytics/analytics.component.ts`
- `frontend/src/app/analytics/analytics.component.html`
- `frontend/src/app/analytics/analytics.component.scss`
- new analytics service and types files

## Fallback Behavior When Disabled or Incomplete

- If `GA4` telemetry is disabled, ranking and review behavior stay exactly the same.
- If site markup is not instrumented, destination visits remain unattributed and must stay neutral.
- If sync fails, local aggregates remain unchanged.
- If geography granularity is `none`, geo charts collapse cleanly to “not collected”.
- If attribution payload is missing required fields, drop the event from attributed reporting and count it in coverage diagnostics.
- If a whole day must be restated, rewrite only the local aggregate rows for that day and source.

## Regression Risks and Concrete Mitigations

### 1. SEO / canonical regressions from tagged internal URLs

Mitigation:

- do not add query strings to internal destination URLs;
- do not use redirect wrappers;
- use DOM metadata plus browser session storage instead.

### 2. Ranking regressions from noisy telemetry

Mitigation:

- `FR-016` is telemetry-only;
- no direct write into `score_final`;
- no ranking math changes in this phase.

### 3. Double-counting from rerenders or repeated observers

Mitigation:

- dedupe impressions in memory per page view and `suggestion_id`;
- dedupe clicks with a short local debounce window;
- store duplicate-drop counts in `TelemetryCoverageDaily`.

### 4. Privacy overcollection

Mitigation:

- no raw anchor text in telemetry payloads;
- no per-user local storage beyond short-lived browser session attribution;
- no user IDs or personal fields;
- geography limited to country / region only.

### 5. Broken attribution for unsupported manual edits

Mitigation:

- support explicit `instrumented` vs `plain_manual` mode;
- unattributed traffic stays separate and neutral;
- never guess a suggestion ID.

### 6. Data drift after schema changes

Mitigation:

- attach `xfil_schema` to every event;
- persist schema version locally on every aggregate row;
- never merge old and new schemas silently.

### 7. Late-arriving `GA4` data causes chart churn

Mitigation:

- use lookback restatement windows;
- track rewritten-row counts;
- mark newest dates as provisional in charts when needed.

## Exact Repo Modules / Files Likely To Be Touched

### Backend analytics

- `backend/apps/analytics/models.py`
- `backend/apps/analytics/admin.py`
- `backend/apps/analytics/views.py`
- `backend/apps/analytics/urls.py`
- `backend/apps/analytics/tests.py`
- `backend/apps/analytics/migrations/<new migration>`
- `backend/apps/analytics/services/ga4_client.py`
- `backend/apps/analytics/tasks.py`

### Settings and API

- `backend/apps/core/views.py`
- `backend/apps/api/urls.py`

### Suggestions and review helpers

- `backend/apps/suggestions/models.py`
- `backend/apps/suggestions/serializers.py`
- `backend/apps/suggestions/views.py`
- `frontend/src/app/review/*`

### Analytics UI

- `frontend/src/app/analytics/analytics.component.ts`
- `frontend/src/app/analytics/analytics.component.html`
- `frontend/src/app/analytics/analytics.component.scss`
- `frontend/src/app/analytics/analytics.service.ts`
- `frontend/src/app/analytics/analytics.types.ts`

### Site integration slices

- first-party integration code for XenForo / WordPress rendering of instrumented links
- any “copy instrumented markup” helper used by reviewers

## Rollout Plan

### Slice 1 - Settings and schema

- add settings storage
- add new analytics models
- add sync-run model
- add schema constants

### Slice 2 - Live-site instrumentation

- add client event emitter for instrumented links
- add session-storage attribution bridge
- add impression and click dedupe

### Slice 3 - `GA4` sync and local aggregates

- add scheduled sync task
- pull daily aggregates
- write `SuggestionTelemetryDaily`
- write `TelemetryCoverageDaily`

### Slice 4 - Charts and diagnostics

- build analytics APIs
- build charts page
- add telemetry health views

### Slice 5 - Review helpers

- add instrumentation status in review
- add optional copy-instrumented-markup helper for supported integrations

## Test Plan

### 1. Disabled parity

- With telemetry disabled, assert:
  - ranking output is unchanged;
  - review actions are unchanged;
  - no telemetry sync runs are scheduled.

### 2. Instrumented event payload shape

- Assert every emitted event includes required common parameters.
- Assert raw anchor text is never sent.

### 3. Impression dedupe

- Render the same link through repeated observer callbacks.
- Assert one impression per page view per `suggestion_id`.

### 4. Click attribution bridge

- Click an instrumented link.
- Assert session storage is written.
- Load the destination page.
- Assert `suggestion_destination_view` is emitted once with matching suggestion metadata.

### 5. Engaged session logic

- Simulate:
  - `10` focused seconds;
  - `50%` scroll;
  - conversion.
- Assert `suggestion_destination_engaged` fires once on first qualifying trigger.

### 6. Unsupported manual-link fallback

- Load a plain non-instrumented internal link.
- Assert no false attributed events are emitted.
- Assert local reporting can still show unattributed traffic separately.

### 7. Daily rollup correctness

- Feed a small synthetic aggregate payload from `GA4`.
- Assert local rows group correctly by:
  - date
  - suggestion
  - version
  - device
  - channel
  - geography

### 8. Geography guardrails

- With `geo_granularity = none`, assert country/region fields are blank.
- With `geo_granularity = country`, assert region is blank.

### 9. Late-arrival rewrite safety

- Re-run sync for a recent day with changed aggregates.
- Assert only the targeted day/source rows are replaced.

### 10. Charts API behavior

- Assert each telemetry endpoint returns stable series data.
- Assert empty states are valid and do not crash the analytics page.

## Final Chosen Behavior

Simple version first.

This phase teaches the app how to watch real behavior.
It does not let the app change ranking yet.

Exact outcome:

- `GA4` tracks suggestion-linked impressions, clicks, destination views, and engaged visits.
- Local daily aggregates store that behavior by suggestion and algorithm version.
- The analytics page gets charts for funnels, trends, versions, devices, channels, geography, and telemetry health.
- Unsupported or missing attribution stays neutral.
- Ranking stays unchanged until a later phase explicitly learns from this data.
