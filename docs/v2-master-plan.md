# XF Internal Linker V2 — Master Implementation Plan

**Version:** 1.0
**Status:** Build-ready
**Stack:** Django + Angular + PostgreSQL + Redis
**Target User:** Noob vibe coder using GUI tools (GitHub Desktop, pgAdmin, VS Code, browser)
**Design Philosophy:** Enterprise-grade architecture, WordPress-level usability, Firebase-level developer experience

---

## Table of Contents

1. [What This Project Does](#1-what-this-project-does)
2. [V1 → V2 Migration Summary](#2-v1--v2-migration-summary)
3. [Architecture](#3-architecture)
4. [Tech Stack](#4-tech-stack)
5. [Project Structure](#5-project-structure)
6. [Database Design (PostgreSQL + pgvector)](#6-database-design-postgresql--pgvector)
7. [Django Backend Specification](#7-django-backend-specification)
8. [Angular Frontend Specification](#8-angular-frontend-specification)
9. [ML/NLP Pipeline (Unchanged Core)](#9-mlnlp-pipeline-unchanged-core)
10. [Real-Time System (WebSockets + Redis)](#10-real-time-system-websockets--redis)
11. [Caching Strategy (Redis)](#11-caching-strategy-redis)
12. [Theme & Customizer System](#12-theme--customizer-system)
13. [Plugin / Add-On Architecture](#13-plugin--add-on-architecture)
14. [API Integrations](#14-api-integrations)
15. [Review Experience & Focus Mode](#15-review-experience--focus-mode)
16. [Analytics & Impact Tracking](#16-analytics--impact-tracking)
17. [Link Graph Visualization](#17-link-graph-visualization)
18. [Anchor Policy Engine](#18-anchor-policy-engine)
19. [Audit Trail & Reviewer Scorecards](#19-audit-trail--reviewer-scorecards)
20. [Contextual Linking Strategy (600-Word Window)](#20-contextual-linking-strategy-600-word-window)
21. [Performance Modes (Balanced / High Performance)](#21-performance-modes-balanced--high-performance)
22. [Portability & Deployment](#22-portability--deployment)
23. [Elasticsearch Future Support](#23-elasticsearch-future-support)
24. [Scalability for Large LLMs](#24-scalability-for-large-llms)
25. [Error Reporting & Diagnostics](#25-error-reporting--diagnostics)
26. [Documentation & Tooltips](#26-documentation--tooltips)
27. [Phased Roadmap](#27-phased-roadmap)
28. [GUI-Only Developer Workflow](#28-gui-only-developer-workflow)
29. [Prompts for AI-Assisted Development](#29-prompts-for-ai-assisted-development)
30. [Non-Negotiable Guardrails](#30-non-negotiable-guardrails)

---

## 1. What This Project Does

A local-first application that suggests highly contextual internal links for XenForo forum content (and optionally WordPress cross-links). For every **destination** piece of content, the system finds the best **host** sentences where a link could be naturally inserted. A human reviews every suggestion in a beautiful dashboard and manually applies edits on the live forum. **The program never writes to the live forum or WordPress database.**

### Terminology (Unchanged from V1)

| Term | Meaning |
|---|---|
| **Destination** | The content being linked **to**. Gets at most one suggestion per pipeline run. |
| **Host** | The content that **contains** the sentence where the link will be inserted. |
| **Host sentence** | The specific sentence inside the host's first post where the link fits. |
| **Anchor phrase** | The word or phrase that becomes the clickable link text. |
| **Distilled text** | Compact topical summary of a destination: title + top information-dense sentences. |

### What's New in V2

| Feature | V1 | V2 |
|---|---|---|
| **Backend** | Flask | Django + Django REST Framework |
| **Frontend** | Jinja2 + HTMX + Alpine.js | Angular 19 + Angular Material |
| **Database** | SQLite | PostgreSQL + pgvector |
| **Embeddings** | .npy files | pgvector columns + .npy cache |
| **Cache/Queue** | None | Redis |
| **Real-time** | HTTP polling | WebSockets (Django Channels) |
| **Jobs** | threading.Thread | Celery + Redis |
| **Theme** | Fixed GSC-inspired | WordPress-like customizer |
| **Plugins** | None | Hot-loadable add-on system |
| **Analytics** | None | GSC + GA4 integration |
| **WordPress** | None | Cross-platform linking |
| **XenForo API** | SSH export only | REST API + Webhooks |
| **Search** | SQLite FTS5 | PostgreSQL FTS → Elasticsearch later |
| **Deployment** | Windows batch files | Docker Compose |

---

## 2. V1 → V2 Migration Summary

### What Stays Exactly The Same
- **All Python ML services** — sentence-transformers, spaCy, PyTorch, distiller, ranker, pipeline logic
- **The matching model** — destination (title + distilled body) → host (sentence-level)
- **Hybrid scoring** — semantic + keyword + node affinity + quality + PageRank + velocity
- **The review workflow** — tool suggests, human reviews, human applies manually
- **Read-only principle** — never write to XenForo or WordPress databases
- **Content-type-agnostic design** — (content_id, content_type) composite keys

### What Changes
- Flask routes → Django views + DRF serializers
- Jinja2 templates → Angular components
- SQLite → PostgreSQL (with pgvector for embeddings)
- threading.Thread → Celery workers
- HTTP polling → WebSockets
- Raw SQL → Django ORM (with raw SQL escape hatch for performance-critical queries)
- .env config → Django settings + database-stored preferences

---

## 3. Architecture

### System Diagram

```
┌────────────────────────────────────────────────────────────────────┐
│  CLOUDPANEL SERVER (read-only access only)                         │
│                                                                    │
│  XenForo MySQL ───▶ XenForo REST API (read-only API key)          │
│  WordPress MySQL ──▶ WordPress REST API (read-only)               │
│                                                                    │
│  XenForo Webhooks ──▶ POST to local app (via tunnel or polling)   │
└───────────────────────────────┬────────────────────────────────────┘
                                │
          REST API / Webhooks / SSH Export (legacy fallback)
                                │
┌───────────────────────────────▼────────────────────────────────────┐
│  LOCAL PC (16 GB RAM now, upgradeable later)                       │
│                                                                    │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  Angular Frontend (localhost:4200)                           │  │
│  │  ├── Angular Material UI                                    │  │
│  │  ├── Theme Customizer (WordPress-like)                      │  │
│  │  ├── D3.js Visualizations (Link Graph, Heatmaps)           │  │
│  │  ├── Monaco Editor (diff previews)                          │  │
│  │  └── WebSocket client (live updates)                        │  │
│  └──────────────────────┬──────────────────────────────────────┘  │
│                         │ REST API + WebSocket                     │
│  ┌──────────────────────▼──────────────────────────────────────┐  │
│  │  Django Backend (localhost:8000)                             │  │
│  │  ├── Django REST Framework (API layer)                      │  │
│  │  ├── Django Channels (WebSocket layer)                      │  │
│  │  ├── Django Admin (data management)                         │  │
│  │  ├── Plugin Manager (hot-loadable add-ons)                  │  │
│  │  └── ML Services (spaCy, sentence-transformers, PyTorch)   │  │
│  └──────────────────────┬──────────────────────────────────────┘  │
│                         │                                          │
│  ┌──────────────────────▼──────────────────────────────────────┐  │
│  │  Celery Workers (background jobs)                           │  │
│  │  ├── Sync jobs (API fetch, SSH fallback)                    │  │
│  │  ├── Embedding generation (GPU/CPU)                         │  │
│  │  ├── Pipeline runs (3-stage ranking)                        │  │
│  │  ├── Verification & stale checks                            │  │
│  │  └── GSC/GA4 sync (rate-limited)                            │  │
│  └──────────────────────┬──────────────────────────────────────┘  │
│                         │                                          │
│  ┌──────────┐    ┌──────▼──────┐    ┌──────────────────────────┐  │
│  │  Redis   │    │ PostgreSQL  │    │  File Storage            │  │
│  │  :6379   │    │ :5432       │    │  ├── .npy embeddings     │  │
│  │          │    │ + pgvector  │    │  ├── JSONL exports       │  │
│  │ • Cache  │    │             │    │  └── Plugin assets       │  │
│  │ • Queue  │    │ • All data  │    │                          │  │
│  │ • PubSub │    │ • Vectors   │    │                          │  │
│  │ • WS     │    │ • FTS       │    │                          │  │
│  └──────────┘    └─────────────┘    └──────────────────────────┘  │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

### Architectural Principles

1. **Export-then-import remains the primary data path.** XenForo REST API and WordPress REST API are read-only. The tool never modifies forum or blog content.

2. **PostgreSQL as the single source of truth.** All data, embeddings (via pgvector), settings, audit logs, and plugin state live in PostgreSQL. `.npy` files are a performance cache, not the source of truth (reversed from V1).

3. **Celery for all background work.** No more threading.Thread. Celery gives us proper task queues, retries, rate limiting, and monitoring — critical for GSC/GA4 API rate limits.

4. **WebSockets for real-time updates.** Django Channels + Redis PubSub replaces HTTP polling. Job progress, stale alerts, and live previews push to the browser instantly.

5. **Angular as a proper SPA.** Full separation of concerns: Django serves JSON, Angular handles all rendering. This enables the theme customizer and plugin UI extensions.

6. **Plugin architecture from day one.** Django apps + Angular lazy-loaded modules. Plugins can be turned on/off without breaking the core.

7. **Docker-first deployment.** `docker-compose up` starts everything: Django, Angular, PostgreSQL, Redis, Celery. Portable to any machine.

8. **Designed for growth.** The architecture supports upgrading to Elasticsearch, larger LLMs (GPT-OSS-120B), and multi-user access later without restructuring.

---

## 4. Tech Stack

### Backend

| Component | Choice | Why |
|---|---|---|
| Language | Python 3.12+ | All ML libraries are Python-native |
| Framework | Django 5.x + DRF 3.x | Batteries-included, massive community, ORM, admin, migrations |
| Database | PostgreSQL 16+ with pgvector | Vector similarity search, full-text search, JSON columns, scalable |
| Cache/Queue Broker | Redis 7+ | Caching, Celery broker, WebSocket channel layer, PubSub |
| Background Jobs | Celery 5.x | Production-grade task queue with retries, rate limiting, scheduling |
| Job Scheduler | Celery Beat | Periodic tasks (auto-resync, GSC sync, stale checks) |
| WebSockets | Django Channels 4.x + Daphne | Real-time job progress, live previews, stale alerts |
| Embeddings | sentence-transformers (multi-qa-MiniLM-L6-cos-v1) | Same model as V1, proven quality |
| NLP | spaCy en_core_web_sm | Sentence splitting, entity recognition, noun chunks |
| GPU | PyTorch with CUDA support | Same as V1, auto-detection |
| API Framework | Django REST Framework | Serializers, viewsets, pagination, filtering, throttling |

### Frontend

| Component | Choice | Why |
|---|---|---|
| Framework | Angular 19 | TypeScript, batteries-included, strongly typed, enterprise-standard |
| UI Library | Angular Material 19 | Google's Material Design, consistent, beautiful out of the box |
| Charts/Viz | D3.js + ngx-charts | Link graphs, heatmaps, analytics dashboards |
| Diff Viewer | Monaco Editor (diff mode) | VS Code's editor — side-by-side diffs for suggestion preview |
| Icons | Material Icons | Consistent with Angular Material |
| State Management | NgRx (later) or Angular Signals | Reactive state for complex dashboards |
| WebSocket Client | rxjs WebSocketSubject | Native Angular WebSocket with reactive streams |
| Theme Engine | CSS Custom Properties + Angular CDK | WordPress-like customizer |

### Infrastructure

| Component | Choice | Why |
|---|---|---|
| Containerization | Docker + Docker Compose | One command to start everything |
| Dev Server (Angular) | Angular CLI (`ng serve`) | Hot reload, TypeScript compilation |
| Dev Server (Django) | Django runserver + Daphne | ASGI for WebSocket support |
| Version Control | Git + GitHub | GitHub Desktop for GUI workflow |
| Database GUI | pgAdmin 4 | PostgreSQL management in browser |
| Redis GUI | RedisInsight (optional) | Visual cache/queue inspection |

---

## 5. Project Structure

```
xf-internal-linker-v2/
│
├── docker-compose.yml              # One command to run everything
├── docker-compose.dev.yml          # Development overrides
├── Dockerfile.backend              # Django + Celery container
├── Dockerfile.frontend             # Angular build container
├── .env.example                    # Template for environment variables
├── .env                            # Local environment (git-ignored)
├── AI-CONTEXT.md                   # AI handoff continuity document
├── PROMPTS.md                      # AI prompt templates
├── README.md                       # User-facing quickstart guide
│
├── backend/                        # Django project
│   ├── manage.py
│   ├── requirements.txt
│   ├── pyproject.toml
│   │
│   ├── config/                     # Django project settings
│   │   ├── __init__.py
│   │   ├── settings/
│   │   │   ├── __init__.py
│   │   │   ├── base.py            # Shared settings
│   │   │   ├── development.py     # Dev-specific settings
│   │   │   ├── production.py      # Production settings
│   │   │   └── testing.py         # Test settings
│   │   ├── urls.py                # Root URL configuration
│   │   ├── asgi.py                # ASGI config (WebSocket support)
│   │   ├── wsgi.py                # WSGI config (traditional HTTP)
│   │   └── celery.py              # Celery app configuration
│   │
│   ├── apps/
│   │   ├── core/                  # Shared utilities, base models
│   │   │   ├── models.py          # Abstract base models
│   │   │   ├── serializers.py     # Shared serializers
│   │   │   ├── permissions.py     # Custom permissions
│   │   │   ├── pagination.py      # Custom pagination classes
│   │   │   ├── middleware.py      # Error tracking middleware
│   │   │   └── exceptions.py     # Custom exception handlers
│   │   │
│   │   ├── content/               # Content items, posts, sentences, scopes
│   │   │   ├── models.py          # ContentItem, Post, Sentence, ScopeItem
│   │   │   ├── serializers.py
│   │   │   ├── views.py           # ViewSets for content CRUD
│   │   │   ├── admin.py           # Django admin configuration
│   │   │   ├── signals.py         # Post-save hooks
│   │   │   └── tasks.py           # Content-related Celery tasks
│   │   │
│   │   ├── suggestions/           # Suggestion generation, review, tracking
│   │   │   ├── models.py          # Suggestion, PipelineRun, Diagnostic
│   │   │   ├── serializers.py
│   │   │   ├── views.py           # Review, approve, reject, batch actions
│   │   │   ├── admin.py
│   │   │   ├── signals.py
│   │   │   └── tasks.py           # Pipeline, verification tasks
│   │   │
│   │   ├── pipeline/              # ML pipeline services (migrated from V1)
│   │   │   ├── services/
│   │   │   │   ├── pipeline.py        # 3-stage retrieval & ranking
│   │   │   │   ├── embeddings.py      # Sentence transformer management
│   │   │   │   ├── distiller.py       # Destination distillation
│   │   │   │   ├── ranker.py          # Composite scoring
│   │   │   │   ├── anchor_extractor.py
│   │   │   │   ├── sentence_splitter.py
│   │   │   │   ├── text_cleaner.py
│   │   │   │   ├── pagerank.py
│   │   │   │   ├── velocity.py
│   │   │   │   └── spacy_loader.py
│   │   │   ├── tasks.py           # Celery tasks for pipeline execution
│   │   │   └── signals.py
│   │   │
│   │   ├── sync/                  # Data synchronization
│   │   │   ├── models.py          # SyncState, SyncArtifact
│   │   │   ├── services/
│   │   │   │   ├── xenforo_api.py     # XenForo REST API client
│   │   │   │   ├── wordpress_api.py   # WordPress REST API client
│   │   │   │   ├── ssh_sync.py        # Legacy SSH export (fallback)
│   │   │   │   ├── importer.py        # Content import logic
│   │   │   │   └── webhooks.py        # XenForo webhook handlers
│   │   │   ├── views.py           # Webhook endpoints, sync triggers
│   │   │   ├── admin.py
│   │   │   └── tasks.py           # Sync Celery tasks
│   │   │
│   │   ├── analytics/             # GSC + GA4 integration
│   │   │   ├── models.py          # SearchMetric, AnalyticsEvent, ImpactReport
│   │   │   ├── services/
│   │   │   │   ├── gsc_client.py      # Google Search Console API
│   │   │   │   ├── ga4_client.py      # Google Analytics 4 API
│   │   │   │   └── impact_tracker.py  # Before/after analysis
│   │   │   ├── serializers.py
│   │   │   ├── views.py
│   │   │   ├── admin.py
│   │   │   └── tasks.py           # Rate-limited GSC/GA4 sync tasks
│   │   │
│   │   ├── audit/                 # Full audit trail
│   │   │   ├── models.py          # AuditEntry, ReviewerScorecard
│   │   │   ├── serializers.py
│   │   │   ├── views.py
│   │   │   ├── admin.py
│   │   │   └── middleware.py      # Auto-log all changes
│   │   │
│   │   ├── links/                 # Link graph, existing links, redirects
│   │   │   ├── models.py          # ExistingLink, RedirectCheck, LinkDensity
│   │   │   ├── services/
│   │   │   │   ├── link_parser.py
│   │   │   │   ├── link_checker.py    # 404/redirect monitor
│   │   │   │   ├── density_analyzer.py
│   │   │   │   └── graph_builder.py   # Link graph for visualization
│   │   │   ├── serializers.py
│   │   │   ├── views.py
│   │   │   ├── admin.py
│   │   │   └── tasks.py           # Periodic link health checks
│   │   │
│   │   ├── themes/                # Theme customizer (WordPress-like)
│   │   │   ├── models.py          # ThemePreset, ThemeSetting
│   │   │   ├── serializers.py
│   │   │   ├── views.py           # Save/load/preview themes
│   │   │   └── admin.py
│   │   │
│   │   ├── plugins/               # Plugin management
│   │   │   ├── models.py          # Plugin, PluginSetting
│   │   │   ├── registry.py        # Plugin discovery & lifecycle
│   │   │   ├── serializers.py
│   │   │   ├── views.py           # Enable/disable/configure plugins
│   │   │   └── admin.py
│   │   │
│   │   └── settings_app/         # App-wide settings management
│   │       ├── models.py          # AppSetting (typed key-value)
│   │       ├── serializers.py
│   │       ├── views.py           # Settings CRUD API
│   │       └── admin.py           # Pretty admin for settings
│   │
│   ├── data/                      # Runtime artifacts (git-ignored)
│   │   ├── embeddings/            # .npy cache files
│   │   └── exports/               # JSONL export files
│   │
│   └── tests/                     # Test suite
│       ├── conftest.py            # Shared fixtures
│       ├── test_pipeline/
│       ├── test_sync/
│       ├── test_suggestions/
│       ├── test_analytics/
│       ├── test_links/
│       └── test_plugins/
│
├── frontend/                      # Angular project
│   ├── angular.json
│   ├── package.json
│   ├── tsconfig.json
│   │
│   └── src/
│       ├── app/
│       │   ├── app.component.ts
│       │   ├── app.config.ts
│       │   ├── app.routes.ts
│       │   │
│       │   ├── core/              # Singleton services, guards, interceptors
│       │   │   ├── services/
│       │   │   │   ├── api.service.ts          # HTTP client wrapper
│       │   │   │   ├── websocket.service.ts    # WebSocket connection
│       │   │   │   ├── theme.service.ts        # Theme engine
│       │   │   │   ├── notification.service.ts # Toast/snackbar notifications
│       │   │   │   └── auth.service.ts         # Session management
│       │   │   ├── interceptors/
│       │   │   │   ├── error.interceptor.ts    # Global error handling
│       │   │   │   └── loading.interceptor.ts  # Loading indicators
│       │   │   └── guards/
│       │   │       └── setup.guard.ts          # First-run setup check
│       │   │
│       │   ├── shared/            # Reusable components, pipes, directives
│       │   │   ├── components/
│       │   │   │   ├── suggestion-card/
│       │   │   │   ├── score-badge/
│       │   │   │   ├── status-chip/
│       │   │   │   ├── diff-viewer/
│       │   │   │   ├── loading-spinner/
│       │   │   │   ├── empty-state/
│       │   │   │   ├── tooltip-help/
│       │   │   │   └── confirmation-dialog/
│       │   │   ├── pipes/
│       │   │   │   ├── time-ago.pipe.ts
│       │   │   │   ├── truncate.pipe.ts
│       │   │   │   └── score-color.pipe.ts
│       │   │   └── directives/
│       │   │       ├── keyboard-shortcut.directive.ts
│       │   │       └── tooltip.directive.ts
│       │   │
│       │   ├── features/          # Feature modules (lazy-loaded)
│       │   │   ├── dashboard/
│       │   │   │   ├── dashboard.component.ts
│       │   │   │   ├── dashboard.routes.ts
│       │   │   │   ├── components/
│       │   │   │   │   ├── suggestion-list/
│       │   │   │   │   ├── suggestion-detail/
│       │   │   │   │   ├── filter-bar/
│       │   │   │   │   ├── batch-actions/
│       │   │   │   │   └── focus-mode/         # Zen review mode
│       │   │   │   └── services/
│       │   │   │       └── dashboard.service.ts
│       │   │   │
│       │   │   ├── jobs/
│       │   │   │   ├── jobs.component.ts
│       │   │   │   ├── jobs.routes.ts
│       │   │   │   └── components/
│       │   │   │       ├── job-progress/
│       │   │   │       ├── job-history/
│       │   │   │       └── job-controls/
│       │   │   │
│       │   │   ├── settings/
│       │   │   │   ├── settings.component.ts
│       │   │   │   ├── settings.routes.ts
│       │   │   │   └── components/
│       │   │   │       ├── sync-settings/
│       │   │   │       ├── pipeline-settings/
│       │   │   │       ├── performance-settings/
│       │   │   │       ├── api-settings/        # GSC, GA4, XF API keys
│       │   │   │       └── plugin-settings/
│       │   │   │
│       │   │   ├── analytics/
│       │   │   │   ├── analytics.component.ts
│       │   │   │   ├── analytics.routes.ts
│       │   │   │   └── components/
│       │   │   │       ├── impact-dashboard/    # Before/after reports
│       │   │   │       ├── gsc-overview/        # Search performance
│       │   │   │       ├── ga4-overview/         # Traffic analytics
│       │   │   │       ├── top-performers/
│       │   │   │       └── underperformers/
│       │   │   │
│       │   │   ├── link-graph/
│       │   │   │   ├── link-graph.component.ts
│       │   │   │   ├── link-graph.routes.ts
│       │   │   │   └── components/
│       │   │   │       ├── graph-2d/            # D3.js force graph
│       │   │   │       ├── graph-3d/            # Three.js 3D graph (later)
│       │   │   │       ├── silo-view/           # Topic cluster visualization
│       │   │   │       ├── heatmap/             # Link density heatmap
│       │   │   │       └── orphan-explorer/     # Island detection
│       │   │   │
│       │   │   ├── appearance/
│       │   │   │   ├── appearance.component.ts
│       │   │   │   ├── appearance.routes.ts
│       │   │   │   └── components/
│       │   │   │       ├── theme-customizer/    # WordPress-like live customizer
│       │   │   │       ├── color-picker/
│       │   │   │       ├── layout-selector/
│       │   │   │       └── font-selector/
│       │   │   │
│       │   │   ├── diagnostics/
│       │   │   │   ├── diagnostics.component.ts
│       │   │   │   └── components/
│       │   │   │       ├── skip-reasons/
│       │   │   │       ├── why-no-suggestion/   # Item-level explorer
│       │   │   │       ├── seo-gap-analysis/    # Missing keyword detection
│       │   │   │       └── error-log/
│       │   │   │
│       │   │   ├── history/
│       │   │   │   └── components/
│       │   │   │       ├── timeline/
│       │   │   │       ├── audit-trail/
│       │   │   │       └── reviewer-scorecard/
│       │   │   │
│       │   │   └── plugins/                     # Plugin management UI
│       │   │       ├── plugins.component.ts
│       │   │       └── components/
│       │   │           ├── plugin-list/
│       │   │           ├── plugin-settings/
│       │   │           └── plugin-marketplace/  # Future
│       │   │
│       │   └── layout/            # App shell
│       │       ├── sidebar/
│       │       ├── header/
│       │       ├── footer/
│       │       └── breadcrumb/
│       │
│       ├── assets/
│       │   ├── themes/            # Theme preset files
│       │   └── icons/
│       │
│       └── styles/
│           ├── themes/
│           │   ├── _variables.scss
│           │   ├── _gsc-theme.scss     # Google Search Console theme
│           │   ├── _dark-theme.scss
│           │   └── _custom-theme.scss  # User customizations
│           └── global.scss
│
├── plugins/                       # First-party plugin packages
│   ├── wordpress-crosslinker/     # WordPress ↔ XenForo cross-linking
│   │   ├── backend/
│   │   │   ├── models.py
│   │   │   ├── views.py
│   │   │   ├── tasks.py
│   │   │   └── plugin.py          # Plugin registration
│   │   └── frontend/
│   │       └── wp-crosslinker/    # Angular module
│   │
│   └── media-gallery/             # XenForo Media Gallery support
│       ├── backend/
│       └── frontend/
│
└── scripts/                       # Utility scripts
    ├── export_xf_data.py          # Remote export (runs on server)
    ├── setup_dev.py               # Development environment setup
    └── migrate_v1_to_v2.py        # V1 SQLite → V2 PostgreSQL migration
```

---

## 6. Database Design (PostgreSQL + pgvector)

### Why PostgreSQL Over SQLite (For Your Future)

| Consideration | SQLite (V1) | PostgreSQL (V2) |
|---|---|---|
| Vector similarity search | Load all embeddings into RAM | `pgvector` — query in DB, no RAM needed |
| Concurrent access | 1 writer at a time | Many concurrent writers |
| Full-text search | FTS5 (basic) | Built-in GIN/GiST indexes (powerful) |
| JSON queries | Basic | `jsonb` with indexing |
| Future Elasticsearch | Manual sync | `pg_logical` replication or triggers |
| Docker portability | File copy | Volume mount, pg_dump/restore |
| Scalability | ~100K rows comfortable | Millions of rows |

### Core Models (Django ORM)

```python
# apps/content/models.py

class ScopeItem(models.Model):
    """Forum nodes and resource categories."""
    scope_id = models.IntegerField()
    scope_type = models.CharField(max_length=30, choices=[
        ('node', 'Forum Node'),
        ('resource_category', 'Resource Category'),
        ('wp_category', 'WordPress Category'),
    ])
    title = models.CharField(max_length=500)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL)
    is_enabled = models.BooleanField(default=True)
    content_count = models.IntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = ['scope_id', 'scope_type']
        indexes = [
            models.Index(fields=['scope_type', 'is_enabled']),
        ]


class ContentItem(models.Model):
    """Threads, resources, and WordPress posts."""
    content_id = models.IntegerField()
    content_type = models.CharField(max_length=30, choices=[
        ('thread', 'Forum Thread'),
        ('resource', 'Resource'),
        ('wp_post', 'WordPress Post'),
    ])
    title = models.CharField(max_length=500)
    url = models.URLField(max_length=1000, blank=True)
    scope = models.ForeignKey(ScopeItem, on_delete=models.CASCADE, null=True)
    distilled_text = models.TextField(blank=True)
    distill_method = models.CharField(max_length=50, default='title_plus_body')
    content_hash = models.CharField(max_length=64, blank=True)
    pagerank_score = models.FloatField(default=0.0, db_index=True)
    velocity_score = models.FloatField(default=0.0, db_index=True)

    # pgvector embedding column
    embedding = VectorField(dimensions=384, null=True)

    # Metadata
    view_count = models.IntegerField(default=0)
    reply_count = models.IntegerField(default=0)
    post_date = models.DateTimeField(null=True)
    last_post_date = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['content_id', 'content_type']
        indexes = [
            models.Index(fields=['content_type', 'pagerank_score']),
            models.Index(fields=['content_type', 'velocity_score']),
            # pgvector index for similarity search
            # CREATE INDEX ON content_items USING ivfflat (embedding vector_cosine_ops)
        ]


class Post(models.Model):
    """First post of each content item."""
    content_item = models.OneToOneField(ContentItem, on_delete=models.CASCADE, related_name='post')
    raw_bbcode = models.TextField()
    clean_text = models.TextField()
    char_count = models.IntegerField(default=0)
    word_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Sentence(models.Model):
    """Individual sentences from posts, with embeddings."""
    content_item = models.ForeignKey(ContentItem, on_delete=models.CASCADE, related_name='sentences')
    text = models.TextField()
    position = models.IntegerField()          # Sentence index in post
    char_count = models.IntegerField()
    start_char = models.IntegerField()        # Character offset in clean_text
    end_char = models.IntegerField()
    word_position = models.IntegerField(default=0)  # Word offset for 600-word window

    # pgvector embedding
    embedding = VectorField(dimensions=384, null=True)

    class Meta:
        indexes = [
            models.Index(fields=['content_item', 'position']),
            models.Index(fields=['word_position']),
        ]
```

```python
# apps/suggestions/models.py

class PipelineRun(models.Model):
    """Metadata for each suggestion generation batch."""
    run_id = models.UUIDField(default=uuid.uuid4, primary_key=True)
    rerun_mode = models.CharField(max_length=30)
    host_scope = models.JSONField(default=dict)
    destination_scope = models.JSONField(default=dict)
    run_state = models.CharField(max_length=20, choices=[
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ])
    suggestions_created = models.IntegerField(default=0)
    destinations_processed = models.IntegerField(default=0)
    destinations_skipped = models.IntegerField(default=0)
    duration_seconds = models.FloatField(null=True)
    error_message = models.TextField(blank=True)
    config_snapshot = models.JSONField(default=dict)  # Frozen config at run time
    created_at = models.DateTimeField(auto_now_add=True)


class Suggestion(models.Model):
    """A single link suggestion: destination ← host sentence."""
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('applied', 'Applied'),
        ('verified', 'Verified'),
        ('stale', 'Stale'),
        ('superseded', 'Superseded'),
    ]

    suggestion_id = models.UUIDField(default=uuid.uuid4, primary_key=True)
    pipeline_run = models.ForeignKey(PipelineRun, on_delete=models.CASCADE, related_name='suggestions')

    # Destination (what we're linking TO)
    destination = models.ForeignKey(ContentItem, on_delete=models.CASCADE, related_name='destination_suggestions')

    # Host (where the link is PLACED)
    host = models.ForeignKey(ContentItem, on_delete=models.CASCADE, related_name='host_suggestions')
    host_sentence = models.ForeignKey(Sentence, on_delete=models.CASCADE)

    # Scores
    score_semantic = models.FloatField()
    score_keyword = models.FloatField()
    score_node_affinity = models.FloatField()
    score_quality = models.FloatField()
    score_pagerank = models.FloatField(default=0.0)
    score_velocity = models.FloatField(default=0.0)
    score_final = models.FloatField(db_index=True)

    # Anchor
    anchor_phrase = models.CharField(max_length=500)
    anchor_confidence = models.CharField(max_length=20)  # strong/weak/none
    anchor_edited = models.CharField(max_length=500, blank=True)

    # Review
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    rejection_reason = models.CharField(max_length=100, blank=True)
    reviewer_notes = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True)

    # Verification
    verified_at = models.DateTimeField(null=True)
    applied_at = models.DateTimeField(null=True)
    stale_reason = models.CharField(max_length=200, blank=True)

    # Supersede chain
    superseded_by = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['status', '-score_final']),
            models.Index(fields=['destination', 'status']),
            models.Index(fields=['host', 'status']),
        ]


class PipelineDiagnostic(models.Model):
    """Why a destination was skipped during a pipeline run."""
    pipeline_run = models.ForeignKey(PipelineRun, on_delete=models.CASCADE)
    destination = models.ForeignKey(ContentItem, on_delete=models.CASCADE)
    skip_reason = models.CharField(max_length=100, db_index=True)
    detail = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
```

```python
# apps/analytics/models.py

class SearchMetric(models.Model):
    """GSC/GA4 performance data for a content item."""
    content_item = models.ForeignKey('content.ContentItem', on_delete=models.CASCADE, related_name='search_metrics')
    date = models.DateField(db_index=True)
    source = models.CharField(max_length=10, choices=[('gsc', 'GSC'), ('ga4', 'GA4')])

    # GSC metrics
    impressions = models.IntegerField(default=0)
    clicks = models.IntegerField(default=0)
    ctr = models.FloatField(default=0.0)
    average_position = models.FloatField(null=True)
    query = models.CharField(max_length=500, blank=True)  # Top query

    # GA4 metrics
    page_views = models.IntegerField(default=0)
    sessions = models.IntegerField(default=0)
    avg_engagement_time = models.FloatField(default=0.0)
    bounce_rate = models.FloatField(null=True)

    class Meta:
        unique_together = ['content_item', 'date', 'source', 'query']
        indexes = [
            models.Index(fields=['date', 'source']),
            models.Index(fields=['content_item', '-date']),
        ]


class ImpactReport(models.Model):
    """Before/after tracking for applied suggestions."""
    suggestion = models.ForeignKey('suggestions.Suggestion', on_delete=models.CASCADE, related_name='impact_reports')
    metric_type = models.CharField(max_length=30)  # impressions, clicks, position, views
    before_value = models.FloatField()
    after_value = models.FloatField()
    before_date_range = models.JSONField()  # {start, end}
    after_date_range = models.JSONField()   # {start, end}
    delta_percent = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)
```

```python
# apps/audit/models.py

class AuditEntry(models.Model):
    """Full audit trail for every action."""
    ACTION_CHOICES = [
        ('approve', 'Approved'),
        ('reject', 'Rejected'),
        ('apply', 'Applied'),
        ('verify', 'Verified'),
        ('edit_anchor', 'Anchor Edited'),
        ('mark_stale', 'Marked Stale'),
        ('supersede', 'Superseded'),
        ('note', 'Note Added'),
        ('setting_change', 'Setting Changed'),
        ('plugin_toggle', 'Plugin Toggled'),
    ]

    action = models.CharField(max_length=30, choices=ACTION_CHOICES, db_index=True)
    target_type = models.CharField(max_length=50)  # suggestion, setting, plugin
    target_id = models.CharField(max_length=100)
    detail = models.JSONField(default=dict)
    ip_address = models.GenericIPAddressField(null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['target_type', 'target_id']),
        ]


class ReviewerScorecard(models.Model):
    """Aggregated reviewer performance metrics."""
    period_start = models.DateField()
    period_end = models.DateField()
    total_reviewed = models.IntegerField(default=0)
    approved_count = models.IntegerField(default=0)
    rejected_count = models.IntegerField(default=0)
    approval_rate = models.FloatField(default=0.0)
    verified_rate = models.FloatField(default=0.0)   # How many approved were later verified
    stale_rate = models.FloatField(default=0.0)       # How many went stale
    avg_review_time_seconds = models.FloatField(null=True)
    top_rejection_reasons = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
```

### PostgreSQL Materialized Views

```sql
-- Underlinked content (refresh periodically)
CREATE MATERIALIZED VIEW mv_underlinked_content AS
SELECT ci.id, ci.title, ci.content_type, ci.pagerank_score,
       COUNT(el.id) AS incoming_links,
       COUNT(s.suggestion_id) AS pending_suggestions
FROM content_contentitem ci
LEFT JOIN links_existinglink el ON el.to_content_item_id = ci.id
LEFT JOIN suggestions_suggestion s ON s.destination_id = ci.id AND s.status = 'pending'
GROUP BY ci.id
HAVING COUNT(el.id) < 3
ORDER BY ci.pagerank_score DESC;

-- Repeat anchors (detect anchor reuse)
CREATE MATERIALIZED VIEW mv_repeat_anchors AS
SELECT LOWER(anchor_phrase) AS anchor,
       COUNT(*) AS usage_count,
       array_agg(DISTINCT destination_id) AS destinations
FROM suggestions_suggestion
WHERE status IN ('approved', 'applied', 'verified')
GROUP BY LOWER(anchor_phrase)
HAVING COUNT(*) > 2
ORDER BY COUNT(*) DESC;

-- Review backlog by age
CREATE MATERIALIZED VIEW mv_review_backlog AS
SELECT DATE(created_at) AS suggestion_date,
       COUNT(*) AS pending_count,
       AVG(score_final) AS avg_score
FROM suggestions_suggestion
WHERE status = 'pending'
GROUP BY DATE(created_at)
ORDER BY suggestion_date;
```

---

## 7. Django Backend Specification

### Django Admin Customization

The Django admin will be customized to be noob-friendly and beautiful:

```python
# apps/content/admin.py

@admin.register(ContentItem)
class ContentItemAdmin(admin.ModelAdmin):
    list_display = ['title', 'content_type', 'scope', 'pagerank_score',
                    'velocity_score', 'view_count', 'reply_count', 'post_date']
    list_filter = ['content_type', 'scope__scope_type', 'scope']
    search_fields = ['title', 'content_id']
    readonly_fields = ['content_id', 'content_type', 'content_hash',
                       'pagerank_score', 'velocity_score', 'created_at', 'updated_at']
    list_per_page = 50
    ordering = ['-pagerank_score']

    fieldsets = (
        ('Content Identity', {
            'fields': ('content_id', 'content_type', 'title', 'url', 'scope'),
        }),
        ('Scores', {
            'fields': ('pagerank_score', 'velocity_score'),
            'classes': ('collapse',),
        }),
        ('Engagement', {
            'fields': ('view_count', 'reply_count', 'post_date', 'last_post_date'),
            'classes': ('collapse',),
        }),
        ('NLP', {
            'fields': ('distilled_text', 'distill_method'),
            'classes': ('collapse',),
        }),
    )

# Use django-unfold or jazzmin for beautiful admin UI
# pip install django-unfold
```

### Admin Categories (Sidebar)

```
Django Admin Sidebar:
├── 📊 Dashboard
│   └── Overview stats widget
├── 📝 Content
│   ├── Content Items (threads, resources, WP posts)
│   ├── Scope Items (nodes, categories)
│   └── Posts & Sentences
├── 🔗 Suggestions
│   ├── Pending Review
│   ├── Approved
│   ├── Applied & Verified
│   └── Pipeline Runs
├── 📈 Analytics
│   ├── Search Metrics (GSC)
│   ├── Traffic Metrics (GA4)
│   └── Impact Reports
├── 🔍 Links
│   ├── Existing Links
│   ├── Redirect Checks
│   └── Link Density
├── 📋 Audit
│   ├── Audit Trail
│   └── Reviewer Scorecards
├── 🎨 Appearance
│   ├── Theme Presets
│   └── Theme Settings
├── 🔌 Plugins
│   ├── Installed Plugins
│   └── Plugin Settings
├── ⚙️ Configuration
│   ├── App Settings
│   ├── Sync Settings
│   └── Performance Settings
└── 👤 Users (future multi-user)
```

### API Endpoints (Django REST Framework)

```
API Prefix: /api/v1/

# Content
GET    /api/v1/content/                    # List content items (paginated, filtered)
GET    /api/v1/content/{id}/               # Content detail
GET    /api/v1/content/{id}/sentences/     # Sentences for a content item
GET    /api/v1/content/{id}/links/         # Existing links for content
GET    /api/v1/content/{id}/why-no-suggestion/  # Why no suggestion explorer
GET    /api/v1/scopes/                     # List scopes
PATCH  /api/v1/scopes/{id}/               # Toggle scope enabled/disabled

# Suggestions
GET    /api/v1/suggestions/                # List suggestions (filtered, paginated)
GET    /api/v1/suggestions/{id}/           # Suggestion detail
GET    /api/v1/suggestions/{id}/diff/      # Side-by-side diff preview
GET    /api/v1/suggestions/{id}/stale-check/  # Live stale check
GET    /api/v1/suggestions/{id}/duplicate-check/  # Live duplicate check
POST   /api/v1/suggestions/{id}/approve/   # Approve suggestion
POST   /api/v1/suggestions/{id}/reject/    # Reject with reason
POST   /api/v1/suggestions/{id}/apply/     # Mark as applied
POST   /api/v1/suggestions/{id}/edit/      # Edit anchor/notes
POST   /api/v1/suggestions/batch/          # Batch approve/reject/skip
GET    /api/v1/suggestions/focus-mode/     # Next suggestion for Focus Mode

# Pipeline
POST   /api/v1/pipeline/run/               # Start pipeline run
GET    /api/v1/pipeline/runs/              # List pipeline runs
GET    /api/v1/pipeline/runs/{id}/         # Run detail with diagnostics
GET    /api/v1/pipeline/diagnostics/       # Aggregated skip reasons
POST   /api/v1/pipeline/rebuild/           # Full rebuild

# Sync
POST   /api/v1/sync/run/                   # Start sync job
POST   /api/v1/sync/import/                # Start import job
GET    /api/v1/sync/state/                 # Current sync state
POST   /api/v1/sync/webhooks/xenforo/      # XenForo webhook endpoint
GET    /api/v1/sync/xenforo/threads/{id}/  # Fetch thread via XF API
GET    /api/v1/sync/wordpress/posts/{id}/  # Fetch WP post via WP API

# Jobs
GET    /api/v1/jobs/                       # List recent jobs
GET    /api/v1/jobs/{id}/                  # Job detail
GET    /api/v1/jobs/active/                # Currently running job
POST   /api/v1/jobs/{id}/cancel/           # Cancel running job

# Analytics
GET    /api/v1/analytics/gsc/overview/     # GSC summary stats
GET    /api/v1/analytics/ga4/overview/     # GA4 summary stats
GET    /api/v1/analytics/impact/           # Before/after impact reports
GET    /api/v1/analytics/top-performers/   # Best performing suggestions
GET    /api/v1/analytics/underperformers/  # Worst performing suggestions
POST   /api/v1/analytics/gsc/sync/        # Trigger GSC data pull

# Links
GET    /api/v1/links/graph/                # Link graph data (D3 format)
GET    /api/v1/links/orphans/              # Orphaned content
GET    /api/v1/links/density/{id}/         # Link density for content
GET    /api/v1/links/redirects/            # Redirect/404 check results
GET    /api/v1/links/silos/                # Topic silo structure
POST   /api/v1/links/check-health/         # Trigger link health check

# Audit
GET    /api/v1/audit/trail/                # Full audit trail
GET    /api/v1/audit/scorecard/            # Reviewer scorecard

# Settings
GET    /api/v1/settings/                   # All settings
PATCH  /api/v1/settings/                   # Update settings
GET    /api/v1/settings/categories/        # Settings grouped by category

# Theme
GET    /api/v1/themes/                     # List theme presets
GET    /api/v1/themes/active/              # Current theme settings
PATCH  /api/v1/themes/active/              # Update theme settings
POST   /api/v1/themes/presets/             # Save theme preset
DELETE /api/v1/themes/presets/{id}/        # Delete theme preset

# Plugins
GET    /api/v1/plugins/                    # List plugins
POST   /api/v1/plugins/{slug}/enable/      # Enable plugin
POST   /api/v1/plugins/{slug}/disable/     # Disable plugin
GET    /api/v1/plugins/{slug}/settings/    # Plugin settings
PATCH  /api/v1/plugins/{slug}/settings/    # Update plugin settings

# Model / Performance
GET    /api/v1/model/status/               # Model, GPU, spaCy status
POST   /api/v1/model/switch-device/        # Switch CPU ↔ GPU

# WebSocket Channels
ws://localhost:8000/ws/jobs/               # Job progress stream
ws://localhost:8000/ws/notifications/      # Stale alerts, completions
ws://localhost:8000/ws/preview/            # Live diff preview updates
```

---

## 8. Angular Frontend Specification

### Navigation Structure (Sidebar)

```
┌──────────────────────────────────┐
│  XF Internal Linker              │
│  ─────────────────               │
│                                  │
│  🏠  Dashboard                   │  ← Suggestion review inbox
│  📊  Analytics                   │  ← GSC/GA4 + impact reports
│  🕸️  Link Graph                  │  ← Visual link structure
│  📋  History                     │  ← Timeline + audit trail
│  💼  Jobs                        │  ← Sync, pipeline, status
│  🔍  Diagnostics                 │  ← Skip reasons, gaps, errors
│                                  │
│  ─── MANAGE ───                  │
│  ⚙️  Settings                    │  ← All configuration
│  🎨  Appearance                  │  ← Theme customizer
│  🔌  Plugins                     │  ← Add-on management
│                                  │
│  ─── STATUS ───                  │
│  🤖  Model Status                │  ← GPU/CPU, model info
│  ❤️  System Health               │  ← Redis, DB, disk
│                                  │
│  ─── MODE ───                    │
│  ⚡ Balanced (CPU)               │
│  🔥 High Performance (GPU+CPU)  │
│                                  │
│  v2.0.0                         │
└──────────────────────────────────┘
```

### Dashboard — Suggestion Review

The main view where you spend most of your time:

```
┌────────────────────────────────────────────────────────────────────────┐
│  Filter Bar                                                            │
│  [Status ▾] [Score ≥ 0.5 ▾] [Type ▾] [Scope ▾] [Search...] [Focus🧘] │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  ✅ SUGGESTION CARD                                    Score: 0.82 │
│  │                                                                    │
│  │  Destination: "How to Set Up a Home Recording Studio"             │
│  │  Host: "Budget Gear Guide for Beginners" (sentence 3)            │
│  │                                                                    │
│  │  "...the most important piece of gear for any                     │
│  │  [home recording studio] setup is a quality audio                 │
│  │  interface that won't break the bank..."                          │
│  │                                                                    │
│  │  Anchor: "home recording studio"   Confidence: Strong             │
│  │                                                                    │
│  │  Scores: Semantic 0.78 │ Keyword 0.85 │ Node 1.0 │ Quality 0.72  │
│  │                                                                    │
│  │  ┌─────────┐  ┌─────────┐  ┌────────┐  ┌─────────┐  ┌────────┐  │
│  │  │ ✅ Approve│  │ ❌ Reject│  │ ✏️ Edit│  │ 👁️ Diff │  │ ⏭️ Skip│  │
│  │  └─────────┘  └─────────┘  └────────┘  └─────────┘  └────────┘  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  Next card...                                                      │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                        │
│  [◀ Page 1 of 12 ▶]    Showing 25 of 287 pending                     │
└────────────────────────────────────────────────────────────────────────┘
```

### Focus Mode (Zen Review)

```
┌────────────────────────────────────────────────────────────────────────┐
│                                                         [Exit Focus ✕] │
│                                                                        │
│                     3 of 47 remaining                                  │
│                     ████████░░░░░░░░░░ 6%                             │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                                                                    │
│  │  DESTINATION                                                       │
│  │  ══════════                                                        │
│  │  "How to Set Up a Home Recording Studio"                          │
│  │  Forum > Music Production > Guides                                │
│  │  👁️ 2,340 views  💬 18 replies  📊 PageRank: 0.034               │
│  │                                                                    │
│  │  ─────────────────────────────────────────                        │
│  │                                                                    │
│  │  HOST SENTENCE                                                     │
│  │  ═════════════                                                     │
│  │  From: "Budget Gear Guide for Beginners"                          │
│  │                                                                    │
│  │  "...the most important piece of gear for any                     │
│  │   ╔══════════════════════╗                                        │
│  │   ║ home recording studio ║ setup is a quality audio              │
│  │   ╚══════════════════════╝                                        │
│  │   interface that won't break the bank..."                         │
│  │                                                                    │
│  │  Anchor: "home recording studio"                                  │
│  │  Score: 0.82 (Semantic 0.78 + Keyword 0.85 + Node 1.0)           │
│  │                                                                    │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                        │
│         [Space] Approve     [R] Reject     [E] Edit     [Esc] Skip   │
│                                                                        │
│  ⚠️ Link already exists? No ✅                                        │
│  ⚠️ Content changed since scan? No ✅                                 │
│  ⚠️ Duplicate anchor? No ✅                                           │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

### Side-by-Side Diff Preview

```
┌────────────────────────────────────────────────────────────────────────┐
│  Diff Preview — "Budget Gear Guide for Beginners"       [Copy ✅] [✕] │
├─────────────────────────────┬──────────────────────────────────────────┤
│  BEFORE (current BBCode)    │  AFTER (with suggested link)            │
│                             │                                          │
│  ...the most important      │  ...the most important                  │
│  piece of gear for any      │  piece of gear for any                  │
│  home recording studio      │  [URL='https://goldmidi.com/           │
│                             │  community/threads/home-               │
│                             │  recording-studio.1234/']              │
│  setup is a quality         │  home recording studio[/URL]           │
│  audio interface...         │  setup is a quality                    │
│                             │  audio interface...                    │
├─────────────────────────────┴──────────────────────────────────────────┤
│  ⚠️ Warning: This post currently has 2 internal links (max 3 allowed) │
│  📋 Copy edited BBCode to clipboard                                   │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 9. ML/NLP Pipeline (Unchanged Core)

### What Migrates Directly

All Python services from V1 move into `backend/apps/pipeline/services/` with minimal changes:

| V1 Service | V2 Location | Changes |
|---|---|---|
| `pipeline.py` | `apps/pipeline/services/pipeline.py` | Use Django ORM instead of raw SQLite |
| `embeddings.py` | `apps/pipeline/services/embeddings.py` | Write to pgvector + .npy cache |
| `distiller.py` | `apps/pipeline/services/distiller.py` | Unchanged |
| `ranker.py` | `apps/pipeline/services/ranker.py` | Read settings from Django ORM |
| `anchor_extractor.py` | `apps/pipeline/services/anchor_extractor.py` | Unchanged |
| `sentence_splitter.py` | `apps/pipeline/services/sentence_splitter.py` | Unchanged |
| `text_cleaner.py` | `apps/pipeline/services/text_cleaner.py` | Unchanged |
| `pagerank.py` | `apps/pipeline/services/pagerank.py` | Read links from Django ORM |
| `velocity.py` | `apps/pipeline/services/velocity.py` | Read metrics from Django ORM |
| `spacy_loader.py` | `apps/pipeline/services/spacy_loader.py` | Unchanged |

### pgvector Integration

The biggest change: embeddings live in PostgreSQL alongside content:

```python
# Using pgvector with Django
from pgvector.django import VectorField, CosineDistance

# Store embedding when generated
content_item.embedding = model.encode(text).tolist()
content_item.save()

# Similarity search — replaces loading entire .npy matrix
similar = ContentItem.objects.annotate(
    distance=CosineDistance('embedding', query_vector)
).order_by('distance')[:50]

# .npy files kept as a PERFORMANCE CACHE for bulk pipeline operations
# pgvector is the source of truth
```

### Performance Strategy (16 GB RAM)

| Operation | Strategy | RAM Usage |
|---|---|---|
| Single similarity lookup | pgvector SQL query | ~0 MB (database handles it) |
| Bulk pipeline run | Load .npy cache into memory | ~200-500 MB (same as V1) |
| Embedding generation | Batch encode, write to both pgvector + .npy | ~500 MB peak |
| Idle state | Nothing in memory | ~0 MB from ML |

---

## 10. Real-Time System (WebSockets + Redis)

### WebSocket Channels

```python
# backend/config/asgi.py
from channels.routing import ProtocolTypeRouter, URLRouter

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": URLRouter([
        path("ws/jobs/", JobProgressConsumer.as_asgi()),
        path("ws/notifications/", NotificationConsumer.as_asgi()),
        path("ws/preview/", LivePreviewConsumer.as_asgi()),
    ]),
})
```

### What Pushes in Real-Time

| Channel | Events | Purpose |
|---|---|---|
| `ws/jobs/` | progress %, stage name, ETA, completion | Live job monitoring |
| `ws/notifications/` | stale alerts, new suggestions, sync completions | Toast notifications |
| `ws/preview/` | Updated diff when editing anchor | Live preview without page reload |

---

## 11. Caching Strategy (Redis)

### What Gets Cached (And For How Long)

| Data | TTL | Why Cache |
|---|---|---|
| Dashboard filter counts | 30 seconds | Avoid COUNT(*) on every filter change |
| Link graph data (D3 JSON) | 5 minutes | Expensive to compute, changes slowly |
| Content item metadata | 2 minutes | Frequently accessed in reviews |
| GSC/GA4 metrics | 1 hour | API data doesn't change rapidly |
| Theme settings | Until changed (invalidate on save) | Prevent DB hit on every page load |
| Pipeline diagnostics summary | 5 minutes | Aggregation queries are expensive |

### What Does NOT Get Cached

| Data | Why |
|---|---|
| Suggestion status | Must be real-time — reviewer needs current state |
| Job progress | Already pushed via WebSocket |
| Stale check results | Must be live — querying XenForo API at review time |
| Duplicate check results | Must be live — querying current links |
| Audit trail | Must reflect actual state |

---

## 12. Theme & Customizer System

### WordPress-Like Customizer

```
┌──────────────────────────────────────────────────────────────┐
│  🎨 Appearance Customizer                          [Save] [✕]│
├──────────────────────────┬───────────────────────────────────┤
│                          │                                   │
│  COLORS                  │  ┌─ Live Preview ──────────────┐  │
│  ├─ Primary: [#1a73e8]   │  │                             │  │
│  ├─ Accent:  [#ea4335]   │  │  (Shows dashboard with      │  │
│  ├─ Background: [#fff]   │  │   changes applied in        │  │
│  ├─ Sidebar: [#f8f9fa]   │  │   real-time)                │  │
│  └─ Text: [#202124]      │  │                             │  │
│                          │  │                             │  │
│  LAYOUT                  │  │                             │  │
│  ├─ Sidebar: [Left ▾]    │  │                             │  │
│  ├─ Density: [Comfortable]│  │                             │  │
│  └─ Cards: [Rounded ▾]   │  │                             │  │
│                          │  │                             │  │
│  TYPOGRAPHY              │  │                             │  │
│  ├─ Font: [Inter ▾]      │  │                             │  │
│  ├─ Size: [14px ▾]       │  │                             │  │
│  └─ Weight: [Regular ▾]  │  │                             │  │
│                          │  │                             │  │
│  PRESETS                 │  │                             │  │
│  ├─ GSC Theme ⭐         │  │                             │  │
│  ├─ Dark Mode 🌙         │  │                             │  │
│  ├─ Ocean Blue 🌊        │  │                             │  │
│  └─ + Save Current...    │  │                             │  │
│                          │  └─────────────────────────────┘  │
└──────────────────────────┴───────────────────────────────────┘
```

### How It Works

```typescript
// frontend/src/app/core/services/theme.service.ts
@Injectable({ providedIn: 'root' })
export class ThemeService {
  // CSS Custom Properties applied to :root
  applyTheme(settings: ThemeSettings): void {
    document.documentElement.style.setProperty('--primary-color', settings.primaryColor);
    document.documentElement.style.setProperty('--accent-color', settings.accentColor);
    document.documentElement.style.setProperty('--bg-color', settings.backgroundColor);
    document.documentElement.style.setProperty('--sidebar-color', settings.sidebarColor);
    document.documentElement.style.setProperty('--text-color', settings.textColor);
    document.documentElement.style.setProperty('--font-family', settings.fontFamily);
    document.documentElement.style.setProperty('--font-size', settings.fontSize);
    document.documentElement.style.setProperty('--border-radius', settings.borderRadius);
    document.documentElement.style.setProperty('--card-shadow', settings.cardShadow);
    // ... more properties
  }
}
```

---

## 13. Plugin / Add-On Architecture

### How Plugins Work

```
Plugin = Django App (backend) + Angular Lazy Module (frontend)
```

**Backend plugin registration:**

```python
# plugins/wordpress-crosslinker/backend/plugin.py

from apps.plugins.registry import PluginBase

class WordPressCrosslinkerPlugin(PluginBase):
    name = "WordPress Cross-Linker"
    slug = "wordpress-crosslinker"
    version = "1.0.0"
    description = "Cross-link between XenForo and WordPress"
    author = "GoldMidi"

    # What this plugin adds
    models = ['WPContent', 'CrossLinkSuggestion']
    api_routes = ['wp-content/', 'cross-suggestions/']
    celery_tasks = ['sync_wordpress', 'generate_cross_suggestions']
    settings_schema = {
        'wp_api_url': {'type': 'url', 'label': 'WordPress API URL'},
        'wp_api_key': {'type': 'secret', 'label': 'API Key'},
    }

    def on_enable(self):
        """Run migrations, register tasks."""
        pass

    def on_disable(self):
        """Deregister tasks, keep data."""
        pass
```

### Plugin Lifecycle

| Action | What Happens | Data Safe? |
|---|---|---|
| **Enable** | Migrations run, tasks registered, routes added | Yes — creates tables |
| **Disable** | Tasks deregistered, routes removed | Yes — data preserved |
| **Uninstall** | Optional: drop tables, remove data | User confirms |
| **Update** | New migrations run, code replaced | Yes — backward compatible |

### First-Party Plugins (Built by You)

| Plugin | Purpose | Status |
|---|---|---|
| `wordpress-crosslinker` | Cross-link XenForo ↔ WordPress (misc.goldmidi.com) | Phase 12 |
| `media-gallery` | XenForo Media Gallery support | Phase 13 |
| `elasticsearch-search` | Replace PostgreSQL FTS with Elasticsearch | Phase 15+ |

---

## 14. API Integrations

### XenForo REST API

```python
# apps/sync/services/xenforo_api.py

class XenForoAPIClient:
    """Read-only XenForo REST API client."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.headers = {'XF-Api-Key': api_key}

    def get_thread(self, thread_id: int) -> dict:
        """Fetch single thread with first post."""
        return self._get(f'/threads/{thread_id}/', params={'with_posts': True})

    def get_threads(self, node_id: int, page: int = 1) -> dict:
        """List threads in a node."""
        return self._get('/threads/', params={'node_id': node_id, 'page': page})

    def get_post(self, post_id: int) -> dict:
        """Fetch single post (for live stale check)."""
        return self._get(f'/posts/{post_id}/')

    def search_threads(self, keywords: str) -> dict:
        """Search threads (for duplicate check)."""
        return self._get('/search/', params={'keywords': keywords, 'search_type': 'thread'})
```

### XenForo Webhooks

```python
# apps/sync/services/webhooks.py

class XenForoWebhookHandler:
    """Handle XenForo webhook events."""

    def handle_thread_created(self, payload: dict):
        """New thread → trigger pipeline for instant suggestions."""
        thread_id = payload['thread_id']
        # Import the new thread
        import_single_thread.delay(thread_id)
        # After import completes, run pipeline targeting this thread
        generate_suggestions_for_thread.delay(thread_id)

    def handle_post_edited(self, payload: dict):
        """Post edited → auto-verify if suggested link was added."""
        post_id = payload['post_id']
        verify_suggestions_for_post.delay(post_id)

    def handle_thread_deleted(self, payload: dict):
        """Thread deleted → mark suggestions stale."""
        thread_id = payload['thread_id']
        mark_suggestions_stale.delay(
            content_id=thread_id,
            content_type='thread',
            reason='Thread deleted on forum'
        )
```

### Google Search Console API

```python
# apps/analytics/services/gsc_client.py

class GSCClient:
    """Google Search Console API with rate limiting."""

    DAILY_QUOTA = 25_000  # GSC daily request limit
    REQUESTS_PER_SECOND = 5  # Safe rate

    def __init__(self, credentials_path: str, site_url: str):
        self.service = build('searchconsole', 'v1', credentials=...)
        self.site_url = site_url

    @rate_limited(calls=5, period=1)  # 5 requests per second
    def get_page_metrics(self, page_url: str, start_date: str, end_date: str) -> dict:
        """Get impressions, clicks, CTR, position for a specific page."""
        request = {
            'startDate': start_date,
            'endDate': end_date,
            'dimensions': ['page', 'query'],
            'dimensionFilterGroups': [{
                'filters': [{'dimension': 'page', 'expression': page_url}]
            }],
            'rowLimit': 100
        }
        return self.service.searchanalytics().query(
            siteUrl=self.site_url, body=request
        ).execute()

    def sync_all_pages(self, content_items: QuerySet, days_back: int = 28):
        """Bulk sync with rate limiting and progress tracking."""
        # Process in batches to stay under daily quota
        for batch in chunked(content_items, 100):
            for item in batch:
                metrics = self.get_page_metrics(item.url, ...)
                SearchMetric.objects.update_or_create(
                    content_item=item,
                    date=today,
                    source='gsc',
                    defaults=metrics
                )
```

### Google Analytics 4 API

```python
# apps/analytics/services/ga4_client.py

class GA4Client:
    """Google Analytics 4 Data API with rate limiting."""

    def __init__(self, credentials_path: str, property_id: str):
        self.client = BetaAnalyticsDataClient(credentials=...)
        self.property_id = property_id

    @rate_limited(calls=10, period=1)
    def get_page_metrics(self, page_path: str, start_date: str, end_date: str) -> dict:
        """Get pageviews, sessions, engagement for a page."""
        request = RunReportRequest(
            property=f'properties/{self.property_id}',
            dimensions=[Dimension(name='pagePath')],
            metrics=[
                Metric(name='screenPageViews'),
                Metric(name='sessions'),
                Metric(name='averageSessionDuration'),
                Metric(name='bounceRate'),
            ],
            dimension_filter=...,
            date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        )
        return self.client.run_report(request=request)
```

### WordPress REST API

```python
# apps/sync/services/wordpress_api.py (Plugin: wordpress-crosslinker)

class WordPressAPIClient:
    """Read-only WordPress REST API client."""

    def __init__(self, base_url: str, auth_token: str = None):
        self.base_url = base_url  # https://misc.goldmidi.com/wp-json/wp/v2

    def get_posts(self, page: int = 1, per_page: int = 100) -> list:
        """List published posts."""
        return self._get('/posts', params={'page': page, 'per_page': per_page, 'status': 'publish'})

    def get_post(self, post_id: int) -> dict:
        """Fetch single post (for stale check)."""
        return self._get(f'/posts/{post_id}')

    def get_categories(self) -> list:
        """List all categories."""
        return self._get('/categories', params={'per_page': 100})
```

---

## 15. Review Experience & Focus Mode

### Keyboard Shortcuts

| Key | Action | Context |
|---|---|---|
| `Space` | Approve current suggestion | Focus Mode & Dashboard |
| `R` | Reject (opens reason picker) | Focus Mode & Dashboard |
| `E` | Edit anchor | Focus Mode & Dashboard |
| `D` | Show diff preview | Focus Mode & Dashboard |
| `Esc` | Skip / close modal | Universal |
| `→` / `←` | Next / previous suggestion | Dashboard |
| `F` | Enter Focus Mode | Dashboard |
| `Ctrl+A` | Select all visible | Dashboard |
| `?` | Show keyboard shortcuts overlay | Universal |

### Live Checks Before Review

When a suggestion card opens in Focus Mode:

1. **Stale Check** — Fetch current post from XenForo API, compare content hash. If changed since last sync, warn: "⚠️ Content has changed since last scan"
2. **Duplicate Check** — Query XenForo API to check if the host post already links to the destination. If yes: "⚠️ Link already exists"
3. **Canonical Check** — Fetch destination URL, check for redirects or canonical tag mismatches
4. **Density Check** — Count existing links in host post. If ≥ 3: "⚠️ Post already has 3+ internal links"

---

## 16. Analytics & Impact Tracking

### GSC/GA4 Sync Schedule (Rate-Limit Aware)

```python
# Celery Beat schedule
CELERY_BEAT_SCHEDULE = {
    'sync-gsc-daily': {
        'task': 'apps.analytics.tasks.sync_gsc_metrics',
        'schedule': crontab(hour=3, minute=0),  # 3 AM daily
        'kwargs': {'days_back': 3},  # Last 3 days (GSC data is delayed)
    },
    'sync-ga4-daily': {
        'task': 'apps.analytics.tasks.sync_ga4_metrics',
        'schedule': crontab(hour=4, minute=0),  # 4 AM daily
        'kwargs': {'days_back': 1},
    },
    'generate-impact-reports': {
        'task': 'apps.analytics.tasks.generate_impact_reports',
        'schedule': crontab(hour=5, minute=0, day_of_week=1),  # Monday 5 AM
    },
}
```

### Before/After Impact Dashboard

```
┌──────────────────────────────────────────────────────────────────┐
│  📈 Impact Reports — Last 30 Days                                │
│                                                                  │
│  Suggestions Applied: 47                                         │
│  Average Position Change: -3.2 (improved by 3 positions)        │
│  Average CTR Change: +12.4%                                      │
│  Total Click Increase: +1,247                                    │
│                                                                  │
│  ┌─ Top Performing Suggestions ─────────────────────────────────┐│
│  │                                                               ││
│  │  1. "Home Recording Studio"                                   ││
│  │     Position: 14.2 → 6.8 (-7.4)  Clicks: 12 → 89 (+641%)  ││
│  │     [D3 chart showing trend line]                            ││
│  │                                                               ││
│  │  2. "Best Budget Audio Interface"                             ││
│  │     Position: 22.1 → 11.3 (-10.8)  Clicks: 3 → 34 (+1033%)││
│  │     [D3 chart showing trend line]                            ││
│  │                                                               ││
│  └───────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ┌─ Least Performing ──────────────────────────────────────────┐ │
│  │  1. "Forum Rules FAQ" — No change detected                  │ │
│  │  2. "Welcome Thread" — Position: 45 → 48 (+3, declined)    │ │
│  └─────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

---

## 17. Link Graph Visualization

### 2D Force-Directed Graph (D3.js)

```
Features:
- Each node = content item (circle size = PageRank score)
- Each edge = existing internal link
- Color = scope/category (auto-grouped)
- Highlight orphans (no connections) in red
- Highlight hubs (many connections) in green
- Click node → show suggestions for that content
- Zoom, pan, drag nodes
- Search/filter by scope, content type
- Export as PNG or SVG
```

### Topic Silo View

```
Forums (Scopes)
├── 🎸 Guitar
│   ├── Thread A ──── Thread B ──── Thread C
│   │                     │
│   │                     └──────── Thread D
│   └── Thread E
│
├── 🎹 Keyboards
│   ├── Thread F ──── Thread G
│   └── Thread H
│
└── ⚠️ Cross-silo links (highlighted in yellow):
    Thread A (Guitar) ──── Thread F (Keyboards)
```

### Link Density Heatmap

```
Content items shown as cells in a grid:
- Green = well-linked (2-3 internal links)
- Yellow = under-linked (1 link)
- Red = orphan (0 links)
- Purple = over-linked (4+ links, "link fatigue" warning)
- Size = PageRank score
```

---

## 18. Anchor Policy Engine

### Rules (Configurable)

| Rule | Default | Purpose |
|---|---|---|
| **Ban generic anchors** | Block: "click here", "read more", "this post", "here" | Prevent SEO-harmful generic links |
| **Max exact-match reuse** | Same anchor used max 3 times across all suggestions | Prevent keyword stuffing |
| **Prefer natural variants** | Penalize exact title matches, boost natural phrasing | More organic link profiles |
| **Max anchor length** | 6 words max | Prevent overly long anchors |
| **Min anchor length** | 1 word min | Allow short anchors |
| **Destination caps** | Max 5 incoming suggestions per destination | Prevent over-promoting one thread |
| **Long-tail preference** | Boost 3-5 word anchors (long-tail keywords) | Better SEO for niche queries |

### How It Works

```python
# apps/pipeline/services/anchor_policy.py

class AnchorPolicyEngine:
    BANNED_ANCHORS = {'click here', 'read more', 'this post', 'here', 'link', 'this'}

    def evaluate(self, anchor: str, destination_id: int) -> PolicyResult:
        violations = []

        # Check banned
        if anchor.lower().strip() in self.BANNED_ANCHORS:
            violations.append('banned_generic_anchor')

        # Check reuse count
        reuse_count = Suggestion.objects.filter(
            anchor_phrase__iexact=anchor,
            status__in=['approved', 'applied', 'verified']
        ).count()
        if reuse_count >= self.max_exact_reuse:
            violations.append('anchor_reuse_exceeded')

        # Check destination caps
        dest_count = Suggestion.objects.filter(
            destination_id=destination_id,
            status__in=['approved', 'applied', 'verified']
        ).count()
        if dest_count >= self.max_destination_suggestions:
            violations.append('destination_cap_exceeded')

        return PolicyResult(
            allowed=len(violations) == 0,
            violations=violations,
            warnings=self._get_warnings(anchor)
        )
```

---

## 19. Audit Trail & Reviewer Scorecards

### Full Audit Trail

Every action is logged:

```
Timeline:
├── 2026-03-23 14:32:01 — Suggestion #abc123 APPROVED
│   └── Anchor: "home recording studio" | Score: 0.82
├── 2026-03-23 14:32:45 — Suggestion #def456 REJECTED
│   └── Reason: "Anchor too generic" | Notes: "Need better phrasing"
├── 2026-03-23 14:33:12 — Suggestion #abc123 ANCHOR EDITED
│   └── Old: "home recording studio" → New: "home recording studio setup"
├── 2026-03-23 15:00:00 — Suggestion #abc123 APPLIED
│   └── Marked as manually applied to live forum
├── 2026-03-24 03:00:00 — Suggestion #abc123 VERIFIED ✅
│   └── Auto-verified: link found in latest sync
└── 2026-03-24 03:00:05 — Setting Changed
    └── embedding_device: "cpu" → "cuda"
```

### Reviewer Scorecard Dashboard

```
┌──────────────────────────────────────────────────────────────┐
│  📊 Reviewer Scorecard — Last 30 Days                        │
│                                                              │
│  Total Reviewed: 287                                         │
│  ├── Approved: 198 (69%)   ████████████████████░░░░░░░░░    │
│  ├── Rejected: 64 (22%)    ██████░░░░░░░░░░░░░░░░░░░░░░    │
│  └── Skipped: 25 (9%)      ██░░░░░░░░░░░░░░░░░░░░░░░░░░    │
│                                                              │
│  Verification Rate: 84% of approved suggestions verified ✅  │
│  Stale Rate: 3% of suggestions went stale before review ⚠️  │
│                                                              │
│  Top Rejection Reasons:                                      │
│  ├── "Anchor too generic" (28 times)                        │
│  ├── "Context mismatch" (15 times)                          │
│  ├── "Content outdated" (12 times)                          │
│  └── "Already manually linked" (9 times)                    │
│                                                              │
│  Avg Review Time: 8.3 seconds per suggestion                │
│  Best Pipeline Run: Run #47 — 91% approval rate             │
└──────────────────────────────────────────────────────────────┘
```

---

## 20. Contextual Linking Strategy (600-Word Window)

### Rule: First 600 Words Only

```python
# apps/pipeline/services/pipeline.py

MAX_HOST_WORDS = 600  # Only scan first 600 words for link insertion

def get_eligible_sentences(content_item: ContentItem) -> QuerySet:
    """Return sentences within the first 600 words only."""
    return content_item.sentences.filter(
        word_position__lte=MAX_HOST_WORDS
    ).order_by('position')
```

### Why 600 Words?

| Reason | Explanation |
|---|---|
| **Reader attention** | Most readers engage with the first half of a post. Links placed later get fewer clicks |
| **SEO value** | Google weights content near the top of the page more heavily |
| **Context quality** | Opening paragraphs set the topic; later paragraphs drift into tangents |
| **Prevents deep-post spam** | Stops the tool from suggesting links in post signatures or closing remarks |

### Maximum 3 Links Per Thread

```python
MAX_LINKS_PER_HOST = 3

def check_link_budget(host_content_id: int) -> int:
    """How many more links can this host accept?"""
    existing = ExistingLink.objects.filter(
        from_content_id=host_content_id
    ).count()
    approved = Suggestion.objects.filter(
        host_id=host_content_id,
        status__in=['approved', 'applied', 'verified']
    ).count()
    used = existing + approved
    return max(0, MAX_LINKS_PER_HOST - used)
```

### Anchor Length Preferences

| Priority | Anchor Type | Example | Score Boost |
|---|---|---|---|
| 1st | Long-tail (3-5 words) | "budget home recording studio" | +0.15 |
| 2nd | Medium (2 words) | "recording studio" | +0.05 |
| 3rd | Short (1 word) | "studio" | +0.00 |
| Blocked | Too long (6+ words) | "the best budget home recording studio guide" | -1.0 (skip) |

---

## 21. Performance Modes (Balanced / High Performance)

### Mode Definitions

| Mode | CPU | GPU | When to Use |
|---|---|---|---|
| **Balanced** | All ML on CPU | GPU idle | Daily review, light pipeline runs, 16 GB RAM |
| **High Performance** | System tasks on CPU | All ML on GPU | Full rebuilds, large pipeline runs, when GPU is free |

### How It Works

```python
# apps/pipeline/services/embeddings.py

class PerformanceMode(Enum):
    BALANCED = "balanced"         # CPU only
    HIGH_PERFORMANCE = "high"     # CPU + GPU

def get_device(mode: PerformanceMode) -> str:
    if mode == PerformanceMode.HIGH_PERFORMANCE:
        if torch.cuda.is_available():
            return "cuda"
    return "cpu"
```

### Switchable in Real-Time

Toggle in the sidebar or settings page. The switch:
1. Updates the setting in the database
2. Sends a WebSocket notification to all connected clients
3. Next pipeline/embedding job uses the new device
4. Does NOT interrupt a running job (applies to next job)

---

## 22. Portability & Deployment

### Docker Compose (Primary Method)

```yaml
# docker-compose.yml
version: '3.9'

services:
  db:
    image: pgvector/pgvector:pg16
    volumes:
      - postgres_data:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: xf_linker
      POSTGRES_USER: linker
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    volumes:
      - ./backend:/app
      - media_data:/app/data
    environment:
      - DATABASE_URL=postgresql://linker:${DB_PASSWORD}@db:5432/xf_linker
      - REDIS_URL=redis://redis:6379/0
      - DJANGO_SETTINGS_MODULE=config.settings.development
    ports:
      - "8000:8000"
    depends_on:
      - db
      - redis
    command: daphne -b 0.0.0.0 -p 8000 config.asgi:application

  celery:
    build:
      context: .
      dockerfile: Dockerfile.backend
    volumes:
      - ./backend:/app
      - media_data:/app/data
    environment:
      - DATABASE_URL=postgresql://linker:${DB_PASSWORD}@db:5432/xf_linker
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - db
      - redis
    command: celery -A config.celery worker -l info --concurrency=2

  celery-beat:
    build:
      context: .
      dockerfile: Dockerfile.backend
    volumes:
      - ./backend:/app
    environment:
      - DATABASE_URL=postgresql://linker:${DB_PASSWORD}@db:5432/xf_linker
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - db
      - redis
    command: celery -A config.celery beat -l info

  frontend:
    build:
      context: .
      dockerfile: Dockerfile.frontend
    ports:
      - "4200:80"
    depends_on:
      - backend

volumes:
  postgres_data:
  media_data:
```

### Migration to Another PC

```
1. git clone the repo on new PC
2. Copy .env file
3. docker-compose up -d
4. pg_dump from old → pg_restore on new (or Docker volume copy)
5. Done — everything runs
```

### Web Server Deployment (Future)

```
Same Docker Compose on a VPS:
- Add nginx reverse proxy
- Add SSL via Let's Encrypt
- Add ALLOWED_HOSTS in Django settings
- Optional: use managed PostgreSQL (Supabase, Neon)
```

---

## 23. Elasticsearch Future Support

### Preparation (Built Now, Used Later)

```python
# apps/content/search_backends.py

class SearchBackend(ABC):
    """Abstract search backend — swap PostgreSQL FTS for Elasticsearch later."""

    @abstractmethod
    def index_content(self, content_item: ContentItem) -> None: ...

    @abstractmethod
    def search(self, query: str, filters: dict) -> list: ...

    @abstractmethod
    def delete(self, content_id: int) -> None: ...


class PostgresSearchBackend(SearchBackend):
    """Default — uses PostgreSQL full-text search."""
    def search(self, query: str, filters: dict) -> list:
        return ContentItem.objects.filter(
            search_vector=SearchQuery(query)
        ).filter(**filters)


class ElasticsearchBackend(SearchBackend):
    """Plugin-provided — uses Elasticsearch."""
    # Implemented in plugins/elasticsearch-search/
    pass
```

### When You Add Elasticsearch

Install the `elasticsearch-search` plugin → it replaces the search backend. No core code changes needed.

---

## 24. Scalability for Large LLMs

### Future-Proofing for GPT-OSS-120B

When you upgrade your PC and want to run large local LLMs:

```python
# apps/pipeline/services/llm_distiller.py (Future)

class LLMDistiller:
    """Use a local LLM for higher-quality distillation."""

    def __init__(self, model_name: str = "gpt-oss-120b"):
        self.model = AutoModelForCausalLM.from_pretrained(model_name)
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)

    def distill(self, title: str, body: str) -> str:
        """LLM-powered distillation replaces heuristic."""
        prompt = f"Summarize the key topics of this forum post in 2-3 sentences:\n\nTitle: {title}\n\nBody: {body[:2000]}"
        return self.model.generate(prompt, max_tokens=200)
```

### Architecture Supports This Because:

| Concern | How V2 Handles It |
|---|---|
| **Model loading time** | Celery workers load models once, process many tasks |
| **GPU memory** | Performance mode switch — explicitly controls GPU usage |
| **Multiple models** | Settings allow switching embedding model + distillation model independently |
| **Batch size** | Configurable — lower for large models, higher for small ones |
| **RAM management** | Celery worker memory limits prevent OOM |

---

## 25. Error Reporting & Diagnostics

### Error Dashboard

```
┌────────────────────────────────────────────────────────────────┐
│  🚨 Errors & Diagnostics                                       │
│                                                                │
│  ┌─ Active Errors ─────────────────────────────────────────┐  │
│  │  ❌ GSC API rate limit exceeded (3 hours ago)            │  │
│  │  ⚠️  SSH connection timeout (5 hours ago)                │  │
│  │  ℹ️  3 suggestions went stale during last sync           │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                │
│  ┌─ Pipeline Diagnostics ──────────────────────────────────┐  │
│  │  Last Run: 287 processed, 23 skipped                    │  │
│  │                                                          │  │
│  │  Skip Reasons:                                           │  │
│  │  ├── No eligible host sentences: 8                      │  │
│  │  ├── Below score threshold: 6                           │  │
│  │  ├── Already linked: 5                                  │  │
│  │  └── Content too short: 4                               │  │
│  │                                                          │  │
│  │  "Why No Suggestion?" Explorer:                         │  │
│  │  [Search content item...                            🔍] │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                │
│  ┌─ SEO Gap Analysis ──────────────────────────────────────┐  │
│  │  Missing Keywords:                                       │  │
│  │  ├── "audio interface" — 12 threads mention it, 0 links │  │
│  │  ├── "MIDI controller" — 8 threads mention it, 1 link   │  │
│  │  └── "studio monitors" — 6 threads mention it, 0 links  │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

---

## 26. Documentation & Tooltips

### In-App Tooltips

Every setting, score, and feature has a tooltip explaining what it does:

```
[?] Semantic Score: How topically similar the host sentence is to the
    destination content. Higher = more relevant. Range: 0.0 to 1.0.
    A score of 0.7+ usually means strong topical alignment.

[?] Velocity Score: How active and recent this content is. Based on
    view/reply growth rate and recency decay. Higher = more active.
    Orphan content (no incoming links) gets a 1.5x boost.

[?] Focus Mode: Review suggestions one at a time with keyboard
    shortcuts. Press Space to approve, R to reject, E to edit,
    Esc to skip. Live checks run automatically before each review.
```

### AI-CONTEXT.md Auto-Update

```python
# Management command: python manage.py update_ai_context
# Runs automatically after every successful job or setting change

class Command(BaseCommand):
    def handle(self, *args, **options):
        context = {
            'project_name': 'XF Internal Linker V2',
            'stack': 'Django + Angular + PostgreSQL + Redis',
            'content_items': ContentItem.objects.count(),
            'pending_suggestions': Suggestion.objects.filter(status='pending').count(),
            'active_plugins': Plugin.objects.filter(is_active=True).values_list('name', flat=True),
            'last_sync': SyncState.objects.latest_sync_time(),
            'current_model': AppSetting.objects.get(key='embedding_model').value,
            'performance_mode': AppSetting.objects.get(key='performance_mode').value,
        }
        # Update AI-CONTEXT.md with current state
        render_ai_context(context)
```

---

## 27. Phased Roadmap

### Overview

| Phase | Name | Duration Estimate | Depends On |
|---|---|---|---|
| **0** | Project Bootstrap | 1 session | Nothing |
| **1** | Django Backend Core | 2-3 sessions | Phase 0 |
| **2** | PostgreSQL Schema & Models | 2-3 sessions | Phase 1 |
| **3** | V1 Data Migration | 1-2 sessions | Phase 2 |
| **4** | ML Pipeline Migration | 2-3 sessions | Phase 3 |
| **5** | Celery & Background Jobs | 1-2 sessions | Phase 4 |
| **6** | Django REST API | 2-3 sessions | Phase 5 |
| **7** | Angular Scaffold & Layout | 2-3 sessions | Phase 6 |
| **8** | Dashboard & Review UI | 3-4 sessions | Phase 7 |
| **9** | WebSocket Integration | 1-2 sessions | Phase 8 |
| **10** | Theme Customizer | 1-2 sessions | Phase 8 |
| **11** | Focus Mode & Diff Preview | 2-3 sessions | Phase 8 |
| **12** | XenForo API & Webhooks | 2-3 sessions | Phase 6 |
| **13** | GSC/GA4 Integration | 2-3 sessions | Phase 12 |
| **14** | Link Graph Visualization | 2-3 sessions | Phase 8 |
| **15** | Analytics & Impact Reports | 2-3 sessions | Phase 13 |
| **16** | Plugin Architecture | 2-3 sessions | Phase 6 |
| **17** | WordPress Cross-Linker Plugin | 2-3 sessions | Phase 16 |
| **18** | Anchor Policy Engine | 1-2 sessions | Phase 8 |
| **19** | Audit Trail & Scorecards | 1-2 sessions | Phase 8 |
| **20** | Docker & Deployment | 1-2 sessions | Phase 9 |
| **21** | Documentation & Polish | 2-3 sessions | Phase 20 |
| **22** | SEO Gap Analysis | 1-2 sessions | Phase 14 |
| **23** | 600-Word Window & Anchor Policy | 1 session | Phase 4 |
| **24** | Redirect/404 Monitor | 1 session | Phase 12 |
| **25** | Elasticsearch Plugin | 2-3 sessions | Phase 16 |

### Phase 0: Project Bootstrap

**What you do (GUI only):**
1. Open GitHub Desktop → Create new repository "xf-internal-linker-v2"
2. Open VS Code → Clone the new repo
3. AI creates initial directory structure, Docker files, and config

**What AI builds:**
- [ ] Directory structure (as specified in Section 5)
- [ ] `docker-compose.yml` with PostgreSQL, Redis
- [ ] `.env.example` with all required environment variables
- [ ] `backend/requirements.txt` with all Python dependencies
- [ ] `backend/config/settings/` with base, development, production, testing
- [ ] `frontend/` scaffolded with Angular CLI
- [ ] `AI-CONTEXT.md` initialized for V2
- [ ] `PROMPTS.md` adapted for V2
- [ ] `README.md` with quickstart guide

**Verification:**
- [ ] `docker-compose up -d` starts PostgreSQL and Redis
- [ ] `python manage.py runserver` shows Django welcome page
- [ ] `ng serve` shows Angular welcome page
- [ ] Both services can communicate

### Phase 1: Django Backend Core

**What AI builds:**
- [ ] Django project with custom user model (future multi-user ready)
- [ ] `apps/core/` with base models, serializers, middleware
- [ ] Django admin configured with django-unfold for beautiful UI
- [ ] Custom admin dashboard with overview stats
- [ ] CORS configuration for Angular dev server
- [ ] Basic health check endpoint (`/api/v1/health/`)
- [ ] Error handling middleware

**Verification:**
- [ ] Django admin accessible at `localhost:8000/admin/`
- [ ] Admin looks beautiful (django-unfold theme)
- [ ] Health check returns 200 OK

### Phase 2: PostgreSQL Schema & Models

**What AI builds:**
- [ ] `apps/content/models.py` — ContentItem, Post, Sentence, ScopeItem
- [ ] `apps/suggestions/models.py` — Suggestion, PipelineRun, PipelineDiagnostic
- [ ] `apps/audit/models.py` — AuditEntry, ReviewerScorecard
- [ ] `apps/analytics/models.py` — SearchMetric, ImpactReport
- [ ] `apps/links/models.py` — ExistingLink, RedirectCheck
- [ ] `apps/themes/models.py` — ThemePreset, ThemeSetting
- [ ] `apps/plugins/models.py` — Plugin, PluginSetting
- [ ] `apps/settings_app/models.py` — AppSetting
- [ ] pgvector extension enabled and VectorField on ContentItem and Sentence
- [ ] All Django admin registrations with fieldsets and filters
- [ ] Initial data migration (default settings, default theme)

**Verification:**
- [ ] `python manage.py migrate` runs cleanly
- [ ] All models visible in Django admin
- [ ] pgvector extension active (`SELECT * FROM pg_extension WHERE extname = 'vector'`)

### Phase 3: V1 Data Migration

**What AI builds:**
- [ ] `scripts/migrate_v1_to_v2.py` — reads V1 SQLite, writes to V2 PostgreSQL
- [ ] Migrates: content_items, posts, sentences, existing_links, suggestions, settings
- [ ] Converts .npy embeddings to pgvector columns
- [ ] Preserves all suggestion history and statuses
- [ ] Validation report showing record counts before/after

**Verification:**
- [ ] All V1 data accessible in V2 Django admin
- [ ] Content counts match between V1 and V2
- [ ] Embeddings stored in pgvector columns

### Phase 4: ML Pipeline Migration

**What AI builds:**
- [ ] `apps/pipeline/services/` — all V1 services migrated
- [ ] ORM queries replace raw SQLite queries
- [ ] pgvector similarity search replaces .npy bulk loading (for single lookups)
- [ ] .npy cache generation for bulk pipeline operations
- [ ] 600-word window enforcement in sentence filtering
- [ ] Max 3 links per host enforcement
- [ ] Unit tests for all migrated services

**Verification:**
- [ ] Pipeline can generate suggestions from migrated data
- [ ] Scores match V1 output (within floating-point tolerance)
- [ ] 600-word window correctly limits host sentences
- [ ] 3-link cap enforced

### Phase 5: Celery & Background Jobs

**What AI builds:**
- [ ] `config/celery.py` — Celery app configuration
- [ ] Task definitions for: sync, import, embeddings, pipeline, verification, stale check
- [ ] Celery Beat schedule for periodic tasks
- [ ] Job model and API for tracking task status
- [ ] WebSocket consumer for real-time job progress
- [ ] Graceful shutdown — tasks complete before worker stops

**Verification:**
- [ ] `celery -A config.celery worker` starts successfully
- [ ] Tasks execute and report progress
- [ ] WebSocket pushes progress to browser
- [ ] App completely shuts down when stopped (no background processes linger)

### Phase 6: Django REST API

**What AI builds:**
- [ ] All API endpoints listed in Section 7
- [ ] DRF serializers with proper validation
- [ ] ViewSets with filtering, pagination, ordering
- [ ] OpenAPI schema auto-generation (drf-spectacular)
- [ ] API documentation at `/api/docs/`

**Verification:**
- [ ] All endpoints return correct JSON
- [ ] Pagination works with page_size parameter
- [ ] Filtering works (status, score, content_type)
- [ ] API docs browsable at `/api/docs/`

### Phase 7: Angular Scaffold & Layout

**What AI builds:**
- [ ] Angular project with Material theme configured
- [ ] App shell: sidebar, header, breadcrumb, footer
- [ ] Routing with lazy-loaded feature modules
- [ ] Core services: API client, WebSocket, theme, notifications
- [ ] HTTP interceptors for error handling and loading states
- [ ] Empty state components (for pages with no data)

**Verification:**
- [ ] App loads with sidebar navigation
- [ ] Routes navigate between empty feature pages
- [ ] Angular Material components render correctly
- [ ] Theme variables apply from CSS custom properties

### Phase 8: Dashboard & Review UI

**What AI builds:**
- [ ] Suggestion list with card-based layout
- [ ] Filter bar (status, score, type, scope, search)
- [ ] Suggestion detail view with all scores
- [ ] Approve, reject, edit, skip actions
- [ ] Batch actions (select multiple → bulk approve/reject)
- [ ] Keyboard shortcuts
- [ ] Loading states, empty states, error states
- [ ] Pagination controls

**Verification:**
- [ ] Suggestions display with all metadata
- [ ] Filters narrow results correctly
- [ ] Approve/reject updates status in real-time
- [ ] Keyboard shortcuts work
- [ ] Batch actions process multiple suggestions

### Phases 9-25: See individual phase descriptions above

Each phase follows the same pattern:
1. AI builds backend (Django models, views, tasks)
2. AI builds frontend (Angular components, services)
3. Verification checklist confirms functionality
4. AI-CONTEXT.md updated
5. Commit and push via GitHub Desktop

---

## 28. GUI-Only Developer Workflow

### Tools You Need (All GUI, No Command Line)

| Tool | Purpose | Download |
|---|---|---|
| **VS Code** | Code editor | https://code.visualstudio.com |
| **GitHub Desktop** | Git management (commit, push, pull) | https://desktop.github.com |
| **Docker Desktop** | Run PostgreSQL, Redis, Django, Angular | https://docker.com/products/docker-desktop |
| **pgAdmin 4** | PostgreSQL database management | https://pgadmin.org |
| **Chrome/Edge** | Browse the app and Django admin | Already installed |
| **Postman** (optional) | Test API endpoints manually | https://postman.com |

### Your Daily Workflow

```
Morning:
1. Open Docker Desktop → click ▶️ Start on "xf-internal-linker-v2"
2. Open Chrome → go to localhost:4200 (Angular app)
3. Review suggestions in dashboard, manage jobs, check analytics

Working with AI:
1. Open VS Code → the project is already there
2. Open Claude Code / Codex / Antigravity terminal in VS Code
3. AI reads AI-CONTEXT.md, makes changes, runs tests
4. Open GitHub Desktop → Review changes → Commit → Push

Evening:
1. Close Chrome tab
2. Open Docker Desktop → click ⏹ Stop on "xf-internal-linker-v2"
3. Everything shuts down — no background processes running
```

### How GitHub Desktop Works For You

```
┌──────────────────────────────────────────────────────────────┐
│  GitHub Desktop                                              │
│                                                              │
│  Changes (3 files)                                           │
│  ├── ✅ backend/apps/pipeline/services/ranker.py            │
│  ├── ✅ frontend/src/app/features/dashboard/dashboard.ts    │
│  └── ✅ AI-CONTEXT.md                                       │
│                                                              │
│  Summary: [Fix anchor scoring for long-tail keywords     ]  │
│  Description: [Updated ranker.py to boost 3-5 word       ]  │
│               [anchors and added display in dashboard     ]  │
│                                                              │
│  [Commit to main]                                           │
│  [Push origin]                                               │
└──────────────────────────────────────────────────────────────┘
```

### When Things Go Wrong (Regression Protection)

```
1. AI runs tests after every change:
   - Backend: pytest (Django tests)
   - Frontend: ng test (Angular tests)
   - If tests fail → AI fixes before committing

2. GitHub Desktop shows you EXACTLY what changed:
   - Green lines = added
   - Red lines = removed
   - You can un-check files you don't want to commit

3. You can always revert:
   - GitHub Desktop → History → right-click → "Revert this commit"
   - Your code goes back to before the change

4. Docker volumes protect your data:
   - Even if you delete the code, your database persists
   - pg_dump creates backups you can restore anytime
```

---

## 29. Prompts for AI-Assisted Development

### Error Checking Prompt

```text
Read `AI-CONTEXT.md` first, then inspect the current repo state.

Check for:
1. Python errors: run `python manage.py check --deploy`
2. Migration issues: run `python manage.py showmigrations`
3. TypeScript errors: run `ng build --configuration=production`
4. Test failures: run `pytest` and `ng test --no-watch`
5. Dependency conflicts: check requirements.txt and package.json
6. Docker health: verify all services are running

Report all errors with file references and suggested fixes.
Do not fix anything until I confirm.
```

### Update/Upgrade Prompt

```text
Read `AI-CONTEXT.md` first, then inspect the current repo state.

Check for:
1. Outdated Python packages: pip list --outdated
2. Outdated npm packages: npm outdated
3. Django security advisories
4. Angular version updates

For each update:
- State the current version and available version
- Assess risk level (safe / moderate / risky)
- Recommend whether to update now or defer

Do not update anything until I confirm.
```

### New Feature Request Prompt

```text
Read `AI-CONTEXT.md` first, then inspect the current repo state.

I want to add: [describe feature]

Before coding:
1. Identify which Django apps this touches
2. Identify which Angular components this touches
3. List new models, serializers, views needed
4. List new Angular components, services needed
5. Assess impact on existing features
6. Estimate effort (small / medium / large)
7. Suggest the smallest first slice

Do not code until I confirm the plan.
```

### V1 Prompts (Adapted for V2)

All V1 prompts from `PROMPTS.md` remain valid with these changes:
- Replace "Flask" with "Django"
- Replace "Jinja/HTMX/Alpine" with "Angular"
- Replace "SQLite" with "PostgreSQL"
- Replace "threading.Thread" with "Celery"
- Replace "SSE" with "WebSocket"

---

## 30. Non-Negotiable Guardrails

### Product / Workflow
- GUI-first always. Daily use happens in the browser, not CLI.
- Manual review remains in the loop. Tool suggests; human decides.
- Up to one best suggestion per destination thread per pipeline run.
- Maximum 3 internal link suggestions per host thread.
- The tool NEVER writes to XenForo MySQL or WordPress MySQL.
- Read-only API access only. No POST/PUT/DELETE to forum or blog APIs.

### Architecture
- Django + DRF for backend. Angular for frontend.
- PostgreSQL + pgvector for all persistent data.
- Redis for caching, Celery broker, and WebSocket channel layer.
- Celery for all background tasks. No inline heavy processing.
- WebSockets for real-time updates. No HTTP polling.
- Docker Compose for deployment. Must work with `docker-compose up`.
- Plugin system must support enable/disable without breaking core.

### ML / Ranking
- Destination representation: title + distilled body text.
- Host selection: sentence-level body text within first 600 words.
- Hybrid scoring: semantic + keyword + node affinity + quality + PageRank + velocity.
- Anchor policy engine enforces quality anchors (no generic, no spam).
- pgvector is source of truth for embeddings. .npy files are caches.

### Data Safety
- Export-then-import is the primary data path.
- XenForo REST API is read-only (GET requests only).
- WordPress REST API is read-only (GET requests only).
- All suggestion history, audit trails, and verification records are preserved.
- Database backups before any migration or major change.

### Git / Collaboration
- Multi-AI handoff via AI-CONTEXT.md (read first, update last).
- One narrow slice per AI session.
- Safe automatic commit/push when tests pass.
- Never force-push, rewrite history, or commit secrets.

### Performance / Resources
- App must completely shut down when Docker containers stop.
- No lingering background processes when not in use.
- Balanced mode (CPU only) as default for 16 GB RAM.
- High Performance mode (GPU) as opt-in.
- Redis cache TTLs prevent stale data without blocking live results.

---

## Appendix A: Complete Dependency List

### Python (backend/requirements.txt)

```
# Django
Django>=5.0,<6.0
djangorestframework>=3.15
django-cors-headers>=4.3
django-filter>=24.0
drf-spectacular>=0.27             # OpenAPI docs
django-unfold>=0.30               # Beautiful admin theme

# Database
psycopg[binary]>=3.1              # PostgreSQL driver
pgvector>=0.3                     # pgvector Django integration

# Async / WebSocket
channels>=4.0
channels-redis>=4.2
daphne>=4.1

# Background Jobs
celery>=5.4
redis>=5.0

# ML / NLP
sentence-transformers>=3.0
spacy>=3.7
torch>=2.0
numpy>=2.0
scipy>=1.12

# Google APIs
google-api-python-client>=2.100
google-auth>=2.25
google-auth-oauthlib>=1.2

# SSH (legacy sync fallback)
paramiko>=3.4

# Utilities
python-dotenv>=1.0
tqdm>=4.60
requests>=2.31
```

### Node.js (frontend/package.json)

```json
{
  "dependencies": {
    "@angular/core": "^19.0.0",
    "@angular/material": "^19.0.0",
    "@angular/cdk": "^19.0.0",
    "d3": "^7.9.0",
    "monaco-editor": "^0.45.0",
    "rxjs": "^7.8.0"
  }
}
```

---

## Appendix B: Environment Variables

```env
# .env.example

# Django
DJANGO_SECRET_KEY=change-me-to-a-random-string
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

# Database
DATABASE_URL=postgresql://linker:your-password@localhost:5432/xf_linker
DB_PASSWORD=your-password

# Redis
REDIS_URL=redis://localhost:6379/0

# XenForo API
XF_API_URL=https://goldmidi.com/community/api
XF_API_KEY=your-xenforo-api-key

# WordPress API
WP_API_URL=https://misc.goldmidi.com/wp-json/wp/v2

# Google Search Console
GSC_CREDENTIALS_PATH=./data/gsc-credentials.json
GSC_SITE_URL=https://goldmidi.com

# Google Analytics 4
GA4_CREDENTIALS_PATH=./data/ga4-credentials.json
GA4_PROPERTY_ID=your-ga4-property-id

# SSH (legacy fallback)
SSH_HOST=your-server.com
SSH_USER=your-user
SSH_AUTH_MODE=agent
```
