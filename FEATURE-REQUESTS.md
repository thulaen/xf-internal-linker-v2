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
- Future ranking-affecting requests should treat C++ as the default execution path for the hot inner loop, while keeping a behavior-matching Python fallback for safety.
- Those ranking requests must also expose a plain-English reason when the C++ speed path is not active or is not helping enough, for example: not compiled, import failed, disabled, unsupported input shape, small batch, or no real speedup measured.
- That status must be visible on the dashboard or diagnostics UI so an operator can see whether C++ is active, whether fallback is being used, and whether the fast path is actually helping.

## Ranking FR Checklist — Every New Ranking Signal Must Do All Five

Every FR that introduces a new ranking signal must complete all five steps before it is considered done. No exceptions.

**Step 1 — Spec**
Write the spec file in `docs/specs/frXXX-*.md` before writing any code. The spec is the source of truth. The implementation must match the spec, not the other way around.

**Step 2 — Researched recommended settings**
Every new signal must have researched starting values. Add them to `backend/apps/suggestions/recommended_weights.py` using the same key naming convention as existing signals (`signal_name.setting_key`). Include an inline comment explaining *why* each value was chosen (patent basis, conservative vs aggressive, what to raise it to after validation). Do not just copy the model-level defaults — these must be deliberately chosen starting points that are safe and useful from day one.

**Step 3 — Preset migration**
The `Recommended` system preset is seeded in `migrations/0016_seed_recommended_preset.py`, which has already run on existing installs. Every new FR must ship a new data migration that upserts the new keys into the existing `WeightPreset` record where `is_system=True` and `name='Recommended'`. Without this, existing installs never see the new recommended values when they load the preset.

**Step 4 — Tooltips and preset key map**
Every new settings field must have an entry in `SETTING_TOOLTIPS` in `frontend/src/app/settings/settings.component.ts`. The entry must have all five fields: `definition`, `impact`, `default` (matching the recommended_weights.py value exactly, not the model-level Django default), `example`, and `range`. Every new field must also have an entry in `UI_TO_PRESET_KEY` (same file) mapping the Angular camelCase key to the backend snake_case AppSetting key. If the field has a sensible warning or danger threshold, add it to `ALERT_THRESHOLDS` too.

**Step 5 — Settings card UI**
Every new signal must have its own settings card in the Ranking Weights tab. Each field on the card must wire to its tooltip using the `tip('signal.key')` pattern already used by every other card. The card must include an enabled toggle and a ranking weight slider at minimum. The card must only appear in the UI when the feature is implemented — do not add placeholder cards for unimplemented features.

## Infrastructure Notes

- 2026-03-26: a one-off supporting infrastructure exception added the `.NET 8` `HttpWorker` helper microservice under `services/http-worker/`.
- `HttpWorker` is only for HTTP-heavy helper work: BrokenLinkChecker, UrlFetcher, HealthChecker, and SitemapCrawler.
- `HttpWorker` does not replace Django as the main app, does not take over DB writes or product business logic, and does not replace Celery across the repo.
- Normal pending phase work continues after this helper addition. The next queued product phase in the current cleaned repo state is Phase 19 / `FR-016`.

## COMPLETED

### FR-016 - GA4 + Matomo Suggestion Attribution & User-Behavior Telemetry
**Requested:** 2026-03-25
**Target phase:** Phase 19
**Completed phase:** Phase 19
**Priority:** High
**Spec draft:** `docs/specs/fr016-ga4-suggestion-attribution-user-behavior-telemetry.md`
**Completed:** 2026-04-03

- Implemented exactly against `docs/specs/fr016-ga4-suggestion-attribution-user-behavior-telemetry.md`.
- Added first-class GA4 and Matomo tracking for suggestion-driven internal-link behavior.
- GA4/Matomo credentials configured entirely through the Angular settings page with live connection status.
- Implemented dual-source telemetry sync (GA4 and Matomo) into a local daily aggregate storage.
- Added a full interactive reporting layer using **Chart.js** (`ng2-charts`) on the Analytics page, including:
  - Horizontal Bar Funnel (Impressions to Conversions)
  - Multi-Axis Trend Line (Clicks, CTR, Engagement)
  - Grouped Bar Algorithm Comparison
  - Doughnut Breakdowns for Device, Channel, and Geography
- Added telemetry-health reporting to monitor tracking coverage and data integrity.
- Verified through `scripts/build-frontend.ps1` and manual browser checks.

---

### FR-015 - Final Slate Diversity Reranking
**Requested:** 2026-03-24
**Target phase:** Phase 18
**Completed phase:** Phase 18
**Priority:** Medium
**Patent inspiration:** `US20070294225A1`
**Completed:** 2026-04-02

- Implemented exactly against `docs/specs/fr015-final-slate-diversity-reranking.md`.
- Added the final host-level MMR diversity pass after hard constraints, FR-014 clustering, and FR-013 feedback reranking.
- Added a C++ FR-015 fast path in `backend/extensions/feedrerank.cpp` with a matching Python fallback plus correctness coverage.
- `Suggestion.score_slate_diversity` and `Suggestion.slate_diversity_diagnostics` now store explainable FR-015 slot-selection details.
- Angular review detail and system diagnostics now show plain-English FR-015 runtime status and diversity diagnostics.
- Repo-local wrappers now cover native extension rebuilds, frontend builds, and full verification without relying on PATH state.
- Local verification passed through `scripts/verify.ps1`, including native rebuild, full backend Django tests, Angular build, and Angular `test:ci`.

---

### FR-014 - Near-Duplicate Destination Clustering
**Requested:** 2026-03-24
**Target phase:** Phase 17
**Completed phase:** Phase 17
**Priority:** High
**Patent inspiration:** `US7698317B2`
**Completed:** 2026-03-28

- Implemented exactly against `docs/specs/fr014-near-duplicate-destination-clustering.md`.
- Added `ContentCluster` model and `ClusteringService` for grouping semantically redundant items (distance < 0.04).
- Added soft suppression in `ranker.py` to prefer canonical versions while still allowing high-relevance subordinates.
- Added background `recalculate_clusters` task and clustering settings API.
- Re-themed Angular Settings and Review UI to include cluster badges and management controls.
- Local verification passed for migration 0014, backend clustering units, and Angular build.

---

### FR-013 - Feedback-Driven Explore/Exploit Reranking
**Requested:** 2026-03-24
**Target phase:** Phase 16
**Completed phase:** Phase 16
**Priority:** High
**Patent inspiration:** `US10102292B2`
**Completed:** 2026-03-27

- Implemented exactly against `docs/specs/fr013-feedback-driven-explore-exploit-reranking.md`.
- Added UCB1-based reranking using Bayesian smoothing of historical reviewer approvals/rejections.
- Added `feedback_rerank.py` with a C++ reinforcement-learning fast path and Python fallback.
- `Suggestion.score_explore_exploit` and `explore_exploit_diagnostics` store the explainable feedback-driven boost.
- Exposed exploration status and exploration-rate controls in Angular Review and Settings.
- Local verification passed for Bayesian math units, C++ correctness tests, and Angular `test:ci`.

---

### FR-012 - Click-Distance Structural Prior Scoring
**Requested:** 2026-03-24
**Target phase:** Phase 15
**Completed phase:** Phase 15
**Priority:** Medium
**Patent inspiration:** `US8037060B2`
**Completed:** 2026-03-27

- Implemented exactly against `docs/specs/fr012-click-distance-structural-prior.md`.
- Added graph-based shortest-path structural prior scoring using inbound `ExistingLink` edges.
- Added `click_distance.py` with multi-step cached BFS lookup and neutral fallback at `0.5`.
- Added Click-Distance settings API, recalculation task, and suggestion-level scoring.
- Suggestion detail and system diagnostics now show plain-English structural evidence and path distance.
- Local verification passed for graph BFS units, migration drift, and Angular build.

---

### FR-011 - Field-Aware Relevance Scoring
**Requested:** 2026-03-24
**Target phase:** Phase 14
**Completed phase:** Phase 14
**Priority:** Medium
**Patent inspiration:** `US7584221B2`
**Spec draft:** `docs/specs/fr011-field-aware-relevance-scoring.md`
**Completed:** 2026-03-26

- Implemented exactly against `docs/specs/fr011-field-aware-relevance-scoring.md`.
- `backend/apps/pipeline/services/field_aware_relevance.py` now scores destination title, body, scope labels, and learned-anchor vocabulary as separate bounded field signals.
- `Suggestion.score_field_aware_relevance` and `Suggestion.field_aware_diagnostics` store the separate FR-011 score and explainable diagnostics.
- Field-Aware Relevance has its own settings API at `GET/PUT /api/settings/field-aware-relevance/`, its own algorithm version stamp, and pipeline-run snapshot wiring.
- Suggestion detail, suggestion admin, Angular review detail, and Angular settings now expose the intended FR-011 fields and controls.
- Local verification passed for the targeted Django test slice, syntax check, migration drift check, and `git diff --check`; Angular unit checks were not runnable in this session because Node/npm was unavailable on the host PATH.

---

### FR-010 - Rare-Term Propagation Across Related Pages
**Requested:** 2026-03-24
**Target phase:** Phase 13
**Completed phase:** Phase 13
**Completed:** 2026-03-25

- Implemented exactly against `docs/specs/fr010-rare-term-propagation-across-related-pages.md`.
- `backend/apps/pipeline/services/rare_term_propagation.py` now builds bounded related-page rare-term profiles, keeps propagated evidence separate from original destination evidence, and leaves disabled, weak, or missing propagation neutral at `0.5`.
- `Suggestion.score_rare_term_propagation` and `Suggestion.rare_term_diagnostics` store the separate FR-010 score and explainable diagnostics without mixing borrowed terms into original text, embeddings, FR-008 phrase inventory, or FR-009 learned-anchor evidence.
- Rare-Term Propagation has its own settings API at `GET/PUT /api/settings/rare-term-propagation/`, its own algorithm version stamp, and pipeline-run snapshot wiring.
- Suggestion detail, suggestion admin, Angular review detail, and Angular settings now expose the intended FR-010 fields and controls.
- Local verification passed for the targeted Django FR-010 test slice under `config.settings.test`, SQLite migration drift check, focused Angular FR-010 specs, and Angular build.

---

### FR-009 - Learned Anchor Vocabulary & Corroboration
**Requested:** 2026-03-24
**Target phase:** Phase 12
**Completed phase:** Phase 12
**Completed:** 2026-03-25

- Implemented exactly against `docs/specs/fr009-learned-anchor-vocabulary-corroboration.md`.
- `backend/apps/pipeline/services/learned_anchor.py` now builds bounded learned anchor families from inbound `ExistingLink.anchor_text`, filters generic noise anchors, dedupes support per source page, and keeps missing or thin evidence neutral at `0.5`.
- `Suggestion.score_learned_anchor_corroboration` and `Suggestion.learned_anchor_diagnostics` store the separate FR-009 learned-anchor signal and explainable corroboration state.
- Learned Anchors have their own settings API at `GET/PUT /api/settings/learned-anchor/`, their own algorithm version stamp, and pipeline-run snapshot wiring.
- Suggestion detail, suggestion admin, Angular review detail, and Angular settings now expose the intended FR-009 fields and controls.
- Local verification passed for the targeted Django FR-009 test slice under `config.settings.test`, SQLite migration drift check, Angular `test:ci`, and Angular build.

---

### FR-008 - Phrase-Based Matching & Anchor Expansion
**Requested:** 2026-03-24
**Target phase:** Phase 11
**Completed phase:** Phase 11
**Completed:** 2026-03-25

- Implemented exactly against `docs/specs/fr008-phrase-based-matching-anchor-expansion.md`.
- `backend/apps/pipeline/services/phrase_matching.py` now builds a bounded destination phrase inventory from title plus distilled text, matches exact and bounded partial phrase evidence, and falls back safely to the current exact-title extractor.
- `Suggestion.score_phrase_relevance` and `Suggestion.phrase_match_diagnostics` store the separate FR-008 phrase signal and explainable phrase-match state.
- Phrase Matching has its own settings API at `GET/PUT /api/settings/phrase-matching/`, its own algorithm version stamp, and pipeline-run snapshot wiring.
- Suggestion detail, suggestion admin, Angular review detail, and Angular settings now expose the intended FR-008 fields and controls.
- Local verification passed for the targeted Django FR-008 test slice, SQLite migration drift check, focused Angular review test, and Angular build.

---

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

 
 ---
 
<br>

---

## PENDING

<br>

---

### FR-017 - GSC Search Outcome Attribution & Delayed Reward Signals
**Requested:** 2026-03-25
**Target phase:** Phase 20
**Status:** In Progress (Slices 1-3 Complete: OAuth, shared Google login UX, and Python performance ingestion)
**Priority:** High

- **Slice 2 Completed (2026-04-03):**
  - Implemented exactly against Interactive OAuth requirements.
  - Added backend OAuth 2.0 handshake (Start, Callback, Unlink) for GA4 and GSC.
  - Updated GA4 and GSC API clients to support both OAuth and Service Account credentials.
  - Refined Angular Settings UI with Google sign-in buttons and live connection status.
  - Verified sync tasks automatically prefer OAuth tokens when available.

- **Slice 3 Completed (2026-04-03):**
  - Added a shared `Google Connection` settings card so one Google account can be connected once and reused for both GA4 and GSC.
  - Added a dedicated backend settings endpoint for Google OAuth app credentials, removing the broken split wiring between GA4 and GSC setup.
  - Repaired `GA4` sync and stabilized `Matomo` sync so analytics imports no longer fail before data reaches storage.
  - Landed the Python `GSC` performance importer with lag-safe upserts, query-level row ingestion, and duplicate-safe daily refresh behavior.
  - Repaired `GSC` keyword-impact math and the attribution window boundary bug in the C# worker.
  - Added score-refresh plumbing so imported analytics now refresh `content_value_score` for the existing ranking pipeline.

### GUI-first requirement (hard rule)
- GSC credentials (OAuth client ID/secret, verified site URL) must be configured entirely through the settings page. No config files, no code, no environment variables.
- The settings card must show a live connection status badge, an "Authorize with Google" OAuth button, and a last-sync display with row count.
- If the OAuth token expires, the card shows a clear warning and a re-authorize button — not a silent failure.

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
- The current code now refreshes `content_value_score` from imported analytics as a simple heuristic bridge. Keep any future direct `GSC` ranking influence gated and explainable until the later offline evaluation layer is in place.
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
**Status:** **Postponed / Resource-Contingent** (Requires more than 16GB RAM for heavy local models like Ollama/vLLM)

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

### FR-021 - Graph-Based Link Candidate Generation (Pixie Random Walk + Instagram Value Scoring)
**Requested:** 2026-03-28
**Target phase:** Phase 24
**Priority:** High
**Spec draft:** `docs/specs/fr021-graph-based-link-candidate-generation.md`

### What's wanted
- Build a bipartite knowledge graph of Articles ↔ Entities extracted from content.
- Run a Pinterest Pixie-style biased random walk from each source article to generate candidate destination links, surfacing topically-related pages that embedding similarity alone would miss.
- Rank the merged candidate pool (graph-walk + embedding) using an Instagram-style weighted value model: a configurable weighted sum of relevance signal, historical page traffic data from R analytics / `SearchMetric`, link freshness, and authority.
- Pass the ranked candidates into the existing multi-signal scoring pipeline (FR-006 to FR-015) unchanged.

### Specific controls / behaviour
- New backend app: `backend/apps/knowledge_graph/` with `EntityNode` and `ArticleEntityEdge` models.
- Entity extraction task runs after every sync and on-demand.
- Pixie walk is biased by edge weight, uses multi-hit boosting for intersection candidates, and early-stops when candidate set is stable.
- All walk parameters are configurable: steps per entity, K candidates, min-stable threshold, entities per article.
- Instagram value model: `score = w_relevance × relevance + w_traffic × traffic + w_freshness × freshness + w_authority × authority − w_penalty × penalty`.
- All weights configurable via `GET/PUT /api/settings/value-model/`.
- Traffic signal draws from `SearchMetric` and R analytics output; falls back to neutral `0.5` when missing.
- `Suggestion` gets `candidate_origin` (embedding / graph_walk / both), `score_value_model`, and `value_model_diagnostics` fields.
- Settings card shows graph stats (article count, entity count, edge count, last built) and "Rebuild Graph Now" button.
- Review detail shows candidate origin and value model signal breakdown.

### Implementation notes for the AI
- The graph is small for a typical site — fits in a few hundred MB at most. No distributed graph infrastructure needed.
- Keep Pixie walk as pure Python graph math. No external graph database required for first pass.
- The value model is a pre-ranking pass only. It does not replace or merge into the existing FR-006 to FR-015 signal scores.
- Existing scoring, hard filters, silo rules, and diversity reranking must remain unchanged.
- Missing traffic data must fall back to neutral, never to zero.
- Automatic weight tuning for the value model belongs to FR-018, not here.

---

### FR-022 - Data Source & System Health Check Dashboard
**Requested:** 2026-03-28
**Target phase:** Phase 25
**Priority:** High
**Spec draft:** `docs/specs/fr022-data-source-system-health-check.md`

### What's wanted
- Add a dedicated `/health` page showing one status card per data source and service.
- Every card answers: is it connected, when did data last arrive, and is anything wrong right now.
- Silent broken connections (expired tokens, stale syncs, downed containers) must be impossible to miss.
- Degraded services must fire `FR-019` operator alerts automatically.
- Recovered services must resolve their alerts automatically.

### Specific controls / behaviour
- Health cards included (13 total):
  1. **GA4** — credentials valid, last data received, auth error detection.
  2. **GSC** — credentials valid, last data received, auth error detection, 48h lag note.
  3. **XenForo Sync** — last sync timestamp + item count, overdue detection.
  4. **WordPress Sync** — last sync timestamp + item count, overdue detection.
  5. **C# Analytics Worker** — .NET service ping, last content-value computation run, last weight-tuning run.
  6. **Matomo** — on-premise instance ping, API token validity, last sync, suggestion-click cardinality coverage vs GA4.
  7. **Algorithm Pipeline** — last run result, suggestion count, suggestion-count-drop detection.
  8. **Auto-Tuning Algorithm** — champion/challenger state, last training run, gate check result (visible once FR-018 is live).
  9. **Embedding Model** — download / warmup / ready / failed state.
  10. **Celery Workers** — worker count, queue depth, backed-up detection.
  11. **HttpWorker Service** — .NET service ping, last task.
  12. **Database** — connection status, migration state.
  13. **Redis / Channel Layer** — PING check.
- New backend app: `backend/apps/health/` with `ServiceHealthRecord` model.
- Periodic Celery task runs all checks every 5 minutes (configurable).
- REST API: `GET /api/health/status/`, per-service immediate check endpoint, settings endpoint.
- Top summary bar: overall system status + "Check All Now" button.
- Cards sorted: errors first, then warnings, then healthy, then not-configured.
- Status dot in sidebar nav and top toolbar visible from any page when any service is degraded.
- All stale thresholds and alert thresholds configurable via `GET/PUT /api/settings/health/`.

### Implementation notes for the AI
- Health checks must be read-only and non-destructive. No write side-effects during a check.
- `ServiceHealthRecord` upserts on every check — one row per service, not a history log.
- All alert emission uses the `FR-019` `emit_operator_alert()` helper with dedupe keys so a persistently-down service does not flood the alert center.
- Resolved alerts (service came back healthy) must call resolve on the matching open alert.
- FR-019 must be implemented before FR-022 because FR-022 depends on `emit_operator_alert()`.
- Auto-tuning card (card 7) gracefully hides or shows "Not enabled" state until FR-018 is shipped.
- Embedding model card (card 8) connects to the same model-state contract already defined in FR-019.

---

### FR-023 - Reddit Hot Decay, Wilson Score Confidence & Traffic Spike Alerts
**Requested:** 2026-03-28
**Target phase:** Phase 26
**Priority:** Medium
**Spec draft:** `docs/specs/fr023-reddit-hot-decay-wilson-score-spike-alerts.md`

### What's wanted
Three independent, non-conflicting improvements built around Reddit's Hot algorithm and Wilson Score math:

1. **Reddit Hot decay** — replace the flat 90-day average inside FR-021's `traffic_signal` slot with Reddit Hot's logarithmic time-decay formula. Recent traffic counts for more. Old traffic fades. Pages gaining momentum right now surface as better link candidates than pages that were popular months ago.
2. **Wilson Score display** — show a confidence-adjusted CTR label in the FR-016 telemetry review UI. Makes it obvious when a "great CTR" is based on 5 impressions vs 5,000.
3. **Hot-score spike alerts** — a new `analytics.hot_score_spike` alert that fires when a page's traffic *momentum* rises sharply, even if raw volume is modest. Complements (does not replace) the existing `analytics.gsc_spike` alert.

### Specific controls / behaviour
- Part 1 modifies exactly one function: the `traffic_signal` computation in the FR-021 value model. Nothing else.
- Reddit Hot formula adapted for traffic: `hot_score = log10(max(traffic_volume, 1)) − gravity × age_in_days`. Summed across daily `SearchMetric` rows. Normalized site-wide with min-max.
- `hot_decay_enabled` toggle — when off, falls back to original flat average. Instant rollback.
- Configurable: `hot_gravity` (default 0.05), `hot_clicks_weight` (1.0), `hot_impressions_weight` (0.05), `hot_lookback_days` (90).
- Part 2 adds `wilson_lower_bound` and `wilson_confidence_label` as computed read-only fields on the FR-016 telemetry API. No DB column. No ranking impact.
- Confidence labels: low (< 20 impressions), moderate (20–99), good (100–499), high (≥ 500).
- Part 3 adds `analytics.hot_score_spike` and `analytics.hot_score_spike_resolved` event types to FR-019.
- Spike detected when: `delta ≥ 1.5` log units AND `relative_lift ≥ 50%` vs 7-day trailing average.
- Severity: `warning` at 50–99% lift, `urgent` at ≥ 100% lift.
- Dedupe cooldown: 24 hours per item per day.

### Implementation notes for the AI
- Part 1 must only modify the `traffic_signal` computation inside the FR-021 knowledge-graph service. Do not touch `score_final`, `score_link_freshness`, or `velocity.py`.
- Part 2 must be computed on read in the serializer/view. Do not add a DB column. Do not feed Wilson Score into any ranking weight.
- Part 3 must use `emit_operator_alert()` from FR-019. Do not build a separate alert path.
- FR-016's rule — "no live ranking from telemetry in first pass" — is fully respected. Parts 2 and 3 are display and alerts only.
- FR-007 and `velocity.py` are not modified by this FR under any circumstances.
- Depends on: FR-021 (Part 1), FR-016 (Part 2), FR-019 (Part 3).

---

### FR-024 - TikTok Read-Through Rate — Engagement Signal
**Requested:** 2026-03-28
**Target phase:** Phase 27
**Priority:** Medium
**Spec draft:** `docs/specs/fr024-tiktok-read-through-rate-engagement-signal.md`

### What's wanted
- Inspired by TikTok's completion rate signal: articles that hold human attention all the way through are better link destinations than keyword-stuffed pages people immediately bounce from.
- Add a sixth signal slot `engagement_signal` to the FR-021 value model.
- Compute it from `SearchMetric.avg_engagement_time` (already stored) divided by an estimated read time from `ContentItem.distilled_text` word count.
- Apply a bounce-rate penalty: `engagement_quality = read_through_rate × (1 − bounce_rate)`.
- Normalize site-wide with min-max, same pattern as other value model signals.
- Falls back to neutral `0.5` when no `SearchMetric` rows exist.

### Specific controls / behaviour
- New settings fields on `GET/PUT /api/settings/value-model/`: `engagement_signal_enabled`, `w_engagement` (default: 0.1), `engagement_lookback_days` (30), `engagement_words_per_minute` (200), `engagement_cap_ratio` (1.5), `engagement_fallback_value` (0.5).
- `value_model_diagnostics` extended with: `engagement_signal`, `read_through_rate_raw`, `engagement_quality_raw`, `avg_engagement_time_seconds`, `avg_bounce_rate`, `word_count`, `estimated_read_time_seconds`, `engagement_metric_rows_used`, `engagement_fallback_used`.
- Review UI shows full engagement breakdown per suggestion.
- Settings card adds engagement sub-section to the FR-021 card.

### Implementation notes for the AI
- Only `SearchMetric.avg_engagement_time` and `bounce_rate` are used. Do not read FR-016 `SuggestionTelemetryDaily` data — that is deferred from ranking by FR-016's staged rollout design.
- Only modify the `engagement_signal` computation function inside the FR-021 value model service. Do not touch `score_final`, FR-007, `velocity.py`, or FR-023.
- `engagement_signal_enabled = false` must return `0.5` fallback cleanly.
- Depends on: FR-021.

---

### FR-025 - Session Co-Occurrence Collaborative Filtering & Behavioral Hub Clustering
**Requested:** 2026-03-28
**Target phase:** Phase 28
**Priority:** Medium
**Spec draft:** `docs/specs/fr025-session-cooccurrence-collaborative-filtering-behavioral-hubs.md`

### What's wanted
- Merges Amazon Item-to-Item Collaborative Filtering and Spotify Discover Weekly co-occurrence into one FR (both need the same underlying data pipeline).
- **Part 1:** New weekly Celery task fetches GA4 session-level page-view sequences and builds a `SessionCoOccurrencePair` table (Jaccard similarity + lift per article pair). No personal data stored.
- **Part 2:** Seventh signal slot `co_occurrence_signal` added to the FR-021 value model. Pairwise signal — non-zero only for pairs with recorded co-occurrence data. Uses Jaccard similarity. Falls back to `0.5` when no data exists.
- **Part 3:** Behavioral hub detection — finds groups of articles frequently read together in the same session using threshold-based connected components. New `BehavioralHub` and `BehavioralHubMembership` models. Operators can view, edit, and hard-link hubs via a `/behavioral-hubs` management page.

### Specific controls / behaviour
- New backend app: `backend/apps/cooccurrence/` with `SessionCoOccurrencePair` and `SessionCoOccurrenceRun` models.
- Minimum thresholds: `min_co_session_count` (default: 5), `min_jaccard` (default: 0.05), `hub_min_jaccard` (default: 0.15), `hub_min_members` (default: 3).
- Settings API: `GET/PUT /api/settings/cooccurrence/` with all thresholds, schedule toggle, last-run stats.
- Value model: `w_cooccurrence` default `0.15`, configurable. Diagnostics show `co_session_count`, `jaccard_similarity`, `lift`.
- `BehavioralHub.auto_link_enabled` flags hub-pair suggestions as `candidate_origin = "behavioral_hub"`.
- Hub management page: list, detail, edit, merge, manual add/remove members.
- FR-019 alerts: `cooccurrence.run_failed` and `cooccurrence.run_completed`.
- FR-014 `ContentCluster` is not modified. A content item can belong to both a cluster and a hub.

### Implementation notes for the AI
- Part 1 reuses GA4 credentials and Data API client from FR-016. It is a separate task and table, not an extension of the FR-016 telemetry pipeline.
- Part 2 adds a pairwise signal to FR-021's value model. Existing signals are not reweighted by default.
- Part 3 hub detection must preserve `manual_remove_override` memberships across re-detection runs.
- The co-occurrence pipeline runs weekly and pre-computes all pair scores. The main suggestion pipeline reads pre-computed rows only — no live GA4 calls during pipeline runs.
- `score_final` in the main ranker is not modified.
- Depends on: FR-016 (GA4 credentials), FR-021 (value model), FR-019 (alerts).

---

### FR-026 - Authentication & Login Status UI
**Requested:** 2026-03-28
**Target phase:** Phase 29
**Priority:** High
**Spec draft:** `docs/specs/fr026-authentication-login-status-ui.md`

### What's wanted
- Show clearly in the GUI whether the operator is logged in or not.
- The backend already has full token + session auth configured. The Angular frontend has never implemented it — the auth interceptor and route guards are empty stubs from Phase 4.
- This FR completes that work and adds a username + logout button to the toolbar.

### Specific controls / behaviour
- New `GET /api/auth/me/` endpoint returns current user's `id`, `username`, `email`, `is_staff`.
- New `POST /api/auth/token/` endpoint (DRF `obtain_auth_token`) for Angular login form.
- New Angular `AuthService` — stores token in `localStorage`, exposes `isLoggedIn$` and `currentUser$`, provides `login()` and `logout()`.
- Auth interceptor stub completed — attaches `Authorization: Token ...` header to all requests. On `401` response: logs out and redirects to `/login`.
- Login page at `/login` — username + password fields, error message on bad credentials, redirect to original URL on success.
- Auth guard applied to all routes except `/login` — unauthenticated users are redirected.
- Toolbar shows: username + logout icon button when logged in. Login page has its own minimal layout (no shell).

### Implementation notes for the AI
- Token stored in `localStorage` under key `xfil_auth_token`.
- On app startup: if token exists in `localStorage`, call `/api/auth/me/` to verify it. If expired/invalid, clear token and redirect to `/login`.
- Do not attach auth header to `POST /api/auth/token/` itself.
- `/api/settings/appearance/` and `/api/dashboard/` are already public (`AllowAny`) — login page loads app theme without auth. Do not change these.
- No role management, no registration page, no OAuth. Accounts created via Django admin only.
- No other FR dependencies.

---

### FR-027 - CANCELLED: R Analytics Tidyverse Upgrade
**Requested:** 2026-03-28
**Target phase:** Phase 30
**Priority:** Cancelled
**Spec:** `docs/specs/fr027-r-analytics-tidyverse-upgrade.md` (cancelled)

### Why cancelled
The R analytics service has been removed from the stack. All goals originally planned for this FR are now covered by:

- **Data manipulation and aggregation** — C# LINQ (built-in, no packages needed). Replaces `dplyr`, `tidyr`, `purrr`.
- **Log-score computation and date arithmetic** — C# `Math`, `DateOnly`, `TimeSpan`. Replaces `lubridate`.
- **Statistical functions** (Wilson score, confidence bounds, L-BFGS optimization for FR-018) — `MathNet.Numerics` NuGet package.
- **Charts and visualizations** — D3.js in the Angular frontend. Replaces `ggplot2` and the Shiny dashboard.
- **Batch writes** — Npgsql batch `UPDATE` via `UNNEST`. Replaces the `purrr::pwalk()` row-by-row fix.

The scaffold functions for FR-023 Hot decay and FR-024 rolling engagement will be implemented in C# inside `services/http-worker/src/HttpWorker.Analytics/` instead.

---

### FR-028 - Algorithm Weight Diagnostics Tab
**Requested:** 2026-03-28
**Target phase:** Phase 31
**Priority:** High
**Spec draft:** `docs/specs/fr028-algorithm-weight-diagnostics-tab.md`

### What's wanted
- A single read-only **Diagnostics** tab on the Settings page showing all 23 scoring signals (16 `score_final` signals + 7 value model signals from FR-021) on one screen.
- Each signal card answers four questions: is it running? how much space is it using? are there errors? what settings is it using?

### Specific controls / behaviour
- New `GET /api/diagnostics/weights/` endpoint — reads from `AppSetting`, `ErrorLog`, PostgreSQL table sizes (`pg_total_relation_size`), and recent `Suggestion` score aggregates. Cached 5 minutes; `?refresh=true` busts cache.
- New backend app: `backend/apps/diagnostics/`.
- New settings endpoint `GET /api/settings/diagnostics/` for cache TTL and lookback window config.
- Each card shows: status badge (`ACTIVE` / `ENABLED` / `DISABLED` / `ERROR` / `NOT BUILT`), ranking weight, weight active flag, signal coverage % (last 7 days), avg signal value, storage (table name + row count + bytes), last computation time, last error message + timestamp.
- For ranking signals with a C++ accelerator, each card also shows C++ runtime status (`C++ ACTIVE`, `PYTHON FALLBACK`, or `C++ NOT HELPING`) and a plain-English reason.
- Expandable "View current settings" panel — read-only key-value list of every configurable parameter for that signal.
- "Go to settings →" link per card navigates to the signal's own settings tab.
- Error cards show a red left border and a "View in Error Log →" link.
- Summary bar: total signals, active count, error count, total storage across all signal tables.
- Signals for not-yet-implemented FRs show `NOT BUILT` state gracefully.
- Auto-refreshes every 5 minutes while the tab is open.

### Implementation notes for the AI
- This FR is read-only. Do not add any editing controls.
- Verify exact table names against live migration files before writing the table registry — they may differ from the names listed in the spec.
- `signal_coverage_pct` and `avg_signal_value` are computed from `Suggestion` score columns for the past 7 days. Return `null` when no suggestions exist in the window.
- Signals with no dedicated database table (phrase matching, field-aware, slate diversity — all computed at pipeline time) show "computed at pipeline time — no dedicated table" for storage.
- No dependency on other pending FRs. Cards for future FRs (FR-021 through FR-027) show `NOT BUILT` until those FRs are implemented.

---

### FR-029 - GPU Embedding Pipeline: fp16 Inference + HIGH_PERFORMANCE Mode
**Requested:** 2026-03-28
**Target phase:** Phase 32
**Priority:** Medium
**Spec draft:** `docs/specs/fr029-gpu-embedding-pipeline-fp16.md`

### What's wanted
- Enable fp16 (half-precision) inference on the bge-m3 embedding model when running on CUDA.
- Set `ML_PERFORMANCE_MODE=HIGH_PERFORMANCE` in Docker Compose so the GPU is actually used.
- The batch_size=128 path already exists — this FR activates it and adds fp16 on top.

### Specific controls / behaviour
- `model.half()` called in `_load_model()` when `device='cuda'`.
- Log line confirming fp16 is active.
- `ML_PERFORMANCE_MODE: HIGH_PERFORMANCE` added to backend + celery service env in `docker-compose.yml`.
- `get_model_status()` returns `"fp16": true` when active — used by FR-028 Diagnostics Tab.

### Implementation notes for the AI
- Do NOT use `torch_dtype=torch.float16` on the `SentenceTransformer` constructor — it does not accept that kwarg.
- Use `model.half()` after loading.
- The `_l2_normalize()` step already casts back to float32 before pgvector storage — no change needed there.
- Only two files change: `embeddings.py` and `docker-compose.yml`.

---

### FR-030 - FAISS-GPU Vector Similarity Search
**Requested:** 2026-03-28
**Target phase:** Phase 33
**Priority:** Medium
**Spec draft:** `docs/specs/fr030-faiss-gpu-vector-search.md`
**Depends on:** FR-029

### What's wanted
- Replace the Stage 1 CPU NumPy matmul (`dest_block @ host_matrix.T`) in the pipeline with a GPU-accelerated FAISS IndexFlatIP search.
- Keep all host content embeddings in VRAM (~391MB for 100k vectors) rather than fetching from pgvector on every pipeline run.
- Graceful CPU fallback when FAISS-GPU is not available (Windows dev, no CUDA, etc.).

### Specific controls / behaviour
- New `backend/apps/pipeline/services/faiss_index.py` — singleton index, build, search, status functions.
- Index built in `PipelineConfig.ready()` at startup. Skipped when `FAISS_INDEX_SKIP_BUILD=1`.
- Celery Beat task `refresh_faiss_index` refreshes the index every 15 minutes.
- `faiss_search(query_vectors, k)` replaces Stage 1 matmul; existing NumPy path stays as fallback.
- `get_faiss_status()` returns index size, device, VRAM estimate — feeds FR-028 Diagnostics Tab.
- Install `faiss-gpu-cu12>=1.8.0` in `backend/requirements.txt`.

### Implementation notes for the AI
- `faiss-gpu-cu12` is Linux/Docker only. Import inside a try/except; fall back to CPU matmul if unavailable.
- Vectors are already L2-normalized — use `IndexFlatIP` (inner product = cosine on unit vectors).
- Each gunicorn worker gets its own `StandardGpuResources()` instance — do not share across processes.
- Stage 2 sentence scoring is NOT changed by this FR — only Stage 1 content-level retrieval.
- Do NOT remove the existing pgvector HNSW indexes — they remain for direct DB queries outside the pipeline.
- `FAISS_INDEX_SKIP_BUILD=1` must be respected so `manage.py migrate` and management commands work cleanly.

---

### FR-031 - Interactive D3.js Force-Directed Link Graph
**Requested:** 2026-04-03
**Target phase:** Phase 34
**Priority:** High
**Spec draft:** `docs/specs/fr031-interactive-d3-link-graph.md`

### What's wanted
- The primary visualization for the Link Graph page: an interactive, zoomable, and pannable network graph of the site's internal links.
- Uses **D3.js** to render content items as nodes and internal links as edges.

### Specific controls / behaviour
- **Node Styling**:
  - Color-coded by `SiloGroup`.
  - Radius size relative to `march_2026_pagerank_score`.
  - Icon based on `content_type` (thread, resource, wp_post, etc.).
- **Force Simulation**:
  - Colliding force to prevent overlap.
  - Link force based on `ExistingLink.link_ordinal` (relative position in source).
  - Charge force to push unrelated clusters apart.
- **Interactivity**:
  - Drag nodes to rearrange (pinning supported).
  - Mouseover node highlights immediate neighbors and fades global web.
  - Tooltip shows page title, URL, silo, and in/out degree.
  - Click node loads a "Node Focus" sidebar with full details.
- **Performance**:
  - Web worker for initial large layout if nodes > 1000.
  - Canvas rendering fallback if node count exceeds 2000.

### Implementation notes for the AI
- Data provided via new `GET /api/graph/topology/` endpoint returning `nodes` and `links`.
- Use the standard D3.js `forceSimulation` pattern in the Angular component.
- Node IDs should be `content_item_pk`.

---

### FR-032 - Automated Orphan & Low-Authority Page Identification
**Requested:** 2026-04-03
**Target phase:** Phase 35
**Priority:** High
**Spec draft:** `docs/specs/fr032-orphan-page-identification.md`

### What's wanted
- Actionable auditing of "dead-end" or "lost" content that receives zero internal links.
- A dedicated "Audit" view within the Link Graph page to identify structural SEO weaknesses.

### Specific controls / behaviour
- **Orphan Detection**: List all `ContentItem` rows where `inbound_link_count == 0`.
- **Low Integrity Warning**: Flag pages with PageRank scores below the bottom 5th percentile.
- **Deep-Linked Discovery**: Flag pages that are ≥ 5 clicks away from the dashboard root (crawl depth audit).
- **Interactive Resolution**: One-click "Generate Suggestion" button next to every orphan to trigger the AI ranker.

### Implementation notes for the AI
- `inbound_link_count` is already maintained via `GraphSyncService`.
- Use a standard Material Table for the audit list.
- Query optimization: Filter orphans in the database, do not pull all nodes to the frontend just to count.

---

### FR-033 - Internal PageRank (Structural Equity) Heatmap
**Requested:** 2026-04-03
**Target phase:** Phase 36
**Priority:** Medium
**Spec draft:** `docs/specs/fr033-internal-pagerank-heatmap.md`

### What's wanted
- Visualize the distribution of "link juice" across the site to detect equity hoarding or starvation.
- Provides a high-level view of structural importance vs. actual SEO performance.

### Specific controls / behaviour
- **Heatmap Layer**: Toggle node color to a "heat" scale based on `march_2026_pagerank_score` (Red = High, Blue = Low).
- **Equity Table**: Sorted list of top "Hubs" (most outbound) and "Authorities" (most inbound).
- **Concentration Alert**: Warning if > 50% of PageRank is concentrated in < 5% of pages.

### Implementation notes for the AI
- Reuse `march_2026_pagerank_score` from FR-006.
- The heatmap calculation should be relative to the current site maximum, not an absolute log scale.

---

### FR-034 - Link Context & Contextual Class Audit
**Requested:** 2026-04-03
**Target phase:** Phase 37
**Priority:** Medium
**Spec draft:** `docs/specs/fr034-link-context-quality-audit.md`

### What's wanted
- Audit the "human quality" of links based on their placement context.
- Distinguish between organic contextual links and isolated "footer-style" or "weak" links.

### Specific controls / behaviour
- **Quality Distribution**: Chart showing % of site links classified as `contextual`, `weak_context`, or `isolated`.
- **Context Filters**: Filter the D3 graph to only show `contextual` links to see the "true" content-driven network.
- **Anchor Diversity Audit**: Per-node breakdown of anchor text variations. Warning for "over-optimized" anchors (many links, same text).

### Implementation notes for the AI
- `ContextClass` column on `ExistingLink` is already populated.
- Use the existing `GraphSyncService.ClassifyContext` logic for any new imports.

---

### FR-035 - Link Freshness & Churn Velocity Timeline
**Requested:** 2026-04-03
**Target phase:** Phase 38
**Priority:** Medium
**Spec draft:** `docs/specs/fr035-link-network-velocity-timeline.md`

### What's wanted
- Monitor the evolution of the link network over time.
- Identify "Network Friction" (links that are frequently broken or disappearing).

### Specific controls / behaviour
- **Velocity Chart**: Stacked area chart of "Links Created" vs. "Links Disappeared" per day.
- **Churn Alert**: Highlight nodes with high link turnover (links that appear and disappear repeatedly).
- **History Viewer**: Scrub through "past states" of the graph based on the `first_seen_at` and `last_seen_at` stamps on freshness edges.

### Implementation notes for the AI
- Data source: `LinkFreshnessEdge` table.
- Grouping by `tracked_at` date or `last_seen_at` to compute daily deltas.

---

### FR-036 - Suggestion vs. Reality Coverage Gap Analysis
**Requested:** 2026-04-03
**Target phase:** Phase 39
**Priority:** High
**Spec draft:** `docs/specs/fr036-suggestion-reality-coverage-gap.md`

### What's wanted
- Highlight "Opportunity Gaps" where the AI has high-relevance suggestions, but the page currently receives no links.
- Bridge the gap between the Link Graph (current state) and Review Page (future state).

### Specific controls / behaviour
- **Ghost Edges**: Toggle "Potential Links" on the graph. These show dotted lines for suggestions with `score_final > 0.8` that haven't been applied.
- **Gap Score**: Compute a "Neglect Score" for pages (High AI Relevance + 0 Internal Links).
- **Actionable Ghosting**: Click a ghost edge to directly open the Suggestion Approve/Apply dialog.

### Implementation notes for the AI
- Join `ContentItem` nodes with `Suggestion` rows where `status == 'pending'`.
- The frontend will need to fetch "Ghost Edges" as a separate optional data layer for the graph.

---

### FR-037 - Silo Connectivity & Cross-Topic Leakage Map
**Requested:** 2026-04-03
**Target phase:** Phase 40
**Priority:** Medium
**Spec draft:** `docs/specs/fr037-silo-connectivity-leakage-map.md`

### What's wanted
- Visualize the integrity of Content Silos.
- Identify where topical authority is "leaking" out of a silo or where silos are poorly connected to the home authority.

### Specific controls / behaviour
- **Silo Boundary Lines**: Draw boundaries or clusters around silo-grouped nodes.
- **Leakage Audit**: Highlight edges that cross between different `SiloGroup` IDs.
- **Isolation Warning**: Flag silos that have high internal connectivity but very few bridges to the rest of the site authority.

### Implementation notes for the AI
- Bounded by `SiloGroup` assignments from FR-005.
- Nodes with `silo_group == null` are treated as "Generic/Shared Authority" nodes.

---

### FR-038 - Information Gain Scoring
**Requested:** 2026-04-03
**Target phase:** Phase 41
**Priority:** Medium
**Patent inspiration:** `US11354342B2` — *Contextual Estimation of Link Information Gain*
**Spec draft:** `docs/specs/fr038-information-gain-scoring.md`

### What's wanted
- Score how much *new* information the destination page adds beyond what the source page already covers.
- A destination that repeats the same ground as the source page is lower value than one that genuinely expands the reader's knowledge.
- This is the complementary signal to `score_semantic`. Semantic rewards topical similarity. Information gain rewards topical novelty. Both should be relatively high for a great internal link.

### Specific controls / behaviour
- New suggestion-level score: `score_information_gain` bounded `[0.5, 1.0]`.
- Neutral `0.5` when source page text is unavailable or too short to compare.
- Computed from token-level set difference between source page body and destination page body — what fraction of the destination's normalized tokens does the source page *not* already contain.
- New `information_gain_diagnostics` JSON field on `Suggestion`.
- New settings: `information_gain.enabled`, `information_gain.ranking_weight` (default `0.0`), `information_gain.min_source_chars` (default `200`).
- `ranking_weight = 0.0` by default — diagnostics run silently until an operator validates the signal.

### Implementation notes for the AI
- Source page distilled text is already available at pipeline time via `PipelineRun` host page records.
- Destination tokens are already normalized by `text_tokens.py` — reuse the same tokenizer for the source page.
- Do not modify `score_semantic`, `score_keyword`, or any FR-008 through FR-015 logic.
- Do not write propagated tokens back to any stored text or embedding field.
- Keep strictly bounded: no penalty below `0.5`, no score above `1.0`.
- Full spec: `docs/specs/fr038-information-gain-scoring.md`.

---

### FR-039 - Entity Salience Match
**Requested:** 2026-04-03
**Target phase:** Phase 42
**Priority:** Medium
**Patent inspiration:** `US9251473B2` — *Identifying Salient Items in Documents*
**Spec draft:** `docs/specs/fr039-entity-salience-match.md`

### What's wanted
- Score how prominently the *most important terms of the source page* appear in the destination page.
- A destination page that is genuinely *about* the source page's core topic is a stronger link target than one that merely mentions the topic in passing.
- "Salient terms" are terms that appear frequently in the source page but are rare across the wider site — they represent what the source page is distinctly about.

### Specific controls / behaviour
- New suggestion-level score: `score_entity_salience_match` bounded `[0.5, 1.0]`.
- Neutral `0.5` when source page has no identifiable salient terms or data is unavailable.
- Salient source terms are extracted using a term-frequency × inverse-document-frequency (TF-IDF) approach over the existing corpus of `ContentItem.distilled_text` fields.
- A term is salient when it appears multiple times in the source page and infrequently across the rest of the site (site-wide document frequency ≤ a configurable threshold).
- Score = proportion of the source page's top salient terms that appear in the destination page body.
- New `entity_salience_diagnostics` JSON field on `Suggestion`.
- New settings: `entity_salience.enabled`, `entity_salience.ranking_weight` (default `0.0`), `entity_salience.max_salient_terms` (default `10`), `entity_salience.max_site_document_frequency` (default `20`), `entity_salience.min_source_term_frequency` (default `2`).
- `ranking_weight = 0.0` by default — diagnostics run silently until an operator validates the signal.

### Implementation notes for the AI
- Site-wide document frequency stats can be computed once per pipeline run from already-loaded `ContentRecord` tokens — the same pattern used by FR-010's rare-term frequency map.
- Do not confuse with FR-010 rare-term propagation. FR-010 asks "what rare terms from *nearby pages* does the *destination* share?" FR-039 asks "what important terms of the *source page* appear in the *destination*?" Different direction, different purpose.
- Do not use spaCy NER or any external NLP dependency. Use only the existing `tokenize_text()` normalizer plus frequency counting over the loaded corpus.
- Do not modify any existing score fields or FR-010 through FR-015 logic.
- Full spec: `docs/specs/fr039-entity-salience-match.md`.

---

### FR-040 - Multimedia Boost — Content Richness Signal
**Requested:** 2026-04-04
**Target phase:** Phase 43
**Priority:** Medium
**Research basis:** Google Image SEO documentation (alt text as confirmed signal), Google patent `US8189685B1` (*Ranking Video Articles*), Wistia video engagement study (2.6× time on page), Google AI Overviews multimedia lift data (317% higher selection with text + images + video + schema).
**Spec draft:** `docs/specs/fr040-multimedia-boost.md`

### What's wanted
- Score how visually rich a destination page is. Pages with video, descriptive images, and good alt text coverage are better link destinations than plain text pages.
- This is the eighth signal slot (`multimedia_signal`) in the FR-021 value model.
- Two-part implementation: (1) extract multimedia metadata from raw HTML at sync time and store it as a new `multimedia_metadata` JSONField on `ContentItem`; (2) compute `multimedia_signal` from that metadata during the pipeline's value model pass.

### Specific controls / behaviour
- New `ContentItem.multimedia_metadata` JSONField (nullable). Populated by the XenForo and WordPress sync services at ingest time. Null until the item is re-synced after deployment.
- New `multimedia_signal` bounded `[0, 1]`. Neutral fallback `0.5` when metadata is null.
- Score is a weighted blend of four components:
  - **Video component** (weight 0.40): no video = 0.0; video present = 0.6–1.0 based on provider (YouTube/Vimeo/native) and VideoObject schema presence.
  - **Alt text coverage** (weight 0.25): proportion of non-decorative images with descriptive alt text. ≥80% = 1.0, 50–79% = 0.5, <50% = 0.0. Text-only pages = 0.5 neutral.
  - **Image presence** (weight 0.20): rewards original images; penalises pages where all images come from known stock CDN hostnames (Unsplash, Getty, Shutterstock, etc.).
  - **Image-to-word ratio** (weight 0.15): optimal = 1 image per 200–600 words. Guards against content padded with images (too many) or long articles with no visuals (too few).
- Tracking pixels (images with `width` or `height` < 100px) are excluded from all counts.
- Decorative images (`alt=""` — correct W3C pattern) are excluded from alt-coverage scoring.
- New settings: `multimedia_signal_enabled` (bool, default: `true`), `w_multimedia` (float, default: `0.10`), `multimedia_fallback_value` (float, default: `0.5`).
- New UI sub-section in the FR-021 settings card: **Multimedia Richness Signal** with enable toggle, weight slider, and a read-only counter showing how many `ContentItem` rows have metadata.
- Suggestion review detail panel shows: video presence + provider, image count (original vs stock), alt coverage %, words per image.

### Implementation notes for the AI
- HTML is parsed **at sync time only** — never at pipeline time. Add `extract_multimedia_metadata(html: str, word_count: int) -> dict` in a new file `backend/apps/content/multimedia_extractor.py`.
- Call the extractor from both `backend/apps/xenforo/` and `backend/apps/wordpress/` sync paths immediately after HTML cleaning.
- Use `html.parser` (Python stdlib) or BeautifulSoup with `html.parser` backend. Never import `lxml` unless already in `requirements.txt`.
- Create a Django migration for the new `multimedia_metadata` JSONField on `ContentItem`.
- The value model formula in `backend/apps/knowledge_graph/services.py` gets an eighth additive slot. Existing signal computations must not change.
- `score_final` in the main ranker is not touched.
- Full spec: `docs/specs/fr040-multimedia-boost.md`.

---

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

*Last updated: 2026-04-04 (Phase 20 / FR-017 Slices 1-3 are complete. Next target is Slice 4 statistical attribution work. FR-038 and FR-039 added as new ranking signal backlog items at Phases 41 and 42. FR-040 Multimedia Boost added at Phase 43.)*
