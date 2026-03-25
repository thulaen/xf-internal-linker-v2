# FR-019 - Operator Alerts, Notification Center & Desktop Attention Signals

## Confirmation

- `FR-019` is a real backlog item in `FEATURE-REQUESTS.md`.
- It is queued for `Phase 22`.
- This spec is being written early because the user explicitly asked for the real build blueprint before implementation.
- Repo confirmed:
  - job progress WebSockets already exist;
  - backend `ErrorLog` storage already exists;
  - there is no persisted notification center yet;
  - there are no browser or Windows desktop notifications yet;
  - there is no sound alert system yet;
  - there is no clear model-download state shown to the user today.

## Current Repo Map

### Existing job progress plumbing

- `backend/apps/pipeline/tasks.py`
  - publishes `job.progress` events over Channels;
  - already emits human-readable progress messages for import, embedding, verification, pipeline, and link-health jobs.
- `backend/apps/pipeline/consumers.py`
  - streams job events to `ws/jobs/<job_id>/`.
- `frontend/src/app/jobs/jobs.component.ts`
  - listens to one job WebSocket;
  - updates inline progress text on the Jobs page only.
- `frontend/src/app/link-health/link-health.component.ts`
  - uses the same pattern for broken-link scans.

### Existing error logging

- `backend/apps/audit/models.py`
  - `ErrorLog` already stores background-job failures;
  - fields already include:
    - `job_type`
    - `step`
    - `error_message`
    - `raw_exception`
    - `why`
    - `acknowledged`
    - `created_at`
- `backend/apps/audit/admin.py`
  - exposes the error log in Django admin.

### Existing shell and likely UI insertion points

- `frontend/src/app/app.component.html`
  - top toolbar already has action icons;
  - this is the right place for a bell icon with unread count.
- `frontend/src/app/app.component.ts`
  - owns top-level shell state and is the right place for a global notification stream subscription.
- `frontend/src/app/core/interceptors/error.interceptor.ts`
  - currently logs HTTP errors to `console.error(...)`;
  - it does not show a snackbar or persist a UI-facing alert today.

### Existing analytics and urgency inputs

- `backend/apps/analytics/models.py`
  - `SearchMetric` already stores daily coarse `gsc` / `ga4` data by content item;
  - this is enough for a first-pass content-level search-spike alert.
- `frontend/src/app/analytics/analytics.component.*`
  - analytics page exists only as a placeholder today.

### Existing settings storage

- `backend/apps/core/models.py`
  - `AppSetting` is the existing typed key/value settings store.
- `backend/apps/core/views.py`
  - current settings APIs live here;
  - there is no notification settings API yet.

## Workflow Drift / Doc Mismatch Found During Inspection

- `docs/v2-master-plan.md` mentions `ws/notifications/` and a frontend `notification.service.ts`, but the live repo does not have either one yet.
- `frontend/src/app/core/interceptors/error.interceptor.ts` says snackbar/error handling was supposed to be added in Phase 4, but the live code only logs to the console.
- A completed job is only obvious if the user is looking at the exact page that opened the job WebSocket.
- A failed background job is stored in `ErrorLog`, but there is no operator-facing alert center that points the user to it.
- Model loading is currently vague:
  - the UI may show `Loading embedding model...`;
  - it does not tell the user whether the model is missing, downloading, warming, ready, or failed.

## Source Summary

### Source documents actually read for this spec

- `FEATURE-REQUESTS.md`
- `AI-CONTEXT.md`
- `docs/v2-master-plan.md`
- `backend/apps/pipeline/tasks.py`
- `backend/apps/pipeline/consumers.py`
- `backend/apps/audit/models.py`
- `backend/apps/analytics/models.py`
- `frontend/src/app/app.component.ts`
- `frontend/src/app/app.component.html`
- `frontend/src/app/jobs/jobs.component.ts`
- `frontend/src/app/core/interceptors/error.interceptor.ts`

### Platform assumptions used

- Browser desktop notifications are the safest first-pass way to satisfy the "Windows notification" requirement when the app is open in Windows.
- Short local audio cues are the safest first-pass way to satisfy the "ring a bell" requirement.
- WebSockets plus persisted backend alert rows are the safest first-pass transport because the repo already uses Channels.

### What was clear

- The app already has enough plumbing to emit events in real time.
- The missing part is not raw transport. The missing part is a proper alert domain:
  - persistence;
  - deduping;
  - severity;
  - unread state;
  - desktop/sound delivery rules;
  - a visible alert center.

### What remained ambiguous

- Whether Windows notifications must work only while the app is open in the browser, or also while it is fully closed.
- Whether sound should be per-alert-type or one shared chime.
- Whether future native desktop packaging is in scope for this phase.

## Notification-Fidelity Note

Simple version first.

This phase is about making important app state hard to miss.
It is not about adding a separate desktop daemon.

### Directly supported by the current repo

- push events over WebSockets;
- persist backend errors;
- store user-configurable preferences in `AppSetting`;
- show top-level UI in the Angular shell.

### Adapted for this repo

- Add a persisted alert/event table so alerts survive page refreshes.
- Add a notification stream separate from the one-job-at-a-time progress stream.
- Use browser desktop notifications as the first implementation of "Windows notification".
- Use a local short audio cue as the first implementation of "ring a bell".
- Keep all operator-facing copy plain-English and timestamped exactly.

### Alternatives considered

1. Keep alerts page-local only.
2. Use transient snackbars only.
3. Add a persisted notification center with optional toast, optional desktop popup, optional sound, and exact links back to the related record.

### Chosen interpretation

- Choose option 3.
- Reason:
  - it solves "I missed it while on another page";
  - it solves "I refreshed and lost the message";
  - it keeps errors and alerts tied together cleanly;
  - it leaves room for later native packaging without blocking the first useful version.

## Problem Definition

Simple version first.

Right now the app can do work in the background, but it does not do a good job of tapping the user on the shoulder when something important happens.

Technical definition:

- add a first-class operator alert system;
- persist alerts so they survive refreshes;
- surface them in the shell with unread count and severity;
- deliver optional desktop and sound cues for important events;
- make model/runtime state less vague;
- connect failures to the existing error log;
- support urgent trend alerts from `GSC` data when available.

## Phase Boundary and Non-Goals

`FR-019` must stay separate from:

- `FR-018` adaptive-model promotion history and promotion-specific alerts;
- `FR-020` runtime model switching, draining, hot swap, zero-downtime backfills, and champion/candidate model orchestration;
- email, SMS, Slack, Discord, or mobile push notifications;
- a native Windows tray app or background service in the first pass;
- changing ranking or automatically applying suggestions;
- forcing the browser to play audio when the user has disabled it;
- forcing desktop notifications when the browser permission is denied.

Important boundary:

- `FR-019` owns the alert contract and operator-facing delivery.
- `FR-020` owns deep model-runtime control.
- Before `FR-020` exists, `FR-019` may still surface basic model states for the currently active embedding model:
  - not downloaded;
  - downloading;
  - warming;
  - ready;
  - failed.

## Chosen Alert Model

### Core ideas

- Every important event becomes a persisted alert row.
- Alerts have severity and exact timestamps.
- Alerts can fan out to one or more channels:
  - in-app bell center;
  - in-app toast/snackbar;
  - desktop popup;
  - sound cue.
- Not every channel is used for every event.
- Repeated noisy events must dedupe into a single alert row with occurrence counting.

### Severity levels

- `info`
  - useful state change;
  - no sound by default;
  - no desktop popup by default.
- `success`
  - important completion;
  - sound optional;
  - desktop popup optional.
- `warning`
  - operator should probably look soon;
  - desktop popup optional based on settings.
- `error`
  - something failed;
  - sound and desktop popup allowed by default thresholds.
- `urgent`
  - time-sensitive operator attention;
  - sound and desktop popup on by default unless muted.

### Alert status model

- `unread`
  - new and not yet opened in the center.
- `read`
  - seen in the UI but not explicitly dismissed.
- `acknowledged`
  - operator intentionally cleared it.
- `resolved`
  - the underlying condition is fixed and the alert is closed automatically or manually.

### Stable event types for first pass

- `job.queued`
- `job.started`
- `job.completed`
- `job.failed`
- `job.stalled`
- `job.websocket_unavailable`
- `model.download_required`
- `model.download_started`
- `model.warming`
- `model.ready`
- `model.load_failed`
- `error.logged`
- `analytics.gsc_spike`
- `analytics.gsc_spike_resolved`

Future event types may be added later, but these names must stay stable once shipped.

## Data Model

### Chosen persistence shape

Use a dedicated backend app:

- `backend/apps/notifications/`

Reason:

- notifications are not the same thing as audit history;
- notifications need delivery-state behavior that does not belong inside `ErrorLog`;
- the app already has enough domain complexity that this deserves its own home.

### `OperatorAlert`

Canonical persisted alert row.

Suggested fields:

- `alert_id` (`UUID`, public-safe identifier)
- `event_type` (`CharField`, indexed)
- `source_area` (`CharField`)
  - examples:
    - `jobs`
    - `pipeline`
    - `models`
    - `analytics`
    - `system`
- `severity` (`CharField`, indexed)
- `status` (`CharField`, indexed)
- `title` (`CharField`)
- `message` (`TextField`)
- `dedupe_key` (`CharField`, indexed)
- `fingerprint` (`CharField`, blank)
- `occurrence_count` (`IntegerField`, default `1`)
- `related_object_type` (`CharField`, blank)
- `related_object_id` (`CharField`, blank)
- `related_route` (`CharField`, blank)
  - frontend route such as `/jobs`, `/analytics`, `/settings`, or a detail deep link
- `payload` (`JSONField`, default `dict`)
- `error_log` (`ForeignKey(ErrorLog)`, null/blank)
- `first_seen_at` (`DateTimeField`)
- `last_seen_at` (`DateTimeField`)
- `read_at` (`DateTimeField`, null/blank)
- `acknowledged_at` (`DateTimeField`, null/blank)
- `resolved_at` (`DateTimeField`, null/blank)
- `created_at` / `updated_at`

### `AlertDeliveryAttempt`

Per-channel delivery log.

Suggested fields:

- `alert` (`ForeignKey(OperatorAlert)`)
- `channel`
  - `in_app`
  - `toast`
  - `desktop`
  - `sound`
- `result`
  - `sent`
  - `skipped`
  - `blocked`
  - `failed`
- `reason` (`TextField`, blank)
- `attempted_at` (`DateTimeField`)

Why keep this table:

- it makes debugging alert spam and silent failures possible;
- it gives a real audit trail for desktop/sound delivery decisions.

### Notification preferences

Use `AppSetting` for first-pass preference storage.

Suggested key:

- `notifications.settings`

Suggested JSON shape:

```json
{
  "desktop_enabled": true,
  "sound_enabled": true,
  "quiet_hours_enabled": false,
  "quiet_hours_start": "22:00",
  "quiet_hours_end": "07:00",
  "min_desktop_severity": "warning",
  "min_sound_severity": "error",
  "enable_job_completed": true,
  "enable_job_failed": true,
  "enable_job_stalled": true,
  "enable_model_status": true,
  "enable_gsc_spikes": true,
  "toast_enabled": true,
  "toast_min_severity": "warning",
  "duplicate_cooldown_seconds": 900,
  "job_stalled_default_minutes": 15,
  "gsc_spike_min_impressions_delta": 50,
  "gsc_spike_min_clicks_delta": 5,
  "gsc_spike_min_relative_lift": 0.5
}
```

## Backend Design

### New backend app

Add:

- `backend/apps/notifications/models.py`
- `backend/apps/notifications/services.py`
- `backend/apps/notifications/views.py`
- `backend/apps/notifications/serializers.py`
- `backend/apps/notifications/consumers.py`
- `backend/apps/notifications/routing.py`

### Core service helper

Primary helper:

```python
emit_operator_alert(
    event_type: str,
    severity: str,
    title: str,
    message: str,
    *,
    source_area: str,
    dedupe_key: str,
    related_object_type: str | None = None,
    related_object_id: str | None = None,
    related_route: str | None = None,
    payload: dict | None = None,
    error_log_id: int | None = None,
) -> OperatorAlert
```

Responsibilities:

- dedupe repeated events inside cooldown window;
- increment occurrence count instead of spamming new rows;
- write delivery intents;
- publish to the notification WebSocket group;
- leave a stable persisted row even if the WebSocket is unavailable.

### WebSocket channel

Add:

- `ws/notifications/`

Purpose:

- push new alert events to all connected operator clients.

Payload shape:

```json
{
  "type": "notification.alert",
  "alert_id": "uuid",
  "event_type": "job.failed",
  "severity": "error",
  "status": "unread",
  "title": "Embedding job failed",
  "message": "The embedding run stopped while loading the model.",
  "related_route": "/jobs",
  "occurrence_count": 1,
  "created_at": "2026-03-25T18:42:11Z",
  "payload": {
    "job_id": "uuid",
    "job_type": "embed"
  }
}
```

### REST API

Add endpoints:

- `GET /api/notifications/alerts/`
  - list alerts;
  - supports filters for `status`, `severity`, `event_type`, `source_area`.
- `GET /api/notifications/alerts/summary/`
  - unread count by severity;
  - latest alert timestamp.
- `POST /api/notifications/alerts/<alert_id>/read/`
- `POST /api/notifications/alerts/<alert_id>/acknowledge/`
- `POST /api/notifications/alerts/<alert_id>/resolve/`
- `POST /api/notifications/alerts/acknowledge-all/`
- `GET /api/settings/notifications/`
- `PUT /api/settings/notifications/`
- `POST /api/notifications/test/`
  - creates a synthetic alert so the operator can test bell, desktop popup, and sound.

### Existing backend emitters to wire in

First pass must emit alerts from:

- `backend/apps/pipeline/tasks.py`
  - queue start / completion / failure;
  - stalled-job checks;
  - model status messages during embedding jobs.
- `backend/apps/audit` error-logging path
  - every new `ErrorLog` row should trigger `error.logged`.
- analytics sync / spike detection task
  - emit `analytics.gsc_spike` from stored `SearchMetric` rows when thresholds are crossed.

### Model download and warmup state contract

`FR-019` does not implement full model hot swap.
It does define the operator-facing state contract.

Minimum first-pass states:

- `download_required`
  - active model is not present locally;
  - first use will need a download.
- `download_started`
  - model fetch has begun.
- `warming`
  - model files exist, model is loading into memory.
- `ready`
  - model is loaded and usable.
- `load_failed`
  - fetch or warmup failed.

Implementation note:

- this can begin with wrapper callbacks around the current embedding loader;
- later `FR-020` can upgrade the same state model into a full runtime registry.

## Frontend Design

### New frontend services

Add:

- `frontend/src/app/core/services/notification.service.ts`
  - REST + WebSocket client;
  - unread count observable;
  - stream of new alerts.
- `frontend/src/app/core/services/desktop-notification.service.ts`
  - browser Notification API wrapper;
  - permission handling;
  - safe fallback when blocked.
- `frontend/src/app/core/services/audio-cue.service.ts`
  - plays short local chimes;
  - obeys quiet hours and severity threshold.
- `frontend/src/app/core/services/toast.service.ts`
  - lightweight wrapper around Angular Material snackbar.

### Shell changes

Update:

- `frontend/src/app/app.component.html`
- `frontend/src/app/app.component.ts`

Add:

- bell icon in the toolbar;
- unread badge;
- quick-open recent alerts menu;
- button to open a full alerts page.

### Alerts page

Add route:

- `/alerts`

Purpose:

- full notification center with filters and history.

Suggested UI sections:

- unread alerts
- all recent alerts
- filters:
  - severity
  - status
  - source area
  - event type
- action buttons:
  - mark read
  - acknowledge
  - resolve
  - open related page

### Toast rules

Use toast/snackbar for:

- `success`, `warning`, `error`, and `urgent` by preference threshold;
- not every `info` alert.

Examples:

- `Import completed`
- `Embedding job failed`
- `Model is downloading for first use`
- `Google search demand spiked for 3 pages`

### Desktop notification rules

First-pass interpretation of "Windows notification":

- browser desktop notifications shown while the Angular app is open in Windows and notification permission is granted.

Rules:

- never force permission on first page load;
- ask only after the user enables desktop notifications in settings or clicks a test button;
- if permission is denied:
  - keep in-app alerts working;
  - store a local UI hint that desktop notifications are blocked.

### Sound rules

First-pass sound behavior:

- one short packaged chime for `warning`;
- one stronger packaged chime for `error` / `urgent`;
- optional success chime for long-running completion events.

Rules:

- sound must be user-configurable;
- sound must obey quiet hours;
- sound must never loop;
- sound should only fire once per deduped alert event window.

## Alert Copy Rules

Every alert must have:

- a short plain-English title;
- a short plain-English body;
- an exact timestamp in stored data;
- a related route when one exists.

Copy examples:

- `Embedding model needs to download`
  - `The current embedding model is not on this machine yet. The first embedding run will download it.`
- `Embedding model is downloading`
  - `The app is downloading the active embedding model for first use. This first run may be slower than normal.`
- `Embedding model failed to load`
  - `The app could not load the active embedding model. Open Jobs or Error Log for details.`
- `Import job completed`
  - `The full import finished successfully.`
- `Google search demand spiked`
  - `Clicks or impressions jumped sharply for a tracked page. Review the Analytics page soon.`

## Dedupe, Cooldown, and Anti-Spam Rules

### Dedupe key examples

- `job.failed:<job_id>`
- `job.completed:<job_id>`
- `model.load_failed:<model_name>`
- `analytics.gsc_spike:<content_item_id>:<date>`
- `error.logged:<error_log_id>`

### Cooldown rules

- same `dedupe_key` inside cooldown window:
  - do not create a new row;
  - increment `occurrence_count`;
  - update `last_seen_at`.
- default cooldown:
  - `15` minutes for warnings/errors;
  - `60` minutes for repeated model-state reminders;
  - `24` hours for the same GSC spike fingerprint on the same page/day.

### Quiet hours

- apply to:
  - sound;
  - desktop popup.
- do not apply to:
  - in-app bell center;
  - persisted alert rows.

## GSC Spike Detection for First Pass

Simple version first.

The first pass does not wait for `FR-017`.
It uses existing coarse `SearchMetric(source="gsc")` rows to raise page-level urgency alerts.

### Candidate rule

For each tracked `ContentItem`:

- compare the most recent complete day or trailing `3`-day window against the previous `7`-day baseline;
- if either metric crosses threshold:
  - impressions delta;
  - clicks delta;
- and relative lift also crosses threshold;
- emit `analytics.gsc_spike`.

### Default thresholds

- impressions increased by at least `50`
- clicks increased by at least `5`
- relative lift at least `50%`

### Alert severity

- `warning`
  - moderate spike
- `urgent`
  - large spike or spike on a page already marked high-value

### Relation to later phases

- `FR-019` only raises the alert.
- `FR-017` later adds proper delayed-reward attribution and cohort logic.

## Logging, Error Handling, and Failure Paths

### Required behavior

- If alert creation fails:
  - the underlying job must still fail or complete honestly;
  - the app must log the notification failure to server logs.
- If desktop notification delivery fails:
  - keep the persisted alert row;
  - mark delivery attempt as `failed` or `blocked`.
- If sound playback fails:
  - keep the persisted alert row;
  - do not retry in a loop.
- If the browser is offline or the WebSocket is disconnected:
  - keep writing alert rows in the backend;
  - client catches up on next REST poll/load.

### ErrorLog linkage

When a background failure already creates `ErrorLog`, the alert must point back to that row.

This gives the operator:

- the friendly summary in the bell center;
- the detailed traceback path in diagnostics/admin.

## Rollout Plan

### Slice 1 - backend persistence and API

- add `notifications` app;
- add models, serializers, views, and migrations;
- add settings storage and summary endpoint.

### Slice 2 - realtime stream and shell UI

- add `ws/notifications/`;
- add toolbar bell with unread badge;
- add alerts page.

### Slice 3 - toast, desktop, and sound delivery

- add frontend delivery services;
- add test notification button in settings;
- add permission status UX.

### Slice 4 - real emitters

- wire job completion/failure/stall alerts;
- wire model download/warmup alerts;
- wire `ErrorLog`-linked alerts.

### Slice 5 - first-pass GSC spike alerts

- add periodic spike detection from coarse `SearchMetric`;
- emit page-level urgent alerts with links to analytics.

## Test Plan

### Backend tests

- model tests:
  - `OperatorAlert` create/read/update status;
  - dedupe and occurrence counting;
  - cooldown behavior.
- API tests:
  - list filters;
  - mark read / acknowledge / resolve;
  - notification settings read/write.
- WebSocket tests:
  - alert event reaches connected clients;
  - payload shape is stable.
- emitter tests:
  - job failed creates alert;
  - new `ErrorLog` creates linked alert;
  - model state transitions create correct alert types.

### Frontend tests

- bell badge updates when a new alert arrives;
- alerts page shows unread and acknowledged states correctly;
- snackbar only shows at or above configured threshold;
- desktop notification service no-ops cleanly when permission is denied;
- audio service respects quiet hours and min severity.

### Manual verification

- run a normal import and verify:
  - bell count changes;
  - completion alert appears;
  - desktop popup appears if enabled.
- trigger a known failure and verify:
  - `ErrorLog` row exists;
  - linked alert exists;
  - alert opens the right page.
- trigger first-time model download and verify:
  - GUI says model not downloaded;
  - then downloading;
  - then warming;
  - then ready, or failed.
- seed `SearchMetric` spike data and verify urgent trend alert.

## Acceptance Criteria

- The user can see unread alerts from anywhere in the app.
- Completed and failed background jobs can trigger operator-facing alerts outside the Jobs page.
- The app can show clearer model state than just `Loading embedding model...`.
- Failures are both:
  - persisted in backend logs;
  - surfaced as operator alerts.
- Browser-based Windows desktop notifications work when permission is granted.
- Bell/sound alerts are configurable and respect quiet hours.
- Repeated events do not spam duplicate alerts.
- Content-level `GSC` spikes can create urgent alerts using existing `SearchMetric` data.

## Out-of-Scope Follow-Up

These belong later, not in the first build of `FR-019`:

- native Windows tray notifications while the browser is fully closed;
- email/SMS/Slack/Discord integrations;
- suggestion-level urgency tied to `FR-017` delayed-reward logic;
- deep model-registry controls and hot-swap orchestration from `FR-020`;
- promotion-specific adaptive-model history UI already owned by `FR-018`.
