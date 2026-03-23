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
- Python 3.12+
- Django 5.x + Django REST Framework
- PostgreSQL 16+ with pgvector
- Redis 7+ (cache, Celery broker, WebSocket channel layer)
- Celery 5.x (background tasks)
- Django Channels 4.x + Daphne (WebSockets)
- sentence-transformers, spaCy, PyTorch (ML/NLP — same as V1)

### Frontend
- Angular 19 + Angular Material
- D3.js (visualizations)
- Monaco Editor (diff previews)
- TypeScript

### Infrastructure
- Docker + Docker Compose
- GitHub + GitHub Desktop (GUI-first Git workflow)

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
- pgvector is source of truth. .npy files are performance caches.

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
- High Performance mode (GPU + CPU) is opt-in.
- Redis cache TTLs prevent stale data without blocking live results.

## Current Phase

**Phase:** 0 — Project Bootstrap
**Status:** Master plan written, directory created, not yet scaffolded

## What Is Complete
- [x] V2 Master Plan written (docs/v2-master-plan.md)
- [x] AI-CONTEXT.md initialized
- [x] PROMPTS.md created
- [x] Project directory created

## What Is Next
- [ ] Phase 0: Initialize git repo, create Docker Compose, scaffold Django project, scaffold Angular project
- [ ] Phase 1: Django backend core (admin, settings, health check)
- [ ] Phase 2: PostgreSQL schema and models with pgvector

## Migration Notes

V1 → V2 migration script needed at Phase 3. The V1 codebase at `../xf-internal-linker/` contains:
- 13 SQLite tables (schema version 15)
- 20 Python service files (6,553 lines)
- 6 route files (2,459 lines)
- 34 test files (485+ tests)
- .npy embedding files in data/

All V1 ML services (pipeline.py, embeddings.py, distiller.py, ranker.py, etc.) migrate to `backend/apps/pipeline/services/` with Django ORM replacing raw SQLite queries.
