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

- Python/C++ remains the single source of truth for all business logic, link scanning, and sitemap processing.
- Normal pending phase work continues after this helper addition. The next queued product phase in the current cleaned repo state is Phase 19 / `FR-016`.

## COMPLETED

### FR-032 - Automated Orphan & Low-Authority Page Identification
**Requested:** 2026-04-03
**Target phase:** Phase 35
**Completed phase:** Phase 35
**Priority:** High
**Spec draft:** `docs/specs/fr032-orphan-page-identification.md`
**Completed:** 2026-04-06

- Implemented exactly against `docs/specs/fr032-orphan-page-identification.md`.
- Upgraded the existing Orphans tab into a full Audits tab with two modes: orphan detection (zero inbound links) and low-authority detection (below 5th percentile PageRank).
- Added `OrphanAuditSerializer` with `inbound_link_count` annotation.
- Backend supports `?mode=orphan|low_authority` filter on `GET /api/graph/orphans/`.
- Added CSV export endpoint (`GET /api/graph/orphans/export-csv/`).
- Added single-page pipeline trigger (`POST /api/graph/orphans/<pk>/suggest/`) with `content_item_ids` support in the pipeline for precise destination targeting.
- Frontend Audits tab includes filter dropdown, CSV export button, "Suggest Links" action per row, and click-to-focus cross-tab interaction that zooms to the node in the D3 network graph.
- Orphan nodes in the D3 visualization are now colored red (`var(--color-error)`) for high-contrast visibility.
- Deep-linked discovery (click depth > 5) deferred to Phase 2 as noted in the spec.
- Verified: 185 backend tests pass, 18 frontend tests pass, production build clean.

---

### FR-019 - Operator Alerts, Notification Center & Desktop Attention Signals
**Requested:** 2026-03-25
**Target phase:** Phase 22
**Completed phase:** Phase 22
**Priority:** High
**Spec draft:** `docs/specs/fr019-operator-alerts-notification-center.md`
**Completed:** 2026-04-04

- Implemented exactly against `docs/specs/fr019-operator-alerts-notification-center.md`.
- Added a full background-persisted `OperatorAlert` model with severity, cooldown, and occurrence counting.
- Built a real-time notification stream (`ws/notifications/`) to push events to the shell.
- Implemented the Angular `NotificationCenterComponent` with a toolbar bell icon and unread count badge.
- Added browser desktop notification and audio cue support (configurable in settings).
- Wired alerts for job failures, large GSC spikes, and engine health problems.
- Verified through `apps.notifications` unit tests (9/9 passing) and manual UI verification.

---

### FR-018 - Auto-Tuned Ranking Weights & Safe Dated Model Promotion
**Requested:** 2026-03-27
**Target phase:** Phase 21
**Completed phase:** Phase 21
**Priority:** High
**Spec draft:** `docs/specs/fr018-auto-tuned-ranking-weights.md`
**Completed:** 2026-04-04

- Implemented exactly against `docs/specs/fr018-auto-tuned-ranking-weights.md`.
- Implemented native Python/Numpy analytics worker for full auto-tune orchestration (collect → optimize → submit).
- Migrated weight optimization from Nelder-Mead to **Scipy L-BFGS-B** using a quadratic penalty function for sum/bound constraints.
- Integrated multi-source signals: GSC (clicks/impressions lift), GA4 (engagement/dwell), Matomo (unsampled per-suggestion CTR), and Review (historical approval rate).
- Added safe dated promotion in Django: automated side-by-side evaluation, status-gated promotion, and automatic rollback on demand drop.
- Added interactive Auto-Tune card in Angular Settings with live challenger diffs, manual promotion/rejection, and adjustment history.
- Verified through `python manage.py test` with passing auto-tune unit tests.

---

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

### FR-017 - GSC Search Outcome Attribution & Delayed Reward Signals
**Requested:** 2026-03-25
**Target phase:** Phase 20
**Completed phase:** Phase 20
**Status:** Complete (All 5 Slices: OAuth, shared Google login UX, Python performance ingestion, Django sync endpoint, Angular Search Impact tab with scatter plot and cohort analysis)
**Priority:** High
**Completed:** 2026-04-04

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

- **Slice 4 Completed (2026-04-04):**
  - The Gamma-Poisson conjugacy math, PostgresRuntimeStore GSC queries, and JobProcessor routing for `gsc_attribution` were already in place from prior slices.
  - Added `[FromQuery] bool sync` to `JobsController.SubmitAsync` — when `sync=true`, the job runs inline via `JobProcessor.ProcessAsync` and returns HTTP 200 with the full `JobResult`, instead of queuing via Redis.
  - This closes the wiring gap: Django's `run_job()` now triggers the attribution flow directly via Celery.
  - Added attribution tests covering sync/async paths and invalid-request handling.

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

### FR-021 - Graph-Based Link Candidate Generation (Pixie Random Walk + Instagram Value Scoring)
**Requested:** 2026-03-28
**Target phase:** Phase 24
**Completed phase:** Phase 24
**Completed:** 2026-04-05
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
**Completed phase:** Phase 25
**Completed:** 2026-04-05
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
  5. **Analytics Engine** — Python service ping, last content-value computation run, last weight-tuning run.
  6. **Matomo** — on-premise instance ping, API token validity, last sync, suggestion-click cardinality coverage vs GA4.
  7. **Algorithm Pipeline** — last run result, suggestion count, suggestion-count-drop detection.
  8. **Auto-Tuning Algorithm** — champion/challenger state, last training run, gate check result (visible once FR-018 is live).
  9. **Embedding Model** — download / warmup / ready / failed state.
  10. **Celery Workers** — worker count, queue depth, backed-up detection.
  11. **Content Worker** — Sync worker status, last task.
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

### FR-025 - Session Co-Occurrence Collaborative Filtering & Behavioral Hub Clustering
**Requested:** 2026-03-28
**Target phase:** Phase 28
**Completed phase:** Phase 28
**Priority:** Medium
**Spec draft:** `docs/specs/fr025-session-cooccurrence-collaborative-filtering-behavioral-hubs.md`
**Completed:** 2026-04-06

- Full cooccurrence app with SessionCoOccurrencePair, BehavioralHub, and BehavioralHubMembership models.
- 7th signal slot (co_occurrence_signal) integrated into Python post-pipeline value model scorer.
- Behavioral Hubs management page with hub detection, membership editing, and auto-link toggle.
- Settings card with co-occurrence sub-section in the Value Model card.
- Preset migration 0026 upserts co-occurrence keys into existing installs (2026-04-07 audit fix).

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
**Completed phase:** Phase 29
**Completed:** 2026-04-05
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

### FR-028 - Algorithm Weight Diagnostics Tab
**Requested:** 2026-03-28
**Target phase:** Phase 31
**Completed phase:** Phase 31
**Completed:** 2026-04-06
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
**Completed phase:** Phase 32
**Priority:** Medium
**Spec draft:** `docs/specs/fr029-gpu-embedding-pipeline-fp16.md`
**Completed:** 2026-04-05

- `model.half()` called in `_load_model()` when `device='cuda'`.
- `ML_PERFORMANCE_MODE: HIGH_PERFORMANCE` set in `docker-compose.yml` backend and celery services.
- `get_model_status()` reports `fp16: true` when active, feeding FR-028 diagnostics tab.

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
**Completed phase:** Phase 33
**Priority:** Medium
**Spec draft:** `docs/specs/fr030-faiss-gpu-vector-search.md`
**Depends on:** FR-029
**Completed:** 2026-04-05

- FAISS IndexFlatIP singleton with GPU/CPU fallback in `faiss_index.py`.
- Celery Beat task `refresh_faiss_index` refreshes every 15 minutes.
- Stage 1 pipeline uses `faiss_search()` replacing NumPy matmul.
- `get_faiss_status()` reports index size and device for FR-028 diagnostics.

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
**Completed phase:** Phase 34
**Priority:** High
**Spec draft:** `docs/specs/fr031-interactive-d3-link-graph.md`
**Completed:** 2026-04-03

- D3.js `LinkGraphVizComponent` with force simulation, silo-based coloring, and PageRank-scaled node radius.
- Drag, zoom, pan, and mouseover neighbor highlighting.
- `GET /api/graph/topology/` endpoint provides D3-compatible nodes and links JSON.

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

### FR-033 - Internal PageRank (Structural Equity) Heatmap
**Requested:** 2026-04-03
**Target phase:** Phase 36
**Priority:** Medium
**Spec draft:** `docs/specs/fr033-internal-pagerank-heatmap.md`
**Completed:** 2026-04-08 (verified against code)

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

### FR-035 - Link Freshness & Churn Velocity Timeline
**Requested:** 2026-04-03
**Target phase:** Phase 38
**Priority:** Medium
**Spec draft:** `docs/specs/fr035-link-network-velocity-timeline.md`
**Completed:** 2026-04-08 (verified against code)

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

### FR-024 - TikTok Read-Through Rate — Engagement Signal
**Requested:** 2026-03-28
**Target phase:** Phase 27
**Completed phase:** Phase 27
**Priority:** Medium
**Spec draft:** `docs/specs/fr024-tiktok-read-through-rate-engagement-signal.md`
**Completed:** 2026-04-06

- Implemented exactly against `docs/specs/fr024-tiktok-read-through-rate-engagement-signal.md`.
- Added `EngagementSignalData` record to C# contracts, 6 new `PipelineOptions` fields.
- Added `GetEngagementMetricsAsync` to `PostgresRuntimeStore`, site-wide `ComputeNormalizedEngagementSignals`.
- Updated `GraphCandidateService.CalculateValueScore` with sixth signal slot and full diagnostic fields.
- Extended Django settings API, Angular settings card, and review detail panel with engagement breakdown.
- Verified: Django tests pass, Angular build clean, Angular tests 18/18, no migration drift.


 ---

<br>

---

## PENDING

<br>

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

---

### [Complete] FR-023 - Reddit Hot Decay, Wilson Score Confidence & Traffic Spike Alerts
**Requested:** 2026-03-28
**Target phase:** Phase 26
**Completed phase:** Phase 26
**Priority:** Medium
**Spec draft:** `docs/specs/fr023-reddit-hot-decay-wilson-score-spike-alerts.md`
**Completed:** 2026-04-07

- C# TrafficDecayService implements Reddit Hot formula with configurable gravity, clicks weight, and impressions weight.
- Django settings endpoint, recommended_weights.py keys, and Angular settings card added (2026-04-07 audit fix).
- Wilson Score display (Part 2) and hot-score spike alerts (Part 3) implemented in C# HttpWorker.
- Preset migration 0026 upserts hot_decay keys into existing installs.

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

### FR-034 - Link Context & Contextual Class Audit
**Requested:** 2026-04-03
**Target phase:** Phase 37
**Priority:** Medium
**Spec draft:** `docs/specs/fr034-link-context-quality-audit.md`
**Status:** Partial
**Note:** Partial — link parser and context scoring refs exist; audit dashboard/trail UI missing

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
**Status:** Partial
**Note:** Partial — silo tracking (_same_silo) exists; leakage map visualization missing

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
**Status:** Partial
**Note:** Partial — config keys in migration exist; ContentItem field and scoring service missing

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

### FR-041 - Originality Provenance Scoring
**Requested:** 2026-04-04
**Target phase:** Phase 44
**Priority:** Medium
**Research basis:** Google patent `US8707459B2` (*Determination of Originality of Content*), Broder-style shingling / resemblance / containment math for lexical near-duplicate families.
**Spec draft:** `docs/specs/fr041-originality-provenance-scoring.md`

### What's wanted
- Reward the page that appears to be the earliest, most source-like version inside a family of very similar pages.
- This is not duplicate suppression and not freshness. It is a small historical-authority signal for the page that most likely introduced the topic first on this site.

### Specific controls / behaviour
- New destination-level score: `originality_provenance_score` bounded `[0.5, 1.0]`.
- Neutral `0.5` when the page has no sufficiently similar peer family or lacks reliable timing data.
- Build lexical near-copy families from word shingles using resemblance and containment thresholds.
- Prefer the earliest `source_published_at` member of a family, with modest support from containment and canonical URL signals.
- New suggestion-level copy field: `score_originality_provenance`.
- New suggestion diagnostics field: `originality_provenance_diagnostics`.
- New settings: `originality_provenance.enabled`, `originality_provenance.ranking_weight` (default `0.0`), `originality_provenance.resemblance_threshold`, `originality_provenance.containment_threshold`.

### Implementation notes for the AI
- Keep this separate from `FR-014` duplicate clustering. `FR-014` groups similar pages; `FR-041` asks which one looks original within that family.
- Add `source_published_at` on `ContentItem` so source-system publication time can be stored when available.
- Use the existing normalized tokenizer and a deterministic shingling pass. Do not introduce external crawling or copyright-ownership logic.
- Full spec: `docs/specs/fr041-originality-provenance-scoring.md`.

---

### FR-042 - Fact Density Scoring
**Requested:** 2026-04-04
**Target phase:** Phase 45
**Priority:** Medium
**Research basis:** NODALIDA 2013 paper *Using Factual Density to Measure Informativeness of Web Documents*, patent `US9286379B2` (*Document Quality Measurement*).
**Spec draft:** `docs/specs/fr042-fact-density-scoring.md`
**Status:** Partial
**Note:** Partial — config keys in migration exist; score field and scoring logic missing

### What's wanted
- Reward destination pages that pack more concrete, fact-like information into fewer words.
- Penalize pages that are mostly vague filler, padding, or generic marketing language.

### Specific controls / behaviour
- New destination-level score: `fact_density_score` bounded `[0.5, 1.0]`.
- Neutral `0.5` for short or underspecified pages where density cannot be estimated reliably.
- Approximate factual propositions using deterministic sentence-level patterns over clean text.
- Normalize estimated fact count by document length, then dampen the score using a filler-sentence ratio.
- New suggestion-level copy field: `score_fact_density`.
- New suggestion diagnostics field: `fact_density_diagnostics`.
- New settings: `fact_density.enabled`, `fact_density.ranking_weight` (default `0.0`), `fact_density.min_word_count`, `fact_density.density_cap_per_100_words`, `fact_density.filler_penalty_weight`.

### Implementation notes for the AI
- Prefer `Post.clean_text`, otherwise `ContentItem.distilled_text`.
- Keep this as a quality-like signal separate from relevance, engagement, and multimedia richness.
- Do not add heavy Open IE dependencies in v1. Use deterministic heuristics only.
- Full spec: `docs/specs/fr042-fact-density-scoring.md`.

---

### FR-043 - Semantic Drift Penalty
**Requested:** 2026-04-04
**Target phase:** Phase 46
**Priority:** Medium
**Research basis:** Hearst TextTiling segmentation math (ACL 1994), patent `US8185378B2` (*Text Coherence Determination*).
**Spec draft:** `docs/specs/fr043-semantic-drift-penalty.md`

### What's wanted
- Penalize destination pages that begin on-topic but drift into unrelated material later.
- Keep focused pages preferred over pages that only look relevant in the opening section.

### Specific controls / behaviour
- New destination-level penalty score: `semantic_drift_penalty_score` bounded `[0.5, 1.0]`.
- Neutral `0.5` for short or single-segment pages where drift cannot be measured reliably.
- Segment destination text using deterministic adjacent-block similarity and depth-score boundaries.
- Use the first coherent segment as the anchor topic and measure how many later segments fall below an anchor-similarity threshold.
- New suggestion-level copy field: `score_semantic_drift_penalty`.
- New suggestion diagnostics field: `semantic_drift_diagnostics`.
- New settings: `semantic_drift.enabled`, `semantic_drift.ranking_weight` (default `0.0`), `semantic_drift.tokens_per_sequence`, `semantic_drift.block_size_in_sequences`, `semantic_drift.anchor_similarity_threshold`, `semantic_drift.min_word_count`.

### Implementation notes for the AI
- Keep this separate from `score_semantic`, `FR-038`, and `FR-039`. Those measure topical fit or novelty, not within-document coherence.
- Compute once per destination and cache the result. Do not recompute per host-destination pair.
- Start as a subtractive experimental penalty with zero ranking weight by default.
- Full spec: `docs/specs/fr043-semantic-drift-penalty.md`.

---

### FR-044 - Internal Search Intensity Signal
**Requested:** 2026-04-04
**Target phase:** Phase 47
**Priority:** Medium
**Research basis:** Matomo Site Search reporting model, Kleinberg burst-detection math, patent `US20050102259A1` (*Systems and Methods for Search Query Processing Using Trend Analysis*).
**Spec draft:** `docs/specs/fr044-internal-search-intensity.md`
**Status:** Partial
**Note:** Partial — config keys in migration exist; score field and analytics aggregation missing

### What's wanted
- Give a temporary boost to destinations that match topics users are actively searching for inside the site right now.
- Use aggregate internal-search demand as a fresh, privacy-safe signal.

### Specific controls / behaviour
- New destination-level score: `internal_search_intensity_score` bounded `[0.5, 1.0]`.
- Neutral `0.5` when internal-search telemetry is missing, stale, or shows no active queries.
- Build daily aggregates for normalized site-search queries and compare recent volume against a longer baseline window.
- Score a destination by the strongest active query it matches, using title/body token overlap against burst-aware query intensity.
- New suggestion-level copy field: `score_internal_search_intensity`.
- New suggestion diagnostics field: `internal_search_diagnostics`.
- New settings: `internal_search.enabled`, `internal_search.ranking_weight` (default `0.0`), `internal_search.recent_days`, `internal_search.baseline_days`, `internal_search.max_active_queries`, `internal_search.min_recent_count`.

### Implementation notes for the AI
- Keep this separate from `FR-016`, `FR-018`, and `FR-019`. This is aggregate search-demand scoring, not attribution telemetry or alerting.
- Store daily aggregate counts only. Do not store user-level query histories in the ranking path.
- Matomo Site Search is the preferred first source if site-search tracking is available.
- Full spec: `docs/specs/fr044-internal-search-intensity.md`.

---

### FR-045 - Anchor Diversity & Exact-Match Reuse Guard
**Requested:** 2026-04-04
**Target phase:** Phase 48
**Priority:** Medium
**Status:** ✅ Complete (2026-04-20, Tier 2 slice 6). Python reference scorer ships (`backend/apps/pipeline/services/anchor_diversity.py`, `Suggestion.score_anchor_diversity`, `Suggestion.anchor_diversity_diagnostics`, migrations 0031/0032, six `anchor_diversity.*` settings keys). **C++ batch fast path** now ships at `backend/extensions/anchor_diversity.cpp` + `backend/extensions/include/anchor_diversity_core.h`, exposed as the `anchor_diversity` pybind11 module, with per-formula `PARITY:` comments per CPP-RULES §25. **Parity test** at `backend/tests/test_parity_anchor_diversity.py` asserts C++/Python agreement at `atol=1e-6, rtol=0` across 5 scenarios covering every state branch. **Pytest benchmark** at `backend/benchmarks/test_bench_anchor_diversity.py` runs both paths at 100 / 1 000 / 5 000 candidates; Google Benchmark at `backend/extensions/benchmarks/bench_anchor_diversity.cpp` covers 100 / 5 000 / 50 000. Python `evaluate_anchor_diversity_batch` delegates to the C++ fast path via `HAS_CPP_EXT` guard. ISS-020 (ledger drift) closed in `docs/reports/REPORT-REGISTRY.md`.
**Research basis:** Google Search Central link-text guidance, Google Search Central spam policies, patent `US20110238644A1` (*Using Anchor Text With Hyperlink Structures for Web Searches*). User-supplied `US7814085B1` was checked and rejected as the wrong source for this topic.
**Spec draft:** `docs/specs/fr045-anchor-diversity-exact-match-reuse-guard.md`

### What's wanted
- Stop one exact anchor phrase from becoming too dominant for the same destination across active suggestions.
- Reduce spammy exact-match repetition without changing phrase matching, learned anchors, or telemetry.

### Specific controls / behaviour
- New suggestion-level score: `score_anchor_diversity` with neutral `0.5` and lower values when the anchor is overly repetitive for the destination.
- New suggestion diagnostics field: `anchor_diversity_diagnostics`.
- Keep `repeated_anchor`, but formalize it as a normalized exact-match warning instead of an ad-hoc flag.
- Score uses active suggestion history for the same destination only, in statuses `pending`, `approved`, `applied`, and `verified`.
- Optional hard block when exact-match count would exceed a configured cap.
- New settings: `anchor_diversity.enabled`, `anchor_diversity.ranking_weight` (default `0.0`), `anchor_diversity.min_history_count`, `anchor_diversity.max_exact_match_share`, `anchor_diversity.max_exact_match_count`, `anchor_diversity.hard_cap_enabled`.

### Implementation notes for the AI
- Keep this separate from `FR-008`. `FR-008` chooses the anchor phrase; `FR-045` scores whether that chosen phrase is overused.
- Keep this separate from `FR-009`. Do not use `ExistingLink.anchor_text` as the repetition corpus in v1; use `Suggestion` history only.
- Keep this separate from `FR-015`. This is anchor-level anti-spam control, not destination-slate diversity.
- Keep this separate from `FR-016` to `FR-018`. No CTR, dwell, approval rates, or delayed reward inputs are allowed.
- This changes hot ranking behavior, so the implementation phase must include both a Python reference path and a C++ batch fast path with parity tests.
- Full spec: `docs/specs/fr045-anchor-diversity-exact-match-reuse-guard.md`.

---

### FR-046 — Multi-Query Fan-Out for Stage 1 Candidate Retrieval
**Requested:** 2026-04-05
**Target phase:** TBD
**Status:** Pending
**Priority:** Medium
**Research basis:** Chen et al. arXiv:2402.03216 (bge-m3 multi-vector); Cormack et al. SIGIR 2009 (RRF); Khattab & Zaharia arXiv:2004.12832 (ColBERT); US8,682,892 B1; US9,342,607 B2; US20190138669 A1
**Spec:** `docs/specs/fr046-query-fan-out-stage1-retrieval.md`

Improves Stage 1 recall for multi-topic destination pages. Instead of embedding a destination as one vector, the page is decomposed into up to N segments (title, intro, body chunks). Each segment is embedded independently, a top-K similarity search is run per segment, and results are merged with Reciprocal Rank Fusion (RRF) before passing to Stage 2. Short pages fall back to the existing single-vector path. **On by default** in the Recommended preset — the short-page fallback makes it safe to ship enabled from day one.

---

### FR-047 — Navigation Path Prediction
**Requested:** 2026-04-06
**Target phase:** TBD
**Status:** Pending
**Priority:** Medium
**Research basis:** Patent US7584181B2 (*Implicit Links Search Enhancement System and Method*), first-order Markov chain navigation models, Kleinberg sequential pattern mining.
**Spec:** `docs/specs/fr047-navigation-path-prediction.md`

### What's wanted
- Detect ordered user navigation sequences from GA4 page_view events and recommend links that shortcut common multi-hop journeys.
- Use directional transition probabilities (A → B, not just {A, B} co-occurrence) as a ranking signal.

### Specific controls / behaviour
- New suggestion-level score: `score_navigation_path` bounded `[0.5, 1.0]`.
- Neutral `0.5` when GA4 data is missing, source page has fewer than `min_sessions`, or transition count is below `min_transition_count`.
- Builds a first-order Markov transition matrix from session-grouped page_view sequences. Computes direct transition probability `P(dest | source)` and indirect shortcut value through intermediate pages.
- Confidence damping blends toward neutral when evidence is thin.
- New suggestion diagnostics field: `navigation_path_diagnostics`.
- New settings: `navigation_path.enabled`, `navigation_path.ranking_weight` (default `0.0`), `navigation_path.lookback_days`, `navigation_path.min_sessions`, `navigation_path.min_transition_count`, `navigation_path.w_direct`, `navigation_path.w_shortcut`.

### Implementation notes for the AI
- Keep this separate from `FR-025`. FR-025 is unordered session co-occurrence; FR-047 is ordered Markov transition sequences. They are complementary, not overlapping.
- Keep this separate from `FR-024`. FR-024 measures single-page dwell; FR-047 measures page-to-page transitions.
- Consumes existing GA4 `page_view` events from FR-016 — do not add new GA4 import logic.
- Daily batch aggregation only in v1. No real-time streaming.
- This changes hot ranking behavior, so the implementation phase must include both a Python reference path and a C++ batch fast path with parity tests.
- Full spec: `docs/specs/fr047-navigation-path-prediction.md`.

---

### FR-048 — Topical Authority Cluster Density
**Requested:** 2026-04-06
**Target phase:** TBD
**Status:** Pending
**Priority:** Medium
**Research basis:** Kleinberg HITS algorithm (1999), Majestic Topical Trust Flow methodology, HDBSCAN density-based clustering (Campello et al. 2013), Google Search Quality Evaluator Guidelines topical authority concept.
**Spec:** `docs/specs/fr048-topical-authority-cluster-density.md`

### What's wanted
- Score destination pages higher when the site has deep topical coverage around that destination's subject.
- Use semantic embedding clusters (not URL structure) to measure topical depth.

### Specific controls / behaviour
- New suggestion-level score: `score_topical_cluster` bounded `[0.5, 1.0]`.
- Neutral `0.5` when clustering is disabled, site has fewer than `min_site_pages` pages, page is a noise outlier, or clusters are stale.
- Clusters all site pages using existing bge-m3 embeddings via HDBSCAN. Computes per-page density as `log(cluster_size) / log(max_cluster_size)`, bounded to `[0.5, 1.0]`.
- Optional staleness decay blends toward neutral as cluster assignments age beyond `max_staleness_days`.
- New suggestion diagnostics field: `topical_cluster_diagnostics`.
- New settings: `topical_cluster.enabled`, `topical_cluster.ranking_weight` (default `0.0`), `topical_cluster.min_cluster_size`, `topical_cluster.min_site_pages`, `topical_cluster.max_staleness_days`, `topical_cluster.fallback_value`.

### Implementation notes for the AI
- Keep this separate from `FR-039`. FR-039 scores individual salient terms on one page; FR-048 measures the size of the topic cluster the page belongs to.
- Keep this separate from silo-aware ranking. Silo groups by URL path prefix; FR-048 groups by semantic embedding similarity.
- Keep this separate from `FR-015`. FR-015 diversifies the suggestion slate; FR-048 scores individual destinations by cluster depth.
- Uses existing `ContentItem.embedding` vectors — do not re-embed pages.
- HDBSCAN runs daily or per-pipeline-run, not per-suggestion. Cache cluster assignments on `ContentItem`.
- This changes hot ranking behavior, so the implementation phase must include both a Python reference path and a C++ batch fast path with parity tests.
- Full spec: `docs/specs/fr048-topical-authority-cluster-density.md`.

---

### FR-049 — Query Intent Funnel Alignment
**Requested:** 2026-04-06
**Target phase:** TBD
**Status:** Pending
**Priority:** Medium
**Research basis:** Patent WO2015200404A1 (*Query Intent Identification from Reformulations*), patent US20110289063A1 (*Determining Query Intent*), standard search marketing funnel models (informational → commercial investigation → transactional).
**Spec:** `docs/specs/fr049-query-intent-funnel-alignment.md`

### What's wanted
- Classify each page into an intent stage (navigational, informational, commercial, transactional) using GSC query patterns and content keyword matching.
- Boost links that move users one stage forward through the buyer journey funnel.

### Specific controls / behaviour
- New suggestion-level score: `score_intent_funnel` bounded `[0.5, 1.0]`.
- Neutral `0.5` when intent classification confidence is below `min_confidence`, GSC data is missing and content-only fallback is inconclusive, or either page is navigational.
- Classifies pages via keyword pattern matching against GSC query strings (primary) or page title/body (fallback). Computes funnel distance between source and destination stages. Maps distance to a Gaussian alignment score peaked at `+1` (one stage forward).
- Confidence damping from both source and destination classifications.
- New suggestion diagnostics field: `intent_funnel_diagnostics`.
- New settings: `intent_funnel.enabled`, `intent_funnel.ranking_weight` (default `0.0`), `intent_funnel.optimal_offset`, `intent_funnel.sigma`, `intent_funnel.min_confidence`, `intent_funnel.navigational_confidence_threshold`.

### Implementation notes for the AI
- Keep this separate from `FR-047`. FR-047 models observed navigation transitions (where users *go*); FR-049 models intent-stage progression (where users *should logically go next*).
- Keep this separate from `FR-025`. FR-025 is unordered session co-occurrence; FR-049 is directed funnel alignment.
- Keep this separate from `FR-016` / `FR-017`. FR-016/017 aggregate traffic metrics; FR-049 classifies queries by intent type.
- Consumes existing GSC query data from FR-017 — do not add new GSC import logic.
- Keyword pattern matching only in v1. No external NLP or ML models.
- This changes hot ranking behavior, so the implementation phase must include both a Python reference path and a C++ batch fast path with parity tests.
- Full spec: `docs/specs/fr049-query-intent-funnel-alignment.md`.

---

### FR-050 — Seasonality & Temporal Demand Matching
**Requested:** 2026-04-06
**Target phase:** TBD
**Status:** Pending
**Priority:** Medium
**Research basis:** Patent US9081857B1 (*Freshness and Seasonality-Based Content Determinations*), classical time-series seasonal decomposition, Google QDF (Query Deserves Freshness) concept.
**Spec:** `docs/specs/fr050-seasonality-temporal-demand.md`

### What's wanted
- Detect annual seasonal traffic patterns per page from 12+ months of GA4/GSC history.
- Dynamically boost destinations whose seasonal peak is approaching and dampen destinations in their off-season.

### Specific controls / behaviour
- New suggestion-level score: `score_seasonality` bounded `[0.5, 1.0]`.
- Neutral `0.5` when page has no seasonal pattern (`seasonal_strength < min_seasonal_strength`), fewer than `min_history_months` of data, or feature is disabled.
- Computes a 12-month seasonal index per page via ratio-to-moving-average decomposition. Measures seasonal strength as variance ratio. Blends current-month index with an anticipation bonus for pages whose peak is within `anticipation_window_months`. Seasonal strength gates the final score so weakly-seasonal pages stay near neutral.
- New suggestion diagnostics field: `seasonality_diagnostics`.
- New settings: `seasonality.enabled`, `seasonality.ranking_weight` (default `0.0`), `seasonality.min_history_months`, `seasonality.min_seasonal_strength`, `seasonality.anticipation_window_months`, `seasonality.w_current`, `seasonality.w_anticipation`, `seasonality.index_cap`.

### Implementation notes for the AI
- Keep this separate from `FR-023`. FR-023 is reactive (recent traffic momentum); FR-050 is predictive (annual seasonal curves).
- Keep this separate from `FR-016` / `FR-017`. FR-016/017 aggregate raw traffic; FR-050 decomposes traffic into seasonal components.
- Keep this separate from `FR-044`. FR-044 detects short-term search demand bursts; FR-050 detects predictable annual cycles.
- Consumes existing GA4/GSC data from FR-016/FR-017 — do not add new import logic.
- Monthly model recomputation only. No real-time seasonal updates.
- Simple ratio-to-moving-average decomposition in v1. No Prophet, ARIMA, or external time-series libraries.
- This changes hot ranking behavior, so the implementation phase must include both a Python reference path and a C++ batch fast path with parity tests.
- Full spec: `docs/specs/fr050-seasonality-temporal-demand.md`.

---

### FR-051 — Reference Context Scoring
**Requested:** 2026-04-07
**Target phase:** TBD
**Status:** Pending
**Priority:** Medium
**Research basis:** Patent US8577893B1 (*Ranking Based on Reference Contexts*, Google 2013).
**Spec:** `docs/specs/fr051-reference-context-scoring.md`

### What's wanted
- Score the ±5-token window around each link insertion point using IDF-weighted rare-word overlap with the destination page.

### Specific controls / behaviour
- New score computed at ranking time per (source_sentence, destination_page) pair.
- Formula: `score = (1/|W|) × Σ_{t ∈ W ∩ D} IDF(t)`, normalised per-query to [0,1].
- Reuses existing BM25 IDF vocabulary — no new model required.
- Settings: `reference_context.enabled`, `reference_context.ranking_weight` (default `0.03`), `reference_context.window_tokens`, `reference_context.idf_smoothing`.
- C++ extension: `refcontext.cpp`.

### Implementation notes for the AI
- Keep separate from `score_keyword` (Jaccard on full token sets) — this is micro-context (10-word window) only.
- Keep separate from `score_semantic` (embedding cosine) — this is token-level, not embedding-level.
- C++ hot path mandatory. Full spec: `docs/specs/fr051-reference-context-scoring.md`.

---

### FR-052 — Readability Level Matching
**Requested:** 2026-04-07
**Target phase:** TBD
**Status:** Pending
**Priority:** Medium
**Research basis:** Patent US20070067294A1 (*Readability and Context Identification and Exploitation*, Google 2005).
**Spec:** `docs/specs/fr052-readability-level-matching.md`

### What's wanted
- Compute Flesch-Kincaid grade level for source and destination pages; penalise links where grade levels differ by more than 3.

### Specific controls / behaviour
- Formula: `FK_grade = 0.39 × (words/sentences) + 11.8 × (syllables/words) - 15.59`. Penalty: `max(0, |FK_src - FK_dst| - 3) / 10`. Score: `max(0, 1 - penalty)`.
- Stored as one float per page at index time.
- Settings: `readability_match.enabled`, `readability_match.ranking_weight` (default `0.02`), `readability_match.max_grade_gap`, `readability_match.penalty_per_grade`.

### Implementation notes for the AI
- Pure Python formula — no C++ needed (three arithmetic ops per page).
- Keep separate from all existing signals — no existing signal measures readability.

---

### FR-053 — Passage-Level Relevance Scoring
**Requested:** 2026-04-07
**Target phase:** TBD
**Status:** Pending
**Priority:** High
**Research basis:** Patent US9940367B1 (*Scoring Candidate Answer Passages*, Google 2018).
**Spec:** `docs/specs/fr053-passage-level-relevance.md`

### What's wanted
- Score each destination at sub-document granularity by finding the best-matching passage (~200 words) rather than scoring the full page.

### Specific controls / behaviour
- Chunk each destination into k=5 passages. Encode each as 1024-dim BGE-M3 vector.
- Formula: `score = max_{i=1..k} cos_sim(query_sentence_embedding, passage_i_embedding)`.
- Passage embeddings stored as separate int8-quantised FAISS index (~256 MB).
- Settings: `passage_relevance.enabled`, `passage_relevance.ranking_weight` (default `0.05`), `passage_relevance.passages_per_page`, `passage_relevance.passage_words`, `passage_relevance.index_quantised`.
- C++ extension: `passagesim.cpp`.

### Implementation notes for the AI
- Keep separate from `score_semantic` (full-document cosine). This is passage-level, not page-level.
- int8 quantisation via `quantemb.cpp` (OPT-06) to keep RAM under 256 MB.

---

### FR-054 — Boilerplate-to-Content Ratio
**Requested:** 2026-04-07
**Target phase:** TBD
**Status:** Pending
**Priority:** Medium
**Research basis:** Patent US8898296B2 (*Detection of Boilerplate Content*, Google 2014).
**Spec:** `docs/specs/fr054-boilerplate-content-ratio.md`

### What's wanted
- Measure the fraction of a destination page that is main content vs. navigation/footer/sidebar chrome. Penalise thin-content destinations.

### Specific controls / behaviour
- Formula: `score = content_chars / total_chars`. Penalise when `score < boilerplate_threshold`.
- Computed at crawl time from DOM zone extraction.
- Settings: `boilerplate_ratio.enabled`, `boilerplate_ratio.ranking_weight` (default `0.02`), `boilerplate_ratio.boilerplate_threshold`, `boilerplate_ratio.min_content_chars`.

### Implementation notes for the AI
- Pure Python — no C++ needed (string length comparison at index time).
- Keep separate from all quality signals — no existing signal measures boilerplate ratio.

---

### FR-055 — Reasonable Surfer Click Probability
**Requested:** 2026-04-07
**Target phase:** TBD
**Status:** Pending
**Priority:** Medium
**Research basis:** Patent US8117209B1 (*Ranking Documents Based on User Behavior and/or Feature Data*, Google 2012).
**Spec:** `docs/specs/fr055-reasonable-surfer-click-probability.md`

### What's wanted
- Score each candidate link by where it would appear on the page: body zone, paragraph index, anchor length, emphasis.

### Specific controls / behaviour
- Formula: `raw = zone_weight × position_decay × anchor_length_factor × emphasis_factor`, normalised to [0,1].
- `position_decay = 1 / (1 + ln(paragraph_index + 1))`.
- Settings: `reasonable_surfer.enabled`, `reasonable_surfer.ranking_weight` (default `0.03`), zone weights, `reasonable_surfer.emphasis_boost`.

### Implementation notes for the AI
- Computed at ranking time per candidate insertion point. Not persisted.
- Keep separate from `score_quality` (PageRank-based). This is position-based, not authority-based.

---

### FR-056 — Long-Click Satisfaction Ratio
**Requested:** 2026-04-07
**Target phase:** TBD
**Status:** Pending
**Priority:** High
**Research basis:** Patent US10229166B1 (*Modifying Search Result Ranking Based on Implicit User Feedback*, Google 2019).
**Spec:** `docs/specs/fr056-long-click-satisfaction-ratio.md`

### What's wanted
- Ratio of sessions where users stayed on the destination >30 s to sessions where they bounced within 10 s. Derived from GA4 session data.

### Specific controls / behaviour
- Formula: `score = (long_clicks + α) / (long_clicks + short_clicks + 2α)`, α=5 (Laplace smoothing).
- Updated daily from GA4 session import.
- Settings: `long_click_ratio.enabled`, `long_click_ratio.ranking_weight` (default `0.04`), `long_click_ratio.long_session_seconds`, `long_click_ratio.short_session_seconds`, `long_click_ratio.laplace_alpha`.

### Implementation notes for the AI
- Uses GA4 data already imported by FR-016. No new import logic.
- Keep separate from `value_model.w_engagement` (read-through rate). This is binary long/short; engagement is continuous time ratio.

---

### FR-057 — Content-Update Magnitude
**Requested:** 2026-04-07
**Target phase:** TBD
**Status:** Pending
**Priority:** Medium
**Research basis:** Patent US8549014B2 (*Document Scoring Based on Document Content Update*, Google 2013).
**Spec:** `docs/specs/fr057-content-update-magnitude.md`

### What's wanted
- Measure how much real content changed between crawls via token symmetric-difference ratio.

### Specific controls / behaviour
- Formula: `magnitude = |tokens_new △ tokens_old| / max(|tokens_new|, |tokens_old|)`.
- Stored as one float per page, updated on each re-crawl.
- Settings: `content_update.enabled`, `content_update.ranking_weight` (default `0.02`), `content_update.max_staleness_days`.

### Implementation notes for the AI
- Keep separate from `link_freshness` (time-based). This is content-based, not timestamp-based.
- Pure Python (set operations at index time, not ranking time).

---

### FR-058 — N-gram Writing Quality Prediction
**Requested:** 2026-04-07
**Target phase:** TBD
**Status:** Pending
**Priority:** Medium
**Research basis:** Patent US9767157B2 (*Predicting Site Quality*, Google/Panda 2017).
**Spec:** `docs/specs/fr058-ngram-writing-quality.md`

### What's wanted
- Build a Kneser-Ney smoothed n-gram language model on known-good pages; score destinations by inverse perplexity to catch auto-generated or spun content.

### Specific controls / behaviour
- Formula: `perplexity(T) = exp(-1/|T| × Σ log P_KN(tᵢ|context))`. Score: `1 / (1 + log(PP / baseline_PP))`.
- n-gram model (~200 MB on disk, discardable after scoring).
- Settings: `ngram_quality.enabled`, `ngram_quality.ranking_weight` (default `0.03`), `ngram_quality.max_n`, `ngram_quality.kn_discount`, `ngram_quality.baseline_perplexity`.
- C++ extension: `ngramqual.cpp`.

### Implementation notes for the AI
- Keep separate from `score_keyword` (overlap metric). This is a language model quality metric.
- C++ hot path for perplexity computation over long token sequences.

---

### FR-059 — Topic Purity Score
**Requested:** 2026-04-07
**Target phase:** TBD
**Status:** Pending
**Priority:** Medium
**Research basis:** Patent US20210004416A1 (*Extracting Key Phrase Candidates and Producing Topical Authority Ranking*, Google 2020).
**Spec:** `docs/specs/fr059-topic-purity-score.md`

### What's wanted
- Fraction of sentences in a site section whose embeddings exceed a cosine-similarity threshold with the section centroid.

### Specific controls / behaviour
- Formula: `purity = on_topic_sentences / total_sentences` where on_topic = `cos_sim(sentence_emb, section_centroid) > θ`.
- Stored as one float per (section, topic) pair at index time.
- Settings: `topic_purity.enabled`, `topic_purity.ranking_weight` (default `0.04`), `topic_purity.on_topic_threshold`, `topic_purity.min_sentences`.

### Implementation notes for the AI
- Keep separate from `FR-048` topical cluster density (cluster-level). This is section-level sentence purity.
- Uses existing BGE-M3 embeddings — no new model.

---

### FR-060 — ListNet Listwise Ranking
**Requested:** 2026-04-07
**Target phase:** TBD
**Status:** Pending
**Priority:** High
**Research basis:** Patent US7734633B2 (*Listwise Ranking*, Microsoft 2010).
**Spec:** `docs/specs/fr060-listnet-listwise-ranking.md`

### What's wanted
- LightGBM model with objective=rank:ndcg trained on editor-approved/rejected lists. Learns from relative ordering of entire batches.

### Specific controls / behaviour
- Plackett-Luce top-1 probability: `P(i|s) = exp(sᵢ) / Σⱼ exp(sⱼ)`. Loss: cross-entropy between true and predicted distributions.
- Model output replaces the composite score at inference — not additive.
- Settings: `listnet.enabled` (default `false`), `listnet.n_estimators`, `listnet.num_leaves`, `listnet.learning_rate`, `listnet.min_training_samples`, `listnet.model_refresh_days`.

### Implementation notes for the AI
- Keep separate from FR-018 (L-BFGS weight tuner). ListNet replaces the scorer; L-BFGS tunes weights within the existing scorer.
- Disabled by default until sufficient training data exists.

---

### FR-061 — RankBoost Weight Optimisation (Weights-Only Mode)
**Requested:** 2026-04-07
**Target phase:** TBD
**Status:** Pending
**Priority:** High
**Research basis:** Patent US8301638B2 (*Automated Feature Selection Based on RankBoost for Ranking*, Microsoft 2012).
**Spec:** `docs/specs/fr061-rankboost-weight-optimisation.md`

### What's wanted
- Adjust signal importance weights up or down via AdaBoost on pairwise preferences from GSC, Matomo, and GA4 data. NEVER drops a signal — floor weight enforced.

### Specific controls / behaviour
- At each round t: find best weak ranker, compute α_t, update sample distribution.
- Weight update: `wᵢ ← max(w_min=0.01, wᵢ + η × δᵢ)`. Floor enforced on all signals.
- Data sources: GSC click/impression deltas, Matomo per-suggestion CTR, GA4 session engagement.
- Settings: `rankboost.enabled` (default `false`), `rankboost.n_rounds`, `rankboost.learning_rate`, `rankboost.min_weight_floor`, `rankboost.data_sources`, `rankboost.retrain_days`.

### Implementation notes for the AI
- Keep separate from FR-018 (L-BFGS tuner). RankBoost is boosting-based pairwise; L-BFGS is gradient-based on a proxy loss.
- CRITICAL: never set any weight to zero. The user explicitly required weights-only mode.

---

### FR-062 — Particle Thompson Sampling + Matrix Factorisation (PTS-MF)
**Requested:** 2026-04-07
**Target phase:** TBD
**Status:** Pending
**Priority:** Medium
**Research basis:** Patent US10332015B2 (*Particle Thompson Sampling for Online Matrix Factorization Recommendation*, Adobe 2019).
**Spec:** `docs/specs/fr062-particle-thompson-sampling-mf.md`

### What's wanted
- Rao-Blackwellized particle filter for online Bayesian matrix factorisation. Solves the cold-start problem.

### Specific controls / behaviour
- Model: `P(r_{ui}=1 | U, V) = σ(uᵢ · vⱼᵀ)`. 30 particles, latent dim=20.
- Score: `ŝ(u,i) = Σ_p w^p × σ(U^p_{u:} · V^p_{i:})`.
- Settings: `pts_mf.enabled` (default `false`), `pts_mf.latent_dim`, `pts_mf.n_particles`, `pts_mf.prior_variance`, `pts_mf.resample_ess_threshold`, `pts_mf.model_refresh_days`.

### Implementation notes for the AI
- Keep separate from FR-013 (UCB1 explore/exploit). PTS-MF is collaborative filtering; UCB1 is bandit.
- RAM budget: ~240 MB. Reduced via L=20, P=30.

---

### FR-063 — Multi-Hyperplane Ranker Ensemble (MHR)
**Requested:** 2026-04-07
**Target phase:** TBD
**Status:** Pending
**Priority:** Medium
**Research basis:** Patent US8122015B2 (*Multi-Ranker For Search*, Microsoft 2012).
**Spec:** `docs/specs/fr063-multi-hyperplane-ranker.md`

### What's wanted
- 6 grade-pair SVMs (for grades 0-3) with BordaCount aggregation. Learns that features separating "great from good" differ from "good from bad".

### Specific controls / behaviour
- For each pair (a,b): train LinearSVC. BordaCount: `score(x) = Σ (n - rank_{ab}(x))`.
- Settings: `mhr.enabled` (default `false`), `mhr.n_grades`, `mhr.svm_c`, `mhr.svm_max_iter`, `mhr.retrain_days`.

### Implementation notes for the AI
- Keep separate from FR-060 (ListNet). MHR uses grade-pair SVMs; ListNet uses LightGBM.
- scikit-learn LinearSVC — no custom C++ needed.

---

### FR-064 — Spectral Relational Clustering (SRC)
**Requested:** 2026-04-07
**Target phase:** TBD
**Status:** Pending
**Priority:** Medium
**Research basis:** Patent US8185481B2 (*Spectral Clustering for Multi-Type Relational Data*, SUNY 2012).
**Spec:** `docs/specs/fr064-spectral-relational-clustering.md`

### What's wanted
- Joint Laplacian eigen decomposition on page-anchor and page-query relation matrices. Richer topic clusters than single-type HDBSCAN.

### Specific controls / behaviour
- `L_joint = λ₁L₁ + λ₂L₂`. Top d=16 eigenvectors → K-Means(K=32).
- Settings: `spectral_rc.enabled` (default `false`), `spectral_rc.n_clusters`, `spectral_rc.eigen_dim`, `spectral_rc.relation_weight_anchor`, `spectral_rc.relation_weight_query`, `spectral_rc.rebuild_days`.

### Implementation notes for the AI
- Keep separate from FR-014 (HDBSCAN near-duplicate clustering). SRC is multi-relational spectral; HDBSCAN is density-based single-view.
- scipy.sparse.linalg.eigsh + sklearn KMeans — no custom C++ needed.

---

### FR-065 — Isotonic Regression Score Calibration
**Requested:** 2026-04-07
**Target phase:** TBD
**Status:** Pending
**Priority:** Medium
**Research basis:** Patent US9189752B1 (*Interpolating Isotonic Regression for Binary Classification*, Google 2015).
**Spec:** `docs/specs/fr065-isotonic-regression-calibration.md`

### What's wanted
- Post-scoring calibration mapping raw composite scores to calibrated probabilities via Pool-Adjacent-Violators + Delaunay interpolation.

### Specific controls / behaviour
- PAV algorithm: O(n). Delaunay interpolation for continuous output.
- Applied after all other scoring: `p_calibrated = IR_model.predict([composite_score])`.
- Settings: `isotonic_calibration.enabled` (default `false`), `isotonic_calibration.min_training_samples`, `isotonic_calibration.retrain_days`.

### Implementation notes for the AI
- scikit-learn IsotonicRegression — no custom C++ needed.
- Keep separate from all scoring signals — this is a post-scoring calibration layer.

---

### FR-066 — SmoothRank: Direct Metric Optimisation (META-01)
**Requested:** 2026-04-07
**Target phase:** TBD
**Status:** Pending
**Priority:** High
**Research basis:** Patent US7895198B2 (*Gradient Based Optimization of a Ranking Measure*, Yahoo 2011).
**Spec:** `docs/specs/fr066-smoothrank-ndcg-optimisation.md`

### What's wanted
- Differentiable NDCG approximation via sigmoid-based position smoothing, then gradient ascent directly on the ranking metric.

### Specific controls / behaviour
- Smooth rank: `π_σ(i) = 1 + Σⱼ≠ᵢ σ((sⱼ - sᵢ) / σ_temp)`. DCG_smooth via soft discount.
- σ_temp annealed from 1.0 to 0.05 over training.
- Settings: `smoothrank.enabled` (default `false`), `smoothrank.sigma_init`, `smoothrank.sigma_min`, `smoothrank.sigma_anneal`, `smoothrank.learning_rate`, `smoothrank.n_epochs`, `smoothrank.retrain_days`.
- C++ extension: `smoothrank.cpp`.

### Implementation notes for the AI
- Keep separate from FR-018 (L-BFGS on proxy loss). SmoothRank optimises the actual NDCG metric.
- C++ hot path mandatory for gradient computation over n² sigmoid calls.

---

### FR-067 — Supervised Rank Aggregation via Markov Chains (META-02)
**Requested:** 2026-04-07
**Target phase:** TBD
**Status:** Pending
**Priority:** Medium
**Research basis:** Patent US7840522B2 (*Supervised Rank Aggregation Based on Rankings*, Microsoft/Tie-Yan Liu 2010).
**Spec:** `docs/specs/fr067-markov-chain-rank-aggregation.md`

### What's wanted
- Learn per-source mixing weights for combining heterogeneous ranked lists using Markov chain stationary distributions, optimised via SDP.

### Specific controls / behaviour
- Transition matrix per source. `π = stationary(Σ_k λ_k T_k)` via power iteration.
- SDP: `min ‖T* - Σ_k λ_k T_k‖_F²` s.t. `λ ≥ 0, Σλ = 1`.
- Settings: `rank_aggregation.enabled` (default `false`), `rank_aggregation.sdp_max_iter`, `rank_aggregation.sdp_tol`, `rank_aggregation.power_iter_max`, `rank_aggregation.power_iter_tol`, `rank_aggregation.retrain_days`.
- C++ extension: `rankagg.cpp`.

### Implementation notes for the AI
- Keep separate from FR-046 (unsupervised RRF). This is supervised with editorial labels.
- C++ for matrix construction and power iteration.

---

### FR-068 — Cascade Telescoping Re-Ranking (META-03)
**Requested:** 2026-04-07
**Target phase:** TBD
**Status:** Pending
**Priority:** High
**Research basis:** Patent US7689615B2 (*Ranking Results Using Multiple Nested Ranking*, Microsoft 2010).
**Spec:** `docs/specs/fr068-cascade-telescoping-reranking.md`

### What's wanted
- 3-stage cascade: all N candidates → top 200 → top 50 → top 10 via progressively richer feature sets. Reduces compute 3-5x.

### Specific controls / behaviour
- Stage 1: cheap features (Jaccard, scope, boilerplate). Stage 2: +BM25, phrase match. Stage 3: +embeddings, all signals.
- Each stage: `Linear(d, 32) → ReLU → Linear(32, 1)`. Trained on pruned datasets.
- Settings: `cascade_rerank.enabled` (default `false`), `cascade_rerank.stage1_top_n`, `cascade_rerank.stage2_top_n`, `cascade_rerank.stage3_top_n`, `cascade_rerank.net_hidden_size`, `cascade_rerank.adam_lr`, `cascade_rerank.retrain_days`.
- C++ extension: `cascade.cpp`.

### Implementation notes for the AI
- C++ hot path for stage scoring (small neural net forward pass).
- Replaces the single-pass scoring with a 3-stage pipeline. Existing signals are not removed — just evaluated at different stages.

---

### FR-069 — Viral Propagation Depth
**Requested:** 2026-04-07 | **Status:** Pending | **Priority:** Low
**Research basis:** US10152544B1 (Meta). Score: `log(depth+1)/log(max_depth+1)`.
**Spec:** `docs/specs/fr069-viral-propagation-depth.md`
- Settings: `viral_depth.enabled`, `viral_depth.ranking_weight` (0.02).

---

### FR-070 — Viral Content Recipient Ranking
**Requested:** 2026-04-07 | **Status:** Pending | **Priority:** Low
**Research basis:** US9323850B1 (Google/YouTube). Recipient authority scoring.
**Spec:** `docs/specs/fr070-viral-recipient-ranking.md`
- Settings: `viral_recipient.enabled`, `viral_recipient.ranking_weight` (0.02).

---

### FR-071 — Large-Scale Sentiment Score
**Requested:** 2026-04-07 | **Status:** Pending | **Priority:** Low
**Research basis:** US7996210B2 (Google). VADER compound polarity mapped [0,1].
**Spec:** `docs/specs/fr071-large-scale-sentiment-score.md`
- Settings: `sentiment_score.enabled`, `sentiment_score.ranking_weight` (0.02).

---

### FR-072 — Trending Content Velocity
**Requested:** 2026-04-07 | **Status:** Pending | **Priority:** Low
**Research basis:** US20150169587A1 (Meta/CrowdTangle). 6-hour engagement acceleration.
**Spec:** `docs/specs/fr072-trending-content-velocity.md`
- Settings: `trending_velocity.enabled`, `trending_velocity.ranking_weight` (0.02).

---

### FR-073 — Professional Graph Proximity
**Requested:** 2026-04-07 | **Status:** Pending | **Priority:** Low
**Research basis:** US20140244561A1 (LinkedIn). Jaccard of GA4 user-ID sets.
**Spec:** `docs/specs/fr073-professional-graph-proximity.md`
- Settings: `professional_proximity.enabled`, `professional_proximity.ranking_weight` (0.02).

---

### FR-074 — Influence Score
**Requested:** 2026-04-07 | **Status:** Pending | **Priority:** Low
**Research basis:** US20140019539A1 (Google). Social reshare-graph PageRank.
**Spec:** `docs/specs/fr074-influence-score.md`
- Settings: `influence_score.enabled`, `influence_score.ranking_weight` (0.02).

---

### FR-075 — Watch-Time Completion Rate
**Requested:** 2026-04-07 | **Status:** Pending | **Priority:** Low
**Research basis:** US9098511B1 (Google/YouTube). Video completion ratio Laplace-smoothed.
**Spec:** `docs/specs/fr075-watch-time-completion-rate.md`
- Settings: `watch_completion.enabled`, `watch_completion.ranking_weight` (0.02).

---

### FR-076 — Dwell-Time Interest Profile Match
**Requested:** 2026-04-07 | **Status:** Pending | **Priority:** Low
**Research basis:** US20150127662A1 (Google). `score = exp(-|μ_src - μ_dst| / 60)`.
**Spec:** `docs/specs/fr076-dwell-time-profile-match.md`
- Settings: `dwell_profile_match.enabled`, `dwell_profile_match.ranking_weight` (0.02).

---

### FR-077 — Geographic Engagement Concentration
**Requested:** 2026-04-07 | **Status:** Pending | **Priority:** Low
**Research basis:** US20080086264A1 (Google). Herfindahl index: `H = Σ(s_country)²`, score = 1 - H.
**Spec:** `docs/specs/fr077-geographic-engagement-concentration.md`
- Settings: `geo_concentration.enabled`, `geo_concentration.ranking_weight` (0.02).

---

### FR-078 — Community Upvote Velocity
**Requested:** 2026-04-07 | **Status:** Pending | **Priority:** Low
**Research basis:** US20140244561A1 (Reddit-derived). First-hour upvote rate vs median.
**Spec:** `docs/specs/fr078-community-upvote-velocity.md`
- Settings: `upvote_velocity.enabled`, `upvote_velocity.ranking_weight` (0.02).

---

### FR-079 — Spam Account Interaction Filter
**Requested:** 2026-04-07 | **Status:** Pending | **Priority:** Low
**Research basis:** WO2013140410A1. `score = 1 - spam_ratio`.
**Spec:** `docs/specs/fr079-spam-interaction-filter.md`
- Settings: `spam_filter.enabled`, `spam_filter.ranking_weight` (0.02).

---

### FR-080 — Content Freshness Decay Rate
**Requested:** 2026-04-07 | **Status:** Pending | **Priority:** Low
**Research basis:** US8832088B1 (Google). Exponential decay: `score = 1/(1+λ)`.
**Spec:** `docs/specs/fr080-content-freshness-decay-rate.md`
- Settings: `freshness_decay_rate.enabled`, `freshness_decay_rate.ranking_weight` (0.02).

---

### FR-081 — Contextual Sentiment Alignment
**Requested:** 2026-04-07 | **Status:** Pending | **Priority:** Low
**Research basis:** US20150286627A1 (Google). `score = 1 - |c_src - c_dst| / 2`.
**Spec:** `docs/specs/fr081-contextual-sentiment-alignment.md`
- Settings: `sentiment_alignment.enabled`, `sentiment_alignment.ranking_weight` (0.02).

---

### FR-082 — Structural Duplicate Detection Score
**Requested:** 2026-04-07 | **Status:** Pending | **Priority:** Low
**Research basis:** US7734627B1 (Google). SimHash of HTML tag sequence.
**Spec:** `docs/specs/fr082-structural-duplicate-detection.md`
- Settings: `structural_dup.enabled`, `structural_dup.ranking_weight` (0.02).

---

### FR-083 — Anomalous Interaction Pattern Filter
**Requested:** 2026-04-07 | **Status:** Pending | **Priority:** Low
**Research basis:** EP3497609B1. Engagement burst z-score anomaly detection.
**Spec:** `docs/specs/fr083-anomalous-interaction-filter.md`
- Settings: `anomaly_filter.enabled`, `anomaly_filter.ranking_weight` (0.02).

---

### FR-084 — Hashtag Co-occurrence Strength
**Requested:** 2026-04-07 | **Status:** Pending | **Priority:** Low
**Research basis:** US10698945B2 (Snap). PMI between topic tags.
**Spec:** `docs/specs/fr084-hashtag-cooccurrence-strength.md`
- Settings: `hashtag_cooccurrence.enabled`, `hashtag_cooccurrence.ranking_weight` (0.02).

---

### FR-085 — Content Format Preference Signal
**Requested:** 2026-04-07 | **Status:** Pending | **Priority:** Low
**Research basis:** US20190050433A1 (Snap). Format affinity scoring.
**Spec:** `docs/specs/fr085-content-format-preference.md`
- Settings: `format_preference.enabled`, `format_preference.ranking_weight` (0.02).

---

### FR-086 — Retweet Graph Authority
**Requested:** 2026-04-07 | **Status:** Pending | **Priority:** Low
**Research basis:** US8370326B2 (Twitter). Reshare-graph PageRank.
**Spec:** `docs/specs/fr086-retweet-graph-authority.md`
- Settings: `retweet_authority.enabled`, `retweet_authority.ranking_weight` (0.02).

---

### FR-087 — Reply Thread Depth Signal
**Requested:** 2026-04-07 | **Status:** Pending | **Priority:** Low
**Research basis:** US8954500B2 (Twitter). `score = min(1, mean_depth / 5)`.
**Spec:** `docs/specs/fr087-reply-thread-depth.md`
- Settings: `reply_depth.enabled`, `reply_depth.ranking_weight` (0.02).

---

### FR-088 — Save/Bookmark Rate
**Requested:** 2026-04-07 | **Status:** Pending | **Priority:** Low
**Research basis:** US9256680B2 (Pinterest). `saves / (views + 10)`.
**Spec:** `docs/specs/fr088-save-bookmark-rate.md`
- Settings: `bookmark_rate.enabled`, `bookmark_rate.ranking_weight` (0.02).

---

### FR-089 — Visual-Topic Consistency Score
**Requested:** 2026-04-07 | **Status:** Pending | **Priority:** Low
**Research basis:** US20140279220A1 (Pinterest). CLIP-lite image-text coherence.
**Spec:** `docs/specs/fr089-visual-topic-consistency.md`
- Settings: `visual_consistency.enabled`, `visual_consistency.ranking_weight` (0.02).

---

### FR-090 — Cross-Platform Engagement Correlation
**Requested:** 2026-04-07 | **Status:** Pending | **Priority:** Low
**Research basis:** US20140244006A1 (Google). Multi-platform spike detection.
**Spec:** `docs/specs/fr090-cross-platform-engagement.md`
- Settings: `cross_platform_engagement.enabled`, `cross_platform_engagement.ranking_weight` (0.02).

---

### FR-092 — Twice-Monthly Graph Walk Refresh
**Requested:** 2026-04-07
**Target phase:** TBD
**Status:** Pending
**Priority:** Medium
**Spec:** `docs/specs/fr092-twice-monthly-graph-walk-refresh.md`

### What's wanted
- Change graph walk generation from nightly to 1st/15th of each month. Nightly pipeline reuses cached walk results on non-walk days. Saves ~7-14 hours CPU/month.

### Specific controls / behaviour
- Walk algorithm unchanged: 20 entities × 1000 Pixie walk steps = 20,000 per article.
- New beat entry: `bimonthly-graph-walk-refresh` at `crontab(hour=2, minute=0, day_of_month="1,15")`.
- Settings: `graph_walk_refresh.enabled`, `graph_walk_refresh.schedule_days`, `graph_walk_refresh.skip_nightly_walks`.

---

### FR-093 — Extended Nightly Data Retention (Tier 1)
**Requested:** 2026-04-07
**Target phase:** TBD
**Status:** Pending
**Priority:** High
**Spec:** `docs/specs/fr093-extended-nightly-retention.md`

### What's wanted
- Extend the existing nightly retention task with 6 tables: Celery TaskResult (7d), OperatorAlert resolved (30d), SyncJob completed (60d), AnalyticsSyncRun (90d), TelemetryCoverageDaily (90d), ReviewerScorecard (180d). Saves ~6-8 GB/year.

### Specific controls / behaviour
- Settings: `retention_tier1.enabled`, `retention_tier1.celery_results_days`, `retention_tier1.resolved_alerts_days`, `retention_tier1.sync_jobs_days`, etc.

---

### FR-094 — Weekly Analytics Pruning (Tier 2)
**Requested:** 2026-04-07
**Target phase:** TBD
**Status:** Pending
**Priority:** High
**Spec:** `docs/specs/fr094-weekly-analytics-pruning.md`

### What's wanted
- Weekly prune of GSCDailyPerformance (90d), SuggestionTelemetryDaily (180d), GSCKeywordImpact (180d). Saves ~15-40 GB/year.

### Specific controls / behaviour
- New beat entry: `weekly-analytics-pruning` at `crontab(hour=4, minute=0, day_of_week=0)`.
- VACUUM ANALYZE after heavy deletes.
- Settings: `retention_tier2.enabled`, `retention_tier2.gsc_daily_performance_days`, `retention_tier2.suggestion_telemetry_days`, `retention_tier2.gsc_keyword_impact_days`.

---

### FR-095 — Quarterly Database Maintenance (Tier 4)
**Requested:** 2026-04-07
**Target phase:** TBD
**Status:** Pending
**Priority:** Medium
**Spec:** `docs/specs/fr095-quarterly-database-maintenance.md`

### What's wanted
- VACUUM FULL on Suggestion table, REINDEX CONCURRENTLY on embedding indexes, full entity re-extraction. Runs 4× per year (Jan/Apr/Jul/Oct). Reclaims ~1-3 GB/year.

### Specific controls / behaviour
- New beat entry: `quarterly-db-maintenance` at `crontab(hour=3, minute=0, day_of_month=1, month_of_year="1,4,7,10")`.
- Settings: `quarterly_maintenance.enabled`, `quarterly_maintenance.vacuum_full_suggestions`, `quarterly_maintenance.reindex_embeddings`, `quarterly_maintenance.rebuild_knowledge_graph`.

---

### FR-096 — Monthly Safe Prune (Tier 5)
**Requested:** 2026-04-07
**Target phase:** TBD
**Status:** Pending
**Priority:** Medium
**Spec:** `docs/specs/fr096-monthly-safe-prune.md`

### What's wanted
- Monthly prune of resolved BrokenLink (60d), ImpactReport (365d), and null out old Suggestion.graph_walk_diagnostics JSON (90d). Does NOT affect GSC, GA4, Matomo, or auto weight tuning. Saves ~0.8-2.8 GB/year.

### Specific controls / behaviour
- New beat entry: `monthly-safe-prune` at `crontab(hour=4, minute=30, day_of_month=1)`.
- Settings: `monthly_safe_prune.enabled`, `monthly_safe_prune.broken_links_days`, `monthly_safe_prune.impact_reports_days`, `monthly_safe_prune.diagnostics_json_days`.

---

## TEMPLATE ONLY

---

### FR-097 — Crawl Priority Scheduling via OR-Tools
**Requested:** 2026-04-10
**Target phase:** TBD
**Status:** Pending
**Priority:** Medium
**Research basis:** Wolf J. et al., "Optimal Re-Visiting of Web Pages", WWW 2002. Knapsack formulation.
**Spec:** `docs/specs/fr097-crawl-priority-scheduling.md`

### What's wanted
- Value-optimized crawl scheduling: given a crawl budget of X pages/hour, pick the pages that maximize freshness-weighted traffic value. Replaces FIFO/sitemap ordering with a knapsack solver.
- Uses Google OR-Tools CP-SAT solver (`pip install ortools`) for the general case, greedy top-K for the common uniform-weight case.

### Specific controls / behaviour
- Settings: `crawl_priority.enabled`, `crawl_priority.budget_per_window` (500), `crawl_priority.half_life_hours` (168), `crawl_priority.min_staleness_hours` (24), `crawl_priority.traffic_weight` (0.7), `crawl_priority.pagerank_weight` (0.3).
- Fallback: if OR-Tools not installed or data missing, uses existing FIFO ordering.

### Implementation notes for the AI
- Python service in `backend/apps/crawler/services/crawl_priority.py`. OR-Tools runs in Python process.
- C++ is NOT used -- OR-Tools provides its own native solver behind the Python API.
- Add `ortools>=9.9` to `backend/requirements.txt`.

---

### FR-098 — Dominant Passage Centrality
**Requested:** 2026-04-13
**Target phase:** TBD
**Status:** Pending
**Priority:** Medium
**Research basis:** Hearst M. A. (1997), TextTiling, *Computational Linguistics* 23(1). Erkan G. & Radev D. R. (2004), LexRank, *JAIR* 22, DOI 10.1613/jair.1523. Patent US7752534B2.
**Spec:** `docs/specs/fr098-dominant-passage-centrality.md`

### What's wanted
- Destination-intrinsic quality signal: does the page have a strong, coherent core passage where sentences reinforce each other?
- Segment the cleaned body text (distilled_text only — not title, not page chrome) into passages using TextTiling boundaries.
- Score sentences within each passage using LexRank (TF-IDF cosine similarity graph + PageRank centrality).
- The dominant passage (highest mean sentence centrality) determines the score.
- Complementary to FR-053 (passage relevance to host) and FR-043 (topic drift). Different axis: internal passage importance.

### Specific controls / behaviour
- Settings: `passage_centrality.enabled` (true), `passage_centrality.ranking_weight` (0.0), `passage_centrality.similarity_threshold` (0.10), `passage_centrality.damping_factor` (0.15), `passage_centrality.max_iterations` (100), `passage_centrality.min_sentences` (3), `passage_centrality.min_body_chars` (200), `passage_centrality.max_ratio` (3.0).
- Neutral fallback: return 0.5 if body too short, fewer than 3 usable sentences, or feature disabled.
- Computed once per destination at index time (destination-intrinsic, not host-dependent). Cached on ContentItem.
- Diagnostics: dominant passage index, centrality ratio, per-passage centrality scores, convergence iterations.

### Implementation notes for the AI
- Python service in `backend/apps/pipeline/services/passage_centrality.py`. No ML model, no GPU, no external API.
- TextTiling segmentation can share approach with FR-043 but must not modify FR-043's scorer or diagnostics.
- LexRank uses TF-IDF + cosine similarity + PageRank power iteration. All parameters from published defaults.
- Performance budget: < 15 ms per page in Python. C++ port unlikely to be needed (index-time, not suggestion-time).
- Storage: ~5-10 MB total for 100K pages. Negligible.

---

### FR-230 — 52-pick pipeline roster (Source → Parse → Score → Reviewable + scheduled updates)

**Requested:** 2026-04-22
**Target phase:** Phases 36–40 (PRs B–P + W1–W4)
**Status:** In progress — helpers shipped for 26 picks (PRs B, C, D, E, K, L, M, N, O); specs landed for all 52 (G1a–G1e); wiring pending (W1–W4); governance catch-up in progress (G2–G6).
**Priority:** High — foundational infrastructure covering every stage of the pipeline.
**Research basis:** See `plans/check-how-many-pending-tidy-iverson.md` for the full decision record and per-pick citations. Every pick is backed by a peer-reviewed paper, IETF RFC, ACM/IEEE standard, or operator-approved patent.
**Spec:** `docs/specs/scheduled-updates-architecture.md` + per-pick `docs/specs/pick-NN-*.md` (52 files). Template at `docs/specs/_spec-template.md`.

### What's wanted
- Ship 52 production-grade helpers across the full pipeline: 6 Source, 6 Crawl & Import, 14 Parse & Embed, 13 Score & Rank, 1 Feedback, 6 Training, 2 On-Demand Eval, 3 Reviewable, 1 Auto-Seeder (Gyöngyi §4.1).
- Add a serial 13:00–23:00-local scheduled-updates runner with pause/resume, deduped missed-job alerts, per-job checkpoints, and a dashboard tab.
- Add Option B meta-hyperparameter auto-tuning via Optuna TPE (pick #42) so every TPE-tuned hyperparameter across the roster is jointly optimised weekly against offline NDCG.
- Turn every pick on by default in the Recommended preset with paper-grounded starting values (per operator directive 2026-04-22).
- Document every pick to the 15-section template in `docs/specs/_spec-template.md` — identity, motivation, academic source, I/O contracts, hyperparameter table (distinguishing TPE-tuned vs fixed), pseudocode, integration points, scheduled-job slot, resource budget, tests, benchmark inputs, edge cases, paired picks, governance checklist.

### Specific controls / behaviour
- **Enabled by default.** Every pick's `<prefix>.enabled` defaults to `true` in `backend/apps/suggestions/recommended_weights.py`, seeded via a migration.
- **TPE vs fixed classification.** Each pick spec's §6 table distinguishes TPE-tuned knobs (ranking quality) from fixed knobs (correctness, RFC compliance, Google quota, licensed algorithm parameters). The meta-HPO job only touches TPE-tuned knobs.
- **Operator approval rail.** HPO proposes; operator accepts via a dashboard "Accept HPO result" card before values are written back to the Recommended preset (pick #42 §15).
- **On-demand vs scheduled.** Kernel SHAP (pick #47) is explicitly on-demand only. Every periodic pick lands in the 20-job list in `docs/specs/scheduled-updates-architecture.md`.
- **Per-pick resource budgets** enforced: Source / Crawl / Parse ≤ 128 MB RAM & ≤ 256 MB disk; Auto-Seeder (#51) ≤ 50 MB RAM & ≤ 50 MB disk; ACI (#52) < 1 MB / < 1 MB. FastText LangID (#14) allowed 126 MB disk as specified.

### Roster (summary table)

| # | Pick | Spec | Stage | Status | TPE | New pip dep? |
|---:|---|---|---|---|---|---|
| 1 | Token Bucket Rate Limiter | [pick-01](docs/specs/pick-01-token-bucket.md) | Source | Shipped PR-C | partial | — |
| 2 | Exponential Backoff + Jitter | [pick-02](docs/specs/pick-02-exponential-backoff-jitter.md) | Source | Shipped PR-C | yes | — |
| 3 | Circuit Breaker | [pick-03](docs/specs/pick-03-circuit-breaker.md) | Source | Reused (existing) | yes | — |
| 4 | Bloom Filter | [pick-04](docs/specs/pick-04-bloom-filter.md) | Source | Shipped PR-C | no (correctness) | — |
| 5 | HyperLogLog | [pick-05](docs/specs/pick-05-hyperloglog.md) | Source | Shipped PR-C | no (correctness) | — |
| 6 | ETag / Conditional GET | [pick-06](docs/specs/pick-06-etag-conditional-get.md) | Source | Shipped PR-C | no (RFC) | — |
| 7 | Trafilatura | [pick-07](docs/specs/pick-07-trafilatura.md) | Crawl | **Deferred** | yes | `trafilatura` |
| 8 | URL Canonicalization (RFC 3986) | [pick-08](docs/specs/pick-08-url-canonicalization.md) | Crawl | To-ship | no (RFC) | — |
| 9 | Robots.txt Parser | [pick-09](docs/specs/pick-09-robots-txt.md) | Crawl | Shipped PR-D | partial | — |
| 10 | Freshness Crawl Scheduling | [pick-10](docs/specs/pick-10-freshness-scheduler.md) | Crawl | Shipped PR-D | yes | — |
| 11 | chardet / encoding detect | [pick-11](docs/specs/pick-11-encoding-detect.md) | Crawl | Shipped PR-D | yes | `charset-normalizer` (modern `chardet`) |
| 12 | SHA-256 Page Fingerprint | [pick-12](docs/specs/pick-12-sha256-page-fingerprint.md) | Crawl | Partial (inline) | partial | — |
| 13 | NFKC Unicode Normalization | [pick-13](docs/specs/pick-13-nfkc-normalization.md) | Parse | Shipped PR-E | no (UAX) | — |
| 14 | FastText LangID (`lid.176.bin`) | [pick-14](docs/specs/pick-14-fasttext-langid.md) | Parse | **Deferred** | yes | `fasttext-langdetect` + 126 MB model |
| 15 | PySBD | [pick-15](docs/specs/pick-15-pysbd.md) | Parse | Reused | no | — |
| 16 | spaCy `en_core_web_sm` | [pick-16](docs/specs/pick-16-spacy-en-core-web-sm.md) | Parse | Reused | yes | — |
| 17 | YAKE! | [pick-17](docs/specs/pick-17-yake.md) | Parse | **Deferred** | yes | `yake` |
| 18 | LDA | [pick-18](docs/specs/pick-18-lda.md) | Parse | **Deferred** | yes | `gensim` |
| 19 | Readability (Flesch-Kincaid + Gunning Fog) | [pick-19](docs/specs/pick-19-readability.md) | Parse | Shipped PR-E | yes | — |
| 20 | Product Quantization | [pick-20](docs/specs/pick-20-product-quantization.md) | Embed | Shipped PR-E | yes | (existing `faiss-gpu`) |
| 21 | Snowball (Porter2) | [pick-21](docs/specs/pick-21-snowball.md) | Parse | **Deferred** | no | `nltk` |
| 22 | VADER | [pick-22](docs/specs/pick-22-vader.md) | Parse | **Deferred** | yes | `vaderSentiment` |
| 23 | KenLM trigram | [pick-23](docs/specs/pick-23-kenlm.md) | Parse | **Deferred** | yes | `kenlm` + `lmplz` |
| 24 | PMI / NPMI Collocations | [pick-24](docs/specs/pick-24-pmi-collocations.md) | Parse | Shipped PR-E | yes | — |
| 25 | Passage Segmentation (Callan) | [pick-25](docs/specs/pick-25-passage-segmentation.md) | Parse | Shipped PR-E | yes | — |
| 26 | Entity Salience (Gamon) | [pick-26](docs/specs/pick-26-entity-salience.md) | Parse | Shipped PR-E | yes | — |
| 27 | BoW-PRF Query Expansion | [pick-27](docs/specs/pick-27-query-expansion-bow.md) | Score | Shipped PR-K | yes | — |
| 28 | QL + Dirichlet | [pick-28](docs/specs/pick-28-ql-dirichlet.md) | Score | Shipped PR-K | yes | — |
| 29 | HITS | [pick-29](docs/specs/pick-29-hits.md) | Score | Shipped PR-M | yes | — |
| 30 | TrustRank | [pick-30](docs/specs/pick-30-trustrank.md) | Score | Shipped PR-M | yes | — |
| 31 | Reciprocal Rank Fusion | [pick-31](docs/specs/pick-31-rrf.md) | Score | Shipped PR-L | yes | — |
| 32 | Platt Sigmoid Calibration | [pick-32](docs/specs/pick-32-platt-calibration.md) | Score | Shipped PR-L | yes | — |
| 33 | Position-Bias IPS | [pick-33](docs/specs/pick-33-ips.md) | Score | Shipped PR-N | yes | — |
| 34 | Cascade Click Model | [pick-34](docs/specs/pick-34-cascade-click-model.md) | Score | Shipped PR-N | yes | — |
| 35 | Elo Rating | [pick-35](docs/specs/pick-35-elo.md) | Score | Shipped PR-N | yes | — |
| 36 | Personalized PageRank | [pick-36](docs/specs/pick-36-personalized-pagerank.md) | Score | Shipped PR-M | yes | — |
| 37 | Node2Vec | [pick-37](docs/specs/pick-37-node2vec.md) | Embed | **Deferred** | yes | `node2vec` / `gensim` |
| 38 | BPR | [pick-38](docs/specs/pick-38-bpr.md) | Score | **Deferred** | yes | `implicit` |
| 39 | Factorization Machines | [pick-39](docs/specs/pick-39-factorization-machines.md) | Score | **Deferred** | yes | `pyfm` / libFM |
| 40 | EMA Feedback Aggregator | [pick-40](docs/specs/pick-40-ema-aggregator.md) | Feedback | Shipped PR-N | yes | — |
| 41 | L-BFGS-B | [pick-41](docs/specs/pick-41-lbfgs-b.md) | Training | Reused | partial | — |
| 42 | TPE (Option B meta-HPO) | [pick-42](docs/specs/pick-42-tpe-optuna.md) | Training | **To ship** | — | `optuna` |
| 43 | Cosine Annealing | [pick-43](docs/specs/pick-43-cosine-annealing.md) | Training | **Deferred** (no torch loop) | yes | — |
| 44 | LambdaLoss | [pick-44](docs/specs/pick-44-lambdaloss.md) | Training | **Deferred** (no torch loop) | yes | — |
| 45 | SWA | [pick-45](docs/specs/pick-45-swa.md) | Training | **Deferred** (no torch loop) | yes | — |
| 46 | OHEM | [pick-46](docs/specs/pick-46-ohem.md) | Training | **Deferred** (no torch loop) | yes | — |
| 47 | Kernel SHAP | [pick-47](docs/specs/pick-47-kernel-shap.md) | Eval | Shipped PR-O | no (correctness) | `shap==0.46.0` (approved 2026-04-22) |
| 48 | Reservoir Sampling | [pick-48](docs/specs/pick-48-reservoir-sampling.md) | Eval | Shipped PR-O | yes | — |
| 49 | Uncertainty Sampling | [pick-49](docs/specs/pick-49-uncertainty-sampling.md) | Review | **To ship (PR-P)** | yes | — |
| 50 | Conformal Prediction | [pick-50](docs/specs/pick-50-conformal-prediction.md) | Review | **To ship (PR-P)** | yes | — |
| 51 | Inverse-PR Auto-Seeder | [pick-51](docs/specs/pick-51-trustrank-auto-seeder.md) | Score | Shipped PR-M | yes | — |
| 52 | Adaptive Conformal Inference | [pick-52](docs/specs/pick-52-adaptive-conformal-inference.md) | Review | **To ship (PR-P)** | yes | — |

### Scheduled-updates architecture (infra for the roster)

A new Django app `backend/apps/scheduled_updates/` (shipped PR-B) runs
every periodic pick serially in the 13:00–23:00 local window with:
- `@scheduled_job(key, cadence_seconds, priority, estimate_seconds, multicore, depends_on)` decorator.
- Redis `SET NX EX` lock (`scheduled_updates:runner`) enforcing single-writer.
- Window guard refuses to start jobs that would overflow past 23:00.
- `JobCheckpoint` contract for per-job progress reporting + pause/resume.
- Deduped `JobAlert` table with `UNIQUE(job_key, alert_type, calendar_date)`.
- Django Channels WebSocket frames on group `scheduled_updates` (throttled to 1/500 ms/job).
- Angular dashboard tab with Alerts banner, Running-now card, Missed-jobs list + Run Now, Schedule calendar, History — all `mat-tab-group` / `mat-card` / `mat-progress-bar` per CLAUDE.md mandatory rules.

### Implementation notes for the AI
- Every sub-PR lands independently: PR-B scheduler infrastructure, PR-C/D/E/K/L/M/N/O helpers, PR-P reviewable layer (ships Uncertainty + Conformal + ACI).
- Wiring into production pipelines happens in W1 (register scheduled jobs) → W2 (crawler / import) → W3 (ranker) → W4 (SHAP endpoint + UI).
- Governance catch-up ships alongside: G1 specs (done 2026-04-22), G2 this FR entry + additional FRs for any pick whose UI surface is large (#42 Option B dashboard, #47 Explain panel), G3 AI-CONTEXT ledger, G4 BUSINESS-LOGIC-CHECKLIST + PERFORMANCE entries, G6 benchmark coverage for all 26 shipped helpers per the CLAUDE.md mandatory-benchmark rule.
- Phantom-reference CI gate (`backend/scripts/check_phantom_references.py`) prevents the 126 retired pending signals / 184 retired pending meta-algos from being resurrected by a future session.

---

### FR-231 — Dashboard "Accept HPO result" approval card (sub-feature of FR-230 / pick #42)

**Requested:** 2026-04-22
**Target phase:** W4 (dashboard wiring)
**Status:** Pending — blocks Option B meta-HPO auto-apply
**Priority:** High (operator-facing surface for pick #42)
**Spec:** [docs/specs/pick-42-tpe-optuna.md](docs/specs/pick-42-tpe-optuna.md) §8.

### What's wanted
- A dashboard card on the Scheduled Updates tab showing the latest `meta_hyperparameter_hpo` study's best trial.
- Delta-view comparing best-trial params vs currently-applied Recommended preset, highlighting TPE-tuned keys that would change.
- "Accept HPO result" button that, on click, writes the best-trial params back to `AppSetting` rows for TPE-tuned keys.
- "Reject" / "Run another study" options for cases where the best-trial NDCG improvement isn't significant.
- Audit log entry per acceptance: operator, timestamp, delta summary, resulting NDCG@10.

### Specific controls / behaviour
- Only TPE-tuned keys from each pick spec's §6 table are eligible for the update.
- Out-of-range values (paper bounds) are clamped before commit.
- Update is atomic: either all keys change, or none do (DB transaction).
- Dashboard shows a "Pending HPO result" badge count when a study has finished but not been accepted.

### Implementation notes for the AI
- Django view: `POST /api/meta-hpo/<study_id>/accept/` with operator auth.
- Angular component under `frontend/src/app/scheduled-updates/accept-hpo-result/`.
- Reuses existing weight-preset service API.
- Must respect the `meta_hpo.auto_apply_best_params=false` safety rail from pick-42 spec — no background auto-apply; always operator-gated.

---

### FR-232 — "Why this score?" Explain panel (sub-feature of FR-230 / pick #47)

**Requested:** 2026-04-22
**Target phase:** W4 (SHAP endpoint + UI)
**Status:** Pending — blocks pick #47 end-to-end visibility
**Priority:** High (operator-facing surface for pick #47)
**Spec:** [docs/specs/pick-47-kernel-shap.md](docs/specs/pick-47-kernel-shap.md) §8.

### What's wanted
- REST endpoint `POST /api/suggestions/<id>/explain` that returns an SHAP decomposition of a suggestion's score.
- Angular "Explain" button on each suggestion card (ranking tab).
- On click, shows top-5 contributing features with signed bar chart (positive bars green, negative bars red) + numeric values.
- Loading spinner (Kernel SHAP takes 1-5 s); cancel button.
- Feature flag `shap_explainer.enabled=true` gates the button's visibility; disabled → tooltip "Kernel SHAP unavailable".

### Specific controls / behaviour
- The ranker must expose a pure `score_fn(features: np.ndarray) -> np.ndarray` callable — a small refactor of the current pipeline-embedded scorer. Reuses existing feature-vector dataclass.
- Background sample is the reservoir-sampled daily set (pick #48 output) — same baseline across all Explain calls in a day for consistency.
- Response cached per-suggestion for 24 h to avoid re-computing on refresh.
- Max peak RAM per call enforced at 200 MB (pick-47 safety rail).

### Implementation notes for the AI
- Django view: `apps/suggestions/views.py:explain_suggestion`.
- Angular: `frontend/src/app/suggestions/explain-panel/`.
- Uses existing Material components: `mat-card` for the panel, `mat-progress-bar` for load, bar chart via `mat-table` + bespoke bar render (no new chart lib).

---

### FR-0XX - Add your next request here

Template placeholder only. Not backlog scope.

```md

---

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

---

*Last updated: 2026-04-22 (G2 — added FR-230 roster entry for the 52-pick plan with full status table, FR-231 Accept-HPO-result card, FR-232 Explain panel — all referencing per-pick specs under docs/specs/pick-NN-*.md).*
