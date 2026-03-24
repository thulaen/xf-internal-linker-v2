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
4. `FEATURE-REQUESTS.md` — pending and completed UI/UX feature requests

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

## Mandatory AI Behaviors — Read FEATURE-REQUESTS.md Every Session

Every AI assistant working on this project MUST do all three of the following:

### 1. Surface pending feature requests at session start
- Read `FEATURE-REQUESTS.md` at the start of every session.
- At the top of your first response, show a short table of all **PENDING** FRs:
  ```
  📋 PENDING FEATURE REQUESTS
  FR-001  Angular theme customizer (light theme, header/footer, logo, scroll-to-top)
  ```
- If no FRs are pending, say "No pending feature requests." and continue.

### 2. Check completed features before implementing anything new
- Before building any new UI feature or setting, scan the **COMPLETED** section
  of `FEATURE-REQUESTS.md` to check if it was already implemented.
- If the user asks for something that is already done, say:
  "This was completed in FR-XXX — here's what was built: [summary]."
  Do NOT re-implement it silently.

### 3. Periodically suggest improvements (every 3–5 sessions)
- After completing a phase or feature, scan the **COMPLETED** section and pick
  1–2 items that could be meaningfully improved (e.g. better UX, missing edge case,
  performance gain, accessibility issue).
- Phrase it as: "💡 Improvement idea for FR-XXX: [one sentence]."
- Only suggest if there is a real, actionable improvement. Don't force it.

### 4. Surface pending configuration actions every session
- Read the **Pending Configuration** section below at session start.
- Show any incomplete items as a warning at the top of your first response:
  ```
  ⚠️  PENDING CONFIGURATION
  XF_API_KEY   XenForo API key not yet created — needed for scheduled auto-sync (Option A)
  ```
- Once the user confirms an item is done, remove it from the list.

---

## Pending Configuration

These are one-time setup tasks the user must complete. Every AI must surface these
at session start until they are marked done.

| # | Item | Why needed | Done? |
|---|---|---|---|
| 1 | Create XenForo API key and set `XENFORO_API_KEY` + `XENFORO_BASE_URL` in `.env` | Required for scheduled auto-sync (Celery Beat Option A) and `verify_suggestions` task | ✅ Done — key set, nightly sync scheduled at 02:00 UTC |
| 2 | Create WordPress Application Password and set `WORDPRESS_BASE_URL` + `WORDPRESS_USERNAME` + `WORDPRESS_APP_PASSWORD` in `.env` | Required for FR-003 WordPress cross-linking (logged, target Phase 5) | ❌ |

### WordPress note
WordPress has a built-in REST API (no plugin needed). For read-only public content it
requires no credentials. For private/draft content it needs an **Application Password**
(WordPress → Users → Profile → Application Passwords — built into WP since 5.6).

If WordPress cross-linking is wanted, log it as a feature request and the AI will build:
- `apps/sync/services/wordpress_api.py` — WP REST API client
- WordPress ContentItems synced alongside XenForo content
- Cross-links (XF thread ↔ WP post) surfaced in suggestion pipeline

---

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

**Phase:** 4 — In Progress
**Status:** FR-002 (JSONL import UI) complete and committed. Phase 4 FR-001 core is live: dark/light theme, AppearanceService, ThemeCustomizerComponent, ScrollToTopComponent, backend appearance settings endpoint. Logo/favicon upload is the remaining Phase 4b item.

## What Is Complete

### Phase 0 — Scaffolding
- [x] V2 Master Plan written (`docs/v2-master-plan.md`)
- [x] AI-CONTEXT.md, PROMPTS.md, FEATURE-REQUESTS.md created
- [x] `docker-compose.yml` — 6 services with health checks
- [x] `backend/Dockerfile` — Python 3.12-slim, ML deps, spaCy model
- [x] `nginx/Dockerfile` + `nginx/nginx.conf` — Angular + API + WebSocket proxy
- [x] Django project structure: config/, all 10 apps/, services/
- [x] `config/settings/base.py` — full settings (DB, Redis, Celery, DRF, CORS, Unfold)
- [x] `config/settings/development.py` + `production.py`
- [x] `config/celery.py` — named queues: default, pipeline, embeddings
- [x] `config/asgi.py` — Django Channels + HTTP routing
- [x] All 10 Django app stubs
- [x] All 8 ML service stubs in `backend/services/`
- [x] `backend/requirements.txt` — pinned production deps (incl. django-unfold, django-filter)
- [x] Angular 19 project: angular.json, package.json, tsconfig files
- [x] App shell (sidenav, toolbar, interceptors, lazy routes, GSC theme)
- [x] `.env.example`, `.gitignore`

### Phase 1 — Django Foundation
- [x] **Models** — all 16 PostgreSQL models with full field definitions + help_text:
  - `content`: ScopeItem, ContentItem (pgvector 384-dim), Post, Sentence (pgvector 384-dim), ContentMetricSnapshot
  - `suggestions`: ScopePreset, PipelineRun, Suggestion, PipelineDiagnostic
  - `analytics`: SearchMetric, ImpactReport
  - `audit`: AuditEntry, ReviewerScorecard, ErrorLog
  - `graph`: ExistingLink
  - `plugins`: Plugin, PluginSetting
  - `core`: AppSetting
- [x] **pgvector** — `VectorExtension()` in `content/migrations/0001_initial.py` (runs before vector columns)
- [x] **Migrations** — `0001_initial.py` for all 7 apps with correct cross-app FK dependencies
- [x] **Django Unfold admin** — GSC blue theme, sidebar nav with icons, fieldsets, colour-coded status badges on Suggestion list
- [x] **DRF serializers** — ContentItem (list + detail), ScopeItem, Post, Sentence, Suggestion (list + detail + review), PipelineRun, PipelineDiagnostic
- [x] **DRF viewsets** — ContentItemViewSet, ScopeItemViewSet, SuggestionViewSet (approve/reject/apply/batch_action), PipelineRunViewSet, PipelineDiagnosticViewSet
- [x] **API router** wired in `apps/api/urls.py` (DefaultRouter, all endpoints live at `/api/`)
- [x] **JobProgressConsumer** WebSocket consumer (`ws/jobs/<job_id>/`) — streams Celery progress to Angular
- [x] **Celery task stubs** — run_pipeline, generate_embeddings, import_content, verify_suggestions (all publish progress via channel layer, ready for Phase 2 ML wiring)

### Phase 2 — ML Services Migration
- [x] `backend/apps/pipeline/services/` package created
- [x] Pure-Python utilities copied with updated imports: `spacy_loader.py`, `text_cleaner.py`, `link_parser.py`, `sentence_splitter.py`, `distiller.py`, `anchor_extractor.py`
- [x] `ranker.py` — all V1 scoring logic + `select_final_candidates`; sqlite3 removed; pure Python
- [x] `pagerank.py` — Django ORM replaces SQLite; `run_pagerank()` convenience entry point
- [x] `velocity.py` — Django ORM replaces SQLite/Flask config; `run_velocity()` entry point
- [x] `embeddings.py` — pgvector VectorField replaces .npy files; `generate_all_embeddings()`; ML_PERFORMANCE_MODE for CPU/GPU switching
- [x] `pipeline.py` — full 3-stage pipeline using Django ORM + pgvector; progress_fn callback for WebSocket
- [x] Celery tasks wired to real services: `run_pipeline`, `generate_embeddings`, `import_content` (triggers PageRank + velocity after import)
- [x] CPU/GPU mode switching via `ML_PERFORMANCE_MODE` env var (BALANCED=CPU, HIGH_PERFORMANCE=GPU)

### Phase 3 — XenForo API Client + Content Import
- [x] XenForo API client: `apps/sync/services/xenforo_api.py` (thread list, resource list, post fetch)
- [x] JSONL import alternative for offline use (bulk export from XF)
- [x] V1 → V2 data migration script (SQLite → PostgreSQL, .npy → pgvector)
- [x] Refined distillation using `distill_body` (top-5 sentences)
- [x] Auto-trigger vector embeddings after content sync
- [x] Link graph refresh: automatic extraction and storage of existing internal links
- [x] Wire `import_content` Celery task to actual API + JSONL (triggers PageRank + velocity after import)
- [x] Content processing pipeline: BBCode cleaning → sentence splitting → sentence storage
- [x] Wire `verify_suggestions` task to XenForo API for live link validation
- [x] Refine resource content sync logic (pagination, body extraction, updates)

### Phase 4 — Angular Frontend Core (FR-001 partial)
- [x] `apps/core/views.py` — `AppearanceSettingsView` (`GET/PUT /api/settings/appearance/`)
- [x] `apps/api/urls.py` — appearance endpoint wired
- [x] `AppSetting.CATEGORY_CHOICES` — added `("appearance", "Appearance")`
- [x] `gsc-theme.scss` — dark mode vars under `[data-theme="dark"]`, added `--toolbar-bg`, `--footer-bg`, `--sidenav-width`, `--layout-max-width`, `--color-accent`
- [x] `AppearanceService` — loads from API on init, applies CSS custom properties, saves on change, supports presets
- [x] `ThemeCustomizerComponent` — right Material drawer: theme toggle, color pickers, font/layout/density selectors, site identity, footer, scroll-to-top toggle, named presets
- [x] `ScrollToTopComponent` — floating FAB, watches `.page-content` scroll, smooth scroll to top
- [x] App shell updated: customizer drawer, footer, `siteName` from config, toolbar uses `--toolbar-bg`
- [ ] Phase 4b: Logo / favicon upload

### Phase 5 — Review Page
- [x] `SuggestionListSerializer` — added `destination_url` and `host_title` denormalized fields
- [x] `PipelineRunViewSet.start` action — `POST /api/pipeline-runs/start/` creates + dispatches run
- [x] `SuggestionService` (Angular) — typed interfaces + `list()`, `approve()`, `reject()`, `apply()`, `batchAction()`, `startPipeline()`
- [x] `ReviewComponent` — status tabs (pending/approved/rejected/applied/all), search, sort, paginator, suggestion cards with inline approve/reject-with-reason, batch selection + batch approve/reject, "Run Pipeline" button
- [x] `SuggestionDetailDialogComponent` — full score breakdown bars, editable anchor, reviewer notes, rejection reason selector, approve/reject/apply actions, applied/verified timestamps
- [x] Anchor text highlighted with `<mark>` in both card sentence and detail dialog

## What Is Next

- [ ] Phase 4b — Logo / favicon upload
- [ ] Phase 6 — Dashboard (counts, recent pipeline runs, quick actions)

## Migration Notes

V1 → V2 migration script is now complete. The V1 codebase at `../xf-internal-linker/` contains:
- 13 SQLite tables (schema version 15)
- 20 Python service files (6,553 lines)
- 6 route files (2,459 lines)
- 34 test files (485+ tests)
- .npy embedding files in data/

All V1 ML services (pipeline.py, embeddings.py, distiller.py, ranker.py, etc.) have been migrated to
`backend/apps/pipeline/services/` with Django ORM replacing raw SQLite queries and pgvector
VectorField columns replacing .npy embedding files. The XenForo API client is the next step.

## Key Decisions Made in Phase 0

- **psycopg 3** (not psycopg2) — modern async-compatible PostgreSQL driver
- **pgvector/pgvector:pg17 Docker image** — pgvector bundled with PostgreSQL 17
- **Angular standalone API** — no NgModules, cleaner and simpler
- **Daphne** as ASGI server (not gunicorn) — required for Django Channels WebSockets
- **Celery results in PostgreSQL** (django-celery-results) — single source of truth
- **numpy 1.x pinned** — sentence-transformers not yet compatible with numpy 2.x
- **GSC color theme as CSS custom properties** — easy to override for theme customizer
