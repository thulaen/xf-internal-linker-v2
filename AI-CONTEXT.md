# AI-CONTEXT.md

This is the first continuity file every AI session must read.

## Project Identity

- Project: XF Internal Linker V2
- Goal: local-first internal-link suggestion system for XenForo and WordPress content with manual review before any link is applied
- Previous version: `../xf-internal-linker/` (Flask + SQLite, feature-complete, 485+ tests)

## Canonical Documents

Execution order and FR IDs are decoupled.

1. `docs/v2-master-plan.md` - architecture and product specification
2. `AI-CONTEXT.md` - current repo state, phase ledger, next target
3. `FEATURE-REQUESTS.md` - backlog source of truth, request dates, request status, target/completed phases
4. `PROMPTS.md` - workflow guidance only

## Tech Stack

### Backend
- Python 3.12 target runtime
- Django 5.2 LTS + DRF
- PostgreSQL 17 + pgvector
- Redis 7.4
- Celery 5.4 + Celery Beat
- Django Channels 4.2 + Daphne

### Frontend
- Node.js 22 LTS target runtime
- Angular 20 + Angular Material 20
- TypeScript 5.8
- SCSS with theme tokens in `frontend/src/styles/gsc-theme.scss`

## Current Phase

- Active target for this session: Phase 12
- FR cross-reference: `FR-009 - Learned Anchor Vocabulary & Corroboration`
- Status: spec-first pass completed this session; implementation is still pending

## Current Session Note

- Session target: Phase 12 / `FR-009 - Learned Anchor Vocabulary & Corroboration`
- Session mode: spec-first pass only
- This session is reserved only for the Phase 12 FR-009 spec-first pass, continuity updates, and safe commit/push handling.
- Scope rule for this session: do not implement FR-009 and do not drift into FR-006, FR-007, FR-008 redesign, FR-011, FR-018, FR-019, or FR-020 work.
- FR-009 spec path: `docs/specs/fr009-learned-anchor-vocabulary-corroboration.md`
- Start-of-session continuity note:
  - `AI-CONTEXT.md` was read first and updated immediately before any other repo reading
  - this session is spec-only and implementation is still pending after this early update
  - the next work after this early update is to inspect repo reality and write the FR-009 spec without widening scope
- What this session completed:
  - inspected the required FR-006, FR-007, FR-008, master-plan, review, admin, settings, serializer, and pipeline paths to confirm the real repo boundaries before writing the spec
  - confirmed the FR-009 spec file was missing and created `docs/specs/fr009-learned-anchor-vocabulary-corroboration.md`
  - defined FR-009 as a separate learned-anchor layer that reads existing `ExistingLink.anchor_text`, keeps missing evidence neutral at `0.5`, keeps ranking impact off by default, and avoids new graph/content storage in the first implementation pass
  - defined review/admin/settings/API expectations for a later FR-009 implementation pass without changing implementation code in this session
- What was intentionally not changed to keep scope clean:
  - no backend implementation files
  - no frontend implementation files
  - no migrations
  - no FR-008, FR-006, or FR-007 redesign
  - no reviewer preference/disallow storage design in the first FR-009 implementation pass
  - no telemetry, alerting, auto-tuning, or later-phase work
- End-of-session continuity note:
  - the FR-009 spec-first pass is complete
  - FR-009 implementation is still pending after this session
  - the next session should be the narrow FR-009 implementation pass using the new spec as the source of truth

## User Communication Preference

- The user is not a developer and prefers plain-English, layman's-terms explanations by default.
- Default communication rule: AI should talk to the user in plain English and explain things like they are five.
- When explaining blockers, risks, test results, or architecture, lead with the simple version first.
- Avoid unnecessary jargon; if a technical term matters, define it briefly in the same reply.
- Keep answers practical and direct; do not assume deep framework or infrastructure knowledge.

Phase 8 shipped:
- read-only WordPress REST client for posts/pages with optional Application Password auth
- WordPress settings API and Angular settings UI for base URL, username, password, manual sync, and Celery Beat schedule
- WordPress `wp_post` and `wp_page` content typing plus `wp_posts` / `wp_pages` scopes
- cross-source existing-link graph refresh for `XF -> WP` and `WP -> XF`
- source-aware review/settings labeling so XenForo vs WordPress content is explicit
- local verification path repaired with Python 3.12 project environment, Django test settings, and Angular 20 build verified under Node.js 22
- frontend npm audit is clean after the Angular 20 toolchain uplift, and frontend `test:ci` now passes via a checked-in smoke test around the HTML-highlighting utility

Phase 9 shipped:
- ordered mixed-syntax internal-link extraction with persisted weighted-edge evidence on `ExistingLink`
- separate `march_2026_pagerank_score` authority computation path with source-row normalization, bounded weighting, and uniform-row fallback
- separate weighted-authority settings API, recalculation task, pipeline snapshotting, and minimal Angular settings controls
- review/admin/content diagnostics now use `march_2026_pagerank_score` as the authority score shown to users
- spec-derived backend tests and Angular review smoke coverage pass locally

Phase 10 shipped:
- separate `LinkFreshnessEdge` history rows keyed by `source -> destination`, with `first_seen_at`, `last_seen_at`, `last_disappeared_at`, and `is_active`
- safe sync behavior that updates history during body-parse paths, reactivates returning links, and does not mark disappearances on non-body paths
- separate `ContentItem.link_freshness_score` and `Suggestion.score_link_freshness` storage with neutral fallback at `0.5`
- separate Link Freshness settings API, recalculation task, bounded ranker hook, and review/admin/content diagnostics
- FR-007 verification passed for backend tests, migration drift, Angular `test:ci`, and Angular build

## What Is Complete

### Platform and Core Flow
- Phase 0: scaffolding, Docker Compose stack, Django/Angular setup, `.env.example`, nginx, Dockerfiles
- Phase 1: core models, migrations, admin, DRF routing, WebSocket job progress, Celery task scaffolding
- Phase 2: V1 ML services migrated into Django/pgvector pipeline services
- Phase 3: XenForo API client, JSONL import flow, content processing, embeddings, existing-link graph refresh, suggestion verification wiring
- Phase 4 / `FR-001`: appearance settings, theme customizer, logo/favicon upload, live shell theming
- Phase 5: review page implementation and pipeline start action
- Phase 6: dashboard aggregate API and Angular dashboard

### Feature Requests Already Shipped
- Phase 7 / `FR-005`: silo groups, persisted silo ranking controls, strict/prefer/disabled silo enforcement, cross-silo diagnostics, same-silo review filtering
- `FR-004`: broken-link detection model, scanner task, API, dashboard surfacing, Angular link-health page
- Phase 8 / `FR-003`: WordPress cross-linking and settings/sync experience
- Phase 8 verification closure: local backend/frontend verification path repaired and passing
- Phase 9 / `FR-006`: weighted link graph, March 2026 PageRank storage, settings, diagnostics, and review exposure implemented from `docs/specs/fr006-weighted-link-graph.md`
- Phase 10 / `FR-007`: separate link-history freshness storage, scoring, settings, ranker integration, diagnostics, and review exposure implemented from `docs/specs/fr007-link-freshness-authority.md`
- Phase 11 / `FR-008`: separate phrase relevance scoring, bounded phrase matching, anchor expansion, settings, diagnostics, and review exposure implemented from `docs/specs/fr008-phrase-based-matching-anchor-expansion.md`

## Execution Ledger

FR IDs are permanent request IDs. Phase numbers below are the execution order.

| Phase | FR ID | Status | Notes |
|---|---|---|---|
| 0 | n/a | Complete | Project scaffolding and guardrails |
| 1 | n/a | Complete | Django foundation and core models |
| 2 | n/a | Complete | ML service migration |
| 3 | n/a | Complete | XenForo import and sync pipeline |
| 4 | FR-001 | Complete | Angular appearance customizer |
| 5 | n/a | Complete | Review workflow UI |
| 6 | n/a | Complete | Dashboard |
| 7 | FR-005 | Complete | Link siloing and topical authority enforcement |
| 8 | FR-003 | Complete | WordPress cross-linking |
| 9 | FR-006 | Complete | Weighted Link Graph / Reasonable Surfer Scoring |
| 10 | FR-007 | Complete | Link Freshness Authority |
| 11 | FR-008 | Complete | Phrase-Based Matching & Anchor Expansion |
| 12 | FR-009 | Next | Learned Anchor Vocabulary & Corroboration |
| 13 | FR-010 | Queued | Rare-Term Propagation Across Related Pages |
| 14 | FR-011 | Queued | Field-Aware Relevance Scoring |
| 15 | FR-012 | Queued | Click-Distance Structural Prior |
| 16 | FR-013 | Queued | Feedback-Driven Explore/Exploit Reranking |
| 17 | FR-014 | Queued | Near-Duplicate Destination Clustering |
| 18 | FR-015 | Queued | Final Slate Diversity Reranking |
| 19 | FR-016 | Queued | GA4 Suggestion Attribution & User-Behavior Telemetry |
| 20 | FR-017 | Queued | GSC Search Outcome Attribution & Delayed Reward Signals |
| 21 | FR-018 | Queued | Auto-Tuned Ranking Weights & Safe Dated Model Promotion |
| 22 | FR-019 | Queued | Operator Alerts, Notification Center & Desktop Attention Signals |
| 23 | FR-020 | Queued | Zero-Downtime Model Switching, Hot Swap & Runtime Registry |

## What Is Next

- Next exact target: Phase 12 / `FR-009 - Learned Anchor Vocabulary & Corroboration`
- Phase 11 reference: `FR-008` was implemented and verified exactly against `docs/specs/fr008-phrase-based-matching-anchor-expansion.md`
- FR-009 stays separate from FR-008 because learned anchor corroboration belongs to its own phase
- Current continuity state: FR-009 spec-first pass is complete and FR-009 implementation is still pending
- Next session type: narrow FR-009 implementation pass only
- Scope reminder: keep FR-009 learned-anchor behavior separate from the shipped FR-008 phrase relevance layer
- Required continuity rule: keep FR IDs and phase numbers explicitly cross-referenced; never infer ordering from the FR number

## Spec Standards for Patent-Derived Phases

Every phase that introduces new math or a patent-derived signal requires a dedicated spec pass before any implementation pass.

- Write the spec to `docs/specs/fr0XX-<slug>.md` before touching implementation code.
- The spec must include a source summary, a math-fidelity note, a full implementation spec, and a test plan. Use `docs/specs/fr006-weighted-link-graph.md` as the quality model.
- FR-007 (freshness): source the math from `US8407231B2`. Do not reuse freshness signals from FR-006's weighted edge features - the boundary is intentional.
- FR-008 (phrase matching): source the math from `US7536408B2`. Do not reuse phrase or surrounding-text signals from FR-006's edge features - the boundary is intentional.
- FR-016 to FR-020 also require a spec/design pass before implementation because they change telemetry schemas, attribution logic, alerting behavior, and model-promotion/runtime safety. Those phases must define neutral fallbacks, rollback paths, and regression gates before any code lands.
- All other patent-inspired phases follow the same two-pass pattern: spec first, implement second, each in its own session.
- FR-018 must also include adaptive-change alerts, immutable history/audit rows, exact timestamped "why weights changed" summaries, and a timeline view before implementation is considered complete.
- FR-019 owns generic operator alerts: model-download reminders, job-complete/failure notifications, bell sounds, desktop notifications, urgent trend warnings, and persisted error-linked alerts.
- FR-020 owns runtime model lifecycle: download, warmup, hot swap, drain, rollback, and zero-downtime model/backfill cutovers. Do not bury that work inside `FR-018`.
- Early user-requested spec drafts exist for:
  - `FR-016` at `docs/specs/fr016-ga4-suggestion-attribution-user-behavior-telemetry.md`
  - `FR-019` at `docs/specs/fr019-operator-alerts-notification-center.md`
- These do not change the active implementation target.

## Session Workflow

Every implementation session must:

1. Read `AI-CONTEXT.md` and `FEATURE-REQUESTS.md` before coding.
2. Inspect the repository and reconcile docs against actual code before trusting the docs.
3. Implement exactly one active phase unless the repo already proves that phase is complete before work starts.
4. Update `AI-CONTEXT.md` and `FEATURE-REQUESTS.md` at session end.
5. Update `PROMPTS.md` only when workflow guidance drifts from reality.
6. Stage only intended files; never stage `tmp/`, `backend/scripts/`, or unrelated changes.

## Pending Configuration

| Item | Why needed | State |
|---|---|---|
| XenForo base URL + API key | live XenForo sync and verification | Already wired; operator must supply real values in env/settings |
| WordPress base URL + optional username/app password | live WordPress sync; private content requires Application Password auth | UI/API shipped; operator must supply real values in env/settings |
| Local runtimes | build/test execution | Python 3.12 and Node.js 22 are now installed locally and working for repo verification |

## Non-Negotiable Guardrails

### Product / Workflow
- GUI-first always
- Manual review remains in the loop
- Up to one best suggestion per destination per pipeline run
- Maximum 3 internal-link suggestions per host thread
- Only scan the first 600 words of host content for insertion
- Never write directly to XenForo or WordPress databases
- Read-only API access only

### Architecture
- Django + DRF backend, Angular frontend, full API separation
- PostgreSQL + pgvector for persistence
- Redis for cache, Celery broker, and channel layer
- Celery for background work; no inline heavy processing
- WebSockets for real-time updates; no HTTP polling
- Docker Compose for deployment

### ML / Ranking
- Destination = title + distilled body text
- Host = sentence-level body text within first 600 words
- Hybrid scoring = semantic + keyword + node affinity + quality + PageRank + velocity
- pgvector is the embeddings source of truth

### Git / Collaboration
- One narrow slice per AI session
- Commit/push only when verified as far as the environment allows
- Never force-push, rewrite history, or commit secrets
