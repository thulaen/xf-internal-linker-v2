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

- Active delivery phase completed this session: Phase 8
- FR cross-reference: `FR-003 - WordPress Cross-Linking`
- Status: complete in repo and locally verified; pending only operator-supplied live credentials/base URLs

## User Communication Preference

- The user is not a developer and prefers plain-English, layman's-terms explanations by default.
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
| 9 | FR-006 | Next | Weighted Link Graph / Reasonable Surfer Scoring |
| 10 | FR-007 | Queued | Link Freshness Authority |
| 11 | FR-008 | Queued | Phrase-Based Matching & Anchor Expansion |
| 12 | FR-009 | Queued | Learned Anchor Vocabulary & Corroboration |
| 13 | FR-010 | Queued | Rare-Term Propagation Across Related Pages |
| 14 | FR-011 | Queued | Field-Aware Relevance Scoring |
| 15 | FR-012 | Queued | Click-Distance Structural Prior |
| 16 | FR-013 | Queued | Feedback-Driven Explore/Exploit Reranking |
| 17 | FR-014 | Queued | Near-Duplicate Destination Clustering |
| 18 | FR-015 | Queued | Final Slate Diversity Reranking |

## What Is Next

- Next exact target: Phase 9 / `FR-006 - Weighted Link Graph / Reasonable Surfer Scoring`
- Scope reminder: add weighted authority as a separate signal without replacing `pagerank_score`
- Required continuity rule: keep FR IDs and phase numbers explicitly cross-referenced; never infer ordering from the FR number

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
