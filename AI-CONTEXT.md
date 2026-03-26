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
- Embedding fallback/default code target: `nomic-ai/nomic-embed-text-v1.5` with 768 dimensions
- Existing `ML_PERFORMANCE_MODE` behavior still supports CPU-safe and GPU-capable execution

### Frontend
- Node.js 22 LTS target runtime
- Angular 20 + Angular Material 20
- TypeScript 5.8
- SCSS with theme tokens in `frontend/src/styles/gsc-theme.scss`

## Current Phase

- Active target for the next session: Phase 18
- FR cross-reference: `FR-015 - Final Slate Diversity Reranking`
- Status: Phase 17 / FR-014 (Near-Duplicate Clustering) is now implemented for its backend scope (SimHash fingerprinting, clustering tasks, and ranker suppression); keep FR-015 separate from FR-014, FR-013, FR-012, FR-011, FR-010, FR-009, and FR-008 evidence

## Current Session Note

- Session target: FR-013 frontend exposure and closure sanity checks
- What changed:
  - added Angular settings exposure for FR-013 through `frontend/src/app/settings/` with a separate Feedback Rerank settings card and save flow
  - added Angular review-detail exposure for `score_feedback_rerank`, `feedback_bucket_key`, and `feedback_rerank_diagnostics`
  - added focused Angular spec coverage for the FR-013 settings card and review-detail diagnostics text
- What was intentionally not changed:
  - no use of `GA4` or `GSC` as FR-013 reward input yet
  - no replacement of FR-011 field-aware relevance
  - no replacement of FR-008 phrase scoring
  - no replacement of FR-009 learned-anchor corroboration
  - no replacement of FR-010 rare-term propagation
  - no business logic moved outside Django
  - no new telemetry schema work from FR-016, FR-017, or FR-018
- Continuity note:
  - FR-013 can now be treated as implemented for its intended repo scope because backend wiring, settings exposure, and review-detail exposure all exist on the active branch
  - frontend unit tests could not be executed in this session because `node` and `npm` were unavailable on the host PATH even though `frontend/node_modules` exists
  - keep FR-014 separate from FR-013, FR-012, FR-011, FR-010, FR-009, FR-008, FR-016, FR-017, and FR-018
- Verification completed:
  - repo sanity check confirmed the FR-013 backend fields and endpoints already exist and match the Angular wiring added here
  - Angular test commands could not run because `npm` and `node` were not available on PATH in this session

## AI Handoff And Git Hygiene

Simple version:
Different AIs must leave the repo either clean or clearly explained.
Do not leave mystery changes behind.

- Every AI session must start with `git status --short` and read the result before editing anything.
- If the worktree is dirty, do not assume the changes are yours.
- Do not delete, overwrite, or reformat unrelated dirty files just to make the tree clean.
- If the dirty files are unrelated, leave them alone and stage only the files for your own slice.
- If the dirty files overlap with the files you need, stop and reconcile carefully before editing. If ownership is unclear, say so plainly.
- Preferred end state for each session: a clean working tree after a narrow commit and push.
- If a clean working tree is not possible, the AI must leave a clear handoff note in `AI-CONTEXT.md` under `Current Session Note` describing:
  - which AI/tool made the session changes, for example `Codex`, `Claude`, or `Antigravity`
  - the exact files intentionally changed
  - whether the changes were committed and pushed
  - what remains uncommitted and why
- Do not claim a session is complete if the intended files are still uncommitted without explanation.
- Never use `git add -A` in a dirty tree.
- Stage only the intended files for the current slice.
- If verification passes and the slice is safe, commit and push it in the same session so the next AI starts from a cleaner base.
- If verification cannot run, say that plainly in the handoff note and do not pretend the tree is safe.

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

Phase 12 shipped:
- separate FR-009 learned-anchor vocabulary and corroboration service built only from inbound `ExistingLink.anchor_text`
- separate `Suggestion.score_learned_anchor_corroboration` and `Suggestion.learned_anchor_diagnostics` storage with neutral fallback at `0.5`
- separate Learned Anchor settings API, pipeline-run snapshot wiring, suggestion detail/admin diagnostics, and Angular review/settings exposure
- learned-anchor ranking impact is bounded, positive-only, and unchanged when `learned_anchor.ranking_weight = 0.0`
- FR-009 verification passed for the targeted Django test slice under SQLite test settings, Angular `test:ci`, Angular build, and migration drift check

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
- Phase 12 / `FR-009`: separate learned-anchor vocabulary, suggestion-level corroboration scoring, settings, diagnostics, review exposure, and admin exposure implemented from `docs/specs/fr009-learned-anchor-vocabulary-corroboration.md`
- Phase 14 / `FR-011`: separate field-aware relevance scoring, settings, diagnostics, review exposure, admin exposure, and snapshot wiring implemented from `docs/specs/fr011-field-aware-relevance-scoring.md`
- Phase 15 / `FR-012`: separate click-distance structural prior scoring, settings, recalculation, diagnostics, review exposure, content exposure, and snapshot wiring implemented from `docs/specs/fr012-click-distance-structural-prior.md`

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
| 12 | FR-009 | Complete | Learned Anchor Vocabulary & Corroboration |
| 13 | FR-010 | Complete | Rare-term propagation shipped with separate backend scoring, settings/snapshot wiring, review/settings exposure, and targeted verification |
| 14 | FR-011 | Complete | Field-aware relevance shipped with separate backend scoring, settings/snapshot wiring, migration, review/admin exposure, and targeted verification |
| 15 | FR-012 | Complete | Click-Distance Structural Prior |
| 16 | FR-013 | Complete | Feedback-Driven Explore/Exploit Reranking |
| 17 | FR-014 | Complete | Near-Duplicate Destination Clustering (Backend) |
| 18 | FR-015 | Queued | Final Slate Diversity Reranking |
| 19 | FR-016 | Queued | GA4 Suggestion Attribution & User-Behavior Telemetry |
| 20 | FR-017 | Queued | GSC Search Outcome Attribution & Delayed Reward Signals |
| 21 | FR-018 | Queued | Auto-Tuned Ranking Weights & Safe Dated Model Promotion |
| 22 | FR-019 | Queued | Operator Alerts, Notification Center & Desktop Attention Signals |
| 23 | FR-020 | Queued | Zero-Downtime Model Switching, Hot Swap & Runtime Registry |

## What Is Next

- Next exact target: Phase 18 / `FR-015 - Final Slate Diversity Reranking`
- Phase 17 reference: `FR-014` shipped as a backend-complete layer for near-duplicate clustering and must stay separate from FR-015, FR-013, FR-012, FR-011, FR-010, FR-009, and FR-008
- Current continuity state: `FR-013` spec, backend wiring, settings exposure, and review-detail exposure now exist on the active branch
- Next session type: start Phase 18 / FR-015 spec-and-repo reconciliation before implementation work
- Scope reminder: do not hide FR-013 feedback evidence inside FR-014 duplicate clustering or earlier scoring layers
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
  - `FR-013` at `docs/specs/fr013-feedback-driven-explore-exploit-reranking.md`
  - `FR-016` at `docs/specs/fr016-ga4-suggestion-attribution-user-behavior-telemetry.md`
  - `FR-019` at `docs/specs/fr019-operator-alerts-notification-center.md`
- These do not change the active implementation target.

## Session Workflow

Every implementation session must:

1. Read `AI-CONTEXT.md` and `FEATURE-REQUESTS.md` before coding.
2. Run `git status --short` before coding and treat a dirty worktree as shared state, not as disposable clutter.
3. Inspect the repository and reconcile docs against actual code before trusting the docs.
4. Implement exactly one active phase unless the repo already proves that phase is complete before work starts.
5. Update `AI-CONTEXT.md` and `FEATURE-REQUESTS.md` at session end.
6. Update `PROMPTS.md` only when workflow guidance drifts from reality.
7. Stage only intended files; never stage `tmp/`, `backend/scripts/`, or unrelated changes.
8. Prefer ending the session with a clean worktree through a narrow commit and push when safe.

## Workflow Guardrails Future AIs Must Follow

Simple version first.

Do not just write code and stop.
This repo expects the docs, checks, and git workflow to move together.

- If the active phase is patent-derived or math-heavy, check whether `docs/specs/fr0XX-<slug>.md` already exists before coding.
- If the spec file is missing, add the spec file in the same overall delivery flow unless the user explicitly asked for spec-only or code-only work.
- When implementing an FR that already has a spec, implement against that spec and keep the code boundary aligned with it.
- Before claiming a phase is done, make sure the matching spec doc exists and that `AI-CONTEXT.md` and `FEATURE-REQUESTS.md` still point at the right next phase.
- Always do sanity checks after code changes, not just before commit.
- Prefer the repo's SQLite test settings for quick verification:
  - `backend\\manage.py test ... --settings=config.settings.test`
  - `backend\\manage.py makemigrations --check --dry-run --settings=config.settings.test`
- If normal Python launcher aliases are broken, the repo `.venv` interpreter may still work even when `py` or `python` does not.
- If frontend checks cannot run because `node` is missing on PATH, say that plainly and do not pretend frontend verification happened.
- Commit and push only after the verification you could actually run is reported clearly.
- When you push code for a phase, prefer also pushing any missing continuity/doc updates that explain the workflow to the next AI.

## FR Spec Parity Rule

For FR-006 and later feature phases, spec parity is part of the workflow.

- A shipped or in-progress feature phase should have a matching `docs/specs/` file unless the roadmap explicitly says the spec is still only a draft elsewhere.
- Do not leave the repo in a state where a new FR implementation exists but the matching spec doc is still missing.
- If you discover that an earlier session implemented code but forgot the matching spec doc, fix that gap before calling the phase workflow clean.

## Pending Configuration

| Item | Why needed | State |
|---|---|---|
| XenForo base URL + API key | live XenForo sync and verification | Already wired; operator must supply real values in env/settings |
| WordPress base URL + optional username/app password | live WordPress sync; private content requires Application Password auth | UI/API shipped; operator must supply real values in env/settings |
| Local runtimes | build/test execution | Direct installed Python 3.12.10 and direct Node paths work for verification; the usual `py`/`python` launcher aliases and `.venv` launcher still need cleanup if a future session wants the shorter commands |

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
- Embedding model fallback/default = `nomic-ai/nomic-embed-text-v1.5` with 768 dimensions
- Existing mode-selection behavior still supports both CPU-safe and GPU-capable operation through `ML_PERFORMANCE_MODE`
- pgvector is the embeddings source of truth

### Git / Collaboration
- One narrow slice per AI session
- Start every session with `git status --short`
- Prefer ending every safe session with a clean worktree
- If the tree stays dirty, leave a clear handoff note naming the AI/tool and the exact files changed
- Commit/push only when verified as far as the environment allows
- Never force-push, rewrite history, or commit secrets
