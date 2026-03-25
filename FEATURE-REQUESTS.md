# Feature Requests - XF Internal Linker V2

This file tracks backlog requests and shipped request slices.

Important:
- FR IDs are permanent request IDs, not execution-order numbers.
- Phase numbers are the delivery order and must be cross-referenced explicitly.
- `FR-016 - Add your next request here` is a template placeholder only. It is not backlog scope and must never be implemented.

## Workflow Rules

- Every session must read `AI-CONTEXT.md` and this file before coding.
- Check completed requests before implementing anything new.
- Verify the repository state before trusting request status text.
- Update this file and `AI-CONTEXT.md` after finishing a session.

## COMPLETED

### FR-007 - Link Freshness Authority
**Requested:** 2026-03-24
**Target phase:** Phase 10
**Completed phase:** Phase 10
**Completed:** 2026-03-25

- Implemented exactly against `docs/specs/fr007-link-freshness-authority.md`.
- `apps/graph/models.py` now stores separate `LinkFreshnessEdge` history rows for unique `source -> destination` peer links.
- Sync now tracks `first_seen_at`, `last_seen_at`, reactivation, and safe disappearance state without letting non-body paths create disappearance events.
- `ContentItem.link_freshness_score` and `Suggestion.score_link_freshness` store the bounded FR-007 score, with neutral fallback at `0.5`.
- Link Freshness has its own settings API, recalculation task, ranker weight, content filtering/ordering support, admin exposure, and review diagnostics.
- Local verification passed for the Django FR-007 test slice, migration drift check, Angular `test:ci`, and Angular build.

---

### FR-006 - Weighted Link Graph / Reasonable Surfer Scoring
**Requested:** 2026-03-24
**Target phase:** Phase 9
**Completed phase:** Phase 9
**Completed:** 2026-03-25

- Implemented exactly against `docs/specs/fr006-weighted-link-graph.md`.
- Existing internal-link extraction now preserves true mixed-syntax order and persists edge-level weighting evidence on `ExistingLink`.
- `ContentItem.march_2026_pagerank_score` stores the authority metric used in the app.
- Weighted authority has its own settings API, recalculation task, pipeline snapshotting, admin exposure, content API exposure, and review diagnostics.
- Ranking impact is bounded through `weighted_authority.ranking_weight`, which defaults to `0.2`.
- Local verification passed for backend tests, migration drift check, Angular `test:ci`, and Angular build.

---

### FR-003 - WordPress Cross-Linking
**Requested:** 2026-03-24
**Target phase:** Phase 8
**Completed phase:** Phase 8
**Completed:** 2026-03-24

- WordPress posts/pages now participate in the same suggestion system as XenForo content.
- `apps/sync/services/wordpress_api.py` provides the read-only posts/pages client with optional Application Password auth.
- WordPress settings are exposed at `GET/PUT /api/settings/wordpress/` and manual sync is exposed at `POST /api/sync/wordpress/run/`.
- Manual sync and scheduled sync both follow the existing Celery/Celery Beat pattern.
- WordPress posts/pages map to `ContentItem(content_type="wp_post"/"wp_page")`.
- Cross-source existing-link graph refresh now resolves `XF -> WP` and `WP -> XF`.
- Review/settings APIs and Angular UI now label content source explicitly.
- Local verification closure completed: Django Phase 8 test slice passes, Python 3.12 backend environment works, the Angular 20 frontend builds under Node.js 22, `npm audit` reports zero vulnerabilities, and the frontend `test:ci` target now has a checked-in smoke test and passes.

---

### FR-005 - Link Siloing & Topical Authority Enforcement
**Requested:** 2026-03-24
**Target phase:** Phase 7
**Completed phase:** Phase 7
**Completed:** 2026-03-24

- `SiloGroup` model added and `ScopeItem.silo_group` now uses nullable `SET_NULL` semantics.
- Silo ranking settings are persisted through `AppSetting` and exposed at `GET/PUT /api/settings/silos/`.
- Pipeline ranking supports `disabled`, `prefer_same_silo`, and `strict_same_silo`.
- Strict-mode suppression emits `cross_silo_blocked` diagnostics.
- Backend CRUD endpoints added for silo groups plus a safe scope-assignment patch flow.
- Angular Settings manages silo groups, scope assignments, and ranking controls.
- Angular Review shows host/destination silo labels and supports a same-silo-only filter.

---

### FR-004 - Broken Link Detection
**Requested:** 2026-03-24
**Completed:** 2026-03-24

- `BrokenLink` model, scanner task, API, CSV export, dashboard surfacing, and Angular `/link-health` page are shipped.

---

### FR-002 - Jobs Page: JSONL File Import UI
**Requested:** 2026-03-24
**Completed:** 2026-03-24

- Drag-and-drop JSONL upload, import-mode selector, live progress, success/failure banners, and sync history are shipped.

---

### FR-001 - Angular Frontend: Light Theme Default + Full Theme Customizer
**Requested:** 2026-03-24
**Completed:** 2026-03-24

- Appearance settings API, Angular customizer UI, live theme application, logo upload, and favicon upload are shipped.

## PENDING

### FR-008 - Phrase-Based Matching & Anchor Expansion
**Requested:** 2026-03-24
**Target phase:** Phase 11
**Priority:** High
**Patent inspiration:** `US7536408B2`

- Extract salient phrases from titles, distilled text, and host sentences.
- Add phrase-level relevance as a separate ranking signal.
- Expand anchor extraction beyond exact title windows with explainable phrase evidence.

---

### FR-009 - Learned Anchor Vocabulary & Corroboration
**Requested:** 2026-03-24
**Target phase:** Phase 12
**Priority:** Medium
**Patent inspiration:** `US9208229B2`

- Learn preferred anchor variants per destination from the existing internal-link graph.
- Surface canonical anchors and alternates in review.
- Allow reviewers to prefer or disallow anchor variants.

---

### FR-010 - Rare-Term Propagation Across Related Pages
**Requested:** 2026-03-24
**Target phase:** Phase 13
**Priority:** Medium
**Patent inspiration:** `US20110196861A1`

- Propagate rare, high-signal terms across nearby related pages.
- Keep propagated evidence bounded, explainable, and separate from original content.
- Use scope/silo/relationship proximity rules to avoid topic drift.

---

### FR-011 - Field-Aware Relevance Scoring
**Requested:** 2026-03-24
**Target phase:** Phase 14
**Priority:** Medium
**Patent inspiration:** `US7584221B2`

- Score title, body, scope labels, and learned anchor vocabulary separately.
- Add bounded field-level weighting and expose diagnostics/tuning.

---

### FR-012 - Click-Distance Structural Prior
**Requested:** 2026-03-24
**Target phase:** Phase 15
**Priority:** Medium
**Patent inspiration:** `US8082246B2`

- Add a soft structural prior based on click distance / shortest-path depth.
- Store it separately from authority and expose diagnostics.

---

### FR-013 - Feedback-Driven Explore/Exploit Reranking
**Requested:** 2026-03-24
**Target phase:** Phase 16
**Priority:** Medium
**Patent inspiration:** `US10102292B2`

- Add a feature-flagged post-ranking reranker using review outcomes and later analytics.
- Limit exploration to a bounded top-N window and keep it explainable.

---

### FR-014 - Near-Duplicate Destination Clustering
**Requested:** 2026-03-24
**Target phase:** Phase 17
**Priority:** Medium
**Patent inspiration:** `US7698317B2`

- Cluster near-duplicate destinations with canonical preference, soft suppression, manual override, and confidence-aware behavior.
- Do not default to cross-source canonicalization.

---

### FR-015 - Final Slate Diversity Reranking
**Requested:** 2026-03-24
**Target phase:** Phase 18
**Priority:** Medium
**Patent inspiration:** `US20070294225A1`

- Apply a late diversity reranker only after hard constraints and duplicate-family normalization.
- Stay inside a close-score window and never override hard suppression rules.

---

### FR-016 - GA4 Suggestion Attribution & User-Behavior Telemetry
**Requested:** 2026-03-25
**Target phase:** Phase 19
**Priority:** High
**Spec draft:** `docs/specs/fr016-ga4-suggestion-attribution-user-behavior-telemetry.md`

### What's wanted
- Add first-class `GA4` tracking for suggestion-driven internal-link behavior so the app can learn from real user activity instead of only reviewer decisions.
- Track the full path from impression to click to destination engagement, while keeping the ranking system stable and off-by-default until telemetry quality is proven.
- Make telemetry rich enough to support future automatic tuning without mixing raw analytics directly into the current ranker.

### Specific controls / behaviour
- Add a versioned analytics event schema for suggestion-linked traffic.
- Track at minimum:
  - `suggestion_link_impression`
  - `suggestion_link_click`
  - `suggestion_destination_view`
  - `suggestion_destination_engaged`
  - `suggestion_destination_conversion` when a site goal exists
  - `suggestion_destination_bounce`
- Track engagement inputs needed for later tuning:
  - engaged time
  - session count
  - returning-vs-new visitor state when available
  - scroll depth buckets
  - page depth / pages per session
  - device class
  - traffic channel / source / medium
  - coarse geography such as country/region only
- Every tracked event must carry stable attribution fields:
  - `suggestion_id`
  - `pipeline_run_id`
  - `algorithm_version`
  - `destination_content_id`
  - `destination_content_type`
  - `host_content_id`
  - `host_content_type`
  - `anchor_text`
  - `anchor_confidence`
  - `link_position_bucket`
  - `same_silo`
  - `source_label`
- Add a local ingestion/sync layer that stores normalized daily aggregates by suggestion, destination, algorithm version, device bucket, channel bucket, and geography bucket.
- Keep raw event names and local aggregate field names versioned so schema changes do not silently poison future learning data.
- Keep review outcomes and `GA4` outcomes separate at storage time, then join them only in a later training/reporting step.
- Add diagnostics that show telemetry coverage quality:
  - missing tag rate
  - unattributed click rate
  - duplicate event rate
  - delayed ingestion rate
  - event schema version mix
- Add admin/settings controls for:
  - telemetry enabled/disabled
  - allowed geography granularity
  - event retention window
  - minimum sample thresholds before data can influence any later model
  - property IDs / secrets / sync windows

### Implementation notes for the AI
- Do not let `GA4` metrics directly change `score_final` in the first implementation pass.
- First pass must be telemetry-only plus reporting-only.
- Existing ranking, review flow, imports, and diagnostics must stay behaviorally identical when telemetry is enabled but no learning phase has promoted a new model.
- New telemetry fields must be additive. Do not rename or overload current score fields.
- Use feature flags and schema versioning from day one.
- Store coarse geography only. Do not use precise location.
- Do not use location as a direct ranking bonus. It is for segmentation, QA, and later evaluation only.
- Treat missing analytics as neutral, never as negative evidence.
- Add rate-limiting, deduplication, and delayed-arrival handling so `GA4` noise does not create regressions.

---

### FR-017 - GSC Search Outcome Attribution & Delayed Reward Signals
**Requested:** 2026-03-25
**Target phase:** Phase 20
**Priority:** High

### What's wanted
- Add `GSC` attribution so the app can measure whether approved/applied internal links helped search outcomes after a realistic delay.
- Turn delayed search feedback into a safe training signal for later algorithm tuning, without confusing short-term traffic noise with true search improvement.

### Specific controls / behaviour
- Track per-destination and per-suggestion search outcome windows before and after a suggestion is applied.
- Store at minimum:
  - impressions
  - clicks
  - CTR
  - average position
  - query count
  - top query deltas
  - landing-page deltas
- Support multiple measurement windows such as:
  - baseline pre-apply window
  - short follow-up window
  - medium follow-up window
  - long follow-up window
- Attribute outcome rows to:
  - destination
  - applied suggestion set
  - algorithm version
  - anchor family
  - source type
  - scope / silo
- Add confidence rules so tiny samples do not look like wins:
  - minimum impressions
  - minimum clicks
  - minimum age since apply
  - seasonality guardrails
  - optional control-group comparison when available
- Add delayed-reward labels such as:
  - positive
  - neutral
  - inconclusive
  - negative
- Keep those labels explainable by storing the exact thresholds and comparison windows used.
- Add impact reports that compare search outcomes by algorithm version and by suggestion cohort, not just by destination.
- Add queue-safe backfills so historical `GSC` imports can be reprocessed without mutating approved review data.

### Implementation notes for the AI
- Do not feed `GSC` directly into live ranking until there is a separate offline evaluation layer.
- Keep `GSC` attribution separate from `GA4` behavior data. They move on different clocks and should not be merged blindly.
- Treat search outcome data as delayed reward, not instant truth.
- Missing `GSC` data must stay neutral.
- Protect against regressions from noisy windows, seasonality, and unrelated sitewide traffic swings.
- The first pass must focus on attribution, cohort reporting, and training labels only.
- Hard review constraints and existing ranking logic must remain unchanged until a later promoted model explicitly opts in.

---

### FR-018 - Auto-Tuned Ranking Weights & Safe Dated Model Promotion
**Requested:** 2026-03-25
**Target phase:** Phase 21
**Priority:** High

### What's wanted
- Automatically tune ranking weights and later reranking weights using reviewer outcomes, apply outcomes, `GA4` behavior data, and delayed `GSC` impact data.
- Every promoted model/version must be dated for clean record keeping and instant rollback.
- The system must improve carefully without causing conflicts, hidden score drift, or silent regressions.

### Specific controls / behaviour
- Define a training dataset that joins:
  - review approvals/rejections
  - manual apply state
  - `GA4` click and engagement outcomes
  - `GSC` delayed search outcomes
  - the exact pipeline snapshot and algorithm version that produced each suggestion
- Train a challenger model or challenger weight set offline first.
- Compare challenger vs champion on frozen holdout data before any live use.
- Promote a challenger only when it clears explicit gates:
  - minimum sample size
  - uplift threshold
  - no hard-constraint violations
  - no fairness/bias alert from geography/device segmentation
  - no regression beyond tolerated limits in approval rate, click rate, or search impact
- Save each promoted version with:
  - full date
  - month
  - year
  - exact timestamp
  - dated slug
  - parent model/version
  - training window
  - feature set version
  - evaluation report snapshot
- Keep a full adaptive-change history log for every automatic change, even when the change is later rolled back.
- Every automatic change history row must include:
  - exact date
  - exact time
  - month
  - year
  - old champion version
  - new challenger/promoted version
  - old weight values
  - new weight values
  - absolute delta by weight
  - percentage delta by weight
  - trigger source
  - trigger summary
  - evaluation window used
  - key metrics that improved
  - key metrics that regressed
  - promotion decision
  - rollback state
- Trigger source must be explicit, for example:
  - reviewer outcome drift
  - `GA4` engagement uplift
  - `GSC` delayed search uplift
  - scheduled retrain window
  - manual operator-approved promotion
- Add automatic alerts when:
  - a challenger is promoted
  - a live adaptive weight set changes
  - a regression gate blocks promotion
  - an active version is rolled back
  - telemetry quality is too weak for safe adaptation
- Alert payloads must include:
  - exact date and time
  - month and year
  - affected algorithm/version
  - short plain-English summary of what changed
  - detailed trigger summary
  - before/after top metrics
  - link to the saved evaluation snapshot or history row
- Add a readable history screen that shows adaptive changes newest-first with expandable detail.
- Add a “why this changed” summary block for each history item that explains in plain English:
  - what triggered the change
  - which weights changed
  - which metrics got better
  - which risks were checked
  - whether the change was later kept or rolled back
- Keep a champion/challenger registry and allow instant rollback to any earlier dated version.
- Support shadow mode:
  - challenger scores are computed and stored
  - live ordering still uses champion
  - reports compare both side by side
- Support capped rollout mode:
  - small traffic slice or bounded destination cohort
  - automatic abort if regression thresholds trip
- Keep tuning scope bounded:
  - first auto-tuning pass may adjust additive weights only
  - hard filters, existing-link blocks, cross-silo strict blocks, and safety constraints must remain non-negotiable
- Add clear diagnostics showing why a new version was promoted or rejected.
- Expose per-version reports for:
  - approval rate
  - rejection reasons
  - apply rate
  - click-through rate
  - engaged-session rate
  - destination dwell / engaged time
  - search uplift
  - segment stability by device/channel/geography
- Expose an adaptive-change timeline chart that marks:
  - when a challenger entered shadow mode
  - when a version was promoted
  - when weights changed automatically
  - when a rollback happened
  - the main trigger behind each event

### Implementation notes for the AI
- Do not let training code overwrite current settings in place.
- New learned weights must live in versioned records, not in the single shared settings table.
- Current hand-tuned settings remain the champion until an explicit promotion step occurs.
- Promotion must be a separate action with a persisted evaluation snapshot and dated version stamp.
- Automatic promotions and automatic weight changes must also write an immutable audit/history record; never rely on ephemeral logs only.
- Keep the live pipeline able to load either:
  - manual settings only
  - a promoted dated weight set
  - a promoted reranker version
- Never change old pipeline-run snapshots after the fact.
- Preserve reproducibility: a historical run must always be traceable to the exact dated algorithm version that created it.
- History summaries and alerts must use exact timestamps, not vague relative words like "today" or "recently".
- Start with additive bounded adjustments only. Do not let the first pass invent new unbounded score components.
- If telemetry quality is low, or sample size is weak, or evaluation is inconclusive, the app must not promote a new version.
- Keep scope clean: generic operator alerts, bell/desktop notifications, job-complete warnings, model-download reminders, and non-adaptation error alerts belong to `FR-019`, not here.
- Keep runtime model download, warmup, hot swap, and zero-downtime model migration behavior in `FR-020`, not here.

---

### FR-019 - Operator Alerts, Notification Center & Desktop Attention Signals
**Requested:** 2026-03-25
**Target phase:** Phase 22
**Priority:** High
**Spec draft:** `docs/specs/fr019-operator-alerts-notification-center.md`

### What's wanted
- Make the GUI less vague when background work is loading, waiting, failing, or done.
- Add a real operator alert system so important problems and important wins are hard to miss.
- Support in-app alerts, a bell/notification center, optional sound, and Windows desktop notifications for urgent events.

### Specific controls / behaviour
- Add a notification center with:
  - unread count
  - severity levels such as info, warning, error, urgent
  - exact timestamp on every alert
  - plain-English title and plain-English details
  - link back to the related job, settings page, error row, suggestion, or analytics view
- Add clearer embedding/model status messages such as:
  - model not downloaded yet
  - downloading model for first use
  - warming model into memory
  - model ready
  - model load failed
- Add job lifecycle alerts for:
  - queued
  - started
  - completed
  - failed
  - stalled / unusually slow
- Add error alerts tied to persisted error rows so the user can see both:
  - the friendly message
  - the saved technical details
- Add Windows desktop notifications for:
  - job completed
  - job failed
  - urgent system warning
  - urgent trending suggestion / search spike event
- Add optional bell/sound alerts for:
  - failures
  - urgent warnings
  - completed long-running jobs
- Add urgent search/trend alerts when:
  - `GSC` shows a strong spike in impressions, clicks, or query demand
  - a destination or suggestion becomes urgent enough to review quickly
- Add anti-spam guardrails:
  - deduplicate repeated alerts
  - cooldown windows
  - per-type mute toggles
  - quiet-hours support
- Add settings for:
  - desktop notifications on/off
  - sound on/off
  - quiet hours
  - minimum severity for sound
  - minimum severity for desktop popups
  - urgent trend thresholds

### Implementation notes for the AI
- This request owns generic operator alerts and attention signals across jobs, sync, model loading, diagnostics, and urgent trend events.
- Keep `FR-018` alerts narrowly about adaptive model promotion / rollback / auto-tuning decisions so the two requests do not overlap.
- Every alert must have an exact timestamp and a stable event type.
- All alert-worthy failures must also be written to persistent storage; never rely on browser-only toasts.
- Browser and Windows notifications must degrade safely when permission is missing.
- Sound must be opt-in or user-controllable and must never loop forever.
- First pass can use WebSockets plus browser notification APIs; native Windows-only polish can be layered on after the core alert model exists.

---

### FR-020 - Zero-Downtime Model Switching, Hot Swap & Runtime Registry
**Requested:** 2026-03-25
**Target phase:** Phase 23
**Priority:** High

### What's wanted
- Make model switching easy and safe as the machine gets stronger over time.
- Support future bigger local models, including things like `DeepSeek-R1`, without turning model changes into risky manual surgery.
- Allow warmup, hot swap, and sync/backfill work with no user-visible downtime.

### Specific controls / behaviour
- Add a versioned model registry for at least:
  - embedding model
  - distillation model
  - optional local LLM helper model
- Track per model entry:
  - model name
  - model family
  - task type
  - vector dimension when relevant
  - device target
  - batch size
  - memory profile / operator note
  - status such as inactive, downloading, warming, ready, draining, failed
- Add a safe switch flow:
  - register candidate model
  - download it
  - warm it
  - health-check it
  - route new jobs to it
  - let in-flight jobs finish on the old model
  - drain the old model cleanly
- Support hot swap without downtime:
  - current jobs keep their original model binding
  - new jobs use the promoted ready model
  - the UI always shows which model each job used
- Support sync/backfill during model changes:
  - rolling re-embed jobs
  - resumable backfills
  - progress and failure alerts
  - no frozen UI while backfill runs
- Handle embedding dimension changes safely:
  - compatibility checks before switch
  - dual-column / dual-version strategy when dimensions differ
  - cutover only after the new vectors are ready
  - no destructive in-place overwrite of old embeddings during first pass
- Add health/error handling for:
  - download failed
  - warmup failed
  - model incompatible with current schema
  - device memory pressure
  - worker crash during swap
- Add settings/UI controls for:
  - current champion model per task
  - candidate model
  - warm/download action
  - promote action
  - rollback action
  - backfill status
  - last health-check result

### Implementation notes for the AI
- This request owns runtime model lifecycle and switching behavior, not `FR-018`.
- All model changes must be versioned and auditable.
- Never mutate the active model for running jobs in place.
- Preserve reproducibility: job records and pipeline snapshots must store the exact model/version used.
- Treat embedding-model swaps and LLM/distiller swaps differently when needed; embedding swaps can require backfill, while text-only helper model swaps may not.
- Design for both small laptop-safe models and future larger local models on a stronger PC.
- Keep the first implementation focused on reliability and rollback, not on squeezing maximum hardware utilization.

## TEMPLATE ONLY

### FR-0XX - Add your next request here

Template placeholder only. Not backlog scope.

```md
### FR-0XX - Short title

**Requested:** YYYY-MM-DD
**Target phase:** Phase X
**Priority:** High / Medium / Low

### What's wanted
[describe the feature]

### Specific controls / behaviour
[list details]

### Implementation notes for the AI
[technical hints]
```

*Last updated: 2026-03-25 (Phase 10 / FR-007 completed against `docs/specs/fr007-link-freshness-authority.md`; next real target is Phase 11 / FR-008; backlog still includes `GA4`, `GSC`, safe auto-tuning, operator alerts, and zero-downtime model-management requests; project stays pure Python/Django)*
