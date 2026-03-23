# AI-CONTEXT.md

<!--
This is the first file every AI must read before doing any work.

Purpose:
- preserve continuity across Codex, Claude Code, and Google Antigravity
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

**Previous version:** XF Internal Linker V1 (Flask + SQLite) — feature-complete with 485+ tests, located at `../xf-internal-linker/`

**Primary outcome:**
- find strong contextual internal-link opportunities
- track suggestions with full audit trail
- integrate GSC/GA4 analytics to measure SEO impact
- support XenForo REST API, Webhooks, and WordPress cross-linking
- keep the workflow practical, reviewable, and safe

## Canonical Documents

1. `docs/v2-master-plan.md` — comprehensive specification (source of truth)
2. `AI-CONTEXT.md` — this file (continuity checkpoint)
3. `PROMPTS.md` — prompt templates for all AI tools

## Tech Stack

### Backend
- Python 3.12 (NOT 3.13 — ML libraries lag behind)
- Django 5.2 LTS + Django REST Framework 3.15+
- PostgreSQL 17 with pgvector 0.7+ extension
- Redis 7.4 (cache, Celery broker, WebSocket channel layer)
- Celery 5.4 + Celery Beat (background tasks + scheduled tasks)
- Django Channels 4.2 + Daphne (WebSockets)
- psycopg 3.x (NOT psycopg2)
- django-environ (env var management)
- sentence-transformers 3.x, spaCy 3.8+, PyTorch 2.3+ (ML/NLP — same as V1)
- numpy 1.x (NOT 2.x — sentence-transformers compatibility)
- scikit-learn (PageRank, scoring)
- pgvector-python (embedding storage and search)

### Frontend
- Node.js 22 LTS
- Angular 19 + Angular Material 19 (standalone component API, no NgModules)
- Angular CDK 19
- D3.js 7+ (link graph visualization — Phase 7)
- Chart.js 4 + ng2-charts (analytics dashboards — Phase 8)
- TypeScript 5.7
- SCSS with GSC color theme (CSS custom properties in gsc-theme.scss)

### Infrastructure
- Docker Compose v2 (no "version:" key)
- pgvector/pgvector:pg17 image (PostgreSQL 17 + pgvector bundled)
- Redis 7.4-alpine
- Nginx 1.27-alpine (serves Angular build, proxies /api/ and /ws/)
- 6 Docker services: postgres, redis, backend, celery-worker, celery-beat, nginx

## Repository Structure (as of Phase 0)

```
xf-internal-linker-v2/
├── backend/
│   ├── config/
│   │   ├── __init__.py          # imports celery app
│   │   ├── celery.py            # Celery app config, named queues
│   │   ├── settings/
│   │   │   ├── base.py          # all shared settings
│   │   │   ├── development.py   # DEBUG=True, CORS_ALLOW_ALL_ORIGINS
│   │   │   └── production.py    # DEBUG=False, HTTPS, strict security
│   │   ├── urls.py              # root URL config
│   │   ├── asgi.py              # ASGI + Django Channels routing
│   │   └── wsgi.py
│   ├── apps/
│   │   ├── core/                # TimestampedModel, health check view
│   │   ├── content/             # ContentItem model stub
│   │   ├── suggestions/         # stub
│   │   ├── pipeline/            # stub + WebSocket routing.py
│   │   ├── analytics/           # stub
│   │   ├── webhooks/            # stub
│   │   ├── audit/               # stub
│   │   ├── graph/               # stub
│   │   ├── plugins/             # stub
│   │   └── api/                 # root API urls.py (includes all apps)
│   ├── services/                # ML service stubs (migrated in Phase 2)
│   │   ├── embeddings.py
│   │   ├── pipeline.py
│   │   ├── distiller.py
│   │   ├── ranker.py
│   │   ├── anchor_extractor.py
│   │   ├── sentence_splitter.py
│   │   ├── link_parser.py
│   │   └── sync.py
│   ├── manage.py
│   ├── requirements.txt         # pinned production deps
│   ├── requirements-dev.txt     # testing + linting tools
│   └── Dockerfile               # Python 3.12-slim, installs spaCy model
├── frontend/
│   ├── angular.json             # Angular CLI config, SCSS components
│   ├── package.json             # Angular 19 + Material 19 + D3 + Chart.js
│   ├── tsconfig.json            # strict TypeScript
│   └── src/
│       ├── main.ts              # bootstrapApplication (standalone)
│       ├── index.html           # loads Inter font + Material Icons
│       ├── styles.scss          # global styles + Material overrides
│       ├── proxy.conf.json      # dev proxy: /api → :8000, /ws → :8000
│       ├── environments/        # environment.ts + environment.production.ts
│       ├── styles/
│       │   └── gsc-theme.scss   # ALL GSC CSS custom properties (colors, spacing)
│       └── app/
│           ├── app.config.ts    # provideRouter + provideHttpClient + interceptors
│           ├── app.routes.ts    # lazy-loaded routes for all 6 pages
│           ├── app.component.*  # shell: Material sidenav + toolbar + router-outlet
│           ├── core/interceptors/
│           │   ├── auth.interceptor.ts
│           │   └── error.interceptor.ts
│           ├── dashboard/       # stub component
│           ├── review/          # stub component
│           ├── graph/           # stub component
│           ├── analytics/       # stub component
│           ├── jobs/            # stub component
│           └── settings/        # stub component
├── nginx/
│   ├── Dockerfile
│   └── nginx.conf               # proxies /api/, /ws/, /admin/ to backend
├── docs/
│   └── v2-master-plan.md
├── docker-compose.yml           # 6 services, named volumes, health checks
├── .env.example                 # all env vars documented with comments
├── .gitignore
├── AI-CONTEXT.md                # this file
└── PROMPTS.md
```

## Non-Negotiable Guardrails

### Product / Workflow
- GUI-first always. Daily use happens in the browser, not CLI.
- Manual review remains in the loop. Tool suggests; human decides.
- Up to one best suggestion per destination per pipeline run.
- Maximum 3 internal link suggestions per host thread.
- Only scan first 600 words of host content for link insertion.
- The tool NEVER writes to XenForo or WordPress databases.
- Read-only API access only.

### Architecture
- Django + DRF backend. Angular frontend. Full API separation.
- PostgreSQL + pgvector for all persistent data.
- Redis for caching, Celery broker, and WebSocket channel layer.
- Celery for all background tasks. No inline heavy processing.
- WebSockets for real-time updates. No HTTP polling.
- Docker Compose for deployment.
- Plugin system: enable/disable without breaking core.

### ML / Ranking
- Destination = title + distilled body text.
- Host = sentence-level body text within first 600 words.
- Hybrid scoring: semantic + keyword + node affinity + quality + PageRank + velocity.
- Anchor policy engine: no generic anchors, cap reuse, prefer long-tail.
- pgvector is source of truth for embeddings. .npy files are NOT used in V2.

### Data Safety
- Export-then-import is the primary data path.
- All APIs are read-only (GET only).
- Full audit trail for all actions.
- Database backups before migrations.

### Git / Collaboration
- Multi-AI handoff via AI-CONTEXT.md (read first, update last).
- One narrow slice per AI session.
- Safe automatic commit/push when tests pass.
- Never force-push, rewrite history, or commit secrets.

### Performance
- App completely shuts down when Docker stops. No lingering processes.
- Balanced mode (CPU only) is default for 16 GB RAM.
- High Performance mode (GPU + CPU) is opt-in via ML_PERFORMANCE_MODE=HIGH_PERFORMANCE.
- Redis cache TTLs prevent stale data without blocking live results.

## Current Phase

**Phase:** 0 — Complete
**Status:** Full project scaffolding created and committed

## What Is Complete

- [x] V2 Master Plan written (`docs/v2-master-plan.md`)
- [x] AI-CONTEXT.md initialized and updated
- [x] PROMPTS.md created
- [x] Project directory created
- [x] `docker-compose.yml` — 6 services with health checks
- [x] `backend/Dockerfile` — Python 3.12-slim, ML deps, spaCy model
- [x] `nginx/Dockerfile` + `nginx/nginx.conf` — Angular + API + WebSocket proxy
- [x] Django project structure: config/, all 10 apps/, services/
- [x] `config/settings/base.py` — full settings (DB, Redis, Celery, DRF, CORS)
- [x] `config/settings/development.py` + `production.py`
- [x] `config/celery.py` — named queues: default, pipeline, embeddings
- [x] `config/asgi.py` — Django Channels + HTTP routing
- [x] All 10 Django app stubs with apps.py, models.py, admin.py, views.py, urls.py
- [x] `apps/core/` — TimestampedModel base class + health check view
- [x] `apps/pipeline/routing.py` — WebSocket URL patterns (ready for Phase 2)
- [x] `apps/api/urls.py` — root API router (Phase 1 app routes commented in)
- [x] All 8 ML service stubs in `backend/services/` with full docstrings
- [x] `backend/requirements.txt` — pinned production deps
- [x] `backend/requirements-dev.txt` — testing + linting
- [x] Angular 19 project: angular.json, package.json, tsconfig files
- [x] `frontend/src/app/app.config.ts` — standalone bootstrap, interceptors
- [x] `frontend/src/app/app.routes.ts` — lazy-loaded routes for all 6 pages
- [x] `frontend/src/app/app.component.*` — Material sidenav shell
- [x] `frontend/src/styles/gsc-theme.scss` — all GSC colors as CSS custom properties
- [x] HTTP interceptors: auth.interceptor.ts, error.interceptor.ts
- [x] All 6 page component stubs (dashboard, review, graph, analytics, jobs, settings)
- [x] `.env.example` — every env var documented with comments
- [x] `.gitignore` — complete exclusions for Python, Node, Docker, secrets

## What Is Next

- [ ] Phase 1: PostgreSQL models for all tables (migrated from V1 SQLite schema)
  - ContentItem with pgvector field for embeddings
  - Suggestion, PipelineRun, AnchorPolicy models
  - Django admin with custom branding and GSC theme
  - DRF serializers and viewsets for core models
  - Redis + Celery health check endpoints
  - Django Channels WebSocket consumer (JobProgress)

## Migration Notes

V1 → V2 migration script needed at Phase 3. The V1 codebase at `../xf-internal-linker/` contains:
- 13 SQLite tables (schema version 15)
- 20 Python service files (6,553 lines)
- 6 route files (2,459 lines)
- 34 test files (485+ tests)
- .npy embedding files in data/

All V1 ML services (pipeline.py, embeddings.py, distiller.py, ranker.py, etc.) migrate to
`backend/services/` with Django ORM replacing raw SQLite queries. The stubs are ready.

## Key Decisions Made in Phase 0

- **psycopg 3** (not psycopg2) — modern async-compatible PostgreSQL driver
- **pgvector/pgvector:pg17 Docker image** — pgvector bundled with PostgreSQL 17
- **Angular standalone API** — no NgModules, cleaner and simpler
- **Daphne** as ASGI server (not gunicorn) — required for Django Channels WebSockets
- **Celery results in PostgreSQL** (django-celery-results) — single source of truth
- **numpy 1.x pinned** — sentence-transformers not yet compatible with numpy 2.x
- **GSC color theme as CSS custom properties** — easy to override for theme customizer
