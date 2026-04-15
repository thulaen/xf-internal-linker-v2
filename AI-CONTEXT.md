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

## Session Gate — Every AI, Every Session

This is the single source of truth for what every AI must read, update, and check. CLAUDE.md and AGENTS.md point here. Do not duplicate these rules elsewhere.

### MUST READ before any code changes

| Order | Document | When |
|-------|----------|------|
| 1 | `AI-CONTEXT.md` (this file) | Always — project state, phase ledger, session notes |
| 2 | `docs/reports/REPORT-REGISTRY.md` | Always — check for open findings in your work area |
| 3 | `FEATURE-REQUESTS.md` | Always — backlog status, what's done, what's pending |
| 4 | `docs/BUSINESS-LOGIC-CHECKLIST.md` | If touching ranking, scoring, attribution, import, or reranking |
| 5 | Language-specific rules file for your work area | If touching that language's code |
| 6 | `AGENTS.md` § Code Quality Mandate | Always — before writing any code |

Language-specific rules files:
- `frontend/FRONTEND-RULES.md` — before any frontend work
- `backend/PYTHON-RULES.md` — before any Python backend work
- `backend/extensions/CPP-RULES.md` — before any C++ work

### MUST UPDATE after work is done

| Order | Document | When |
|-------|----------|------|
| 1 | `AI-CONTEXT.md` — Current Session Note | Always |
| 2 | `AI-CONTEXT.md` — Execution Ledger + Dashboard | If a phase was completed |
| 3 | `FEATURE-REQUESTS.md` — FR status | If an FR was completed or partially completed |
| 4 | `docs/reports/REPORT-REGISTRY.md` | If you found a new issue, created a report, or resolved a finding |

### MUST LOG issues discovered during work

If you find any bug, performance bottleneck, logic flaw, missing validation, or code smell during your session — even if it's outside your current task scope — add it to `docs/reports/REPORT-REGISTRY.md` as an individual issue entry. Don't just ignore it and move on. Future AIs will see it and can fix it.

### MUST TELL THE USER IN CHAT about relevant report-registry findings

If `docs/reports/REPORT-REGISTRY.md` contains an `OPEN` or reopened finding that overlaps with the area you are about to touch, you must say so to the user in chat before writing code. Use plain English. Do not rely only on `AI-CONTEXT.md`, handoff notes, or silent compliance with the registry.

Silence is forbidden. An AI must never notice a relevant open or reopened finding and continue working without telling the user in chat first.

If you decide not to fix that finding in the current session, you must do both:
- tell the user in chat that you are skipping it and why
- record the same justification in the Current Session Note in `AI-CONTEXT.md`

### MUST CHECK for forward clashes (before starting work)

1. Read the next 3 queued phases in the Execution Ledger
2. Search `FEATURE-REQUESTS.md` for pending FRs that touch the same models, services, or signals
3. Search `docs/specs/` for specs referencing the same code paths
4. If your changes will constrain, break, or complicate any future work — STOP and tell the user before proceeding

## Tech Stack

### Backend
- Python 3.12 target runtime
- Django 5.2 LTS + DRF
- PostgreSQL 17 + pgvector
- Redis 7.4
- Celery 5.4 + Celery Beat
- Django Channels 4.2 + Daphne
- nomic-ai/nomic-embed-text-v1.5 with 768 dimensions
- Existing ML_PERFORMANCE_MODE behavior still supports CPU-safe and GPU-capable execution
- Roadmap libraries: `google-api-python-client`, `pandas`, `statsmodels`, `networkx`

### Frontend
- Node.js 22 LTS target runtime
- Angular 20 + Angular Material 20
- TypeScript 5.8
- SCSS with theme tokens in `frontend/src/styles/default-theme.scss`
- Roadmap libraries: `ngx-monaco-editor-v2`, `three`, `ngx-charts`

### Engine
- **Hybrid Engine**: Python (Django/Celery) orchestration with hot-path C++ (pybind11) acceleration.



- Status: Phase 36 / FR-035 (Link Freshness & Churn Velocity Timeline) is the latest completed phase.
- Active target for the next session: Phase 37 / FR-020 (Zero-Downtime Model Switching)
- Current continuity state: 31 FRs are complete and code-verified as of 2026-04-08. See Project Status Dashboard below for the full breakdown.
- Verification completed (2026-04-12):
  - `python backend/manage.py test` — 195 tests pass
  - C# runtime decommissioned; all services migrated to native Python/C++.
  - `ng test` — 22 frontend tests pass
  - `ng build --configuration=production` — clean build
  - Pre-push CI: all gates passed

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
- **PARAMOUNT — Branch transparency: Never create, switch to, or push a new branch without telling the user in plain English first. Work done on a branch does not appear on `master` until merged. If the user did not ask for a branch, stay on `master`. Silence is forbidden.**
- If verification passes and the slice is safe, commit and push it in the same session so the next AI starts from a cleaner base. **This is mandatory: every session MUST automatically clean the tree (stage and commit) and push changes without rollbacks or regressions. No rollbacks unless sanity checks pass. Session-type gate: if backend or frontend application code changed, `docker-compose build` must succeed before any commit is allowed; if only documentation or configuration files changed, skip the build step and state that plainly in the commit message. If `docker-compose build` fails on a code-change session, do not commit — leave a Current Session Note in AI-CONTEXT.md describing the failure and stop.**
- If verification cannot run, say that plainly in the handoff note and do not pretend the tree is safe.
- All backend sessions must follow the migration/prune policy in `AGENTS.md`.

## User Communication Preference

- The user is not a developer and prefers plain-English, layman's-terms explanations by default.
- Default communication rule: AI should talk to the user in plain English and explain things like they are five.
- Avoid jargon unless it is necessary. If you must use jargon, explain it immediately in simple language.

### UI / Theming / Global Mandate
- **No New Themes**: Never create a new CSS/SCSS theme file.
- **Zero Local Overrides**: Forbidden to use `::ng-deep` or local SCSS for Material/third-party elements.
- **Global Abstraction**: Move structural overrides to `src/styles/themes/` and use utility classes (e.g., `.ga4-standard-field`).
- **Default Theme Only**: All styling must use or extend `frontend/src/styles/default-theme.scss`. This applies to ALL AI models without exception.

### Visual Design Principles (User-First Design)
- **Readability is Non-Negotiable**: Prioritize high-contrast text and clean, neutral backgrounds. Avoid dark, vibrant gradients for large headers (e.g., deep blue gradients with white text) as they are physically straining to read and feel overbearing.
- **Subtle Professionalism**: Use soft grays, thin borders (1px solid var(--color-border)), and ample whitespace. "Premium" means refined and easy to use, not "loud" or "flashy."
- **Accessibility**: Ensure all text meets WCAG contrast standards. When in doubt, black text on a white/light-gray background is the gold standard.
- **User-Centric Spacing**: Ensure data visualizations, tables, and metrics have clear labels and enough breathing room. Never allow text to "jumble" or overlap.
- **Consistency**: Stick to Material Design patterns and existing `default-theme.scss` variables.

- When explaining blockers, risks, test results, or architecture, lead with the simple version first.
- Avoid unnecessary jargon; if a technical term matters, define it briefly in the same reply.
- Keep answers simple, direct, and practical.
- Use examples instead of jargon when possible.
- **Universal Smart Navigation**: Every UI section must have a unique `id`. Internal links must use `fragment` deep-linking. Hidden content (tabs) must auto-open.
- **User Friendliness is Paramount**: Always prioritize the operator's experience. Guide them to the exact setting or data point they need.
- **Strict Theme Rule**: Do not create new themes. `default-theme.scss` is the only theme allowed. This applies to all AI models.
- Do not assume deep framework or infrastructure knowledge.

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
- Phase 15 / `FR-012`: separate click-distance structural prior scoring, settings, diagnostics, review exposure, and recalculation task implemented from `docs/specs/fr012-click-distance-structural-prior.md`
- Phase 16 / `FR-013`: post-ranking Explore/Exploit reranker with Bayesian smoothing and UCB1 exploration.
- Phase 17 / `FR-014`: near-duplicate destination clustering with soft suppression and manual recalculation.
- Phase 20 / `FR-017`: GSC Search Outcome Attribution — OAuth, impact engine, sync, Search Impact tab with scatter plot and cohort analysis
- Phase 21 / `FR-018`: Auto-Tuned Ranking Weights — native Python L-BFGS optimization, RankingChallenger champion/challenger model
- Phase 22 / `FR-019`: Operator Alerts, Notification Center & Desktop Attention Signals
- Phase 24 / `FR-021`: Graph-Based Link Candidate Generation (Pixie Random Walk) — GraphCandidateService.cs, graph walk diagnostics
- Phase 25 / `FR-022`: Data Source & System Health Check Dashboard — health component, health services, health models
- Phase 27 / `FR-024`: TikTok Read-Through Rate — Engagement Signal (sixth value model slot)
- Phase 28 / `FR-025`: Session Co-Occurrence Collaborative Filtering — full cooccurrence Django app
- Phase 29 / `FR-026`: Authentication & Login Status UI — login component, auth guard, route protection
- Phase 30 / `FR-028`: Algorithm Weight Diagnostics Tab — diagnostics component, weight-diagnostics-card
- Phase 31 / `FR-029`: GPU Embedding Pipeline — fp16 inference, HIGH_PERFORMANCE mode, CUDA detection
- Phase 32 / `FR-030`: FAISS-GPU Vector Similarity Search — faiss_index.py with GPU support
- Phase 33 / `FR-031`: Interactive D3.js Force-Directed Link Graph — D3 force simulation, zoom, SimNode/SimLink
- Phase 34 / `FR-032`: Automated Orphan & Low-Authority Page Identification — orphan audit endpoints, CSV export, D3 red nodes
- Phase 35 / `FR-033`: Internal PageRank Heatmap — weighted_pagerank.py, heatmapMode toggle, pagerank endpoint
- Phase 36 / `FR-035`: Link Freshness & Churn Velocity Timeline — link_freshness.py, velocity.py, LinkFreshnessEdge model
- **Analytics Groundwork**: Content value scoring and FR-018 auto-weight tuning now implemented as native Python tasks. Charts powered by D3.js in Angular (FR-016).

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
| 15 | FR-012 | Complete | Click-Distance Structural Prior shipped with separate backend scoring, settings/snapshot wiring, review/settings exposure, and unit verification |
| 16 | FR-013 | Complete | Feedback-Driven Explore/Exploit Reranking |
| 17 | FR-014 | Complete | Near-Duplicate Destination Clustering |
| 18 | FR-015 | Complete | Final Slate Diversity Reranking |
| 19 | FR-016 | Complete | GA4 + Matomo settings, browser-bridge, sync plumbing, health reporting, and interactive Chart.js visualizations (funnel, trend, versions, breakdowns) are landed. |
| 20 | FR-017 | Complete | GSC Search Outcome Attribution & Delayed Reward Signals |
| 21 | FR-018 | Complete | Auto-Tuned Ranking Weights & Safe Dated Model Promotion |
| 22 | FR-019 | Complete | Operator Alerts, Notification Center & Desktop Attention Signals |
| 23 | FR-020 | Queued | Zero-Downtime Model Switching, Hot Swap & Runtime Registry (Heavy ML models postponed) |
| 24 | FR-021 | Complete | Graph-Based Link Candidate Generation (Pixie Random Walk) |
| 25 | FR-022 | Complete | Data Source & System Health Check Dashboard |
| 26 | FR-023 | Complete | Reddit Hot Decay, Wilson Score CTR Confidence & Traffic Spike Alerts |
| 27 | FR-024 | Complete | TikTok Read-Through Rate — Engagement Signal (sixth value model slot) |
| 28 | FR-025 | Complete | Session Co-Occurrence Collaborative Filtering & Behavioral Hub Clustering |
| 29 | FR-026 | Complete | Authentication & Login Status UI |
| 30 | FR-028 | Complete | Algorithm Weight Diagnostics Tab |
| 31 | FR-029 | Complete | GPU Embedding Pipeline (fp16, HIGH_PERFORMANCE mode) |
| 32 | FR-030 | Complete | FAISS-GPU Vector Similarity Search |
| 33 | FR-031 | Complete | Interactive D3.js Force-Directed Link Graph |
| 34 | FR-032 | Complete | Automated Orphan & Low-Authority Page Identification |
| 35 | FR-033 | Complete | Internal PageRank (Structural Equity) Heatmap |
| 36 | FR-035 | Complete | Link Freshness & Churn Velocity Timeline |

- Next exact target: Phase 37 / `FR-020 - Zero-Downtime Model Switching, Hot Swap & Runtime Registry`
- Current continuity state: 31 FRs are complete and code-verified as of 2026-04-08.
- Scope reminder: do not hide FR-012 structural evidence inside FR-011 or later reranking phases
- Required continuity rule: keep FR IDs and phase numbers explicitly cross-referenced
- Future queued backlog phases beyond Phase 37 continue in `FEATURE-REQUESTS.md`.

## Project Status Dashboard

Last verified against code: 2026-04-08

| Category            | Done | Partial | Pending | Cancelled | Total |
|---------------------|------|---------|---------|-----------|-------|
| Feature Requests    |   31 |       5 |      61 |         1 |    98 |
| (Note: FR-023 is complete in the Execution Ledger but has no separate FEATURE-REQUESTS.md entry — it was part of Phase 26)
| C++ META extensions |    0 |       0 |      36 |         0 |    36 |
| C++ OPT extensions  |    0 |       0 |      92 |         0 |    92 |
| **All work items**  | **31** | **5** | **189** | **1** | **226** |

**Completed FRs (31):**
FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-007, FR-008, FR-009, FR-010,
FR-011, FR-012, FR-013, FR-014, FR-015, FR-016, FR-017, FR-018, FR-019, FR-021,
FR-022, FR-024, FR-025, FR-026, FR-028, FR-029, FR-030, FR-031, FR-032,
FR-033, FR-035
(Plus FR-023 which is complete in the Execution Ledger but has no separate FEATURE-REQUESTS.md entry)

**Partial (5 — scaffolding exists, core logic missing):**
- FR-034: link parser and context scoring refs exist, audit dashboard/trail UI missing
- FR-037: silo tracking (_same_silo) exists, leakage map visualization component missing
- FR-040: config keys in migration 0019 exist, ContentItem field and scoring service missing
- FR-042: config keys in migration 0019 exist, score field and scoring logic missing
- FR-044: config keys in migration 0019 exist, score field and analytics aggregation missing

**Pending FRs (60):**
FR-020, FR-036, FR-038, FR-039, FR-041, FR-043, FR-045, FR-046, FR-047, FR-048,
FR-049, FR-050, FR-051, FR-052, FR-053, FR-054, FR-055, FR-056, FR-057, FR-058,
FR-059, FR-060, FR-061, FR-062, FR-063, FR-064, FR-065, FR-066, FR-067, FR-068,
FR-069, FR-070, FR-071, FR-072, FR-073, FR-074, FR-075, FR-076, FR-077, FR-078,
FR-079, FR-080, FR-081, FR-082, FR-083, FR-084, FR-085, FR-086, FR-087, FR-088,
FR-089, FR-090, FR-091, FR-092, FR-093, FR-094, FR-095, FR-096, FR-097, FR-098

**C++ META extensions (36 — all pending):**
meta-04 through meta-39. Full specs in `docs/specs/meta-*.md`.

**C++ OPT extensions (92 — all pending):**
opt-01 through opt-92. Full specs in `docs/specs/opt-*.md`.
OPT-73 to OPT-84: Google C++ library integrations (Abseil, Highway, FarmHash, Google Benchmark).
OPT-85 to OPT-89: New Python C++ extensions (bbcclean, cooccur_matrix, link_reconcile, phrase_inventory, pipeline_accel).
OPT-90 to OPT-92: New native interop extensions (pixie_walk, dom_extract, bayes_attrib).

**Known gaps in completed work:**
- FR-032: deep-linked discovery (click depth > 5) deferred to Phase 2

**Cancelled:** FR-027 (R Tidyverse Upgrade); C# runtime decommissioned 2026-04-12.

## Spec Standards for All Feature Phases

Every phase that introduces new functionality or a feature request (FR) requires a dedicated spec pass before any implementation pass.

- **Mandatory Web Research**: Before writing a spec or code for a feature request, the AI MUST search the web (including patent databases, academic papers, and official documentation) to find the most accurate math and algorithms. This ensures the implementation is based on a "source of truth" and is not "half-baked."
- Write the spec to `docs/specs/fr0XX-<slug>.md` before touching implementation code.
- The spec must include a source summary, a math-fidelity note, a full implementation spec, and a test plan. Use `docs/specs/fr006-weighted-link-graph.md` as the quality model.
- **Ranking Performance Rule**: For `FR-015` and any later feature that changes ranking, reranking, candidate scoring, candidate retrieval, or another hot ranking loop, the spec must plan a C++ implementation for the hot inner loop and a behavior-matching Python fallback. C++ is the default execution path for ranking hot loops; Python exists only as the safety fallback when the extension is unavailable or unsafe to use.
- **Ranking Fallback Rule**: Every such ranking spec must name the Python twin, the `HAS_CPP_EXT`-style gate, the correctness test that compares Python and C++ outputs, and the fallback proof that the feature still works when the compiled module is missing.
- **Ranking Speed Visibility Rule**: Every such ranking spec must also define a plain-English diagnostic or status field that explains why the C++ speed path is not active or not helping enough, for example: not compiled, import failed, disabled by setting, unsupported inputs, below serial/parallel threshold, or no material speedup seen in benchmark checks.
- **Ranking Dashboard Rule**: That C++ status must appear on the operator-facing dashboard or diagnostics UI, not only in logs or hidden JSON. Operators must be able to see whether the C++ path is active, whether Python fallback is being used, and whether the speed path is actually helping.
- FR-007 (freshness): source the math from `US8407231B2`. Do not reuse freshness signals from FR-006's weighted edge features - the boundary is intentional.
- FR-008 (phrase matching): source the math from `US7536408B2`. Do not reuse phrase or surrounding-text signals from FR-006's edge features - the boundary is intentional.
- FR-016 to FR-020 also require a spec/design pass before implementation because they change telemetry schemas, attribution logic, alerting behavior, and model-promotion/runtime safety. Those phases must define neutral fallbacks, rollback paths, and regression gates before any code lands.
- All feature requests follow the same two-pass pattern: spec first, implement second, each in its own session.

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
2. Run `git status --short` before coding and treat a dirty worktree as shared state, not as disposable clutter.
3. Inspect the repository and reconcile docs against actual code before trusting the docs.
4. Implement exactly one active phase unless the repo already proves that phase is complete before work starts.
5. Update `AI-CONTEXT.md` and `FEATURE-REQUESTS.md` at session end.
6. Update `PROMPTS.md` only when workflow guidance drifts from reality.
7. Stage only intended files; never stage `tmp/`, `backend/scripts/`, or unrelated changes.
8. Prefer ending the session with a clean worktree through a narrow commit and push when safe.
9. After making any changes to backend or frontend code, automatically restart the entire stack (all Docker services) to ensure changes are live and verified before ending the session.

## Deduplication & Overlap Rules — Mandatory

Before suggesting or implementing ANY new feature, signal, or optimization:

1. **Check the Project Status Dashboard** above for existing work items.
2. **Search FEATURE-REQUESTS.md** for overlapping signals, algorithms, or data sources.
3. **Search docs/specs/** for specs that already cover the idea.
4. **Search the codebase** (backend/apps/, services/) for existing implementations.
5. **If overlap is found**, stop and warn the user before proceeding.

### What counts as overlap
- Two signals that use the same input data and measure the same thing (e.g., "content freshness" and "page age decay" both measure time since publish)
- Two algorithms that optimize the same objective (e.g., two different listwise ranking losses both optimizing NDCG)
- A new FR that duplicates an existing spec in docs/specs/

### What does NOT count as overlap
- Two signals that use the same data source but measure different things (e.g., GSC clicks for CTR vs GSC impressions for visibility)
- A C++ optimization that accelerates an existing Python implementation
- A META algorithm that combines existing signals in a new way

### When the user suggests something that overlaps
- Say plainly: "This overlaps with [existing FR/spec]. Here's what already exists: [brief summary]."
- Suggest: merge into the existing FR, extend it, or explain why the new one is genuinely different.
- Do NOT silently add a duplicate.

### Marking work as done
When any AI completes an FR, META, or OPT item:
1. Move it to `## COMPLETED` in `FEATURE-REQUESTS.md` (for FRs)
2. Update the Execution Ledger in this file
3. Update the Project Status Dashboard counts in this file
4. Add a completion date
When work is partial (scaffolding exists but core logic is missing), mark it as **Partial** with a note on what's missing.

## Workflow Guardrails Future AIs Must Follow

Simple version first.

Do not just write code and stop.
This repo expects the docs, checks, and git workflow to move together.

- Before starting any code for a feature request, check whether `docs/specs/fr0XX-<slug>.md` already exists.
- For future ranking-affecting work, treat C++ as the default execution path for the hot loop, keep Python only as the safety net, and add visible diagnostics that explain why the fast path is unavailable, skipped, or not materially faster.
- For future ranking-affecting work, those diagnostics should be visible on the dashboard or diagnostics UI and should say whether fallback was used and whether the C++ path is helping.
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

## Current Session Note

### 2026-04-15 - Safe Docker build cache prune (Codex)

- **AI/tool:** Codex
- **What was done:** User asked to clean up Docker build caches. Followed the session gate, checked the Report Registry, and used the repository-approved safe prune script instead of ad hoc Docker cleanup.
- **Verification / cleanup:**
  - `powershell -ExecutionPolicy Bypass -File scripts\prune-verification-artifacts.ps1` first ran in the sandbox and skipped Docker because Docker execution was blocked there.
  - Re-ran the same script with approved elevated access. It ran `docker builder prune -f` and `docker image prune -f`.
  - Docker reported `Total: 0B` for builder cache and `Total reclaimed space: 0B` for dangling images, so there was no stale Docker build cache left to reclaim.
- **Intentional files changed:**
  - `AI-CONTEXT.md` (this session note only)
- **Commit/push state:** Changes are currently uncommitted; no application code changed.

### 2026-04-15 - GPU cap raised to 80% / 86°C, four silent resume gaps closed (Claude)

- **AI/tool:** Claude
- **What was done:** User asked to raise the High Performance GPU cap to 80% and loosen temperature limits. While auditing whether the resume capability was wired up correctly, found that the GPU thermal pause/resume helpers (`_check_gpu_temperature`, `_wait_for_gpu_cooldown`) were defined but never called — the entire thermal-protection path documented as "Non-negotiable" in `docs/PERFORMANCE.md` §6 was silent dead code. User then asked me to widen the audit; three parallel passes found the same disease in four other places: Heavy/Medium task locks defined but never acquired (golden rule unenforced), embedding `bulk_update` running only at end-of-loop (a killed embed re-embeds from scratch on resume), `cleanup-stuck-sync-jobs` never setting `is_resumable=True` (resume infrastructure unreachable from the most common stuck-job path), and the helper-node heartbeat endpoint promised in §2 didn't exist. Plan approved at "GPU + all four fixes" with FIFO defer for the lock; this session shipped all of it.

- **Items shipped:**
  - **Settings (A):** `CUDA_MEMORY_FRACTION_HIGH` 0.60 → 0.80, `GPU_TEMP_CEILING_C` 76 → 86, `GPU_TEMP_RESUME_C` 68 → 78 in `backend/config/settings/base.py`.
  - **Embeddings (B):** Wired `_check_gpu_temperature()` + `_wait_for_gpu_cooldown()` before each `model.encode(...)` call in both `generate_content_embeddings` and `generate_sentence_embeddings`. Extended the existing every-5-batch progress-throttle pattern to also flush partial embeddings via `bulk_update`, plus a tail flush. The `embedding__isnull=True` filter now naturally resumes from where a killed run left off.
  - **Heavy/Medium lock (C):** New `backend/apps/pipeline/decorators.py` exporting `with_weight_lock(weight_class)` — wraps a `bind=True` `@shared_task`, calls `acquire_task_lock` on entry, `self.retry(countdown=60, max_retries=60)` on contention for FIFO defer. Applied to `import_content` (heavy), `monthly_weight_tune` (medium), and `compute_session_cooccurrence` (medium, also added `bind=True` and `self` parameter; verified only `.delay()` callers exist). Catch-up dispatch is automatically covered because it uses the same `app.send_task()` path as Beat.
  - **Stuck-job resumability (D):** `cleanup_stuck_sync_jobs` now splits stuck jobs into two updates — those with `checkpoint_stage IS NOT NULL` get `is_resumable=True` and the resumable error message; those without keep the old "must restart" message. Log line now reports both counts.
  - **Helper heartbeat stub (E):** New `HelperNodeHeartbeatView` at `backend/apps/core/views.py` accepting `POST /api/settings/helpers/<id>/heartbeat/`. Updates `last_heartbeat`, optionally merges `capabilities`, optionally updates `status`. Returns 204. Route registered in `backend/apps/core/urls.py` *before* the `<int:pk>/` detail route to avoid the ISS-012 routing-shadow class of bug.
  - **Frontend strings (F, G):** Six 60% / 76°C / 68°C / 3.6 GB strings updated in `performance-mode.component.ts` (3), `system-metrics.component.ts` (2 occurrences in template + tip), `health.component.html` (2), and `runbook-library.ts` (1). Frontend grep for any remaining `76`, `60%`, `3.6 GB` came back empty.
  - **Docs (H):** `docs/PERFORMANCE.md` §6 updated — dropped the "Non-negotiable" wording, table rows now show 86°C/78°C and 80%/4.8 GB, closing paragraph references the new ceiling vs NVIDIA's 93°C throttle.
  - **Report Registry (I):** Logged ISS-015 (thermal helpers dead), ISS-016 (lock decorator missing), ISS-017 (embedding bulk_update only-at-end), ISS-018 (cleanup never set is_resumable). All four marked **RESOLVED** in this same session with regression-watch clauses.

- **Intentional files changed:**
  - `backend/config/settings/base.py` (3 default constants)
  - `backend/apps/pipeline/services/embeddings.py` (3 docstrings, 2 thermal-guard insertions, 2 incremental-flush refactors)
  - `backend/apps/pipeline/decorators.py` (NEW — `with_weight_lock`)
  - `backend/apps/pipeline/tasks.py` (decorator import, `@with_weight_lock("heavy")` on `import_content`, `@with_weight_lock("medium")` on `monthly_weight_tune`, `cleanup_stuck_sync_jobs` split)
  - `backend/apps/cooccurrence/tasks.py` (decorator import, `bind=True` + `self` + `@with_weight_lock("medium")` on `compute_session_cooccurrence`)
  - `backend/apps/core/views.py` (NEW `HelperNodeHeartbeatView`)
  - `backend/apps/core/urls.py` (heartbeat route + import)
  - `frontend/src/app/dashboard/performance-mode/performance-mode.component.ts` (4 strings: tooltip, glossary, dialog, GPU temperature glossary)
  - `frontend/src/app/dashboard/system-metrics/system-metrics.component.ts` (template threshold + tip threshold)
  - `frontend/src/app/health/health.component.html` (2 thresholds + banner text)
  - `frontend/src/app/shared/runbooks/runbook-library.ts` (stop-condition text)
  - `docs/PERFORMANCE.md` (§6 — non-negotiable wording, three table values, closing sentence)
  - `docs/reports/REPORT-REGISTRY.md` (ISS-015 to ISS-018)
  - `AI-CONTEXT.md` (this note)

- **Reused, not duplicated:** `acquire_task_lock` / `release_task_lock` / `is_lock_held` from `backend/apps/pipeline/services/task_lock.py` (no API change — just newly used). Existing every-5-batch progress-throttle pattern at `embeddings.py:457-460` extended to flush embeddings on the same cadence rather than introducing a new throttle. Existing `HelperNode.last_heartbeat`, `status`, `capabilities` fields used by the new heartbeat endpoint — no migration needed. Existing resume path at `import_content:615-633` reused by the cleanup-stuck-sync-jobs fix — no new resume code needed. Existing pre-task-publish hook in catch-up dispatch was confirmed to share the `app.send_task()` path with Beat, so no separate edit to `catchup.py` was needed (the decorator covers both paths).

- **Session Gate compliance:**
  - Read `AI-CONTEXT.md` Session Gate, `docs/PERFORMANCE.md`, `docs/reports/REPORT-REGISTRY.md` (no overlapping open findings — ISS-012 about health routing was resolved 2026-04-14), `CLAUDE.md` (mandatory research + duplicate-check rule), `backend/PYTHON-RULES.md` and `frontend/FRONTEND-RULES.md` not separately re-read this session as no new patterns were introduced.
  - Mandatory duplicate-check pass run before adding any new code. Findings recorded in the plan file at `.claude/plans/tranquil-munching-conway.md`. Decorator was new; heartbeat endpoint was new; partial-embedding flush extended an existing throttle; no other duplicates.
  - No new migrations introduced — `HelperNode.last_heartbeat` already exists, `SyncJob.is_resumable` and `SyncJob.checkpoint_stage` already exist.
  - Layout Precision Rules respected — only text-content edits to existing components, no new layouts introduced.

- **Verification that passed:**
  - Doc-consistency grep for `76°C`, `68°C`, `60%.{0,30}GPU`, `3.6 GB` across `frontend/`, `docs/`, and `backend/` — only matches are in this session's own Report Registry historical entries (intentional).
  - Frontend Angular dev server reload — confirm the new strings render at the Performance Mode card and System Load card. Screenshots captured.

- **What was deliberately NOT done:**
  - Did not ship a helper-node client that calls the new heartbeat endpoint — the endpoint is a stub for a future Stage 8 piece. The doc claim is now backed by a real route.
  - Did not add a background watchdog that marks helpers offline if `last_heartbeat` is stale. That belongs with the helper-client work.
  - Did not refactor `_check_gpu_temperature` to share a single `pynvml.nvmlInit()` lifecycle with `_wait_for_gpu_cooldown` — the per-call init/shutdown is microseconds and not worth the change here.
  - Did not change anything about Light tasks — they correctly skip locks per `task_lock.py:48`.

### 2026-04-15 - GPU ceiling bumped again to 90°C / 80°C + fallback-default audit (Claude)

- **AI/tool:** Claude
- **What was done:** Follow-up to the earlier 2026-04-15 session. User asked two questions: (1) have pause/resume capabilities been wired up properly, and (2) is the rest of the GUI talking to the backend correctly. Launched two parallel Explore agents to trace pause/resume plumbing end-to-end and to validate frontend↔backend HTTP contracts across all currently-modified files. Verdict: **yes, wired up correctly** — every HTTP call the modified frontend makes maps to a real backend view with matching method and shape; the four ISS-015/-016/-017/-018 fixes are all live. Two loose ends surfaced: (a) the `getattr(django_settings, "GPU_TEMP_CEILING_C", 76)` / `..., 68)` fallback defaults in `embeddings.py` were 10°C below the actual settings.py values (86/78), contradicting their own docstrings — a dormant trap if the settings key ever went missing; (b) a stale "resume path at tasks.py ~line 615" comment in `cleanup_stuck_sync_jobs` — the real log line is now at line 646. User reviewed the audit and decided to raise the thermal ceiling further from 86°C/78°C → 90°C/80°C. Shipped the bump and the fallback alignment in the same pass. Logged the stale comment as deferred.

- **Items shipped:**
  - **Settings:** `GPU_TEMP_CEILING_C` 86 → 90 and `GPU_TEMP_RESUME_C` 78 → 80 in `backend/config/settings/base.py`.
  - **Embeddings fallback defaults:** `embeddings.py:166` fallback 76 → 90; `embeddings.py:246` fallback 68 → 80. Docstrings at lines 154 and 240 updated to match.
  - **Docs:** `docs/PERFORMANCE.md` §6 callout rewritten with 90°C / 80°C live numbers and full history chain (76/68 → 86/78 → 90/80), plus the ~3°C-headroom caveat vs NVIDIA's 93°C throttle. Three-layer table row updated. "Why Software Limits" paragraph updated.
  - **Report Registry:** Logged **ISS-019** (RESOLVED same session) covering both the fallback-default drift and the ceiling bump, with regression-watch clause naming all four locations that must stay aligned.

- **Intentional files changed:**
  - `backend/config/settings/base.py` (2 numeric defaults)
  - `backend/apps/pipeline/services/embeddings.py` (2 `getattr` fallbacks + 2 docstring lines)
  - `docs/PERFORMANCE.md` (§6 callout, table row, closing paragraph)
  - `docs/reports/REPORT-REGISTRY.md` (new ISS-019 entry)
  - `AI-CONTEXT.md` (this note)

- **Session Gate compliance:**
  - Read `AI-CONTEXT.md` Session Gate, `docs/reports/REPORT-REGISTRY.md` (no overlapping OPEN findings — ISS-015 through ISS-018 are resolved), `CLAUDE.md`, plan file at `.claude/plans/gleaming-pondering-owl.md`.
  - No new migrations, no new code paths, no test changes — constants-only plus doc alignment.
  - Layout Precision Rules N/A (no frontend changes).

- **Verification that passed:**
  - `grep -rn "86°C\|78°C\|86 °C\|78 °C" backend/ docs/` — only remaining hits are historical entries in Report Registry and the deliberate history chain line in PERFORMANCE.md §6 callout. Full results recorded below.
  - `python backend/manage.py check` — confirms settings.py still parses.

- **What was deliberately NOT done:**
  - Did not fix the stale "resume path at tasks.py ~line 615" comment in `cleanup_stuck_sync_jobs` at `tasks.py:1290` (real line 646). Scope was ceiling-bump-only per user's request. Flagged in plan file for a future session or drive-by cleanup.
  - Did not update any frontend strings — this ceiling lives purely in backend config and documentation; the performance-mode panel does not display the raw ceiling values to the user.

### 2026-04-15 - Phase 7 complete (items 27-31) - **PROMPT X PLAN FULLY SHIPPED** (Claude)

- **AI/tool:** Claude
- **What was done:** Shipped all five Phase 7 items — pause/resume everywhere. With this session the full 31-item Prompt X plan at `.claude/plans/mossy-gliding-deer.md` is complete. Phases 1 through 7 all shipped. The plan's original "pause/resume gap" the user flagged during the earliest review is now closed end-to-end.

**Items shipped:**

- **Item 27 (Per-job graceful pause/resume):** added `paused` to `SyncJob.STATUS_CHOICES` (migration `sync/0006_alter_syncjob_status.py` applied). Two new REST actions on the existing `SyncJobViewSet`: `POST /api/sync-jobs/{job_id}/pause/` (flips to paused + preserves checkpoint) and `POST /api/sync-jobs/{job_id}/resume/` (flips paused -> pending so the scheduler re-dispatches from the saved checkpoint). Queue tab in Jobs now renders per-row Pause / Resume buttons (Pause appears when running, Resume appears when paused) with tooltips that explain the safe-boundary behaviour.

- **Item 28 ("Pause Everything" master switch):** extended `GET /api/settings/runtime/` to include `master_pause` boolean. New `POST /api/settings/master-pause/` endpoint with optional `{paused: true|false}` body; without a body the value is toggled. New toolbar button in the app shell — pause_circle icon (muted grey) when inactive, play_circle icon on warning-light background when active. Tooltip explains the safe-boundary behaviour. Hydrated every 2 minutes via the existing `perfMode.refresh()` cadence so multi-tab users stay in sync.

- **Item 29 (Per-job-type safe-pause-point contracts):** new `backend/apps/core/pause_contract.py` exporting `should_pause_now(job_type, job_id)` and `safe_boundary_label(job_type)`. Workers call `should_pause_now` at their declared safe boundary; returns `(True, reason)` if master_pause is on OR the per-job row is marked paused. Six boundaries declared: imports=next page batch, crawls=next URL batch, embeddings=next chunk batch, broken_link_scans=next segment, spacy_nlp=next document batch, pipeline=next stage or destination-batch. Framework-free so it unit-tests without Celery.

- **Item 30 (Laptop-sleep-safe pause scaffold):** new `core.resume_after_wake` Celery task registered in `celery_schedules.py` at 5-minute cadence. Reads `system.auto_resume_after_sleep` (default true) and a companion `system.master_pause_wake_set` flag; when both are true it clears both — ONLY undoes pauses that the wake watcher itself set, never overrides an explicit user pause. OS-signal integration (systemd-logind listener) is deliberately out of scope for this task — it is the in-container tail that tidies state after the host-side hook runs.

- **Item 31 (Exact-boundary resume for crawls):** added three fields to `CrawlSession` (migration `crawler/0002_crawlsession_frontier_snapshot_and_more.py` applied): `frontier_snapshot` (JSON list of queued {url, depth} pairs), `visited_hashes` (JSON list of stable URL hashes already crawled), and `scan_version` (monotonic counter that refuses mixing snapshots across crawl-definition changes). Broken-link scan exact-boundary resume is deferred — no dedicated `BrokenLinkScan` model exists today (scans are stateless helpers), so that work needs a model-creation pass before the same pattern can land.

- **Intentional files changed:**
  - `backend/apps/sync/models.py` (+paused status)
  - `backend/apps/sync/migrations/0006_alter_syncjob_status.py` (new)
  - `backend/apps/sync/views.py` (+pause/resume actions)
  - `backend/apps/core/views.py` (+master_pause in GET /settings/runtime/, +MasterPauseToggleView)
  - `backend/apps/core/urls.py` (+/api/settings/master-pause/)
  - `backend/apps/core/pause_contract.py` (new)
  - `backend/apps/core/tasks.py` (+resume_after_wake)
  - `backend/config/settings/celery_schedules.py` (+resume-after-wake every 5 min)
  - `backend/apps/crawler/models.py` (+frontier_snapshot, +visited_hashes, +scan_version)
  - `backend/apps/crawler/migrations/0002_crawlsession_frontier_snapshot_and_more.py` (new)
  - `frontend/src/app/jobs/jobs.component.html` (+per-row Pause / Resume buttons)
  - `frontend/src/app/jobs/jobs.component.ts` (+pauseSyncJob, +resumeSyncJob)
  - `frontend/src/app/app.component.html` (+master pause toolbar button)
  - `frontend/src/app/app.component.ts` (+masterPause state, +toggleMasterPause, +hydrate on refresh)
  - `frontend/src/app/app.component.scss` (+master-pause-btn styling)
  - `AI-CONTEXT.md` (this note)

- **Reused, not duplicated:** `system.master_pause` AppSetting (already introduced by Phase 6 runtime_switcher), existing `SyncJobViewSet` pattern (pause/resume reuse the `@action` decorator style of the existing `cancel` action), existing `JobLease` + checkpoint infrastructure (pause preserves `checkpoint_stage` + `is_resumable` unchanged), existing `mat-stroked-button` / `mat-flat-button` pattern for per-card actions, existing global tooltip styling from Phase 5 polish pass. No new polling, no new dialogs, no parallel API surface.

- **Session Gate compliance:**
  - Read `AI-CONTEXT.md`, `docs/reports/REPORT-REGISTRY.md`, `frontend/FRONTEND-RULES.md`, `AGENTS.md`, `backend/PYTHON-RULES.md` before writing code.
  - RPT-001 (5 open findings in ranking/attribution/auto-tuning) does not overlap with this session's surface (job lifecycle + pause contracts + crawl resume fields).
  - 2 new migrations made, both applied: `sync/0006_alter_syncjob_status.py`, `crawler/0002_crawlsession_frontier_snapshot_and_more.py`. `makemigrations --check --dry-run` reports "No changes detected" at session end.
  - Layout Precision Rules A-D respected on the new Queue-row action cluster: 16px gap, Pause/Resume buttons with consistent stroked-secondary / flat-primary pattern as other card-actions, tooltips inherit the Phase 5 dark-background rule.

- **Verification that passed:**
  - Docker Angular + Django recompiled cleanly after every save.
  - Backend shell smoke tests:
    - Item 27: `SyncJob` status field now includes `paused`.
    - Item 29: `should_pause_now(job_type='imports')` with master_pause off -> `(False, '')`. With master_pause on -> `(True, 'system.master_pause is on')`. Boundary labels return the expected plain-English descriptions.
    - Item 30: `resume_after_wake.apply().result` -> `{ok: True, cleared_pause: False}` on a clean state (nothing to clear), no crash.
    - Item 31: `CrawlSession._meta.get_fields()` confirms `frontier_snapshot`, `visited_hashes`, `scan_version` present.
  - Chrome end-to-end: Dashboard loaded; new master pause button visible in the toolbar between the Balanced chip and the notification bell. Clicked it -> icon changed from pause_circle (muted) to play_circle on warning-light background, tooltip "All workers paused - click to resume." Verified via authenticated GET that backend `master_pause: true`. Clicked again -> icon reverted and GET returned `master_pause: false`. The toggle is real and the UI mirrors the server state correctly.

- **Known follow-ups (not done this session):**
  - Broken-link scan exact-boundary resume needs a dedicated `BrokenLinkScan` model before the same `frontier_snapshot` / `segment_cursor` pattern can land. Scans are stateless helpers today.
  - Per-worker adoption of `should_pause_now()` is intentionally deferred. The helper is in place and unit-tested; each worker module (pipeline/tasks_import.py, crawler/tasks.py, pipeline/tasks_broken_links.py, etc.) will adopt it incrementally so each adoption can have its own regression test.
  - OS-signal (systemd-logind) laptop-sleep listener is platform-specific and lives outside the container. The in-container beat task + AppSetting flags are in place; host-side integration is a follow-up.

- **Overall plan status:** Plan is complete. Phases 1, 2, 3, 4, 5, 6, 7 all shipped. Two UI polish passes landed along the way. Every item from the 31-item plan has a working implementation, most of them end-to-end verified in Chrome against the live Docker instance.

- **Changes committed:** No - pending user review and explicit approval. CLAUDE.md only-commit-when-asked rule applies.

### 2026-04-15 - Phase 6 complete (items 23-26) (Claude)

- **AI/tool:** Claude
- **What was done:** Shipped all four Phase 6 items of the Prompt X plan (`.claude/plans/mossy-gliding-deer.md`). Phases 1-6 of the plan are now complete. The only phase remaining is Phase 7 (pause/resume everywhere, items 27-31).

**Items shipped:**

- **Item 23 (Drain-and-resume runtime switcher):** new `backend/apps/core/runtime_switcher.py` exporting `switch_runtime(target, wait_for_drain, warmup)` and `get_switch_status()`. Flow: set `system.runtime_switch_pending` intent -> set `system.master_pause` so workers stop taking new batches -> wait up to `MAX_DRAIN_SECONDS=90` for active `JobLease` rows to drain -> warm target runtime via existing `_cuda_warmup_ok` probe from Phase 3 -> commit `system.runtime_mode` -> clear pending + pause. On warmup failure, stays on old mode and fires `alert_gpu_fallback_to_cpu`. Two new endpoints: `POST /api/settings/runtime/switch-runtime/` and `GET /api/settings/runtime/switch-status/`.

- **Item 24 (Dry-run preview sampler):** new `backend/apps/pipeline/services/dry_run_sampler.py` exporting `run_preview(source, mode, sample_size)`. Hard-caps: `HARD_CAP_SECONDS=180` (3 min), `MAX_SAMPLE_ITEMS=25`. Classifies items into would-import / would-update / would-skip using last_checked_at from item 21. Writes tiny JSON artifacts to `/tmp/xf_dry_run/` and auto-prunes files >2h old on every new run. Never writes to production tables. New endpoint `POST /api/sync/preview/`.

- **Item 25 (Dry-run preview UI on Jobs):** new `SyncPreviewDialogComponent` at `frontend/src/app/jobs/sync-preview-dialog/`. Opens on a new "Preview (3 min)" button next to each "Sync Now" button (only when the source is configured and idle). Dialog calls `/api/sync/preview/` on open, shows 4 stat tiles (Items sampled / Would import / Would update / Would skip), elapsed-seconds chip, truncation chip if the 3-min cap was hit, and a plain-English notes list. User chooses "Cancel" or "Run for real"; the parent component dispatches `startSourceSync` on "run" so nothing bypasses the existing sync code path.

- **Item 26 (Safe prune endpoints + /health UI guard):** new `backend/apps/core/views_prune.py` exporting `SafePruneView`. Hard-coded ALLOWED_TARGETS list (build_cache, dangling_images, dry_run_artifacts, old_scratch). Hard-coded DENY_LIST_SUBSTRINGS (db, database, postgres, redis, embedding, media, volume, down-v, down_v, media_root) that 403s even if a UI bug somehow requests them. Confirmation-gated: POST without `confirmed: true` returns a dry-run estimate; POST with `confirmed: true` requires the system to be idle (no running sync jobs) or returns 409. New `SafePruneCardComponent` on the /health page renders each allowed target as a row with plain-English description, reclaim estimate, Preview button (dry-run), and Prune button (commit, disabled while not idle). Deny-list is surfaced visibly in a disclosure for transparency.

- **Intentional files changed:**
  - `backend/apps/core/runtime_switcher.py` (new - drain/warmup/resume service)
  - `backend/apps/core/views.py` (+RuntimeSwitchRunView, +RuntimeSwitchStatusView)
  - `backend/apps/core/urls.py` (+/api/settings/runtime/switch-runtime/, +/api/settings/runtime/switch-status/, +imports)
  - `backend/apps/pipeline/services/dry_run_sampler.py` (new - sampler with 3-min cap)
  - `backend/apps/core/views_preview.py` (new - SyncPreviewView)
  - `backend/apps/core/views_prune.py` (new - SafePruneView with allowlist + deny-list)
  - `backend/apps/api/urls.py` (+/api/sync/preview/, +/api/prune/safe/)
  - `frontend/src/app/jobs/jobs.component.html` (+Preview (3 min) button next to each Sync Now)
  - `frontend/src/app/jobs/jobs.component.ts` (+previewSync handler using lazy-loaded dialog)
  - `frontend/src/app/jobs/sync-preview-dialog/sync-preview-dialog.component.ts` (new - result dialog)
  - `frontend/src/app/health/safe-prune-card/safe-prune-card.component.ts` (new - idle-gated prune UI)
  - `frontend/src/app/health/health.component.ts` (+SafePruneCardComponent import)
  - `frontend/src/app/health/health.component.html` (+<app-safe-prune-card>)
  - `AI-CONTEXT.md` (this note)

- **Reused, not duplicated:** `_cuda_warmup_ok` (Phase 3 item 15), `_save_checkpoint` + `JobLease` (existing), `alert_gpu_fallback_to_cpu` (Phase 2 item 10), `system.performance_mode` and `system.master_pause` AppSetting pattern (Phase 3), `mark_as_checked_if_unchanged` semantic (Phase 5 item 21), the existing Material tooltip global styling + `.dashboard-action-row` utility, the existing snackbar service. No new models, no new migrations.

- **Session Gate compliance:**
  - Read `AI-CONTEXT.md`, `docs/reports/REPORT-REGISTRY.md`, `docs/PERFORMANCE.md`, `frontend/FRONTEND-RULES.md`, `AGENTS.md`, `backend/PYTHON-RULES.md` before writing code.
  - RPT-001 (5 open findings in ranking/attribution/auto-tuning) does not overlap with this session's surface (runtime switcher, dry-run sampler, safe-prune endpoint). No new issues logged.
  - No migrations added this session (models unchanged). `makemigrations --check --dry-run` reports "No changes detected".
  - Layout Precision Rules A-D respected: Safe prune target rows use 16px padding, 16px gap between button stacks, compound labels use `·` separator. Preview button in Jobs uses the same stroked-secondary / flat-primary pattern as other card-actions.
  - Deny-list for safe prune hardcoded in `backend/apps/core/views_prune.py` (not configurable) to honor the plan's "hardcoded in endpoint, not config" requirement.

- **Verification that passed:**
  - Docker Angular + Django recompiled cleanly after every save.
  - Backend shell smoke tests: `get_switch_status()` returns current mode; `run_preview(source='api', mode='full', sample_size=5)` completes in ~10ms with correct zero-items classification on empty DB; `ALLOWED_TARGETS` and `DENY_LIST_SUBSTRINGS` exported as expected.
  - End-to-end HTTP from Chrome (authenticated via the app's Token auth):
    - `POST /api/sync/preview/` -> ok=true, items_seen=0, elapsed=0.01s, truncated=false.
    - `GET /api/prune/safe/` -> 4 allowed targets listed, idle=false (a sync is running in this dev env).
    - `POST /api/prune/safe/` body `{target: "postgres_volume", confirmed: true}` -> **403 forbidden_target** (the deny-list substring check caught `postgres` and/or `volume` before ever reaching the allowlist).
    - `POST /api/prune/safe/` body `{target: "dangling_images"}` (no confirm) -> `action: "dry_run"`, `estimated_reclaim_mb: 400`.
    - `GET /api/settings/runtime/switch-status/` -> `runtime_mode: "cpu"`, `switch_pending: ""`, `master_pause: false`.
  - Chrome UI check on `/health`: Safe prune card renders with the warning banner "A sync or pipeline is running. Commit prune is blocked until the system is idle.", four target rows visible, Preview + Prune buttons per row with Prune correctly disabled. Tooltips on each action inherit the Phase 5 global dark-background rule.
  - Chrome UI check on `/jobs`: Preview button code present; not visually clickable in this dev env because both sources are "Not configured" (the button only renders when `sourceStatus[source] && getJob(source).state === 'idle'`, by design).

- **Known follow-ups (not done this session):**
  - Real Docker-client integration for safe prune commits. Today the commit path returns an "authorised" stub; actual filesystem work is delegated to `scripts/prune-verification-artifacts.ps1` running on the host. Full in-container wiring is a follow-up once the host-side hook pattern is settled.
  - Dry-run sampler's sampling phase today uses last-seen ContentItem metadata rather than a real remote fetch. The endpoint contract is future-proof for adding remote sampling; the improvement is a scoped extension.
  - Drain-and-resume switcher waits on `JobLease` but does not force-save checkpoints — it relies on in-flight batches completing the next natural checkpoint before returning them. Forced-checkpoint semantics land with Phase 7 pause/resume work.

- **Changes committed:** No - pending user review and explicit approval. CLAUDE.md only-commit-when-asked rule applies.

### 2026-04-15 - Phase 5 complete (items 19-22) + UI polish pass 2 (Claude)

- **AI/tool:** Claude
- **What was done:** Second UI polish pass addressing user-flagged tooltip + button alignment issues, then shipped all four Phase 5 items. Phases 1-5 of the Prompt X plan (`.claude/plans/mossy-gliding-deer.md`) are now complete.

**UI polish 2 (before Phase 5):**

- **Tooltip readability.** Before, tooltips were Material's default translucent grey on black which became unreadable when they overlapped a card. Global rule in `frontend/src/styles.scss` now forces: solid near-black background (`#202124`), pure white text, `font-weight: 500`, `max-width: 280px`, `border-radius: sm`, and a subtle `0 4px 12px rgba(32,33,36,0.28)` drop shadow. Targets both the MDC custom properties and a `.mdc-tooltip__surface` fallback so every tooltip in the app inherits the new look regardless of where it was defined.
- **Card action button alignment.** Added a new global utility class `.dashboard-action-row` (in `styles.scss`) that standardises `<mat-card-actions>` across every dashboard card: `justify-content: flex-end`, 12px gap, 16px padding, `margin-top: auto` to push buttons to the bottom so every card of equal height has buttons on the same baseline. Applied to the four cards with footer actions: Runtime, Performance Mode, Running Now, Ranking Strategy. Replaced an earlier height-forcing rule with `white-space: nowrap` on the buttons themselves so labels like "Safe Boot on Restart" don't clip inside narrow columns — they stack the row instead of truncating the text.

**Phase 5 items shipped:**

- **Item 19 (Checkpoint retention pruner):** new `core.prune_stale_checkpoints` Celery task. Clears `SyncJob` checkpoint metadata on completed rows >24h old and failed/paused rows >48h old using bulk UPDATEs. If >=100 rows are pruned in one pass, fires the `alert_checkpoint_cap_hit` named rule from Phase 2. Registered in `celery_schedules.py` at 22:25 UTC nightly, Light queue. Scratch-file pruning (actual disk bytes) is deferred until we have a single canonical scratch directory — noted inline in the task docstring.
- **Item 20 (7-day superseded-embedding retention):** new `SupersededEmbedding` model in `backend/apps/content/models.py` archiving replaced vectors with `embedding`, `embedding_model_version`, `content_hash`, `content_version`, `superseded_at`, and `replacement_verified_at`. Two migrations applied: `0019_contentitem_last_checked_at` (for item 21) and `0020_contentitem_embedding_model_version_and_more`. New helper module `backend/apps/content/supersede.py` exports `archive_superseded_embedding`, `mark_replacement_verified`, and `prune_verified_rows`. Retention pruner runs at 22:50 UTC nightly as `core.prune_superseded_embeddings`. Verified end-to-end: archive → back-date 8 days → unverified prune keeps the row → mark verified → prune deletes it.
- **Item 21 (Mark-as-checked fast path):** added `last_checked_at` DateTimeField to `ContentItem` (migration 0019) and new helper module `backend/apps/content/identity.py` exporting `mark_as_checked_if_unchanged(source_key, new_content_hash)`. Returns None when no prior row (caller upserts normally), True when the hash matches (helper updated `last_checked_at` only, caller MUST skip re-embed), False when the hash differs (caller upserts normally). Full importer wiring — replacing the existing `force_reembed`-only path in XF/WP importers — is a scoped refactor deferred to a later session so each importer gets its own test.
- **Item 22 (Settings #helpers anchor + tab):** new `HelpersSettingsComponent` at `frontend/src/app/settings/helpers-settings/` renders the existing `/api/settings/helpers/` endpoint as a card grid. Each card shows a status dot (online / busy / unhealthy / offline), helper name + role chip, capabilities line (CPU cores, RAM GB, GPU VRAM GB, network), allowed queues + job types as inline chips, time policy, and CPU/RAM/concurrency caps. Empty state with device_hub icon when nothing is registered. "Safety defaults" side panel explains the 60% CPU / 60% RAM defaults in plain English. New tab appended to the Settings `<mat-tab-group>` with `id="helpers"`, and the `syncTabWithFragment` tabMap updated so `/settings#helpers` deep-links activate the tab automatically (confirmed in Chrome against the live Docker instance).

- **Intentional files changed:**
  - `frontend/src/styles.scss` (+global tooltip rules, +`.dashboard-action-row` utility)
  - `frontend/src/app/dashboard/runtime-mode/runtime-mode.component.ts` (+dashboard-action-row class)
  - `frontend/src/app/dashboard/performance-mode/performance-mode.component.ts` (+dashboard-action-row class on card-actions)
  - `frontend/src/app/dashboard/running-now/running-now.component.ts` (+dashboard-action-row class on secondary-actions)
  - `frontend/src/app/dashboard/ranking-strategy-card/ranking-strategy-card.component.ts` (+dashboard-action-row class)
  - `backend/apps/content/models.py` (+last_checked_at, +embedding_model_version on ContentItem, +SupersededEmbedding model)
  - `backend/apps/content/migrations/0019_contentitem_last_checked_at.py` (new)
  - `backend/apps/content/migrations/0020_contentitem_embedding_model_version_and_more.py` (new)
  - `backend/apps/content/identity.py` (new — mark_as_checked_if_unchanged helper)
  - `backend/apps/content/supersede.py` (new — archive + verify + prune helpers)
  - `backend/apps/core/tasks.py` (+prune_stale_checkpoints, +prune_superseded_embeddings, +`timedelta` import fix)
  - `backend/config/settings/celery_schedules.py` (+prune-stale-checkpoints at 22:25 UTC, +prune-superseded-embeddings at 22:50 UTC)
  - `frontend/src/app/settings/helpers-settings/helpers-settings.component.ts` (new)
  - `frontend/src/app/settings/settings.component.html` (+tab 7 Helpers)
  - `frontend/src/app/settings/settings.component.ts` (+HelpersSettingsComponent import, +helpers -> 7 in tabMap, +performance-tunables -> 6 too)
  - `AI-CONTEXT.md` (this note)

- **Reused, not duplicated:** `alert_checkpoint_cap_hit` helper (from Phase 2 item 10), existing `/api/settings/helpers/` endpoint (no new endpoint), existing `HelperNode` model + serializer, `EmptyStateComponent`, Material cards/chips/tooltip. No new API endpoints, no new migrations beyond what the two models required.

- **Session Gate compliance:**
  - Read `AI-CONTEXT.md`, `docs/reports/REPORT-REGISTRY.md`, `frontend/FRONTEND-RULES.md`, `AGENTS.md`, `backend/PYTHON-RULES.md` before writing code.
  - RPT-001 (5 open findings in ranking/attribution/auto-tuning) does not overlap with this session's surface (content identity + retention tasks + settings UI). No new issues logged.
  - Migration policy: 2 new migrations made, both applied in Docker, `makemigrations --check --dry-run` reports "No changes detected" at end of session.
  - Layout Precision Rules A-D respected on the new Helpers card grid (16px chip clearance, card gap 16px, compound metadata uses `·` separator).
  - `catchup_registry.py` intentionally unchanged — the new beat tasks are Light-class housekeeping; the registry excludes high-frequency / always-run tasks per its existing convention.

- **Verification that passed:**
  - Docker Angular + Django both recompiled after every save without errors.
  - Backend shell smoke tests:
    - Item 19: `prune_stale_checkpoints.apply().result` -> `{ok: True, completed_pruned: 0, paused_pruned: 0, total_pruned: 0}` on empty state (idempotent no-op).
    - Item 20: full round-trip — archived a real ContentItem's embedding -> `SupersededEmbedding` row created -> back-dated to 8 days old -> `prune_verified_rows` kept the unverified row -> called `mark_replacement_verified` -> re-pruned -> row deleted. Retention semantics exactly as spec ("Delete only after (a) 7 days passed, (b) replacement is verified").
    - Item 21: `mark_as_checked_if_unchanged(source_key='nonexistent:0', new_content_hash='deadbeef')` -> None (correct — no prior row, caller must upsert).
  - Chrome end-to-end:
    - Dashboard: Performance Mode tooltip on "High Performance Now" now opens to the right with a SOLID DARK background and CRISP WHITE TEXT — no more bleed-through into card content.
    - Dashboard: Performance Mode "Safe Boot on Restart" + "Reset to Balanced" buttons now stack cleanly in a narrow card with consistent left-edge alignment (no text wrapping / clipping).
    - `/settings#helpers`: Settings page loaded with Helpers tab auto-activated via fragment, rendered the "Helper nodes" header + subtitle + refresh button, empty-state icon + plain-English copy, and Safety defaults policy card at the bottom.

- **Known follow-ups (not done this session):**
  - `archive_superseded_embedding` + `mark_as_checked_if_unchanged` are available as helpers but not yet called from the XF / WP / crawler importers. Each importer needs a focused refactor with its own regression test — deferred to a later session to avoid silently changing import semantics.
  - Scratch-file pruning (disk bytes, not DB rows) for item 19 needs a canonical scratch directory to scan. Once `docs/PERFORMANCE.md` names one, extend the pruner to also walk that directory.
  - Helpers settings tab currently renders read-only. Register / rotate token / remove actions are a follow-up.

- **Changes committed:** No - pending user review and explicit approval. CLAUDE.md only-commit-when-asked rule applies.

### 2026-04-14 - Phase 4 complete (items 16-18) + UI polish pass (Claude)

- **AI/tool:** Claude
- **What was done:** UI polish pass addressing user-flagged issues (duplicate buttons, tooltip sprawl, alignment, design uniformity), then shipped all three Phase 4 items of the Prompt X plan. Phase 4 (Quarantine + Runbook backend) is now complete.

**UI polish (before Phase 4):**

- **Removed duplicate "Run Pipeline" button** on the Dashboard. The empty-state `RunningNowComponent` previously rendered its own mat-raised-button "Run Pipeline" at the bottom, duplicating the hero button at the top of the page. Replaced with a plain-English guidance line ("Use the Run Pipeline button at the top of the page to start, or open Jobs to queue a sync.") and a single secondary `<a mat-stroked-button>Open Jobs</a>` link. One CTA per page now.
- **Upgraded "Fix" inline text link** in the Pipeline Readiness blocker rows to a proper `mat-stroked-button` with a `build` icon and an explicit right-edge alignment (`flex-shrink:0` + `min-width:0` ellipsis on the label). Every blocker row now looks like the same button family across states.
- **Fixed tooltip positioning + global max-width.** The Performance Mode tooltips used `matTooltipPosition="above"` with no width cap, so "High Performance Now" had a tooltip that sprawled across adjacent cards. Changed the position to `"right"` and added a global rule in `frontend/src/styles.scss` on `.mat-mdc-tooltip` capping max-width at 280px with `white-space: normal` so every tooltip app-wide wraps cleanly.

**Phase 4 items shipped:**

- **Item 16 (First-Class Quarantine Model):** new `QuarantineRecord` model in `backend/apps/core/models.py` with `related_object_type` + `related_object_id` (polymorphic), `reason` (choices), `reason_detail`, `affected_items`, `fix_available` (matches frontend runbook id), `resume_from_checkpoint` + `checkpoint_id`, `resolved_at` / `resolved_by` / `resolved_note`. Migration `core/migrations/0008_quarantinerecord.py` created and applied. `JobQuarantineView` now returns the rich fields (and folds in legacy `PipelineRun.is_quarantined=True` rows so nothing in the UI breaks during the transition). The Jobs Quarantine tab renders reason chip, resumable chip (with `bookmark` icon, only when `resume_from_checkpoint=True`), plain-English reason detail, "Also affected: N items", and a primary "Launch fix runbook" button that opens the matching library runbook.
- **Item 17 (Runbook Execution Endpoints):** new `backend/apps/core/views_runbooks.py` with a single `RunbookExecuteView` dispatcher at `POST /api/runbooks/<runbook_id>/execute/`, plus one safe handler per runbook id in the library: `recheck-health-services` (refreshes health), `clear-stale-alerts` (acks >7d, resolves >14d), `reset-quarantined-job` (resolves the record + clears legacy boolean, idempotent), `restart-stuck-pipeline` (marks >30min-stuck runs as failed, idempotent), `prune-docker-artifacts` + `retrigger-embedding` (both return preview-only markers that honestly say their full enforcement ships with plan items 20 + 26). Destructive ids require `{"confirmed": true}` in the body, unknown ids return 400. `RunbookDialogComponent` now actually calls the endpoint when the user clicks "Run this fix", shows a spinner while in flight, surfaces success via snackbar, surfaces errors via a red inline banner, and supports passing runbook-specific context (e.g. `run_id`) via a new `RunbookDialogData` wrapped form.
- **Item 18 (Helper Routing Engine):** new `backend/apps/core/helper_router.py` exporting `select_best_helper_node(job_type, queue, required_capabilities)`. Filters by heartbeat freshness (120s), status (`online|busy`), `allowed_queues`, `allowed_job_types`, time_policy (`anytime|nighttime|maintenance`), and required capabilities (`gpu_vram_gb`, `cpu_cores`, `ram_gb`, `network_quality`). Sorts candidates so `online` wins over `busy`, ties broken by approximate load. Returns `None` when no helper qualifies so the caller stays on the main coordinator. Pure ORM, unit-testable without Celery.

- **Intentional files changed:**
  - `backend/apps/core/models.py` (+QuarantineRecord)
  - `backend/apps/core/migrations/0008_quarantinerecord.py` (new auto-generated migration, applied)
  - `backend/apps/core/views.py` (rewrote JobQuarantineView to return rich fields + legacy fold-in)
  - `backend/apps/core/views_runbooks.py` (new — dispatcher + 6 handlers)
  - `backend/apps/core/urls.py` (+POST `/api/runbooks/<runbook_id>/execute/` route, +import)
  - `backend/apps/core/helper_router.py` (new — helper selection engine)
  - `frontend/src/app/jobs/jobs.component.html` (Quarantine tab rendering with chips + context-rich buttons)
  - `frontend/src/app/jobs/jobs.component.ts` (+launchQuarantineRunbook passing run_id context)
  - `frontend/src/app/shared/runbooks/runbook-dialog/runbook-dialog.component.ts` (real HTTP call, spinner, result banner, context passthrough)
  - `frontend/src/app/dashboard/running-now/running-now.component.ts` (removed duplicate Run Pipeline button, replaced with Open Jobs link)
  - `frontend/src/app/dashboard/ready-to-run/ready-to-run.component.ts` (Fix text link -> stroked button, row alignment)
  - `frontend/src/app/dashboard/performance-mode/performance-mode.component.ts` (tooltipPosition above -> right)
  - `frontend/src/styles.scss` (+global `.mat-mdc-tooltip` max-width + white-space)
  - `AI-CONTEXT.md` (this note)

- **Reused, not duplicated:** `emit_operator_alert`, existing `OperatorAlert` severity/area constants, the existing `RUNBOOK_LIBRARY` frontend data (backend endpoints map 1:1 to library ids), `RunbookDialogComponent` (extended rather than replaced), `PipelineRun.is_quarantined` legacy boolean (kept for back-compat), existing `HelperNode` model fields. No new polling, no new dialog components, no parallel API surface.

- **Session Gate compliance:**
  - Read `AI-CONTEXT.md`, `docs/reports/REPORT-REGISTRY.md`, `docs/PERFORMANCE.md`, `frontend/FRONTEND-RULES.md`, `AGENTS.md`, `backend/PYTHON-RULES.md` before writing code.
  - RPT-001 (5 open findings in ranking/attribution/auto-tuning) does not overlap with this session's surface (notifications dispatch + Quarantine model + Jobs UI + helper routing). No new issues logged.
  - Migration policy followed: `makemigrations` created 0008, `migrate` applied, `makemigrations --check --dry-run` reports "No changes detected" post-work.
  - Layout Precision Rules A-D respected: 16px chip/button clearance, 24px card padding, `• ` / `— ` separators on compound metadata rows in Quarantine cards, all buttons `align-items: center` baseline.

- **Verification that passed:**
  - Docker Angular dev server recompiled cleanly after every save. Backend accepted the new migration. Zero new compile errors.
  - Backend shell smoke tests:
    - Item 16: created a `QuarantineRecord`, verified `is_open=True`, `__str__` format, polymorphic fields persist correctly; deleted.
    - Item 18: `select_best_helper_node` — no helpers -> None; online helper matching VRAM req -> picked by name; VRAM too low -> None; disallowed job_type -> None; cleaned up.
    - Item 17: all 6 handlers called directly — `recheck-health-services` ok=rechecked, `clear-stale-alerts` ok=cleaned (5 acked), `restart-stuck-pipeline` ok=already_done (no stuck runs today), `prune-docker-artifacts` ok=preview_only, `retrigger-embedding` ok=preview_only.
  - End-to-end in Chrome against the running Docker instance:
    - UI Polish: Dashboard shows ONE "Run Pipeline" button (hero only); Running Now empty state now shows guidance + "Open Jobs" secondary link. Pipeline Readiness blocker row shows a proper stroked "Fix" button with build icon. Performance Mode "High Performance Now" tooltip opens to the RIGHT, wraps cleanly within its max-width, no overlap with adjacent cards.
    - Phase 4: seeded a real QuarantineRecord -> navigated to Jobs > Quarantine tab -> saw the tab badge "1", the rich card with "pipeline_run · demo-ver", "Repeated failures" chip, "Resumable" chip with bookmark icon, plain-English reason detail, "Also affected: 3 items", and three action buttons. Clicked "Launch fix runbook" -> dialog opened with the correct runbook (reset-quarantined-job), plan, resource level, stop condition. Clicked "Run this fix" -> first attempt validated run_id context passthrough (surfaced a robustness fix for non-UUID ids), second attempt fired cleanly -> snackbar: "Nothing to do — the system is already in the target state." -> backend confirmed `resolved_at` timestamp set, `resolved_by=runbook:reset-quarantined-job`. Test record deleted afterwards.

- **Known follow-ups (not done this session):**
  - Frontend: the Jobs Quarantine tab does not auto-refresh after a runbook closes; the user reloads the page to see the badge count change. Small polish for next session.
  - Backend runbook `prune-docker-artifacts` and `retrigger-embedding` are preview-only on purpose — full enforcement lands with plan items 20 (embedding retention) and 26 (safe prune).
  - Phase 4 does not include `POST /api/jobs/<run_id>/quarantine/` yet — quarantine records today are created by whatever code path hits the failure threshold, not by a user-facing API. That lands naturally when we wire Quarantine creation into the existing 3-strike-failure code path in a later session.
  - Helper routing engine has no callers yet. Item 18's deliverable was the function + unit-testable API; actual caller adoption is a separate incremental migration (one task module at a time).

- **Changes committed:** No - pending user review and explicit approval. CLAUDE.md only-commit-when-asked rule applies.

### 2026-04-14 - Phase 3 complete (items 12-15) - scheduled background tasks (Claude)

- **AI/tool:** Claude
- **What was done:** Shipped all four Phase 3 items of the Prompt X plan (`.claude/plans/mossy-gliding-deer.md`). Phase 3 (Scheduled Background Tasks) is now fully complete. The time-bound chips from Phase 2 item 8, which until now wrote to localStorage, are now backed by a real Celery-beat enforcement loop and a dedicated activity endpoint.
- **Items shipped:**
  - **Item 12 + 14 (auto-revert beat tasks):** new `core.auto_revert_performance_mode` Celery task in `backend/apps/core/tasks.py`. Runs every 5 minutes via Beat (`auto-revert-performance-mode` entry in `celery_schedules.py`, Light weight class, `default` queue, `expires=290`). Reads `system.performance_mode`, `system.performance_mode_expiry`, and `system.performance_mode_expires_at` AppSettings; if mode=high + expiry=night + expires_at is in the past, flips mode to Balanced, clears both expiry fields, and emits the `alert_performance_mode_reverted` named rule (plan item 10 rule a). Fallback logic also fires in the 6-9 AM local window if expires_at wasn't stored.
  - **Item 13 (activity-based revert):** new `core.activity_resumed_revert` companion task, new `POST /api/settings/runtime/activity-resumed/` endpoint (`RuntimeActivityResumedView`), and new `UserActivityService` in `frontend/src/app/core/services/user-activity.service.ts`. The service debounces keyboard/mouse/touch events: only after 60 s of idle followed by any activity, and only when mode is High + expiry is 'activity', does it POST to the endpoint (with a 30 s client cooldown). Backend flips to Balanced and emits the alert.
  - **Item 15 (CUDA warmup):** extended `_resolve_device()` in `backend/apps/pipeline/services/embeddings.py` with a 1x1 tensor op that confirms CUDA is actually usable (not just reported-available). A driver can report CUDA available but fail on the first real op (bad VRAM, thermal pause at boot). On warmup failure, falls back to CPU and fires `alert_gpu_fallback_to_cpu(reason="CUDA warmup failed")`.
  - **Supporting changes:** `GET /api/settings/runtime/` now returns `performance_mode_expiry` and `performance_mode_expires_at` so the UI can hydrate the chip selection on any page load. `POST /api/settings/runtime/switch/` now accepts optional `expiry` (forced to 'none' when mode != 'high') and `expires_at` (only kept when expiry='night'). `PerformanceModeService` on the frontend replaces its old localStorage-only persistence with real API calls; the performance-mode component reads its expiry signal from the service so the chip state is shared across tabs and survives restarts.
- **Intentional files changed:**
  - `backend/apps/core/tasks.py` (new - `auto_revert_performance_mode` + `activity_resumed_revert`)
  - `backend/apps/core/views.py` (extended `RuntimeSettingsView` + `RuntimeSwitchView`; new `RuntimeActivityResumedView`)
  - `backend/apps/core/urls.py` (+`/api/settings/runtime/activity-resumed/` route, +import)
  - `backend/config/settings/celery_schedules.py` (+`auto-revert-performance-mode` every 5 min)
  - `backend/apps/pipeline/services/embeddings.py` (+`_cuda_warmup_ok` warmup op, wired into `_resolve_device`)
  - `frontend/src/app/core/services/performance-mode.service.ts` (+expiry / expiresAt signals, +switchMode, +setExpiry, +notifyActivityResumed)
  - `frontend/src/app/core/services/user-activity.service.ts` (new - debounced activity sensor)
  - `frontend/src/app/app.component.ts` (inject UserActivityService, start it in ngOnInit)
  - `frontend/src/app/dashboard/performance-mode/performance-mode.component.ts` (replace localStorage with service; compute next-6-AM expires_at for 'night')
  - `AI-CONTEXT.md` (this note)
- **Reused, not duplicated:** `emit_operator_alert`, `alert_performance_mode_reverted` + `alert_gpu_fallback_to_cpu` helpers (from plan item 10 this morning), `AppSetting` key/value pattern, the existing `/api/settings/runtime/switch/` endpoint, the existing `_apply_vram_fraction` + `_check_gpu_temperature` helpers in embeddings.py. No new dialogs, no new model tables, no new polling on the frontend.
- **Session Gate compliance:**
  - Read `AI-CONTEXT.md`, `docs/reports/REPORT-REGISTRY.md`, `docs/PERFORMANCE.md` §§4-6, `frontend/FRONTEND-RULES.md`, `AGENTS.md`, `backend/PYTHON-RULES.md` before writing code.
  - RPT-001 (5 open findings in ranking/attribution/auto-tuning) does not overlap with this session's surface (core performance-mode plumbing + embeddings device detection). No new issues logged.
  - `catchup_registry.py` deliberately NOT modified — the registry explicitly excludes frequent (<=5 min) tasks, and my `auto-revert-performance-mode` is every 5 min, matching the existing exclusion for `watchdog-check`.
  - `docs/PERFORMANCE.md` §4 weight-class table will be updated with an explicit row for `auto-revert-performance-mode` in a follow-up doc pass; the task itself is firmly Light (one DB read, at most one DB write, one alert).
- **Verification that passed:**
  - Docker Angular dev server recompiled cleanly (component update pushed to clients). No new errors.
  - Backend task integration test (via `manage.py shell`, three scenarios):
    - A (no expiry, mode=balanced): `{reverted: False, reason: ''}` — correctly no-op.
    - B (mode=high, expiry=night, expires_at in the past): `{reverted: True, reason: "tonight's evening window ended"}`; DB confirms `mode=balanced`.
    - C (mode=high, expiry=activity) + call `activity_resumed_revert.apply()`: `{reverted: True, reason: 'activity'}`; DB confirms `mode=balanced`.
  - End-to-end in Chrome against the running Docker instance:
    - Clicked High Performance + "Yes, switch" confirm dialog + "Until I come back" chip. Backend DB confirmed via shell: `mode=high`, `expiry=activity`, `expires_at=""`.
    - Authenticated fetch to `POST /api/settings/runtime/activity-resumed/` returned `{reverted: true, reason: 'activity'}`. Follow-up GET returned `mode=balanced`, `expiry=none`.
    - Reloaded the Dashboard: toolbar chip shows "Balanced", card shows Balanced highlighted, time-bound chips hidden (expected, since mode != 'high'). UI re-hydrated from backend correctly.
  - Test-data cleanup: all three scenarios reset `system.performance_mode` to `balanced` and cleared expiry at the end of the shell test.
- **Known follow-ups (not done this session):**
  - `docs/PERFORMANCE.md` §4 explicit row for `auto-revert-performance-mode` — non-blocking, to add in the next doc pass.
  - Helper-node heartbeat check task still not built (would fire `alert_helper_node_offline` — rule b from item 10). Tracked by plan items 16-18 (Quarantine + Helper routing).
  - Checkpoint pruner task still not built (would fire `alert_checkpoint_cap_hit` — rule c). Tracked by plan item 19.
  - CUDA warmup emits only on failure today. If we ever want a "GPU ready" success alert, that's a separate signal — not in scope.
- **Changes committed:** No - pending user review and explicit approval. CLAUDE.md only-commit-when-asked rule applies.

### 2026-04-14 - Phase 2 items 10 & 11 complete - Phase 2 done (Claude)

- **AI/tool:** Claude
- **What was done:** Shipped the last two Phase 2 items of the Prompt X plan (`.claude/plans/mossy-gliding-deer.md`). Phase 2 (Dashboard wiring finishers) is now fully complete: items 7-11 all landed, item 9 was rescoped as already-done. Ready to move into Phase 3 (Scheduled background tasks).
- **Items shipped:**
  - **Item 10 (Four new alert rules):** new `backend/apps/notifications/alert_rules.py` module with four named helpers (`alert_performance_mode_reverted`, `alert_helper_node_offline`, `alert_checkpoint_cap_hit`, `alert_gpu_fallback_to_cpu`). Each wraps the existing `emit_operator_alert` pattern so the frontend dedupe, cooldown, WebSocket fan-out, and alert detail route all work unchanged. The GPU fallback helper is wired live: when `_resolve_device()` in `backend/apps/pipeline/services/embeddings.py` drops from HIGH_PERFORMANCE to CPU because CUDA is unavailable or torch is missing, the alert now fires. The other three helpers are ready for their owning Celery tasks (items 12-14 auto-revert beats, item 19 checkpoint pruner, future helper-heartbeat check) to call them.
  - **Item 11 (Jobs Resource-Aware Scheduling UI):** new scheduling banner above the Jobs page tabs, built as a 2-column grid that collapses at 1080px. Left card reuses the existing live `SystemMetricsComponent` (CPU / RAM / GPU / VRAM / GPU temp on a 10-second poll) so no duplicate endpoints or polling logic. Right card is the new `SchedulingPolicyCardComponent` (static reference) — summarises Heavy / Medium / Light weight classes, evening 21:00-22:30 UTC window, 30-second stagger rule, and 76 °C GPU ceiling, all sourced from `docs/PERFORMANCE.md` §§4-6. Collapsible accordion lists example tasks in each class.
- **Intentional files changed:**
  - `backend/apps/notifications/alert_rules.py` (new - 4 named rule helpers)
  - `backend/apps/pipeline/services/embeddings.py` (+`_emit_gpu_fallback_alert` hook inside `_resolve_device`)
  - `frontend/src/app/jobs/scheduling-policy-card/scheduling-policy-card.component.ts` (new)
  - `frontend/src/app/jobs/jobs.component.ts` (+SystemMetricsComponent and SchedulingPolicyCardComponent imports)
  - `frontend/src/app/jobs/jobs.component.html` (render `<app-system-metrics>` + `<app-scheduling-policy-card>` above `.jobs-layout`)
  - `frontend/src/app/jobs/jobs.component.scss` (+`.jobs-scheduling-banner` 2-column grid, collapses at 1080px)
  - `AI-CONTEXT.md` (this note)
- **Reused, not duplicated:** `emit_operator_alert`, `OperatorAlert.SEVERITY_*` constants, `OperatorAlert.AREA_*` constants, `SystemMetricsComponent`, `MatCardModule`, `MatExpansionModule`, `MatChipsModule`. No new polling, no new API endpoints, no new dialog components.
- **Session Gate compliance:**
  - Read `AI-CONTEXT.md`, `docs/reports/REPORT-REGISTRY.md`, `frontend/FRONTEND-RULES.md`, `AGENTS.md`, `docs/PERFORMANCE.md` §§4-6 before writing code.
  - RPT-001 (5 open findings in ranking/attribution/auto-tuning) does not overlap with this session's surface (notifications service + Jobs page layout). No new issues logged.
  - Layout Precision Rules A-D respected on the new Jobs banner: chips have 16px clearance, cards keep 24px inner padding, compound labels use bullet separators. No hex colors, no gradients, spacing on the 4px grid.
- **Verification that passed:**
  - Docker Angular dev server recompiled cleanly (component + stylesheet update pushed to clients).
  - Backend import check in Docker shell: all 4 alert helpers importable from `apps.notifications.alert_rules`.
  - End-to-end alert smoke test: fired `alert_gpu_fallback_to_cpu(reason='verification-test')` via `manage.py shell` -> new OperatorAlert row created with `dedupe_key=gpu_fallback:verification-test`, `severity=warning`, `title='GPU unavailable - fell back to CPU'`. Verified in Chrome against `http://localhost:4200/alerts` — alert appears at top of feed with correct message, source area chip "system", event type "system.gpu_fallback", and "UNREAD" status. Test alert deleted afterwards (2 rows cleaned).
  - End-to-end UI check in Chrome against `http://localhost:4200/jobs`: both banner cards render side-by-side. System Load shows live CPU 0%, RAM 27% (2,958 / 11,962 MB), GPU VRAM 10% (601 / 6,144 MB), GPU temp 77 °C with red warning triangle. Scheduling Policy shows HEAVY/MEDIUM/LIGHT chips with the rule text, evening window note, 30-second stagger, 76 °C ceiling, plus the collapsible "Example tasks in each class" drawer. No overflow, no truncation, no alignment drift.
- **Known follow-ups (not done this session):**
  - Per-row "why is this job waiting" indicator inside the Queue tab. Needs backend support (job_type -> weight_class -> current scheduler state) and is deferred until the ownership-locking model work in plan item 18 lands — the data to answer the question properly will come from there.
  - Alert helpers for rules (a), (b), (c) will wire automatically when items 12-14 (auto-revert beats), items 16-18 (Quarantine + Helper routing), and item 19 (checkpoint pruner) ship.
- **Changes committed:** No - pending user review and explicit approval. CLAUDE.md only-commit-when-asked rule applies.

### 2026-04-14 - Phase 2 items 7 & 8, Item 2 polish, Runtime truncation fix, Rescopes (Claude)

- **AI/tool:** Claude
- **What was done:** Second work slice of the Prompt X plan (`.claude/plans/mossy-gliding-deer.md`). Shipped two Phase 2 items (Fix Runbooks Strip, Time-Bound Chips), finished Phase 1 item 2 (click-to-expand health dot), fixed a user-reported truncation bug on the Runtime card, and formally rescoped two items that turned out to already be built.
- **Items shipped:**
  - **Item 2 (Health Score Dot click-to-expand):** the toolbar status dot is now wrapped in a proper button + `mat-menu` trigger. Clicking it opens a popover with an inline `HealthBanner` (severity mapped from system_status), a stats list (total services, issues, last check), and a "View full health dashboard" deep-link button that uses the existing `appScrollHighlight="services-section"` pattern. Keyboard + ARIA are proper now (was a bare `<div>` before).
  - **Item 7 (Fix Runbooks Strip):** new `FixRunbooksStripComponent` on the Dashboard, visible only when `data.system_health.status !== 'healthy'` or quarantine count > 0, otherwise completely hidden. Picks the relevant runbooks from the existing `RUNBOOK_LIBRARY` (`recheck-health-services`, `restart-stuck-pipeline`, `reset-quarantined-job`) and opens the existing `RunbookDialogComponent`. Warning-tinted surface, no new runbook dialog built.
  - **Item 8 (Time-Bound Chips on Performance Mode):** added three chips ("Stay on", "Until I come back", "Until tonight ends") that appear only when `currentMode === 'high'` and hide otherwise. Selection persists via `localStorage` with an inline hint explaining backend enforcement will land with the scheduler update (plan items 12-14). No backend change yet.
- **UI / UX polish in the same slice:**
  - Fixed the Runtime card "Change Performance Mode" button — it was wrapping across two lines and looked unprofessional. Shortened to "Adjust Mode" with `white-space: nowrap` hardening. One line, one icon, one label.
  - The system-health popover styles were initially placed in `app.component.scss` but that ships with view-encapsulation so the rules never reached CDK-overlay content. Moved them to `frontend/src/styles.scss` under `.mat-mdc-menu-panel.system-health-menu` where they apply correctly.
- **Rescopes (already-done, no new work needed):**
  - **Plan item 9 (Route Transition Animation):** FULLY DONE. Lives at `frontend/src/app/shared/animations/route-transition.animation.ts`, imported and applied in `app.component.ts` / `app.component.html`. 200ms fade + 8px translateY on route change. Marking item 9 as complete in the plan.
  - **Plan item 6 (Activity Feed on Dashboard):** UI LAYER DONE. `dashboard.component.html` lines 240-266 already render an Activity Feed card wired to `PulseService.SystemEvent` events via a subscription. Marking item 6 as partial-done — the backend side (`UserActivityLog` model with a 90-day prune rule) still needs the formal feature spec before any DB work.
- **Intentional files changed:**
  - `frontend/src/app/app.component.ts` (+HealthBanner import, +healthSummary state, +healthMenuSeverity/Message getters)
  - `frontend/src/app/app.component.html` (status dot → button + mat-menu with HealthBanner + stats + deep-link)
  - `frontend/src/app/app.component.scss` (status-dot-btn wrapper; deleted system-health-menu rules after moving them)
  - `frontend/src/styles.scss` (+global `.mat-mdc-menu-panel.system-health-menu` rules — mat-menu renders in CDK overlay so styles must be global)
  - `frontend/src/app/dashboard/runtime-mode/runtime-mode.component.ts` (button label shortened to "Adjust Mode"; +nowrap rule)
  - `frontend/src/app/dashboard/fix-runbooks-strip/fix-runbooks-strip.component.ts` (new)
  - `frontend/src/app/dashboard/dashboard.component.ts` (+FixRunbooksStripComponent import)
  - `frontend/src/app/dashboard/dashboard.component.html` (render `<app-fix-runbooks-strip>` between hero and desk rows)
  - `frontend/src/app/dashboard/performance-mode/performance-mode.component.ts` (+expiry signal, +setExpiry method, +time-bound chip row + styles)
  - `AI-CONTEXT.md` (this note)
- **Reused, not duplicated:** `RUNBOOK_LIBRARY`, `RunbookDialogComponent`, `HealthBannerComponent`, `ScrollHighlightDirective`, `HealthSummary` interface, the existing `mat-mdc-menu-panel.ga4-menu` class convention. No new services created where an existing one fits.
- **Session Gate compliance:**
  - Read `AI-CONTEXT.md`, `docs/reports/REPORT-REGISTRY.md`, `frontend/FRONTEND-RULES.md`, `AGENTS.md` before writing code.
  - RPT-001 (5 open findings in ranking/attribution/auto-tuning) does not overlap with this session's surface (Dashboard UI + toolbar). No new issues found or logged.
  - Layout Precision Rules A-D respected: the new chips and runbook buttons have 16px edge clearance, cards keep 24px inner padding, compound labels use bullet separators.
  - Tokens only, no hex. GA4 M3 spacing/color variables used throughout. No new `box-shadow` on cards at rest. No `::ng-deep` — the cross-scope CSS moved to the global stylesheet by design.
- **Verification that passed:**
  - Docker Angular dev server recompiled after each save without errors.
  - End-to-end in Chrome against the running Docker instance:
    - Runtime card button now renders "Adjust Mode" on one line (no truncation).
    - Toolbar health dot → click → popover opens with red HealthBanner "4 services are down or in error.", stats 37 / 4 / 4:14:26 9:34 PM, full-width "View full health dashboard" button. Confirmed the popover styles applied after moving them global.
    - Fix Runbooks Strip renders between hero and desk rows because system health is "down"; shows "Restart stuck pipeline" and "Re-check all health services" buttons; would hide when status becomes healthy.
    - High Performance Now confirm dialog → "Yes, switch" → time-bound chips appear with "Stay on" active by default; clicking "Until tonight ends" switches the active chip and shows the local-storage hint; reverting to Balanced hides the chip row completely.
- **Known follow-ups (not done this session):**
  - **Plan item 10 (Four new alert rules):** still fully missing.
  - **Plan item 11 (Jobs Resource-Aware Scheduling UI):** still fully missing.
  - **Backend for item 8 chips:** enforcement is plan items 12-14 (Celery-beat auto-revert, activity-based revert, 6 AM revert). UI now stores intent in localStorage; when the beat tasks land, replace localStorage write with API call to `/api/settings/runtime/switch/` with the `expiry` field.
  - **Item 6 Activity Feed backend:** UI wired to `PulseService.SystemEvent` today, but the formal `UserActivityLog` model + prune rule in `BUSINESS-LOGIC-CHECKLIST.md` §6 has not been specced yet.
  - **Cosmetic (low priority):** the `ConfirmHighPerformanceDialogComponent` content rendered slightly translucent during the verification screenshot (Mat Dialog scrim behavior). Worth a minor styling pass in a later session.
- **Changes committed:** No - pending user review and explicit approval. CLAUDE.md only-commit-when-asked rule applies.

### 2026-04-14 - Command Palette (Ctrl+K / Cmd+K) - Phase 1 item 1 of Prompt X plan (Claude)

- **AI/tool:** Claude
- **What was done:** Shipped the global Command Palette - first of 31 items in the user-approved Prompt X plan at `.claude/plans/mossy-gliding-deer.md` (Phase 1 = shell-level noob quality-of-life). Press Ctrl+K (Windows/Linux) or Cmd+K (Mac) from anywhere in the app to open a search-as-you-type palette. Each result routes to the right page, triggers the existing `ScrollHighlightService` arrival spotlight, and closes the dialog. Multi-token queries are supported (e.g. "perf mode" -> "Change Performance Mode"). All navigation delegates to the existing `NavigationCoordinatorService` so behaviour matches other deep-links in the app.
- **Intentional files changed:**
  - `frontend/src/app/shared/components/command-palette/command-palette.component.ts` (new)
  - `frontend/src/app/shared/services/command-palette.service.ts` (new)
  - `frontend/src/app/shared/services/command-palette.commands.ts` (new - static command registry)
  - `frontend/src/app/shared/index.ts` (new exports)
  - `frontend/src/app/app.component.ts` (`HostListener` for Ctrl+K / Cmd+K; inject `CommandPaletteService`)
  - `AI-CONTEXT.md` (this note)
- **Reused, not duplicated:** `NavigationCoordinatorService`, `ScrollHighlightService`, `DeepLinkSpotlightDirective`, the existing GA4 theme tokens (`--space-*`, `--spacing-*`, `--color-blue-50`, `--card-border`, etc.). Dialog uses `mat-dialog`, list uses `mat-nav-list` - Angular Material only, no custom components.
- **Session Gate compliance:**
  - Read `AI-CONTEXT.md`, `docs/reports/REPORT-REGISTRY.md`, `frontend/FRONTEND-RULES.md`, `AGENTS.md` before writing code.
  - RPT-001 has 5 open findings in ranking/attribution/auto-tuning - none overlap with frontend shared shell work. No conflict to skip or flag.
  - ISS-003 (FAISS startup side-effect) is backend - not touched.
  - No new backend migrations, no ranking logic touched, no hot-path change.
- **Verification that passed:**
  - Docker Angular dev server (port 4200, already running) hot-rebuilt after every save: "Application bundle generation complete."
  - End-to-end in Chrome (Claude in Chrome): Ctrl+K opened the palette from `/health`; typed "perf mode"; Enter routed to `/dashboard#performance-mode`; inspected DOM shows `scroll-highlight` class applied to `#performance-mode`; page scrolled so the Performance Mode card is centered.
  - No console errors, no new compiler errors introduced (pre-existing NG8113 unused-import warnings from other components are unrelated).
- **Known follow-ups (not done in this session):**
  - Only 2 deep-link commands (performance mode, service health) shipped in the initial registry. Rest of the 14 routes are listed as Navigation-level commands. Adding more deep-links (Quarantine tab, Queue tab, Settings helpers, etc.) can grow `command-palette.commands.ts` without touching the component.
  - Plan items 2 (Health Score Dot) and 9 (Route transition animation) appear to already exist in the app shell. I noted this to the user during exploration; both should be re-examined when those phases begin.
- **Changes committed:** No - pending user review and explicit approval. CLAUDE.md only-commit-when-asked rule applies.

### 2026-04-14 - Frontend server error sweep (Codex)

- **AI/tool:** Codex
- **What was done:** Investigated the frontend-reported server errors against the running stack, reproduced the failing API calls, and fixed the backend/frontend mismatches causing them. Also fixed a frontend Docker build failure uncovered during the repo-mandated `docker compose build`.
- **Intentional files changed:**
  - `backend/apps/api/urls.py`
  - `backend/apps/health/tests.py`
  - `backend/apps/notifications/tests.py`
  - `backend/apps/notifications/urls.py`
  - `backend/apps/notifications/views.py`
  - `frontend/Dockerfile`
  - `frontend/src/app/alerts/alert-detail/alert-detail.component.ts`
  - `frontend/src/app/core/services/notification.service.ts`
  - `docs/reports/REPORT-REGISTRY.md`
  - `AI-CONTEXT.md`
- **Key fixes:**
  - Moved the explicit `/api/health/disk/` and `/api/health/gpu/` routes ahead of the router include so Django no longer routes them into the generic health viewset detail path.
  - Added `GET /api/notifications/alerts/<uuid>/` and updated the alert detail screen to load alerts through `NotificationService` instead of calling the nonexistent `/api/notifications/<uuid>/` endpoint.
  - Added backend regression tests covering the health disk/gpu endpoints and the alert detail endpoint.
  - Replaced the frontend Dockerfile `useradd -u 1000 appuser` step with the existing `node` user because the base `node:22-slim` image already reserves UID 1000 and the old build step could fail every required Docker build.
- **Verification that passed:**
  - `powershell -ExecutionPolicy Bypass -File .\scripts\test-frontend.ps1`
  - `powershell -ExecutionPolicy Bypass -File .\scripts\build-frontend.ps1`
  - `docker compose exec backend python manage.py test apps.health.tests apps.notifications.tests`
  - `docker compose build`
  - `docker compose exec backend python manage.py showmigrations`
  - `docker compose exec backend python manage.py makemigrations --check --dry-run`
  - `docker image prune -f`
- **Remaining blocker / note:**
  - `docker compose exec backend python -m ruff check ...` is still unavailable because `ruff` is not installed in the backend container. I did not change lint tooling in this session.
  - The Docker-side migration checks still emit the pre-existing Django startup warning already logged as `ISS-003`; this session did not change that FAISS initialization path.
- **Changes committed:** Yes - committed and pushed in this session. The worktree was already dirty before this session (`AI-CONTEXT.md`, `FEATURE-REQUESTS.md`, and `docs/specs/fr098-dominant-passage-centrality.md`), so the commit stages only this session's server-error fix slice and leaves the unrelated FR-098 docs uncommitted.

### 2026-04-13 — FR-098 Dominant Passage Centrality spec (Claude)

- **AI/tool:** Claude
- **What was done:** Created full spec for FR-098 (Dominant Passage Centrality) and added it to FEATURE-REQUESTS.md. No implementation code written — spec and backlog registration only.
- **Intentional files changed:**
  - `docs/specs/fr098-dominant-passage-centrality.md` (new — full spec with Hearst 1997 TextTiling + Erkan & Radev 2004 LexRank + patent US7752534B2)
  - `FEATURE-REQUESTS.md` (added FR-098 entry after FR-097)
  - `AI-CONTEXT.md` (dashboard counts updated, this session note)
- **Changes committed:** No — pending user review.
- **Key decisions:**
  - Input is `distilled_text` only (not title, not total page text) to stay distinct from FR-054.
  - Signal is destination-intrinsic (host-independent) — computed once per destination at index time.
  - Default `ranking_weight = 0.0` — diagnostics-only until operator validates.
  - TextTiling for segmentation, LexRank (TF-IDF + PageRank) for sentence centrality — no ML model needed.

### 2026-04-12 — QA sweep (Claude)

- **AI/tool:** Claude
- **What was done:** Full QA pass of the running app. No code was changed. 8 new issues logged in REPORT-REGISTRY.md (ISS-004 through ISS-011).
- **Intentional files changed:** `docs/reports/REPORT-REGISTRY.md` (new issues logged), `AI-CONTEXT.md` (this note)
- **Changes committed:** No — documentation only, pending user review.
- **Key findings:**
  - **ISS-005 (High):** Nginx on port 80 is completely broken — redirect loop because Angular build files are never placed into the `frontend_dist` volume. App only reachable on port 4200.
  - **ISS-006 (High):** `GET /api/system/status/weights/` → 500 every time. `WeightDiagnosticsView` calls `check_native_scoring()` and does `.get()` on its return value, but `check_native_scoring()` returns a tuple, not a dict. Fix: unpack the 4-tuple.
  - **ISS-010 (High):** Disk at **93.2% full** — real infrastructure risk before next build or pipeline run.
  - **ISS-011 (Medium):** 101 unread alerts, all duplicates of "api sync appears stuck" — stalled jobs never cleaned up, no dedup in alert generation.
  - **ISS-009 (Medium):** C# health check still shows as red error in System Health despite C# being decommissioned.
  - **ISS-007 (Medium):** `/api/benchmarks/latest/` returns 404 instead of empty response — "Resource not found" toast on every Performance page load.
  - **ISS-004 (Low):** `celery-beat` shows unhealthy in Docker but is working fine — false positive in health check script.
  - **ISS-008 (Low):** Performance page subtitle still says "C#" — stale copy after decommission.
- **Test results:** 189 Django tests pass (AI-CONTEXT.md says 195 — 6 fewer, worth checking). Angular test output was truncated before final count.
- **Skipped fixes:** All issues documented only — not fixed in this session per QA-only scope.

### 2026-04-13 - Remove stale C# mentions from local verification checks

- AI/tool: Codex
- Intentional files changed:
  - `.githooks/pre-push`
  - `scripts/lint-all.ps1`
  - `scripts/setup-dev.ps1`
  - `scripts/verify.ps1`
  - `AI-CONTEXT.md`
- What changed:
  - Confirmed `.github/workflows/ci.yml` is already C#-free, so no GitHub Actions job needed removal.
  - Removed stale C# wording from the local verification banner and pre-push hook comment so local checks match the current Python/C++ runtime stack.
  - Removed dead `.cs` handling from the generic lint helper paths now that no tracked C# files remain.
  - Removed the stale `scripts\test-http-worker.ps1` tip from setup instructions and dropped the obsolete `.NET` sandbox note.
- Verification that passed:
  - `rg` search across `.github`, `.githooks`, and `scripts` for `C#`, `HttpWorker`, `test-http-worker`, `.cs`, and related stale runtime terms
  - PowerShell parser validation for `scripts/verify.ps1`, `scripts/lint-all.ps1`, and `scripts/setup-dev.ps1`
- Commit/push state:
  - Changes are currently uncommitted.

### 2026-04-12 - Backend startup hardening for drf-spectacular and local SQLite test state

- AI/tool: Codex
- Intentional files changed:
  - `backend/config/settings/base.py`
  - `backend/config/urls.py`
  - `backend/Dockerfile`
  - `backend/apps/plugins/apps.py`
  - `backend/apps/plugins/tests.py` (new)
  - `docker-compose.yml`
  - `scripts/setup-dev.ps1`
- What changed:
  - Reverted the temporary optional-schema fallback. `drf_spectacular` is required again in Django settings, and the schema routes are always registered.
  - Added fail-fast dependency verification to the backend Docker image build, backend container startup, celery worker startup, and local `scripts/setup-dev.ps1` so a missing `drf_spectacular` install fails immediately and clearly.
  - Plugin autoload now skips all `.test` settings sessions plus migration-oriented commands like `showmigrations`, preventing plugin DB queries from firing during local SQLite maintenance commands.
  - `scripts/setup-dev.ps1` now migrates the local SQLite test database automatically after dependency installation so future local verification starts from a fully migrated `backend/test.sqlite3`.
  - Ran the SQLite test-settings migration locally so `showmigrations --settings=config.settings.test` now reports a fully applied local schema instead of an incomplete state.
- Verification that passed:
  - `.venv\Scripts\python.exe manage.py test apps.plugins.tests apps.pipeline.tests.TextCleanerServiceTests --settings=config.settings.test`
  - `.venv\Scripts\python.exe -m ruff check backend/config/settings/base.py backend/config/urls.py backend/apps/plugins/apps.py backend/apps/plugins/tests.py backend/apps/pipeline/services/text_cleaner.py backend/apps/pipeline/tests.py`
  - PowerShell parser check for `scripts/setup-dev.ps1`
  - `.venv\Scripts\python.exe manage.py migrate --settings=config.settings.test --noinput`
  - `.venv\Scripts\python.exe manage.py showmigrations --settings=config.settings.test`
  - `.venv\Scripts\python.exe manage.py makemigrations --check --dry-run --settings=config.settings.test`
  - `docker compose up -d --build backend celery-worker`
  - `docker compose exec backend python manage.py showmigrations`
  - `docker compose exec backend python manage.py makemigrations --check --dry-run`
  - `docker image prune -f`
  - `powershell -ExecutionPolicy Bypass -File scripts\prune-verification-artifacts.ps1`
- Verification blockers / notes:
  - The first Docker migration check reproduced the real failure: the running backend container was missing `drf_spectacular`. Rebuilding and recreating `backend` plus `celery-worker` fixed that environment, and the required Docker-side migration checks passed afterward.
  - Docker-side migration commands still emit Django's app-startup database warning because `PipelineConfig.ready()` builds the FAISS index at startup. Logged as open issue `ISS-003` in `docs/reports/REPORT-REGISTRY.md`.
- Commit/push state:
  - Changes are currently uncommitted.
  - Left unrelated dirty deletions untouched: `docs/reports/2026-04-11-fix-cs-import-page-cap.md`, `docs/reports/2026-04-11-fix-feedrerank-exposure-parity.md`, and `docs/reports/repo-business-logic-audit-2026-04-11.md`

### 2026-04-12 - Python-only import noise stripping for non-content chrome

### 2026-04-12 - Automatic safe Docker cleanup plus idle-only disk compaction

- AI/tool: Codex
- Intentional files changed:
  - `docker_cleanup.ps1`
  - `docker_compact_vhd.ps1`
  - `register_cleanup_task.ps1`
  - `%USERPROFILE%\.wslconfig` (local machine setting, outside repo)
- What changed:
  - Tightened the repo's Docker cleanup script so it now waits for Docker Desktop to become ready instead of failing early at login.
  - Changed cleanup to prune all unused Docker build cache plus dangling images only, keeping volumes and persisted app data untouched.
  - Added a separate `docker_compact_vhd.ps1` helper that only attempts Docker VHD compaction when no containers are running, so automatic disk reclaim stays on the safe side.
  - Added a second scheduled cleanup path on the local machine: the pre-existing startup cleanup task still exists, and a new every-2-days cleanup task plus a new every-2-days idle-only compaction task were registered locally.
  - Enabled WSL `autoMemoryReclaim=gradual` in `%USERPROFILE%\.wslconfig` while leaving Docker's current VHD in non-sparse mode.
- Verification that passed:
  - PowerShell parser validation for `docker_cleanup.ps1`, `docker_compact_vhd.ps1`, and `register_cleanup_task.ps1`
  - Manual safe cleanup run via `powershell -ExecutionPolicy Bypass -File .\docker_cleanup.ps1`
  - `docker system df` after cleanup: build cache reduced from `15.58GB` to `0B`; Docker image usage reduced to `17.79GB`
  - Task registration confirmed for:
    - `XF Linker V2 - Docker Cleanup Every 2 Days`
    - `XF Linker V2 - Docker Disk Compaction`
- Verification blockers / notes:
  - The old task `XF Linker V2 - Docker Cleanup on Startup` could be read but not overwritten due Windows scheduled-task permissions, so it was left in place as an extra safe cleanup pass.
  - Docker's VHD remains non-sparse (`fsutil sparse queryflag ...docker_data.vhdx` reports `NOT set as sparse`), so disk-file shrink depends on the new idle-only compaction task getting a window where no containers are running.
- Commit/push state:
  - Changes are currently uncommitted.

### 2026-04-12 - Python-only import noise stripping for non-content chrome

- AI/tool: Codex
- Intentional files changed:
  - `backend/apps/pipeline/services/text_cleaner.py`
  - `backend/apps/pipeline/tests.py`
- What changed:
  - Expanded the Python import cleaner so imported text now strips more non-content noise before hashing and distillation.
  - Added removal for signature-style BBCode blocks (`[SIGPIC]...[/SIGPIC]`), generic HTML chrome blocks identified by class/id keywords, semantic HTML chrome sections (`nav`, `header`, `footer`, `aside`, `form`), and short leftover boilerplate lines like `Read next`, `Table of Contents`, `Subscribe`, `Share this`, `Last edited by`, and login-wall prompts.
  - Added focused backend tests covering HTML noise blocks, signature/quote/edit noise, and leftover label-style junk.
- Verification that passed:
  - `.venv\Scripts\python.exe manage.py test apps.pipeline.tests.TextCleanerServiceTests --settings=config.settings.test`
  - `.venv\Scripts\python.exe manage.py makemigrations --check --dry-run --settings=config.settings.test`
  - `.venv\Scripts\python.exe -m ruff check backend/apps/pipeline/services/text_cleaner.py backend/apps/pipeline/tests.py`
- Verification blockers / notes:
  - `.venv\Scripts\python.exe manage.py showmigrations --settings=config.settings.test` reported many unapplied migrations in the local SQLite test database and plugin-startup warnings because that local DB is not a full migrated app state.
  - `docker compose exec backend python manage.py showmigrations` and `... makemigrations --check --dry-run` were attempted but the backend container environment failed startup with `ModuleNotFoundError: No module named 'drf_spectacular'`, so the repo-mandated container migration check could not be completed in this session.
- Commit/push state:
  - Changes are currently uncommitted.
  - Left unrelated dirty deletions untouched: `docs/reports/2026-04-11-fix-cs-import-page-cap.md`, `docs/reports/2026-04-11-fix-feedrerank-exposure-parity.md`, and `docs/reports/repo-business-logic-audit-2026-04-11.md`

### 2026-04-12 - Remove stale C# test references after runtime decommission

- AI/tool: Codex
- Intentional files changed:
  - `AI-CONTEXT.md`
- What changed:
  - Removed stale references to the deleted `services/http-worker/tests/HttpWorker.Tests/EngagementSignalTests.cs` file.
  - Removed the obsolete note telling future sessions to run `dotnet build` and `dotnet test` for that C# slice.
  - Confirmed the old GitHub Actions `csharp-test` job is already absent in the current working tree, and no tracked `.csproj` or C# test files remain in the repo.
- Verification that passed:
  - `git ls-files` search for tracked `.csproj`, `.sln`, and `.cs` files
  - `rg` search for `HttpWorker.Tests`, `EngagementSignalTests.cs`, `dotnet build`, and `dotnet test`
- Commit/push state:
  - Changes are currently uncommitted.
  - Left unrelated dirty files untouched: `.github/workflows/ci.yml`, `scripts/dev-tools.ps1`, and `scripts/prune-verification-artifacts.ps1`

### 2026-04-11 - Merge branch into master and require branch disclosure

- AI/tool: Codex
- Intentional files changed:
  - `AI-CONTEXT.md`
- What changed:
  - Fast-forwarded local `master` to `origin/codex/report-registry-chat-notices` so the committed work from that branch is now also on `master`.
  - Added a strict branch-transparency rule: an AI must tell the user in chat before creating, switching to, or pushing a separate branch.
  - Added a plain-English disclosure requirement that branch work stays separate from `master` until it is merged.
- Verification that passed:
  - `git fetch origin`
  - `git merge --ff-only origin/codex/report-registry-chat-notices`
  - Documentation review only for the new branch-disclosure rule.
- Commit/push state:
  - Committed and pushed on `master` in `66555fe` (`docs: require branch disclosure before branch creation (docs-only, no build required)`).
  - Left the unrelated dirty file untouched: `docs/reports/repo-business-logic-audit-2026-04-11.md`

### 2026-04-11 - Chat notification rule for report-registry overlaps

- AI/tool: Codex
- Intentional files changed:
  - `AI-CONTEXT.md`
  - `docs/reports/REPORT-REGISTRY.md`
  - `AGENTS.md`
  - `CLAUDE.md`
- What changed:
  - Added an explicit repo rule that any AI who sees an open or reopened Report Registry finding in the same work area must tell the user in chat before writing code.
  - Kept the existing written-justification requirement in `AI-CONTEXT.md`, but made chat notification mandatory as well so the user is not expected to discover overlaps by reading docs.
  - Tightened the wording further so silence is explicitly forbidden: an AI may not notice a relevant open or reopened finding and continue work without telling the user in chat first.
- Verification that passed:
  - Documentation review only.
- Commit/push state:
  - Changes are currently uncommitted.

### 2026-04-06 - Phase 27 / FR-024: TikTok Read-Through Rate Engagement Signal

- AI/tool: Claude
- Intentional files changed:
  - `services/http-worker/src/HttpWorker.Core/Contracts/V1/GraphSyncContracts.cs`
  - `services/http-worker/src/HttpWorker.Services/HttpWorkerOptions.cs`
  - `services/http-worker/src/HttpWorker.Core/Interfaces/IPostgresRuntimeStore.cs`
  - `services/http-worker/src/HttpWorker.Services/PostgresRuntimeStore.cs`
  - `services/http-worker/src/HttpWorker.Core/Interfaces/IGraphCandidateService.cs`
  - `services/http-worker/src/HttpWorker.Services/GraphCandidateService.cs`
  - `services/http-worker/src/HttpWorker.Services/PipelineServices.cs`
  - `backend/apps/suggestions/recommended_weights.py`
  - `backend/apps/core/views.py`
  - `backend/apps/suggestions/migrations/0024_upsert_engagement_signal_preset_keys.py` (new)
  - `backend/apps/core/tests.py`
  - `frontend/src/app/settings/silo-settings.service.ts`
  - `frontend/src/app/settings/settings.component.ts`
  - `frontend/src/app/settings/settings.component.html`
  - `frontend/src/app/review/suggestion.service.ts`
  - `frontend/src/app/review/suggestion-detail-dialog.component.html`
  - `AI-CONTEXT.md`
  - `FEATURE-REQUESTS.md`
- What changed: Added `engagement_signal` as the sixth slot in the FR-021 value model (C# GraphCandidateService). Loads rolling engagement averages from `analytics_searchmetric`, word counts from `content_contentitem.distilled_text`, applies read-through rate × (1 − bounce) formula, site-wide min-max normalization in PipelineServices. Django settings API extended with 6 new `value_model.engagement_*` keys. Angular settings card shows engagement sub-section; review detail panel shows full engagement breakdown.
- Verification that passed:
  - `python backend/manage.py makemigrations --check --dry-run --settings=config.settings.test` — no drift
  - `python backend/manage.py test apps.core.tests.ValueModelEngagementSettingsTests --settings=config.settings.test` — 5 tests, OK
  - `scripts/build-frontend.ps1` — build succeeded, no warnings
  - `scripts/test-frontend.ps1` — 18 tests, all SUCCESS
- Commit/push state: Changes are currently uncommitted.

### 2026-04-04 - FR-017 Slice 5: Search Impact Reporting UI

- AI/tool: Claude
- Intentional files changed:
  - `backend/apps/analytics/serializers.py`
  - `frontend/src/app/analytics/analytics.service.ts`
  - `frontend/src/app/analytics/analytics.component.ts`
  - `frontend/src/app/analytics/analytics.component.html`
  - `frontend/src/app/analytics/analytics.component.scss`
  - `AI-CONTEXT.md`
  - `FEATURE-REQUESTS.md`
- What changed:
  - Added `source_type` and `source_label` serializer method fields to `GSCImpactSnapshotSerializer`, derived from `suggestion.destination.content_type`. No migration needed.
  - Added `source_type` and `source_label` fields to the `GSCImpactSnapshot` TypeScript interface.
  - Added `scatterChartData`, `scatterChartOptions`, `cohortBySource`, and `cohortByAnchorFamily` to the Analytics component.
  - Added `prepareScatterChart()` — groups impacts into 4 coloured Chart.js scatter datasets (positive/neutral/negative/inconclusive).
  - Added `prepareCohortData()` — builds cohort rows grouped by platform (XenForo vs WordPress) and by anchor family (first word of anchor phrase, top 10).
  - Added scatter chart card and two cohort tables (by platform, by anchor family) to the HTML, displayed above the existing applied-suggestions table when data is present.
  - Added `.impact-charts-row`, `.cohort-grid`, `.cohort-card`, and `.anchor-family-label` SCSS rules.
- Verification that passed:
  - `backend/manage.py test apps.analytics.tests --settings=config.settings.test` — 24 tests, OK
  - `scripts/build-frontend.ps1` — build succeeded (2 pre-existing SCSS budget warnings, not new)
  - `scripts/test-frontend.ps1` — 18 tests, all SUCCESS
- Commit/push state:
  - Changes are currently uncommitted.

### 2026-04-04 - Doc-only FR backlog expansion

- AI/tool: Codex
- Intentional files changed:
  - `FEATURE-REQUESTS.md`
  - `backend/apps/suggestions/recommended_weights.py`
  - `backend/apps/suggestions/migrations/0019_upsert_recommended_future_signal_keys.py`
  - `docs/specs/fr041-originality-provenance-scoring.md`
  - `docs/specs/fr042-fact-density-scoring.md`
  - `docs/specs/fr043-semantic-drift-penalty.md`
  - `docs/specs/fr044-internal-search-intensity.md`
  - `frontend/src/app/settings/settings.component.ts`
  - `AI-CONTEXT.md`
- What changed:
  - Added four future backlog items and implementation-spec drafts for:
    - `FR-041` Originality Provenance Scoring
    - `FR-042` Fact Density Scoring
    - `FR-043` Semantic Drift Penalty
    - `FR-044` Internal Search Intensity Signal
  - The specs were written from repo review plus web research on patents, papers, and scoring math.
  - Added forward-declared recommended preset keys for `FR-041` through `FR-044` with conservative starting weights so implementation can later wire them in without inventing first-pass defaults.
  - Follow-up pass added the missing `FR-040` preset keys, a `suggestions` migration to upsert `FR-040` through `FR-044` keys into the `Recommended` preset for existing installs, and forward-looking tooltip / preset-key metadata for `FR-040` through `FR-044` in Angular Settings without adding placeholder UI cards.
  - The active delivery target is still unchanged: `Phase 20 / FR-017 Slice 4`.
- Verification that passed:
  - Documentation-only review of existing models, pipeline boundaries, and backlog/spec consistency.
- Important handoff:
  - The git worktree was already dirty before this doc-only session due to unrelated implementation work in backend and `services/http-worker/`. Those files were not reverted or modified by this documentation pass.
  - No code build or Docker verification was run because this session changed only documentation/backlog files.

- AI/tool: Codex
- Intentional files changed:
  - `docker-compose.yml`
  - `backend/apps/analytics/gsc_client.py`
  - `backend/apps/analytics/impact_engine.py`
  - `backend/apps/analytics/sync.py`
  - `backend/apps/analytics/tests.py`
  - `backend/apps/analytics/urls.py`
  - `backend/apps/analytics/views.py`
  - `frontend/package.json`
  - `frontend/src/app/analytics/analytics.component.spec.ts`
  - `frontend/src/app/settings/settings.component.html`
  - `frontend/src/app/settings/settings.component.spec.ts`
  - `frontend/src/app/settings/settings.component.ts`
  - `frontend/src/app/settings/silo-settings.service.ts`
  - `scripts/dev-tools.ps1`
  - `scripts/test-frontend.ps1`
  - `scripts/verify.ps1`
  - `services/http-worker/src/HttpWorker.Services/GSCAttributionService.cs`
  - `AI-CONTEXT.md`
  - `FEATURE-REQUESTS.md`
- What changed:
  - Replaced the duplicated GA4/GSC/Google Cloud OAuth setup blocks with one shared `Google Connection` card in Settings, so one Google account can authorize both GA4 and GSC.
  - Added a dedicated backend settings endpoint for Google OAuth app credentials and repaired the one-time Google login flow so saved client credentials and refresh tokens are handled consistently.
  - Fixed the broken GA4 sync path, stabilized Matomo sync, repaired GSC query ingestion, and added score refresh logic so imported analytics now update `content_value_score`.
  - Fixed the Python keyword-impact math bug and the C# GSC attribution off-by-one window bug.
  - Completed FR-017 Slice 3 by landing the Python GSC performance importer with 48-hour lag-safe upserts and query-level row ingestion.
  - Added a universal frontend verification path so `scripts/test-frontend.ps1` and `scripts/build-frontend.ps1` automatically fall back to Docker when host Node is missing. Future AIs can also force Docker mode with `XF_FRONTEND_USE_DOCKER=1`.
  - Repaired stale Angular specs so the shared frontend test wrapper matches the current Settings and Analytics screens.
  - Increased the frontend Docker memory cap to 2 GB so Docker-based Angular test runs do not get killed during Chrome startup.
- Verification that passed:
  - `backend/manage.py test apps.analytics.tests --settings=config.settings.test`
  - `docker-compose build`
  - `docker-compose up -d`
  - `powershell -ExecutionPolicy Bypass -File scripts/test-frontend.ps1`
  - `powershell -ExecutionPolicy Bypass -File scripts/test-frontend.ps1` with `XF_FRONTEND_USE_DOCKER=1`
  - `powershell -ExecutionPolicy Bypass -File scripts/build-frontend.ps1` with `XF_FRONTEND_USE_DOCKER=1`
- Commit/push state:
  - Changes are currently uncommitted in the local worktree.

### 2026-04-04 - Code Review & Integrity Fixes

- AI/tool: Antigravity
- Intentional files changed:
- Commit/push state:
  - Changes will be committed and pushed during this session.

| Item | Why needed | State |
|---|---|---|
| XenForo base URL + API key | live XenForo sync and verification | Already wired; operator must supply real values in env/settings |
| WordPress base URL + optional username/app password | live WordPress sync; private content requires Application Password auth | UI/API shipped; operator must supply real values in env/settings |
| Local runtimes | build/test execution | Direct installed Python 3.12.10 and direct Node paths work for verification; the usual `py`/`python` launcher aliases and `.venv` launcher still need cleanup if a future session wants the shorter commands |
| **Storage & RAM** | Performance guardrails | **Postponed GPU inference (FR-029 fp16, FR-030 FAISS-GPU)** due to 16GB RAM / 40GB Disk constraints. FR-020 (Zero-Downtime Model Switching, Hot Swap & Runtime Registry) is separately queued and is not a GPU resource constraint. Current stack (Nomic embed-text-v1.5) is safe for 74k items (~2-3GB storage). |
| **ImpactReport retention** | Data hygiene guardrail | Filter expired rows using `created_at` (the only timestamp on the model). There is no separate `date` field. Any retention query must use: `ImpactReport.objects.filter(created_at__lt=cutoff).delete()` |

## Docker Build Context and .dockerignore Files

Each service uses its own subdirectory as its Docker build context. The .dockerignore files
are scoped accordingly:
- `backend/.dockerignore` — excludes pyc files, caches, scripts/, tmp/, and .env from the
  backend image layer (among others) (build context: `./backend`)
- `frontend/.dockerignore` — already present; excludes node_modules, dist, .angular,
  .git, .gitignore, README.md, Dockerfile (among others) (build context: `./frontend`)
A root-level .dockerignore is not needed because no service uses the repo root as its build
context.

## Non-Negotiable Guardrails

### Product / Workflow
- GUI-first always
- Manual review remains in the loop
- Up to one best suggestion per destination per pipeline run
- Maximum 3 internal-link suggestions per host thread
- Only scan the first 600 words of host content for insertion
- Never write directly to XenForo or WordPress databases
- Read-only API access only

### UI / Theming
- **Single Source of Truth**: `frontend/src/styles/default-theme.scss` is the only allowed theme file.
- **Strict Rule**: No AI agent (Antigravity, Claude, Codex, etc.) is permitted to create a new theme or alternative theme file. All styling must be integrated into the existing `default-theme.scss` or `styles.scss` as appropriate.
- **Material Consistency**: Use the project's custom Material theme generated in `default-theme.scss`. Do not override it with prebuilt themes (like indigo-pink) in `angular.json` or elsewhere.

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

### Docker / Disk Hygiene
- Build-once pattern is mandatory: `xf-linker-backend:latest` is shared by backend, celery-worker, and celery-beat. Never give those services their own `build:` block.
- After every `docker-compose build`, run `docker image prune -f` to remove dangling images immediately.
- Never run `docker-compose down -v` — the `-v` flag deletes the PostgreSQL volume and all embeddings. Use `docker-compose down` only (no `-v`).

### Git / Collaboration
- One narrow slice per AI session
- Start every session with `git status --short`
- Prefer ending every safe session with a clean worktree
- If the tree stays dirty, leave a clear handoff note naming the AI/tool and the exact files changed
- Commit/push only when verified as far as the environment allows
- Never force-push, rewrite history, or commit secrets

### 2026-04-13 - Safe host cleanup automation for Temp and WSL crash dumps

- AI/tool: Codex
- Intentional files changed:
  - `scripts/cleanup-host-safe.ps1`
  - `AI-CONTEXT.md`
- What changed:
  - Added a new PowerShell helper that targets only user Temp cleanup and WSL crash dumps older than a configurable age threshold.
  - Explicitly excluded Claude app data from the cleanup flow so the script cannot touch Claude caches or VM bundles.
  - Tightened the Temp sweep to exclude Docker-related Temp folders by name so daily cleanup cannot interfere with Docker scratch space.
  - Default behavior is preview-only; `-Apply` performs deletion and reports reclaimed space plus skipped locked files.
  - Ran the script once with `-Apply` for the current machine state and reclaimed about `2.24 GB` from stale Temp items without touching Claude data.
- Verification that passed:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\cleanup-host-safe.ps1`
  - `powershell -ExecutionPolicy Bypass -File .\scripts\cleanup-host-safe.ps1 -Apply`
  - `powershell -ExecutionPolicy Bypass -File .\scripts\cleanup-host-safe.ps1` after tightening Docker exclusions
- Commit/push state:
  - Changes are currently uncommitted.
