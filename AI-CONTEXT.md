# AI-CONTEXT.md

<!--
This is the first file every AI must read before doing any work.

Purpose:
- preserve continuity across Codex, Claude Code, and Google AI Studio (Gemini)
- make handoffs reliable when usage limits force tool switching
- keep architecture stable
- reduce repeated re-analysis and drift

Update rules:
- update this file at the end of every coding session
- keep it factual and concise
- do not turn it into a diary
- do not leave stale "current" sections behind
- when architecture changes, update the guardrails section immediately
-->

## Project Identity

**Project name:** XF Internal Linker V2
**Goal:** Enterprise-grade local-first application that suggests highly contextual internal links for XenForo content (and optionally WordPress cross-links), with manual review before anything is applied.

**Previous version:** XF Internal Linker V1 (Flask + SQLite) - feature-complete with 485+ tests, located at `../xf-internal-linker/`

**Primary outcome:**
- find strong contextual internal-link opportunities
- track suggestions with full audit trail
- integrate GSC/GA4 analytics to measure SEO impact
- support XenForo REST API, webhooks, and WordPress cross-linking
- keep the workflow practical, reviewable, and safe

## Canonical Documents

1. `docs/v2-master-plan.md` - comprehensive specification (source of truth)
2. `AI-CONTEXT.md` - this file (continuity checkpoint)
3. `PROMPTS.md` - prompt templates for all AI tools
4. `FEATURE-REQUESTS.md` - pending and completed UI/UX feature requests

## Tech Stack

### Backend
- Python 3.12 (not 3.13)
- Django 5.2 LTS + DRF 3.15+
- PostgreSQL 17 + pgvector
- Redis 7.4
- Celery 5.4 + Celery Beat
- Django Channels 4.2 + Daphne
- psycopg 3.x (not psycopg2)
- django-environ
- sentence-transformers 3.x, spaCy 3.8+, PyTorch 2.3+
- numpy 1.x (not 2.x)

### Frontend
- Node.js 22 LTS
- Angular 19 + Angular Material 19
- Angular CDK 19
- TypeScript 5.7
- SCSS with GSC theme variables in `frontend/src/styles/gsc-theme.scss`

### Infrastructure
- Docker Compose v2
- Services: postgres, redis, backend, celery-worker, celery-beat, nginx

## Mandatory AI Behaviors

Every AI assistant working on this project must:

1. Read `FEATURE-REQUESTS.md` at session start and surface all pending FRs.
2. Check completed FRs before implementing anything new to avoid duplication.
3. Surface incomplete items from **Pending Configuration** at session start.
4. Update `AI-CONTEXT.md` and `FEATURE-REQUESTS.md` at the end of each coding session.

## Pending Configuration

| # | Item | Why needed | Done? |
|---|---|---|---|
| 1 | Set `XENFORO_API_KEY` + `XENFORO_BASE_URL` in `.env` | Required for scheduled auto-sync and `verify_suggestions` | Done - nightly sync scheduled at 02:00 UTC |
| 2 | Set `WORDPRESS_BASE_URL` + `WORDPRESS_USERNAME` + `WORDPRESS_APP_PASSWORD` in `.env` | Required for FR-003 WordPress cross-linking | No |

## Non-Negotiable Guardrails

### Product / Workflow
- GUI-first always.
- Manual review remains in the loop.
- Up to one best suggestion per destination per pipeline run.
- Maximum 3 internal link suggestions per host thread.
- Only scan the first 600 words of host content for insertion.
- Never write directly to XenForo or WordPress databases.
- Read-only API access only.

### Architecture
- Django + DRF backend, Angular frontend, full API separation.
- PostgreSQL + pgvector for all persistence.
- Redis for cache, Celery broker, and channel layer.
- Celery for background work. No inline heavy processing.
- WebSockets for real-time updates. No HTTP polling.
- Docker Compose for deployment.

### ML / Ranking
- Destination = title + distilled body text.
- Host = sentence-level body text within first 600 words.
- Hybrid scoring = semantic + keyword + node affinity + quality + PageRank + velocity.
- pgvector is the embeddings source of truth. No `.npy` files in V2.

### Data Safety
- Export-then-import is the primary data path.
- All external integrations are read-only.
- Keep the audit trail intact.
- Back up the database before migrations.

### Git / Collaboration
- Multi-AI handoff happens through this file.
- One narrow slice per AI session.
- Commit/push only when the slice is verified as far as the environment allows.
- Never force-push, rewrite history, or commit secrets.

## Current Phase

**Phase:** 7 - Complete. FR-005 - Complete.
**Status:** All planned work through Phase 7 is now done, including FR-005 Link Siloing & Topical Authority Enforcement. The app now supports silo groups on scopes, persisted silo ranking controls, strict/prefer/disabled enforcement modes, cross-silo diagnostics, settings-page silo management, and same-silo review filtering. Next target is FR-003 WordPress Cross-Linking.

## What Is Complete

### Phase 0 - Scaffolding
- V2 master plan, prompts, and continuity docs created.
- Docker Compose stack created with postgres, redis, backend, celery-worker, celery-beat, nginx.
- Django project and Angular 19 app scaffolded.
- `.env.example`, `.gitignore`, nginx config, and Dockerfiles added.

### Phase 1 - Django Foundation
- Core data model built across content, suggestions, analytics, audit, graph, plugins, and settings.
- Initial migrations created for all apps with pgvector enabled.
- Django Unfold admin configured.
- DRF serializers/viewsets and `/api/` router wired.
- Job progress WebSocket consumer added at `ws/jobs/<job_id>/`.
- Celery task stubs created for pipeline, embeddings, import, and verification.

### Phase 2 - ML Services Migration
- V1 ML utilities migrated into `backend/apps/pipeline/services/`.
- Ranking, pagerank, velocity, embeddings, and pipeline orchestration ported to Django/pgvector.
- Celery tasks wired to real ML services.
- CPU/GPU mode switching added via `ML_PERFORMANCE_MODE`.

### Phase 3 - XenForo API Client + Content Import
- XenForo REST client added.
- JSONL import flow added as offline alternative.
- Content processing pipeline implemented: BBCode cleaning, sentence splitting, distillation, embeddings.
- Existing-link graph refresh added during import.
- `verify_suggestions` wired to XenForo API.

### Phase 4 - Angular Frontend Core / FR-001
- Appearance settings API added.
- Light-only GSC theming finalized; dark mode removed by design.
- Theme customizer, logo upload, favicon upload, footer controls, presets, and scroll-to-top implemented.
- App shell updated to reflect appearance settings live.

### Phase 5 - Review Page
- Suggestion list/detail APIs extended for review UX.
- Pipeline start action added.
- Angular review page implemented with tabs, search, sort, paginator, batch actions, detail dialog, and highlighted anchors.

### Phase 6 - Dashboard
- Dashboard aggregate API added at `GET /api/dashboard/`.
- Angular dashboard implemented with stat cards, sync banner, pipeline runs table, recent imports, and quick actions.

### FR-004 - Broken Link Detection
- `BrokenLink` model added in `apps/graph/` with UUID PK, source content FK, URL, HTTP status, redirect URL, first/last detection timestamps, reviewer status, and notes.
- Migration added at `backend/apps/graph/migrations/0002_brokenlink.py`.
- `backend/apps/graph/services/__init__.py` and `backend/apps/sync/services/__init__.py` are committed so Celery late imports in `backend/apps/pipeline/tasks.py` resolve at worker startup.
- Broken Links admin registered; admin sidebar now includes a Broken Links entry.
- `extract_urls()` added to `backend/apps/pipeline/services/link_parser.py` for deduplicated URL extraction from BBCode/bare URLs.
- `scan_broken_links` Celery task added with HEAD -> GET fallback, 0.5s rate limiting, 10,000 URL safety cap, `update_or_create()` persistence, and WebSocket progress updates on `ws/jobs/<job_id>/`.
- `BrokenLinkSerializer` and `BrokenLinkViewSet` added with `/api/broken-links/`, `/api/broken-links/scan/`, and `/api/broken-links/export-csv/`.
- Dashboard API now includes `open_broken_links`.
- New Angular `/link-health` page added with live scan progress, summary counts, status/http-status filters, paginated Material table, row actions, CSV export, and empty state.
- Dashboard warning stat card and sidebar badge now surface the open broken-link count and link to Link Health.

### FR-005 - Link Siloing & Topical Authority Enforcement
- `SiloGroup` model added in `apps/content/` and `ScopeItem.silo_group` now uses a nullable `SET_NULL` foreign key for safe assignment and deletion.
- Migration added at `backend/apps/content/migrations/0002_silogroup_scopeitem_silo_group.py`.
- Content admin and API now expose silo groups plus a narrow `PATCH /api/scopes/{id}/` path for updating only `silo_group`.
- Persisted silo ranking settings added at `GET/PUT /api/settings/silos/` using `AppSetting` keys for mode, same-silo boost, and cross-silo penalty.
- Pipeline ranking now respects `disabled`, `prefer_same_silo`, and `strict_same_silo`, with `cross_silo_blocked` diagnostics emitted when strict mode rejects otherwise eligible matches.
- Review API responses now include host/destination silo metadata and support a same-silo filter.
- Angular Settings now manages silo groups, scope assignments, and ranking controls, and Angular Review now shows silo labels plus a same-silo-only filter.
- Backend tests added for silo API/settings contracts, `SET_NULL` deletion behavior, ranker behavior across modes, and same-silo review filtering.

### Refactor / Cleanup
- Shared `highlight.utils.ts` extracted.
- `REJECTION_REASONS` exported from `suggestion.service.ts`.
- `JobsComponent` and `SuggestionDetailDialogComponent` converted to `inject()` pattern.
- Global `.page-header` / `.page-title` styles centralized in `styles.scss`.

## What Is Next

- FR-003 - WordPress Cross-Linking.
  Backend: WordPress REST client, content import mapping, cross-site existing-link graph updates, and read-only credentials.
  Frontend: settings UI for WordPress credentials and sync controls, plus source-aware scope/content labeling.

## Migration Notes

The V1 -> V2 migration script is complete. The V1 codebase at `../xf-internal-linker/` contains:
- 13 SQLite tables (schema version 15)
- 20 Python service files
- 6 route files
- 34 test files
- `.npy` embeddings in `data/`

All V1 ML services have been migrated into `backend/apps/pipeline/services/` with Django ORM + pgvector replacing SQLite + `.npy`.

## Key Decisions Made in Phase 0

- psycopg 3, not psycopg2
- pgvector/PostgreSQL 17 Docker image
- Angular standalone API, no NgModules
- Daphne for ASGI/Channels
- Celery results stored in PostgreSQL
- numpy pinned to 1.x
- GSC color theme implemented as CSS custom properties
