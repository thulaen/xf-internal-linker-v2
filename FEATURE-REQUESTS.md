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

### FR-091 — C++ Extension Retrofit
**Requested:** 2026-04-07
**Target phase:** TBD
**Status:** Pending
**Priority:** Critical
**Research basis:** CPP-RULES.md (project-internal safety standard).
**Spec:** `docs/specs/fr091-cpp-extension-retrofit.md`

### What's wanted
- Bring all 12 existing C++ extensions to CPP-RULES.md compliance: mandatory compiler flags, NaN/Inf validation, flush-to-zero MXCSR setup, double-precision accumulators.

### Specific controls / behaviour
- Fix 1: Add `-Wall -Wextra -Werror -Wconversion -Wshadow` etc. to all 12 extensions in setup.py.
- Fix 2: NaN/Inf input validation (`std::isfinite()`) in scoring.cpp, simsearch.cpp, feedrerank.cpp.
- Fix 3: `_MM_SET_FLUSH_ZERO_MODE` + `_MM_SET_DENORMALS_ZERO_MODE` in scoring, simsearch, feedrerank, pagerank.
- Fix 4: Double accumulator in l2norm.cpp for float reductions.

### Implementation notes for the AI
- Run `test_parity_simple.py` and `bench_extensions.py` after retrofit. Parity within 1e-4. Performance regression <5%.

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

## Phase 2 Forward-Declared Backlog (FR-099 … FR-224 + META-40 … META-249)

**Added:** 2026-04-15
**Status:** All Pending — forward-declared spec stubs only; implementation in future phases.
**Rationale:** Provides a deep, research-backed library of 126 ranking signals + 210 meta-algorithms (optimisers, losses, regularisers, calibrators, schedulers, samplers, feature engineering, dimensionality reduction, kernels, information theory, clustering, attribution, active/semi-supervised/causal/RL/bandits, matrix factorisation, NN init/normalisation, calibration variants, feature selection, metric learning, anomaly detection, population training, streaming trees) the team can draw from when tuning the linker. Each entry has a full spec file with math, paper citation, C++ implementation notes, and per-signal disk/RAM budget.

**Budgets (confirmed by the plan):**
- Ranking signals: ≤ 32 MB disk, ≤ 512 MB peak RAM per signal (sequential execution).
- Light meta batch (META-40 … META-105): ≤ 15 MB disk, ≤ 128 MB peak RAM per meta (sequential).
- Broad meta batch (META-106 … META-249): ≤ 15 MB disk, ≤ 256 MB peak RAM per meta (sequential).

**Plan reference:** `C:\Users\goldm\.claude\plans\zesty-roaming-treasure.md` (full formulas, C++ entry-function names, budget math, phased rollout R1–R7 for signals, M1–M6 for light metas, N1–N11 for broad metas).

### Ranking Signals FR-099 … FR-224 (126 entries)

| FR | Title | Block | Paper | Spec |
|---|---|---|---|---|
| FR-099 | BM25+ Lower-Bound Term-Frequency Normalization | A (Classical IR) | Lv & Zhai, CIKM 2011 | [fr099](docs/specs/fr099-bm25-plus-lower-bound.md) |
| FR-100 | BM25L Length-Unbiased | A (Classical IR) | Lv & Zhai, ECIR 2011 | [fr100](docs/specs/fr100-bm25l-length-unbiased.md) |
| FR-101 | DFR PL2 | A (Classical IR) | Amati & van Rijsbergen, TOIS 2002 | [fr101](docs/specs/fr101-dfr-pl2.md) |
| FR-102 | DFR InL2 | A (Classical IR) | Amati, PhD thesis 2003 | [fr102](docs/specs/fr102-dfr-inl2.md) |
| FR-103 | DFR DPH | A (Classical IR) | Amati, FUB @ TREC 2005 | [fr103](docs/specs/fr103-dfr-dph.md) |
| FR-104 | Axiomatic F2EXP | A (Classical IR) | Fang & Zhai, SIGIR 2006 | [fr104](docs/specs/fr104-axiomatic-f2exp.md) |
| FR-105 | Two-Stage Language Model | A (Classical IR) | Zhai & Lafferty, CIKM 2002 | [fr105](docs/specs/fr105-two-stage-language-model.md) |
| FR-106 | Positional Language Model | A (Classical IR) | Lv & Zhai, SIGIR 2009 | [fr106](docs/specs/fr106-positional-language-model.md) |
| FR-107 | Relevance-based LM (RM3) | A (Classical IR) | Lavrenko & Croft, SIGIR 2001 | [fr107](docs/specs/fr107-relevance-lm-rm3.md) |
| FR-108 | Sequential Dependence Model (SDM) | B (Proximity & term-dependence) | Metzler & Croft, SIGIR 2005 | [fr108](docs/specs/fr108-sequential-dependence-model.md) |
| FR-109 | Weighted SDM (WSDM) | B (Proximity & term-dependence) | Bendersky, Metzler & Croft, SIGIR 2010 | [fr109](docs/specs/fr109-weighted-sequential-dependence.md) |
| FR-110 | Full Dependence Model | B (Proximity & term-dependence) | Metzler & Croft, SIGIR 2005 | [fr110](docs/specs/fr110-full-dependence-model.md) |
| FR-111 | BM25TP (Term Proximity) | B (Proximity & term-dependence) | Rasolofo & Savoy, ECIR 2003 | [fr111](docs/specs/fr111-bm25tp-term-proximity.md) |
| FR-112 | MinSpan Proximity Score | B (Proximity & term-dependence) | Tao & Zhai, SIGIR 2007 | [fr112](docs/specs/fr112-minspan-proximity.md) |
| FR-113 | Ordered Span Proximity | B (Proximity & term-dependence) | Büttcher et al., SIGIR 2006 | [fr113](docs/specs/fr113-ordered-span-proximity.md) |
| FR-114 | BoolProx | B (Proximity & term-dependence) | Svore, Kanani & Khan, SIGIR 2011 | [fr114](docs/specs/fr114-boolprox.md) |
| FR-115 | Markov Random Field Per-Field | B (Proximity & term-dependence) | Huston & Croft, SIGIR 2013 | [fr115](docs/specs/fr115-mrf-per-field.md) |
| FR-116 | HITS Authority Score | C (Graph centrality beyond PageRank) | Kleinberg, JACM 1999 | [fr116](docs/specs/fr116-hits-authority-score.md) |
| FR-117 | HITS Hub Score | C (Graph centrality beyond PageRank) | Kleinberg, JACM 1999 | [fr117](docs/specs/fr117-hits-hub-score.md) |
| FR-118 | TrustRank | C (Graph centrality beyond PageRank) | Gyöngyi, Garcia-Molina & Pedersen, VLDB 2004 | [fr118](docs/specs/fr118-trustrank.md) |
| FR-119 | Anti-TrustRank | C (Graph centrality beyond PageRank) | Krishnan & Raj, AIRWeb 2006 | [fr119](docs/specs/fr119-anti-trustrank.md) |
| FR-120 | SALSA | C (Graph centrality beyond PageRank) | Lempel & Moran, WWW 2000 | [fr120](docs/specs/fr120-salsa.md) |
| FR-121 | SimRank | C (Graph centrality beyond PageRank) | Jeh & Widom, KDD 2002 | [fr121](docs/specs/fr121-simrank.md) |
| FR-122 | Katz Centrality | C (Graph centrality beyond PageRank) | Katz, Psychometrika 1953 | [fr122](docs/specs/fr122-katz-centrality.md) |
| FR-123 | K-Shell Coreness | C (Graph centrality beyond PageRank) | Kitsak et al., Nature Physics 2010 | [fr123](docs/specs/fr123-k-shell-coreness.md) |
| FR-124 | Harmonic Centrality | C (Graph centrality beyond PageRank) | Marchiori & Latora, Physica A 2000 | [fr124](docs/specs/fr124-harmonic-centrality.md) |
| FR-125 | LeaderRank | C (Graph centrality beyond PageRank) | Lü et al., PLoS ONE 2011 | [fr125](docs/specs/fr125-leaderrank.md) |
| FR-126 | IA-Select (Intent-Aware Diversification) | D (Diversity rerankers) | Agrawal, Gollapudi, Halverson & Ieong, WSDM 2009 | [fr126](docs/specs/fr126-ia-select-diversification.md) |
| FR-127 | xQuAD Explicit Aspect Diversification | D (Diversity rerankers) | Santos, Macdonald & Ounis, WWW 2010 | [fr127](docs/specs/fr127-xquad-aspect-diversification.md) |
| FR-128 | PM2 Proportional Diversification | D (Diversity rerankers) | Dang & Croft, SIGIR 2012 | [fr128](docs/specs/fr128-pm2-proportional-diversification.md) |
| FR-129 | DPP Determinantal Point Process | D (Diversity rerankers) | Kulesza & Taskar, FTML 2012 | [fr129](docs/specs/fr129-dpp-determinantal-point-process.md) |
| FR-130 | Submodular Coverage Reranking | D (Diversity rerankers) | Lin & Bilmes, ACL 2011 | [fr130](docs/specs/fr130-submodular-coverage-reranking.md) |
| FR-131 | Portfolio-Theory Reranking | D (Diversity rerankers) | Wang & Zhu, SIGIR 2009 | [fr131](docs/specs/fr131-portfolio-theory-reranking.md) |
| FR-132 | Latent Diversity Model (LDM) | D (Diversity rerankers) | Ashkan, Clarke & Agichtein, CIKM 2015 | [fr132](docs/specs/fr132-latent-diversity-model.md) |
| FR-133 | Quota-Based Diversity | D (Diversity rerankers) | Capannini et al., SIGIR 2011 | [fr133](docs/specs/fr133-quota-based-diversity.md) |
| FR-134 | Kleinberg Burst Detection | E (Temporal dynamics) | Kleinberg, KDD 2002 | [fr134](docs/specs/fr134-kleinberg-burst-detection.md) |
| FR-135 | PELT Change-Point Detection | E (Temporal dynamics) | Killick, Fearnhead & Eckley, JASA 2012 | [fr135](docs/specs/fr135-pelt-change-point-detection.md) |
| FR-136 | CUSUM Cumulative Anomaly | E (Temporal dynamics) | Page, Biometrika 1954 | [fr136](docs/specs/fr136-cusum-cumulative-anomaly.md) |
| FR-137 | STL Seasonal-Trend Decomposition | E (Temporal dynamics) | Cleveland, McRae & Cleveland, JOS 1990 | [fr137](docs/specs/fr137-stl-seasonal-trend-decomposition.md) |
| FR-138 | Mann-Kendall Non-Parametric Trend | E (Temporal dynamics) | Mann, Econometrica 1945 | [fr138](docs/specs/fr138-mann-kendall-nonparametric-trend.md) |
| FR-139 | Theil-Sen Robust Slope | E (Temporal dynamics) | Theil 1950 / Sen 1968 | [fr139](docs/specs/fr139-theil-sen-robust-slope.md) |
| FR-140 | Fourier Periodicity Strength | E (Temporal dynamics) | Stoica & Moses, *Spectral Analysis* 2005 | [fr140](docs/specs/fr140-fourier-periodicity-strength.md) |
| FR-141 | Autocorrelation at Lag-k (ACF) | E (Temporal dynamics) | Box & Jenkins, *Time Series* 1976 | [fr141](docs/specs/fr141-autocorrelation-lag-k.md) |
| FR-142 | Partial Autocorrelation (PACF) | E (Temporal dynamics) | Box & Jenkins, 1976 | [fr142](docs/specs/fr142-partial-autocorrelation.md) |
| FR-143 | EWMA Smoothed Click-Rate | E (Temporal dynamics) | Roberts, Technometrics 1959 | [fr143](docs/specs/fr143-ewma-smoothed-click-rate.md) |
| FR-144 | HyperLogLog Unique-Visitor Sketch | F (Sketch-based low-RAM) | Flajolet, Fusy, Gandouet & Meunier, AOFA 2007 | [fr144](docs/specs/fr144-hyperloglog-unique-visitors.md) |
| FR-145 | HyperLogLog++ Extended Precision | F (Sketch-based low-RAM) | Heule, Nunkesser & Hall, EDBT 2013 | [fr145](docs/specs/fr145-hyperloglog-plus-plus.md) |
| FR-146 | CountMin Sketch Anchor-Rarity | F (Sketch-based low-RAM) | Cormode & Muthukrishnan, J. Algorithms 2005 | [fr146](docs/specs/fr146-countmin-sketch-anchor-rarity.md) |
| FR-147 | Count-Sketch Signed Frequency | F (Sketch-based low-RAM) | Charikar, Chen & Farach-Colton, ICALP 2004 | [fr147](docs/specs/fr147-count-sketch-signed-frequency.md) |
| FR-148 | Space-Saving Top-K Anchors | F (Sketch-based low-RAM) | Metwally, Agrawal & El-Abbadi, ICDT 2005 | [fr148](docs/specs/fr148-space-saving-top-k-anchors.md) |
| FR-149 | T-Digest Quantile Tracker | F (Sketch-based low-RAM) | Dunning, arXiv:1902.04023 (2019) | [fr149](docs/specs/fr149-t-digest-quantile-tracker.md) |
| FR-150 | Lossy Counting Frequency | F (Sketch-based low-RAM) | Manku & Motwani, VLDB 2002 | [fr150](docs/specs/fr150-lossy-counting-frequency.md) |
| FR-151 | b-bit MinHash Similarity | F (Sketch-based low-RAM) | Li & König, COLT 2010 / CACM 2011 | [fr151](docs/specs/fr151-b-bit-minhash-similarity.md) |
| FR-152 | Passive-Voice Ratio | G (Text-structure features) | Hundt & Mair, Corpus Linguistics 2004 | [fr152](docs/specs/fr152-passive-voice-ratio.md) |
| FR-153 | Nominalization Density | G (Text-structure features) | Halliday, *Intro to Functional Grammar* 1985 | [fr153](docs/specs/fr153-nominalization-density.md) |
| FR-154 | Hedging Language Density | G (Text-structure features) | Hyland, *Hedging in Scientific Research Articles* 1998 | [fr154](docs/specs/fr154-hedging-language-density.md) |
| FR-155 | Discourse-Connective Density | G (Text-structure features) | Pitler & Nenkova, ACL 2008 | [fr155](docs/specs/fr155-discourse-connective-density.md) |
| FR-156 | Cohesion Score (Coh-Metrix) | G (Text-structure features) | Graesser, McNamara, Louwerse & Cai, BRM 2004 | [fr156](docs/specs/fr156-cohesion-score-cohmetrix.md) |
| FR-157 | Part-of-Speech Diversity | G (Text-structure features) | Biber, *Variation across speech and writing* 1988 | [fr157](docs/specs/fr157-part-of-speech-diversity.md) |
| FR-158 | Sentence-Length Variance | G (Text-structure features) | Crossley et al., *Readability Research* 2019 | [fr158](docs/specs/fr158-sentence-length-variance.md) |
| FR-159 | Yule's K Lexical Concentration | G (Text-structure features) | Yule, *Statistical Study of Literary Vocabulary* 1944 | [fr159](docs/specs/fr159-yule-k-lexical-concentration.md) |
| FR-160 | MTLD Lexical Diversity | G (Text-structure features) | McCarthy & Jarvis, BRM 2010 | [fr160](docs/specs/fr160-mtld-lexical-diversity.md) |
| FR-161 | Punctuation-Entropy Score | G (Text-structure features) | Shannon, BSTJ 1948 / Stamatatos, JASIS 2009 | [fr161](docs/specs/fr161-punctuation-entropy.md) |
| FR-162 | Cascade Click Model (CCM) | H (Click-model signals) | Craswell, Zoeter, Taylor & Ramsey, WSDM 2008 | [fr162](docs/specs/fr162-cascade-click-model.md) |
| FR-163 | Dynamic Bayesian Network Click Model | H (Click-model signals) | Chapelle & Zhang, WWW 2009 | [fr163](docs/specs/fr163-dbn-click-model.md) |
| FR-164 | User Browsing Model (UBM) | H (Click-model signals) | Dupret & Piwowarski, SIGIR 2008 | [fr164](docs/specs/fr164-user-browsing-model.md) |
| FR-165 | Position Bias Model (PBM) | H (Click-model signals) | Richardson, Dominowska & Ragno, WWW 2007 | [fr165](docs/specs/fr165-position-bias-model.md) |
| FR-166 | Dependent Click Model (DCM) | H (Click-model signals) | Guo, Li & Wang, WebConf 2009 | [fr166](docs/specs/fr166-dependent-click-model.md) |
| FR-167 | Click Chain Model | H (Click-model signals) | Guo, Liu & Osborne, SIGIR 2009 | [fr167](docs/specs/fr167-click-chain-model.md) |
| FR-168 | Click Graph Random Walk | H (Click-model signals) | Craswell & Szummer, SIGIR 2007 | [fr168](docs/specs/fr168-click-graph-random-walk.md) |
| FR-169 | Regression-Based Click Propensity | H (Click-model signals) | Wang et al., WWW 2018 | [fr169](docs/specs/fr169-regression-click-propensity.md) |
| FR-170 | Query Clarity Score | I (Query performance prediction) | Cronen-Townsend, Zhou & Croft, SIGIR 2002 | [fr170](docs/specs/fr170-query-clarity-score.md) |
| FR-171 | Weighted Information Gain (WIG) | I (Query performance prediction) | Zhou & Croft, SIGIR 2007 | [fr171](docs/specs/fr171-weighted-information-gain.md) |
| FR-172 | Normalized Query Commitment (NQC) | I (Query performance prediction) | Shtok et al., CIKM 2009 | [fr172](docs/specs/fr172-normalized-query-commitment.md) |
| FR-173 | Simplified Clarity Score | I (Query performance prediction) | He & Ounis, ECIR 2004 | [fr173](docs/specs/fr173-simplified-clarity-score.md) |
| FR-174 | Query Scope | I (Query performance prediction) | He & Ounis, SIGIR 2004 | [fr174](docs/specs/fr174-query-scope.md) |
| FR-175 | Query Feedback | I (Query performance prediction) | Zhou & Croft, SIGIR 2006 | [fr175](docs/specs/fr175-query-feedback.md) |
| FR-176 | Pre-Retrieval Predictor AvgICTF | I (Query performance prediction) | He & Ounis, SIGIR 2004 | [fr176](docs/specs/fr176-avg-ictf-preretrieval-predictor.md) |
| FR-177 | Pre-Retrieval Predictor SCQ | I (Query performance prediction) | Zhao, Scholer & Tsegay, ECIR 2008 | [fr177](docs/specs/fr177-scq-preretrieval-predictor.md) |
| FR-178 | Pointwise Mutual Information (PMI) | J (Information-theoretic) | Church & Hanks, Computational Linguistics 1990 | [fr178](docs/specs/fr178-pointwise-mutual-information.md) |
| FR-179 | Normalized PMI (NPMI) | J (Information-theoretic) | Bouma, GSCL 2009 | [fr179](docs/specs/fr179-normalized-pmi.md) |
| FR-180 | Log-Likelihood Ratio Term Association | J (Information-theoretic) | Dunning, Computational Linguistics 1993 | [fr180](docs/specs/fr180-log-likelihood-ratio-term-association.md) |
| FR-181 | KL Divergence Source→Destination | J (Information-theoretic) | Kullback & Leibler, Annals of Math Stat 1951 | [fr181](docs/specs/fr181-kl-divergence-source-destination.md) |
| FR-182 | Jensen-Shannon Divergence | J (Information-theoretic) | Lin, IEEE Trans Information Theory 1991 | [fr182](docs/specs/fr182-jensen-shannon-divergence.md) |
| FR-183 | Rényi Divergence α-Family | J (Information-theoretic) | Rényi, 4th Berkeley Symposium 1961 | [fr183](docs/specs/fr183-renyi-divergence.md) |
| FR-184 | Hellinger Distance | J (Information-theoretic) | Hellinger, JRM 1909 / Le Cam 1986 | [fr184](docs/specs/fr184-hellinger-distance.md) |
| FR-185 | Word Mover's Distance | J (Information-theoretic) | Rubner, Tomasi & Guibas, IJCV 2000 / Kusner et al., ICML 2015 | [fr185](docs/specs/fr185-word-movers-distance.md) |
| FR-186 | Site-Level PageRank | K (Site/host-level authority) | Bharat & Henzinger, SIGIR 1998 | [fr186](docs/specs/fr186-site-level-pagerank.md) |
| FR-187 | Host TrustRank | K (Site/host-level authority) | Gyöngyi, Garcia-Molina & Pedersen, VLDB 2004 (host variant) | [fr187](docs/specs/fr187-host-trustrank.md) |
| FR-188 | SpamRank Propagation | K (Site/host-level authority) | Benczúr, Csalogány & Sarlós, WebKDD 2005 | [fr188](docs/specs/fr188-spamrank-propagation.md) |
| FR-189 | BadRank Inverse PageRank | K (Site/host-level authority) | Sobek, *BadRank as the Opposite of PageRank* 2002 | [fr189](docs/specs/fr189-badrank-inverse-pagerank.md) |
| FR-190 | Host Age Boost | K (Site/host-level authority) | US Patent 8972390 (Google, Ward 2015) + Google API leak 2024 | [fr190](docs/specs/fr190-host-age-boost.md) |
| FR-191 | Subdomain Diversity Penalty | K (Site/host-level authority) | Bharat et al., WWW 2001 | [fr191](docs/specs/fr191-subdomain-diversity-penalty.md) |
| FR-192 | Doorway-Page Detector | K (Site/host-level authority) | Fetterly, Manasse & Najork, WebDB 2004 | [fr192](docs/specs/fr192-doorway-page-detector.md) |
| FR-193 | Block-Level PageRank | K (Site/host-level authority) | Kamvar et al., WWW 2003 | [fr193](docs/specs/fr193-block-level-pagerank.md) |
| FR-194 | Host-Cluster Cohesion | K (Site/host-level authority) | Eiron & McCurley, SIGIR 2004 | [fr194](docs/specs/fr194-host-cluster-cohesion.md) |
| FR-195 | Link-Pattern Naturalness | K (Site/host-level authority) | Broder et al., WWW 2000 | [fr195](docs/specs/fr195-link-pattern-naturalness.md) |
| FR-196 | Cloaking Detector | L (Anti-spam / adversarial) | Wu & Davison, AIRWeb 2005 | [fr196](docs/specs/fr196-cloaking-detector.md) |
| FR-197 | Link-Farm Ring Detector | L (Anti-spam / adversarial) | Gyöngyi & Garcia-Molina, AIRWeb 2005 | [fr197](docs/specs/fr197-link-farm-ring-detector.md) |
| FR-198 | Keyword-Stuffing Detector | L (Anti-spam / adversarial) | Ntoulas, Najork, Manasse & Fetterly, WWW 2006 | [fr198](docs/specs/fr198-keyword-stuffing-detector.md) |
| FR-199 | Content-Spin Detector | L (Anti-spam / adversarial) | Bendersky & Gabrilovich, WSDM 2011 | [fr199](docs/specs/fr199-content-spin-detector.md) |
| FR-200 | Sybil-Attack Detector | L (Anti-spam / adversarial) | Yu, Gibbons, Kaminsky & Xiao, SIGCOMM 2008 (SybilGuard) | [fr200](docs/specs/fr200-sybil-attack-detector.md) |
| FR-201 | AstroTurf Pattern Detector | L (Anti-spam / adversarial) | Ratkiewicz et al., ICWSM 2011 | [fr201](docs/specs/fr201-astroturf-pattern-detector.md) |
| FR-202 | Clickbait Classifier | L (Anti-spam / adversarial) | Chakraborty et al., ASONAM 2016 | [fr202](docs/specs/fr202-clickbait-classifier.md) |
| FR-203 | Content-Farm Detector | L (Anti-spam / adversarial) | Lin, Liu & Xue, WWW 2013 | [fr203](docs/specs/fr203-content-farm-detector.md) |
| FR-204 | Author H-Index Within Forum | M (Author / reputation) | Hirsch, PNAS 2005 | [fr204](docs/specs/fr204-author-h-index-within-forum.md) |
| FR-205 | Co-Authorship Graph PageRank | M (Author / reputation) | Liu, Bollen, Nelson & Van de Sompel, IPM 2005 | [fr205](docs/specs/fr205-co-authorship-graph-pagerank.md) |
| FR-206 | Account-Age Gravity | M (Author / reputation) | US Patent 8972390 (Google 2015) + reputation-systems literature | [fr206](docs/specs/fr206-account-age-gravity.md) |
| FR-207 | Edit-History Density | M (Author / reputation) | Adler & de Alfaro, WWW 2007 | [fr207](docs/specs/fr207-edit-history-density.md) |
| FR-208 | Moderator Endorsement Signal | M (Author / reputation) | Adler & de Alfaro, WWW 2007 | [fr208](docs/specs/fr208-moderator-endorsement-signal.md) |
| FR-209 | Reply-Quality-to-Post Ratio | M (Author / reputation) | Agichtein, Castillo, Donato, Gionis & Mishne, WSDM 2008 | [fr209](docs/specs/fr209-reply-quality-to-post-ratio.md) |
| FR-210 | Cross-Thread Topic Consistency | M (Author / reputation) | Kleinberg & Wang, ICWSM 2011 | [fr210](docs/specs/fr210-cross-thread-topic-consistency.md) |
| FR-211 | Trust Propagation on User Graph | M (Author / reputation) | Guha, Kumar, Raghavan & Tomkins, WWW 2004 | [fr211](docs/specs/fr211-trust-propagation-user-graph.md) |
| FR-212 | User Eigentrust | M (Author / reputation) | Kamvar, Schlosser & Garcia-Molina, WWW 2003 | [fr212](docs/specs/fr212-user-eigentrust.md) |
| FR-213 | Heading Hierarchy Correctness | N (Structural page-quality) | W3C HTML5 Sectioning Model 2014 + Nagappan et al., ICSE 2006 | [fr213](docs/specs/fr213-heading-hierarchy-correctness.md) |
| FR-214 | Alt-Text Coverage Ratio | N (Structural page-quality) | W3C WCAG 2.1 SC 1.1.1 + US Patent 9418120 | [fr214](docs/specs/fr214-alt-text-coverage-ratio.md) |
| FR-215 | Schema.org Completeness | N (Structural page-quality) | Schema.org consortium spec + US Patent 9916304 | [fr215](docs/specs/fr215-schema-org-completeness.md) |
| FR-216 | Open-Graph Completeness | N (Structural page-quality) | Facebook OG Protocol 2010 + Twitter Card spec | [fr216](docs/specs/fr216-open-graph-completeness.md) |
| FR-217 | Mobile-Friendly Score | N (Structural page-quality) | US Patent 9152714 (Google 2014) | [fr217](docs/specs/fr217-mobile-friendly-score.md) |
| FR-218 | Core Web Vital — LCP | N (Structural page-quality) | W3C Web Perf Working Group, LCP spec 2020 | [fr218](docs/specs/fr218-core-web-vital-lcp.md) |
| FR-219 | Core Web Vital — CLS | N (Structural page-quality) | W3C, Cumulative Layout Shift spec 2020 | [fr219](docs/specs/fr219-core-web-vital-cls.md) |
| FR-220 | Core Web Vital — INP | N (Structural page-quality) | W3C Interaction-to-Next-Paint spec 2024 | [fr220](docs/specs/fr220-core-web-vital-inp.md) |
| FR-221 | Passage TextTiling Boundary Strength | O (Passage-level micro-features) | Hearst, Computational Linguistics 1997 | [fr221](docs/specs/fr221-passage-texttiling-boundary-strength.md) |
| FR-222 | C99 Passage Segmentation | O (Passage-level micro-features) | Choi, NAACL 2000 | [fr222](docs/specs/fr222-c99-passage-segmentation.md) |
| FR-223 | Dotplotting Topic Boundary | O (Passage-level micro-features) | Reynar, SIGIR 1998 | [fr223](docs/specs/fr223-dotplotting-topic-boundary.md) |
| FR-224 | BayesSeg Bayesian Segmentation | O (Passage-level micro-features) | Eisenstein & Barzilay, EMNLP 2008 | [fr224](docs/specs/fr224-bayesseg-bayesian-segmentation.md) |

### Meta-Algorithms META-40 … META-249 (210 entries)

| META | Title | Block | Paper | Spec |
|---|---|---|---|---|
| META-40 | Newton's Method | P1 (Second-order optimisers) | Newton 1685 / Raphson 1690 | [meta-40](docs/specs/meta-40-newton-method.md) |
| META-41 | Gauss-Newton | P1 (Second-order optimisers) | Gauss, *Theoria Motus* 1809 | [meta-41](docs/specs/meta-41-gauss-newton.md) |
| META-42 | Levenberg-Marquardt | P1 (Second-order optimisers) | Levenberg 1944 / Marquardt, J. SIAM 1963 | [meta-42](docs/specs/meta-42-levenberg-marquardt.md) |
| META-43 | L-BFGS-B (Bounded) | P1 (Second-order optimisers) | Byrd, Lu, Nocedal & Zhu, SIAM J. Sci. Comput. 1995 | [meta-43](docs/specs/meta-43-lbfgs-b-bounded.md) |
| META-44 | Full BFGS | P1 (Second-order optimisers) | Broyden 1970 / Fletcher 1970 / Goldfarb 1970 / Shanno 1970 | [meta-44](docs/specs/meta-44-bfgs-full.md) |
| META-45 | Fletcher-Reeves Conjugate Gradient | P1 (Second-order optimisers) | Fletcher & Reeves, Computer J. 1964 | [meta-45](docs/specs/meta-45-fletcher-reeves-conjugate-gradient.md) |
| META-46 | AdaGrad | P2 (Advanced first-order optimisers) | Duchi, Hazan & Singer, JMLR 2011 | [meta-46](docs/specs/meta-46-adagrad.md) |
| META-47 | AdaDelta | P2 (Advanced first-order optimisers) | Zeiler, arXiv:1212.5701 (2012) | [meta-47](docs/specs/meta-47-adadelta.md) |
| META-48 | Nadam | P2 (Advanced first-order optimisers) | Dozat, ICLR Workshop 2016 | [meta-48](docs/specs/meta-48-nadam.md) |
| META-49 | AMSGrad | P2 (Advanced first-order optimisers) | Reddi, Kale & Kumar, ICLR 2018 | [meta-49](docs/specs/meta-49-amsgrad.md) |
| META-50 | Lookahead | P2 (Advanced first-order optimisers) | Zhang, Lucas, Hinton & Ba, NeurIPS 2019 | [meta-50](docs/specs/meta-50-lookahead-optimizer.md) |
| META-51 | Rectified Adam (RAdam) | P2 (Advanced first-order optimisers) | Liu et al., ICLR 2020 | [meta-51](docs/specs/meta-51-radam-rectified-adam.md) |
| META-52 | Lion | P2 (Advanced first-order optimisers) | Chen et al., arXiv:2302.06675 (2023) | [meta-52](docs/specs/meta-52-lion-optimizer.md) |
| META-53 | Yogi | P2 (Advanced first-order optimisers) | Zaheer, Reddi, Sachan, Kale & Kumar, NeurIPS 2018 | [meta-53](docs/specs/meta-53-yogi-optimizer.md) |
| META-54 | GP-EI Bayesian Optimization | P3 (Bayesian optimisation & HPO) | Močkus 1974 / Jones, Schonlau & Welch, J. Global Opt 1998 | [meta-54](docs/specs/meta-54-gp-ei-bayesian-optimization.md) |
| META-55 | Tree-Structured Parzen Estimator (TPE) | P3 (Bayesian optimisation & HPO) | Bergstra, Bardenet, Bengio & Kégl, NIPS 2011 | [meta-55](docs/specs/meta-55-tpe-tree-parzen-estimator.md) |
| META-56 | SMAC (Sequential Model-Based Algorithm Configuration) | P3 (Bayesian optimisation & HPO) | Hutter, Hoos & Leyton-Brown, LION 2011 | [meta-56](docs/specs/meta-56-smac-sequential-model-ac.md) |
| META-57 | BOHB | P3 (Bayesian optimisation & HPO) | Falkner, Klein & Hutter, ICML 2018 | [meta-57](docs/specs/meta-57-bohb-bayesian-hyperband.md) |
| META-58 | Hyperband | P3 (Bayesian optimisation & HPO) | Li, Jamieson, DeSalvo, Rostamizadeh & Talwalkar, JMLR 2017 | [meta-58](docs/specs/meta-58-hyperband.md) |
| META-59 | GP-UCB Acquisition | P3 (Bayesian optimisation & HPO) | Srinivas, Krause, Kakade & Seeger, ICML 2010 | [meta-59](docs/specs/meta-59-gp-ucb-acquisition.md) |
| META-60 | NSGA-II | P4 (Multi-objective) | Deb, Pratap, Agarwal & Meyarivan, IEEE TEVC 2002 | [meta-60](docs/specs/meta-60-nsga-ii.md) |
| META-61 | NSGA-III | P4 (Multi-objective) | Deb & Jain, IEEE TEVC 2014 | [meta-61](docs/specs/meta-61-nsga-iii.md) |
| META-62 | MOEA/D | P4 (Multi-objective) | Zhang & Li, IEEE TEVC 2007 | [meta-62](docs/specs/meta-62-moea-d.md) |
| META-63 | ε-Constraint Method | P4 (Multi-objective) | Haimes, Lasdon & Wismer, IEEE SMC 1971 | [meta-63](docs/specs/meta-63-epsilon-constraint-method.md) |
| META-64 | Tchebycheff Scalarisation | P4 (Multi-objective) | Miettinen, *Nonlinear Multiobjective Optimization* 1999 | [meta-64](docs/specs/meta-64-tchebycheff-scalarization.md) |
| META-65 | Particle Swarm Optimization | P5 (Metaheuristic / swarm) | Kennedy & Eberhart, IEEE ICNN 1995 | [meta-65](docs/specs/meta-65-particle-swarm-optimization.md) |
| META-66 | Ant Colony Optimization | P5 (Metaheuristic / swarm) | Dorigo, PhD thesis Politecnico Milano 1992 | [meta-66](docs/specs/meta-66-ant-colony-optimization.md) |
| META-67 | Cuckoo Search | P5 (Metaheuristic / swarm) | Yang & Deb, World Congress NaBIC 2009 | [meta-67](docs/specs/meta-67-cuckoo-search.md) |
| META-68 | Firefly Algorithm | P5 (Metaheuristic / swarm) | Yang, *Nature-Inspired Metaheuristics* 2008 | [meta-68](docs/specs/meta-68-firefly-algorithm.md) |
| META-69 | Bat Algorithm | P5 (Metaheuristic / swarm) | Yang, NICSO 2010 | [meta-69](docs/specs/meta-69-bat-algorithm.md) |
| META-70 | FTRL-Proximal | P6 (Online learning) | McMahan, Holt, Sculley et al., KDD 2013 | [meta-70](docs/specs/meta-70-ftrl-proximal.md) |
| META-71 | Online Newton Step (ONS) | P6 (Online learning) | Hazan, Agarwal & Kale, Machine Learning 2007 | [meta-71](docs/specs/meta-71-online-newton-step.md) |
| META-72 | Online Mirror Descent | P6 (Online learning) | Beck & Teboulle, Op. Res. Letters 2003 | [meta-72](docs/specs/meta-72-online-mirror-descent.md) |
| META-73 | Online AdaBoost (OC variant) | P6 (Online learning) | Chen et al., JMLR 2012 | [meta-73](docs/specs/meta-73-online-adaboost-oc.md) |
| META-74 | Projected Online Gradient | P6 (Online learning) | Zinkevich, ICML 2003 | [meta-74](docs/specs/meta-74-projected-online-gradient.md) |
| META-75 | ADMM Streaming | P6 (Online learning) | Boyd, Parikh, Chu, Peleato & Eckstein, FnT ML 2011 | [meta-75](docs/specs/meta-75-admm-streaming.md) |
| META-76 | ApproxNDCG | P7 (Listwise / rank-aware losses) | Qin, Liu & Li, Information Retrieval 2010 | [meta-76](docs/specs/meta-76-approxndcg.md) |
| META-77 | LambdaLoss | P7 (Listwise / rank-aware losses) | Wang, Li, Metzler & Najork, CIKM 2018 | [meta-77](docs/specs/meta-77-lambda-loss.md) |
| META-78 | NeuralNDCG | P7 (Listwise / rank-aware losses) | Pobrotyn & Białobrzeski, arXiv:2102.07831 (2021) | [meta-78](docs/specs/meta-78-neural-ndcg.md) |
| META-79 | SoftRank | P7 (Listwise / rank-aware losses) | Taylor, Guiver, Robertson & Minka, WSDM 2008 | [meta-79](docs/specs/meta-79-softrank.md) |
| META-80 | Smooth-AP | P7 (Listwise / rank-aware losses) | Brown, Gu, Ferreira & Zisserman, ECCV 2020 | [meta-80](docs/specs/meta-80-smooth-ap.md) |
| META-81 | Listwise Cross-Entropy | P7 (Listwise / rank-aware losses) | Cao, Qin, Liu, Tsai & Li, ICML 2007 | [meta-81](docs/specs/meta-81-listwise-cross-entropy.md) |
| META-82 | FISTA Proximal Gradient | P8 (Regularisation) | Beck & Teboulle, SIAM J. Imaging Sciences 2009 | [meta-82](docs/specs/meta-82-fista-proximal-gradient.md) |
| META-83 | Nuclear-Norm Regularisation | P8 (Regularisation) | Fazel, Hindi & Boyd, ACC 2001 | [meta-83](docs/specs/meta-83-nuclear-norm-regularization.md) |
| META-84 | Group LASSO | P8 (Regularisation) | Yuan & Lin, JRSS-B 2006 | [meta-84](docs/specs/meta-84-group-lasso.md) |
| META-85 | Fused LASSO | P8 (Regularisation) | Tibshirani, Saunders, Rosset, Zhu & Knight, JRSS-B 2005 | [meta-85](docs/specs/meta-85-fused-lasso.md) |
| META-86 | SCAD (Smoothly Clipped Absolute Deviation) | P8 (Regularisation) | Fan & Li, JASA 2001 | [meta-86](docs/specs/meta-86-scad-penalty.md) |
| META-87 | Platt Sigmoid Scaling | P9 (Calibration) | Platt, *Advances in Large Margin Classifiers* 1999 | [meta-87](docs/specs/meta-87-platt-sigmoid-scaling.md) |
| META-88 | Beta Calibration | P9 (Calibration) | Kull, Silva Filho & Flach, AISTATS 2017 | [meta-88](docs/specs/meta-88-beta-calibration.md) |
| META-89 | Dirichlet Calibration | P9 (Calibration) | Kull et al., NeurIPS 2019 | [meta-89](docs/specs/meta-89-dirichlet-calibration.md) |
| META-90 | Histogram Binning | P9 (Calibration) | Zadrozny & Elkan, ICML 2001 | [meta-90](docs/specs/meta-90-histogram-binning-calibration.md) |
| META-91 | Cosine Annealing with Warm Restarts | P10 (Learning-rate schedulers) | Loshchilov & Hutter, ICLR 2017 | [meta-91](docs/specs/meta-91-cosine-annealing-warm-restart.md) |
| META-92 | 1-Cycle Learning Rate | P10 (Learning-rate schedulers) | Smith, USAF Tech Rep 2018 | [meta-92](docs/specs/meta-92-one-cycle-lr.md) |
| META-93 | Transformer Warmup-Linear-Decay | P10 (Learning-rate schedulers) | Vaswani, Shazeer, Parmar et al., NIPS 2017 | [meta-93](docs/specs/meta-93-transformer-warmup-linear-decay.md) |
| META-94 | Polynomial Decay | P10 (Learning-rate schedulers) | Goyal, He, Xue, Greff, Ranjan et al., arXiv:1706.02677 | [meta-94](docs/specs/meta-94-polynomial-decay-lr.md) |
| META-95 | Step Decay with Plateau Detection | P10 (Learning-rate schedulers) | He, Zhang, Ren & Sun, ICCV 2015 | [meta-95](docs/specs/meta-95-step-decay-plateau.md) |
| META-96 | Stochastic Weight Averaging (SWA) | P11 (Model averaging) | Izmailov, Podoprikhin, Vetrov, Garipov & Wilson, UAI 2018 | [meta-96](docs/specs/meta-96-stochastic-weight-averaging.md) |
| META-97 | Polyak-Ruppert Averaging | P11 (Model averaging) | Polyak & Juditsky, SIAM J. Control 1992 | [meta-97](docs/specs/meta-97-polyak-ruppert-averaging.md) |
| META-98 | Snapshot Ensemble | P11 (Model averaging) | Huang, Li, Pleiss, Liu, Hopcroft & Weinberger, ICLR 2017 | [meta-98](docs/specs/meta-98-snapshot-ensemble.md) |
| META-99 | Deep Ensembles | P11 (Model averaging) | Lakshminarayanan, Pritzel & Blundell, NIPS 2017 | [meta-99](docs/specs/meta-99-deep-ensembles.md) |
| META-100 | Distributionally Robust Optimization (DRO) | P12 (Robustness & sampling) | Ben-Tal, El Ghaoui & Nemirovski, *Robust Optimization* 2009 | [meta-100](docs/specs/meta-100-dro.md) |
| META-101 | Wasserstein-DRO | P12 (Robustness & sampling) | Esfahani & Kuhn, SIAM J. Opt. 2018 | [meta-101](docs/specs/meta-101-wasserstein-dro.md) |
| META-102 | Hard-Negative Mining (OHEM) | P12 (Robustness & sampling) | Shrivastava, Gupta & Girshick, CVPR 2016 | [meta-102](docs/specs/meta-102-hard-negative-mining-ohem.md) |
| META-103 | Reservoir Sampling | P12 (Robustness & sampling) | Vitter, ACM TOMS 1985 | [meta-103](docs/specs/meta-103-reservoir-sampling.md) |
| META-104 | Importance-Weighted Mini-Batching | P12 (Robustness & sampling) | Csiba & Richtárik, arXiv:1805.07929 (2018) | [meta-104](docs/specs/meta-104-importance-weighted-minibatch.md) |
| META-105 | Stratified k-Fold Mini-Batching | P12 (Robustness & sampling) | Kohavi, IJCAI 1995 (from Geisser 1975) | [meta-105](docs/specs/meta-105-stratified-k-fold-minibatch.md) |
| META-106 | Metropolis-Hastings | Q1 (MCMC sampling) | Metropolis et al., J. Chem. Phys. 1953 / Hastings, Biometrika 1970 | [meta-106](docs/specs/meta-106-metropolis-hastings.md) |
| META-107 | Gibbs Sampling | Q1 (MCMC sampling) | Geman & Geman, IEEE TPAMI 1984 | [meta-107](docs/specs/meta-107-gibbs-sampling.md) |
| META-108 | Slice Sampling | Q1 (MCMC sampling) | Neal, Annals of Statistics 2003 | [meta-108](docs/specs/meta-108-slice-sampling.md) |
| META-109 | Hamiltonian Monte Carlo | Q1 (MCMC sampling) | Duane, Kennedy, Pendleton & Roweth, Phys. Letters B 1987 | [meta-109](docs/specs/meta-109-hamiltonian-monte-carlo.md) |
| META-110 | No-U-Turn Sampler (NUTS) | Q1 (MCMC sampling) | Hoffman & Gelman, JMLR 2014 | [meta-110](docs/specs/meta-110-nuts-no-u-turn-sampler.md) |
| META-111 | Stochastic Gradient Langevin Dynamics | Q1 (MCMC sampling) | Welling & Teh, ICML 2011 | [meta-111](docs/specs/meta-111-sgld.md) |
| META-112 | Elliptical Slice Sampling | Q1 (MCMC sampling) | Murray, Prescott & Adams, AISTATS 2010 | [meta-112](docs/specs/meta-112-elliptical-slice-sampling.md) |
| META-113 | Sequential Monte Carlo | Q1 (MCMC sampling) | Del Moral, C. R. Acad. Sci. Paris 1996 | [meta-113](docs/specs/meta-113-sequential-monte-carlo.md) |
| META-114 | Mean-Field Variational Inference | Q2 (Variational inference) | Beal, PhD thesis UCL 2003 | [meta-114](docs/specs/meta-114-mean-field-vi.md) |
| META-115 | Expectation Propagation | Q2 (Variational inference) | Minka, UAI 2001 | [meta-115](docs/specs/meta-115-expectation-propagation.md) |
| META-116 | Stein Variational Gradient Descent | Q2 (Variational inference) | Liu & Wang, NeurIPS 2016 | [meta-116](docs/specs/meta-116-stein-variational-gradient-descent.md) |
| META-117 | Black-Box VI | Q2 (Variational inference) | Ranganath, Gerrish & Blei, AISTATS 2014 | [meta-117](docs/specs/meta-117-black-box-vi.md) |
| META-118 | Reparameterisation-Trick VI | Q2 (Variational inference) | Kingma & Welling, ICLR 2014 | [meta-118](docs/specs/meta-118-reparameterization-trick-vi.md) |
| META-119 | Amortised VI | Q2 (Variational inference) | Gershman & Goodman, CogSci 2014 | [meta-119](docs/specs/meta-119-amortised-vi.md) |
| META-120 | Genetic Algorithm (Classical) | Q3 (Evolutionary / swarm) | Holland, *Adaptation in Natural and Artificial Systems* 1975 | [meta-120](docs/specs/meta-120-genetic-algorithm.md) |
| META-121 | Evolution Strategies (1+1, μ/ρ+λ) | Q3 (Evolutionary / swarm) | Rechenberg, *Evolutionsstrategie* 1973 | [meta-121](docs/specs/meta-121-evolution-strategies.md) |
| META-122 | Natural Evolution Strategies (NES) | Q3 (Evolutionary / swarm) | Wierstra, Schaul, Glasmachers, Sun, Peters & Schmidhuber, JMLR 2014 | [meta-122](docs/specs/meta-122-natural-evolution-strategies.md) |
| META-123 | Tabu Search | Q3 (Evolutionary / swarm) | Glover, Operations Research 1986 | [meta-123](docs/specs/meta-123-tabu-search.md) |
| META-124 | GRASP | Q3 (Evolutionary / swarm) | Feo & Resende, J. Global Optimization 1995 | [meta-124](docs/specs/meta-124-grasp.md) |
| META-125 | Variable Neighborhood Search | Q3 (Evolutionary / swarm) | Mladenović & Hansen, Computers & OR 1997 | [meta-125](docs/specs/meta-125-variable-neighborhood-search.md) |
| META-126 | Adaptive Large Neighborhood Search (ALNS) | Q3 (Evolutionary / swarm) | Ropke & Pisinger, Transportation Science 2006 | [meta-126](docs/specs/meta-126-alns.md) |
| META-127 | Harmony Search | Q3 (Evolutionary / swarm) | Geem, Kim & Loganathan, Simulation 2001 | [meta-127](docs/specs/meta-127-harmony-search.md) |
| META-128 | Natural Gradient | Q4 (Advanced gradient methods) | Amari, Neural Computation 1998 | [meta-128](docs/specs/meta-128-natural-gradient.md) |
| META-129 | AdaBelief | Q4 (Advanced gradient methods) | Zhuang, Tang, Ding, Tatikonda, Dvornek, Papademetris & Duncan, NeurIPS 2020 | [meta-129](docs/specs/meta-129-adabelief.md) |
| META-130 | Nesterov Accelerated Gradient | Q4 (Advanced gradient methods) | Nesterov, Soviet Mathematics Doklady 1983 | [meta-130](docs/specs/meta-130-nesterov-accelerated-gradient.md) |
| META-131 | Mirror Descent (Offline) | Q4 (Advanced gradient methods) | Nemirovski & Yudin, *Problem Complexity* 1983 | [meta-131](docs/specs/meta-131-mirror-descent-offline.md) |
| META-132 | Proximal Gradient (ISTA) | Q4 (Advanced gradient methods) | Rockafellar, *Convex Analysis* 1976 / Daubechies et al., CPAM 2004 | [meta-132](docs/specs/meta-132-proximal-gradient-ista.md) |
| META-133 | Apollo Optimiser | Q4 (Advanced gradient methods) | Ma, NeurIPS 2021 | [meta-133](docs/specs/meta-133-apollo-optimiser.md) |
| META-134 | LAMB | Q4 (Advanced gradient methods) | You et al., ICLR 2020 | [meta-134](docs/specs/meta-134-lamb.md) |
| META-135 | LARS | Q4 (Advanced gradient methods) | You, Gitman & Ginsburg, arXiv 2017 | [meta-135](docs/specs/meta-135-lars.md) |
| META-136 | Label Smoothing | Q5 (Regularisation / noise injection) | Szegedy, Vanhoucke, Ioffe, Shlens & Wojna, CVPR 2016 | [meta-136](docs/specs/meta-136-label-smoothing.md) |
| META-137 | Mixup | Q5 (Regularisation / noise injection) | Zhang, Cissé, Dauphin & Lopez-Paz, ICLR 2018 | [meta-137](docs/specs/meta-137-mixup.md) |
| META-138 | CutMix | Q5 (Regularisation / noise injection) | Yun, Han, Oh, Chun, Choe & Yoo, ICCV 2019 | [meta-138](docs/specs/meta-138-cutmix.md) |
| META-139 | Cutout | Q5 (Regularisation / noise injection) | DeVries & Taylor, arXiv 2017 | [meta-139](docs/specs/meta-139-cutout.md) |
| META-140 | DropConnect | Q5 (Regularisation / noise injection) | Wan, Zeiler, Zhang, LeCun & Fergus, ICML 2013 | [meta-140](docs/specs/meta-140-dropconnect.md) |
| META-141 | Stochastic Depth | Q5 (Regularisation / noise injection) | Huang, Sun, Liu, Sedra & Weinberger, ECCV 2016 | [meta-141](docs/specs/meta-141-stochastic-depth.md) |
| META-142 | Gradient Noise Injection | Q5 (Regularisation / noise injection) | Neelakantan, Vilnis, Le, Sutskever, Kaiser, Kurach & Martens, arXiv 2015 | [meta-142](docs/specs/meta-142-gradient-noise-injection.md) |
| META-143 | Polynomial Feature Expansion | Q6 (Feature-engineering) | Fukunaga, *Intro to Stat. Pattern Recognition* 1990 | [meta-143](docs/specs/meta-143-polynomial-feature-expansion.md) |
| META-144 | B-Spline Basis Features | Q6 (Feature-engineering) | de Boor, *A Practical Guide to Splines* 1978 | [meta-144](docs/specs/meta-144-b-spline-basis-features.md) |
| META-145 | Natural Cubic Spline Basis | Q6 (Feature-engineering) | Green & Silverman, *Nonparametric Regression* 1993 | [meta-145](docs/specs/meta-145-natural-cubic-spline-basis.md) |
| META-146 | Fourier Random Features | Q6 (Feature-engineering) | Rahimi & Recht, NIPS 2007 | [meta-146](docs/specs/meta-146-fourier-random-features.md) |
| META-147 | Hashing Trick | Q6 (Feature-engineering) | Weinberger, Dasgupta, Langford, Smola & Attenberg, ICML 2009 | [meta-147](docs/specs/meta-147-hashing-trick.md) |
| META-148 | Target Encoding | Q6 (Feature-engineering) | Micci-Barreca, SIGKDD Explorations 2001 | [meta-148](docs/specs/meta-148-target-encoding.md) |
| META-149 | Count Encoding | Q6 (Feature-engineering) | Pargent, Bischl & Thomas, NeurIPS 2021 | [meta-149](docs/specs/meta-149-count-encoding.md) |
| META-150 | Leave-One-Out Target Encoding | Q6 (Feature-engineering) | Micci-Barreca 2001 (LOO variant) | [meta-150](docs/specs/meta-150-loo-target-encoding.md) |
| META-151 | PCA | Q7 (Dimensionality reduction) | Pearson, Philosophical Magazine 1901 | [meta-151](docs/specs/meta-151-pca.md) |
| META-152 | Kernel PCA | Q7 (Dimensionality reduction) | Schölkopf, Smola & Müller, Neural Computation 1998 | [meta-152](docs/specs/meta-152-kernel-pca.md) |
| META-153 | Independent Component Analysis (ICA) | Q7 (Dimensionality reduction) | Hyvärinen & Oja, Neural Networks 2000 | [meta-153](docs/specs/meta-153-ica.md) |
| META-154 | Sparse PCA | Q7 (Dimensionality reduction) | Zou, Hastie & Tibshirani, JCGS 2006 | [meta-154](docs/specs/meta-154-sparse-pca.md) |
| META-155 | Linear Discriminant Analysis (LDA) | Q7 (Dimensionality reduction) | Fisher, Annals of Eugenics 1936 | [meta-155](docs/specs/meta-155-lda-linear-discriminant-analysis.md) |
| META-156 | Canonical Correlation Analysis (CCA) | Q7 (Dimensionality reduction) | Hotelling, Biometrika 1936 | [meta-156](docs/specs/meta-156-cca-canonical-correlation-analysis.md) |
| META-157 | Random Projection (Johnson-Lindenstrauss) | Q7 (Dimensionality reduction) | Johnson & Lindenstrauss 1984 / Achlioptas, JCSS 2003 | [meta-157](docs/specs/meta-157-random-projection-jl.md) |
| META-158 | Kernel Ridge Regression | Q8 (Kernel methods) | Saunders, Gammerman & Vovk, ICML 1998 | [meta-158](docs/specs/meta-158-kernel-ridge-regression.md) |
| META-159 | Support Vector Regression | Q8 (Kernel methods) | Drucker, Burges, Kaufman, Smola & Vapnik, NIPS 1996 | [meta-159](docs/specs/meta-159-support-vector-regression.md) |
| META-160 | Nyström Approximation | Q8 (Kernel methods) | Williams & Seeger, NIPS 2001 | [meta-160](docs/specs/meta-160-nystrom-approximation.md) |
| META-161 | Random Fourier Features | Q8 (Kernel methods) | Rahimi & Recht, NIPS 2007 | [meta-161](docs/specs/meta-161-random-fourier-features.md) |
| META-162 | Gaussian Process Regression | Q8 (Kernel methods) | Rasmussen & Williams, *GPs for ML* 2006 | [meta-162](docs/specs/meta-162-gaussian-process-regression.md) |
| META-163 | Kraskov Mutual Information Estimator | Q9 (Information-theoretic model selection) | Kraskov, Stögbauer & Grassberger, Physical Review E 2004 | [meta-163](docs/specs/meta-163-kraskov-mutual-information.md) |
| META-164 | Information Bottleneck | Q9 (Information-theoretic model selection) | Tishby, Pereira & Bialek, Allerton 1999 | [meta-164](docs/specs/meta-164-information-bottleneck.md) |
| META-165 | Minimum Description Length (MDL) | Q9 (Information-theoretic model selection) | Rissanen, Automatica 1978 | [meta-165](docs/specs/meta-165-minimum-description-length.md) |
| META-166 | Akaike Information Criterion (AIC) | Q9 (Information-theoretic model selection) | Akaike, IEEE TAC 1974 | [meta-166](docs/specs/meta-166-aic.md) |
| META-167 | Bayesian Information Criterion (BIC) | Q9 (Information-theoretic model selection) | Schwarz, Annals of Statistics 1978 | [meta-167](docs/specs/meta-167-bic.md) |
| META-168 | k-Means | Q10 (Clustering) | MacQueen, Berkeley Symposium 1967 / Lloyd, IEEE TIT 1982 | [meta-168](docs/specs/meta-168-k-means.md) |
| META-169 | k-Medoids (PAM) | Q10 (Clustering) | Kaufman & Rousseeuw, *Stat. Data Analysis* 1987 | [meta-169](docs/specs/meta-169-k-medoids-pam.md) |
| META-170 | DBSCAN | Q10 (Clustering) | Ester, Kriegel, Sander & Xu, KDD 1996 | [meta-170](docs/specs/meta-170-dbscan.md) |
| META-171 | HDBSCAN | Q10 (Clustering) | Campello, Moulavi & Sander, KDD 2013 | [meta-171](docs/specs/meta-171-hdbscan.md) |
| META-172 | OPTICS | Q10 (Clustering) | Ankerst, Breunig, Kriegel & Sander, SIGMOD 1999 | [meta-172](docs/specs/meta-172-optics.md) |
| META-173 | Mean Shift | Q10 (Clustering) | Comaniciu & Meer, IEEE TPAMI 2002 | [meta-173](docs/specs/meta-173-mean-shift.md) |
| META-174 | Affinity Propagation | Q10 (Clustering) | Frey & Dueck, Science 2007 | [meta-174](docs/specs/meta-174-affinity-propagation.md) |
| META-175 | BIRCH | Q10 (Clustering) | Zhang, Ramakrishnan & Livny, SIGMOD 1996 | [meta-175](docs/specs/meta-175-birch.md) |
| META-176 | Permutation Importance | Q11 (Feature attribution) | Breiman, Machine Learning 2001 | [meta-176](docs/specs/meta-176-permutation-importance.md) |
| META-177 | SHAP Values | Q11 (Feature attribution) | Lundberg & Lee, NIPS 2017 | [meta-177](docs/specs/meta-177-shap-values.md) |
| META-178 | LIME | Q11 (Feature attribution) | Ribeiro, Singh & Guestrin, KDD 2016 | [meta-178](docs/specs/meta-178-lime.md) |
| META-179 | Integrated Gradients | Q11 (Feature attribution) | Sundararajan, Taly & Yan, ICML 2017 | [meta-179](docs/specs/meta-179-integrated-gradients.md) |
| META-180 | Mean Decrease Impurity | Q11 (Feature attribution) | Breiman, Machine Learning 2001 | [meta-180](docs/specs/meta-180-mean-decrease-impurity.md) |
| META-181 | Uncertainty Sampling | Q12 (Active learning) | Lewis & Catlett, ICML 1994 | [meta-181](docs/specs/meta-181-uncertainty-sampling.md) |
| META-182 | Query by Committee | Q12 (Active learning) | Seung, Opper & Sompolinsky, COLT 1992 | [meta-182](docs/specs/meta-182-query-by-committee.md) |
| META-183 | Expected Model Change | Q12 (Active learning) | Settles & Craven, 2008 | [meta-183](docs/specs/meta-183-expected-model-change.md) |
| META-184 | Density-Weighted Sampling | Q12 (Active learning) | Settles, JCDL 2012 | [meta-184](docs/specs/meta-184-density-weighted-sampling.md) |
| META-185 | Batch-Mode Active Learning | Q12 (Active learning) | Hoi, Jin, Zhu & Lyu, ICML 2006 | [meta-185](docs/specs/meta-185-batch-mode-active-learning.md) |
| META-186 | Self-Training (Pseudo-Labelling) | Q13 (Semi-supervised) | Scudder, IEEE TIT 1965 | [meta-186](docs/specs/meta-186-self-training.md) |
| META-187 | Co-Training | Q13 (Semi-supervised) | Blum & Mitchell, COLT 1998 | [meta-187](docs/specs/meta-187-co-training.md) |
| META-188 | Label Propagation (Graph) | Q13 (Semi-supervised) | Zhu, Ghahramani & Lafferty, ICML 2003 | [meta-188](docs/specs/meta-188-label-propagation-graph.md) |
| META-189 | MixMatch | Q13 (Semi-supervised) | Berthelot, Carlini, Goodfellow, Papernot, Oliver & Raffel, NeurIPS 2019 | [meta-189](docs/specs/meta-189-mixmatch.md) |
| META-190 | FixMatch | Q13 (Semi-supervised) | Sohn, Berthelot, Carlini, Zhang, Li, Cubuk, Kurakin, Zhang & Raffel, NeurIPS 2020 | [meta-190](docs/specs/meta-190-fixmatch.md) |
| META-191 | Inverse Propensity Weighting | Q14 (Causal inference) | Rosenbaum & Rubin, Biometrika 1983 | [meta-191](docs/specs/meta-191-inverse-propensity-weighting.md) |
| META-192 | Double Machine Learning | Q14 (Causal inference) | Chernozhukov, Chetverikov, Demirer, Duflo, Hansen, Newey & Robins, Econometrics 2018 | [meta-192](docs/specs/meta-192-double-machine-learning.md) |
| META-193 | Doubly Robust Estimator | Q14 (Causal inference) | Bang & Robins, Biometrics 2005 | [meta-193](docs/specs/meta-193-doubly-robust-estimator.md) |
| META-194 | Causal Forest | Q14 (Causal inference) | Athey, Tibshirani & Wager, Annals of Statistics 2019 | [meta-194](docs/specs/meta-194-causal-forest.md) |
| META-195 | Meta-Learner Family (T/S/X-learner) | Q14 (Causal inference) | Künzel, Sekhon, Bickel & Yu, PNAS 2019 | [meta-195](docs/specs/meta-195-meta-learner-family.md) |
| META-196 | Q-Learning | Q15 (Reinforcement learning) | Watkins & Dayan, Machine Learning 1992 | [meta-196](docs/specs/meta-196-q-learning.md) |
| META-197 | SARSA | Q15 (Reinforcement learning) | Rummery & Niranjan, CUED tech rep 1994 | [meta-197](docs/specs/meta-197-sarsa.md) |
| META-198 | REINFORCE Policy Gradient | Q15 (Reinforcement learning) | Williams, Machine Learning 1992 | [meta-198](docs/specs/meta-198-reinforce-policy-gradient.md) |
| META-199 | Actor-Critic | Q15 (Reinforcement learning) | Konda & Tsitsiklis, NIPS 2000 | [meta-199](docs/specs/meta-199-actor-critic.md) |
| META-200 | PPO | Q15 (Reinforcement learning) | Schulman, Wolski, Dhariwal, Radford & Klimov, arXiv 2017 | [meta-200](docs/specs/meta-200-ppo.md) |
| META-201 | DDPG | Q15 (Reinforcement learning) | Lillicrap, Hunt, Pritzel, Heess, Erez, Tassa, Silver & Wierstra, ICLR 2016 | [meta-201](docs/specs/meta-201-ddpg.md) |
| META-202 | ε-Greedy | Q16 (Contextual bandits) | Watkins, Cambridge PhD 1989 | [meta-202](docs/specs/meta-202-epsilon-greedy.md) |
| META-203 | LinUCB | Q16 (Contextual bandits) | Li, Chu, Langford & Schapire, WWW 2010 | [meta-203](docs/specs/meta-203-linucb.md) |
| META-204 | LinTS (Linear Thompson Sampling) | Q16 (Contextual bandits) | Agrawal & Goyal, ICML 2013 | [meta-204](docs/specs/meta-204-lints-linear-thompson-sampling.md) |
| META-205 | Cascading Bandits | Q16 (Contextual bandits) | Kveton, Szepesvári, Wen & Ashkan, ICML 2015 | [meta-205](docs/specs/meta-205-cascading-bandits.md) |
| META-206 | Singular Value Decomposition (SVD) | Q17 (Matrix factorisation) | Golub & Van Loan, *Matrix Computations* 1983 | [meta-206](docs/specs/meta-206-svd.md) |
| META-207 | Non-Negative Matrix Factorisation (NMF) | Q17 (Matrix factorisation) | Lee & Seung, Nature 1999 | [meta-207](docs/specs/meta-207-nmf-non-negative-mf.md) |
| META-208 | Probabilistic Matrix Factorisation (PMF) | Q17 (Matrix factorisation) | Salakhutdinov & Mnih, NIPS 2008 | [meta-208](docs/specs/meta-208-probabilistic-mf.md) |
| META-209 | Bayesian PMF | Q17 (Matrix factorisation) | Salakhutdinov & Mnih, ICML 2008 | [meta-209](docs/specs/meta-209-bayesian-pmf.md) |
| META-210 | Weighted ALS (Implicit Feedback) | Q17 (Matrix factorisation) | Hu, Koren & Volinsky, ICDM 2008 | [meta-210](docs/specs/meta-210-weighted-als-implicit.md) |
| META-211 | Xavier / Glorot Initialisation | Q18 (NN init & normalisation) | Glorot & Bengio, AISTATS 2010 | [meta-211](docs/specs/meta-211-xavier-glorot-init.md) |
| META-212 | He Initialisation | Q18 (NN init & normalisation) | He, Zhang, Ren & Sun, ICCV 2015 | [meta-212](docs/specs/meta-212-he-init.md) |
| META-213 | Orthogonal Initialisation | Q18 (NN init & normalisation) | Saxe, McClelland & Ganguli, ICLR 2014 | [meta-213](docs/specs/meta-213-orthogonal-init.md) |
| META-214 | Layer Normalization | Q18 (NN init & normalisation) | Ba, Kiros & Hinton, arXiv 2016 | [meta-214](docs/specs/meta-214-layer-normalization.md) |
| META-215 | Batch Normalization | Q18 (NN init & normalisation) | Ioffe & Szegedy, ICML 2015 | [meta-215](docs/specs/meta-215-batch-normalization.md) |
| META-216 | Group Normalization | Q18 (NN init & normalisation) | Wu & He, ECCV 2018 | [meta-216](docs/specs/meta-216-group-normalization.md) |
| META-217 | Weight Normalization | Q18 (NN init & normalisation) | Salimans & Kingma, NIPS 2016 | [meta-217](docs/specs/meta-217-weight-normalization.md) |
| META-218 | Spectral Normalization | Q18 (NN init & normalisation) | Miyato, Kataoka, Koyama & Yoshida, ICLR 2018 | [meta-218](docs/specs/meta-218-spectral-normalization.md) |
| META-219 | BBQ (Bayesian Binning into Quantiles) | Q19 (Calibration variants) | Naeini, Cooper & Hauskrecht, AAAI 2015 | [meta-219](docs/specs/meta-219-bbq-bayesian-binning-quantiles.md) |
| META-220 | Spline Calibration | Q19 (Calibration variants) | Gupta, Podkopaev & Er, 2021 | [meta-220](docs/specs/meta-220-spline-calibration.md) |
| META-221 | Venn-Abers Predictors | Q19 (Calibration variants) | Vovk & Petej, Machine Learning 2014 | [meta-221](docs/specs/meta-221-venn-abers-predictors.md) |
| META-222 | Focal-Loss Calibration | Q19 (Calibration variants) | Mukhoti, Kulharia, Sanyal, Golodetz, Torr & Dokania, NeurIPS 2020 | [meta-222](docs/specs/meta-222-focal-loss-calibration.md) |
| META-223 | Cumulative Histogram Calibration | Q19 (Calibration variants) | Kumar, Liang & Ma, NeurIPS 2019 | [meta-223](docs/specs/meta-223-cumulative-histogram-calibration.md) |
| META-224 | Recursive Feature Elimination | Q20 (Feature selection) | Guyon, Weston, Barnhill & Vapnik, Machine Learning 2002 | [meta-224](docs/specs/meta-224-recursive-feature-elimination.md) |
| META-225 | Stability Selection | Q20 (Feature selection) | Meinshausen & Bühlmann, JRSS-B 2010 | [meta-225](docs/specs/meta-225-stability-selection.md) |
| META-226 | mRMR (Min-Redundancy Max-Relevance) | Q20 (Feature selection) | Peng, Long & Ding, IEEE TPAMI 2005 | [meta-226](docs/specs/meta-226-mrmr.md) |
| META-227 | Mutual-Information Feature Ranking | Q20 (Feature selection) | Battiti, IEEE TNN 1994 | [meta-227](docs/specs/meta-227-mi-feature-ranking.md) |
| META-228 | χ² Feature Test | Q20 (Feature selection) | Liu & Setiono, Knowledge Discovery 1995 | [meta-228](docs/specs/meta-228-chi-squared-feature-test.md) |
| META-229 | ANOVA F-Statistic | Q20 (Feature selection) | Fisher, Metron 1918 | [meta-229](docs/specs/meta-229-anova-f-statistic.md) |
| META-230 | Forward Selection | Q20 (Feature selection) | Efroymson, *Math Methods for Digital Computers* 1960 | [meta-230](docs/specs/meta-230-forward-selection.md) |
| META-231 | Boruta Wrapper | Q20 (Feature selection) | Kursa & Rudnicki, J. Stat. Software 2010 | [meta-231](docs/specs/meta-231-boruta-wrapper.md) |
| META-232 | Mahalanobis Metric | Q21 (Distance metric learning) | Mahalanobis, PNI 1936 | [meta-232](docs/specs/meta-232-mahalanobis-metric.md) |
| META-233 | LMNN | Q21 (Distance metric learning) | Weinberger, Blitzer & Saul, NIPS 2005 | [meta-233](docs/specs/meta-233-lmnn.md) |
| META-234 | NCA (Neighbourhood Components Analysis) | Q21 (Distance metric learning) | Goldberger, Roweis, Hinton & Salakhutdinov, NIPS 2005 | [meta-234](docs/specs/meta-234-nca-neighbourhood-components.md) |
| META-235 | ITML | Q21 (Distance metric learning) | Davis, Kulis, Jain, Sra & Dhillon, ICML 2007 | [meta-235](docs/specs/meta-235-itml.md) |
| META-236 | LogDet Metric Learning | Q21 (Distance metric learning) | Kulis, Sustik & Dhillon, ICML 2009 | [meta-236](docs/specs/meta-236-logdet-metric-learning.md) |
| META-237 | LOF (Local Outlier Factor) | Q22 (Anomaly / outlier detection) | Breunig, Kriegel, Ng & Sander, SIGMOD 2000 | [meta-237](docs/specs/meta-237-lof-local-outlier-factor.md) |
| META-238 | One-Class SVM | Q22 (Anomaly / outlier detection) | Schölkopf, Williamson, Smola, Shawe-Taylor & Platt, Neural Computation 2001 | [meta-238](docs/specs/meta-238-one-class-svm.md) |
| META-239 | Elliptic Envelope | Q22 (Anomaly / outlier detection) | Rousseeuw & Van Driessen, Technometrics 1999 | [meta-239](docs/specs/meta-239-elliptic-envelope.md) |
| META-240 | Autoencoder Reconstruction Error | Q22 (Anomaly / outlier detection) | Sakurada & Yairi, MLSDA 2014 | [meta-240](docs/specs/meta-240-autoencoder-reconstruction-error.md) |
| META-241 | Minimum Covariance Determinant | Q22 (Anomaly / outlier detection) | Rousseeuw, J. Amer. Stat. Assoc. 1984 | [meta-241](docs/specs/meta-241-minimum-covariance-determinant.md) |
| META-242 | Generalisation-Loss Early Stopping | Q23 (Validation / PBT) | Prechelt, Neural Networks 1998 | [meta-242](docs/specs/meta-242-gl-early-stopping.md) |
| META-243 | Population Based Training | Q23 (Validation / PBT) | Jaderberg, Dalibard, Osindero, Czarnecki, Donahue, Razavi, Vinyals, Green, Dunning, Simonyan et al., arXiv 2017 | [meta-243](docs/specs/meta-243-population-based-training.md) |
| META-244 | Multi-Armed Bandit HPO | Q23 (Validation / PBT) | Jamieson & Talwalkar, AISTATS 2016 | [meta-244](docs/specs/meta-244-mab-hpo.md) |
| META-245 | Adaptive Random Forest | Q24 (Streaming trees & online decomposition) | Gomes, Bifet, Read, Barddal, Enembreck, Pfahringer, Holmes & Abdessalem, Machine Learning 2017 | [meta-245](docs/specs/meta-245-adaptive-random-forest.md) |
| META-246 | Mondrian Forest | Q24 (Streaming trees & online decomposition) | Lakshminarayanan, Roy & Teh, NIPS 2014 | [meta-246](docs/specs/meta-246-mondrian-forest.md) |
| META-247 | Mini-Batch k-Means | Q24 (Streaming trees & online decomposition) | Sculley, WWW 2010 | [meta-247](docs/specs/meta-247-minibatch-kmeans.md) |
| META-248 | Incremental PCA | Q24 (Streaming trees & online decomposition) | Ross, Lim, Lin & Yang, IJCV 2008 | [meta-248](docs/specs/meta-248-incremental-pca.md) |
| META-249 | Online SVD (Brand) | Q24 (Streaming trees & online decomposition) | Brand, Linear Algebra and its Applications 2006 | [meta-249](docs/specs/meta-249-online-svd-brand.md) |

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

*Last updated: 2026-04-15 (Phase 2 forward-declared backlog added in compressed table format: 126 ranking signals FR-099 … FR-224 across blocks A–O + 210 meta-algorithms META-40 … META-249 across blocks P1–P12 and Q1–Q24 = 336 new entries. Each row links to its full spec file under `docs/specs/`. All entries are Pending — spec stubs only, implementation deferred to future phases per plan `C:\Users\goldm\.claude\plans\zesty-roaming-treasure.md`.)*
