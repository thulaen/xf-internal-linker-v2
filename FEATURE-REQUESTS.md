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

## COMPLETED

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
- Local verification closure completed: Django Phase 8 test slice passes, Python 3.12 backend environment works, the Angular 20 frontend builds under Node.js 22, and `npm audit` reports zero vulnerabilities.

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

## PENDING

### FR-006 - Weighted Link Graph / Reasonable Surfer Scoring
**Requested:** 2026-03-24
**Target phase:** Phase 9
**Priority:** High
**Patent inspiration:** `US7716225B1`

- Preserve the existing `pagerank_score`.
- Add a separate weighted authority signal based on edge-level prominence/relevance features.
- Persist edge-level weighting features.
- Expose diagnostics and tuning so standard vs weighted authority can be compared.

---

### FR-007 - Link Freshness Authority
**Requested:** 2026-03-24
**Target phase:** Phase 10
**Priority:** Medium
**Patent inspiration:** `US8407231B2`

- Track first-seen and last-seen internal-link timing.
- Add a link-recency/link-growth score separate from engagement velocity.
- Expose review diagnostics and sorting/filtering for fresh vs stale authority.

---

### FR-008 - Phrase-Based Matching & Anchor Expansion
**Requested:** 2026-03-24
**Target phase:** Phase 11
**Priority:** High
**Patent inspiration:** `US7536408B2`

- Extract salient phrases from titles, distilled text, and host sentences.
- Add phrase-level relevance as a separate ranking signal.
- Expand anchor extraction beyond exact title windows with explainable phrase evidence.

---

### FR-009 - Learned Anchor Vocabulary & Corroboration
**Requested:** 2026-03-24
**Target phase:** Phase 12
**Priority:** Medium
**Patent inspiration:** `US9208229B2`

- Learn preferred anchor variants per destination from the existing internal-link graph.
- Surface canonical anchors and alternates in review.
- Allow reviewers to prefer or disallow anchor variants.

---

### FR-010 - Rare-Term Propagation Across Related Pages
**Requested:** 2026-03-24
**Target phase:** Phase 13
**Priority:** Medium
**Patent inspiration:** `US20110196861A1`

- Propagate rare, high-signal terms across nearby related pages.
- Keep propagated evidence bounded, explainable, and separate from original content.
- Use scope/silo/relationship proximity rules to avoid topic drift.

---

### FR-011 - Field-Aware Relevance Scoring
**Requested:** 2026-03-24
**Target phase:** Phase 14
**Priority:** Medium
**Patent inspiration:** `US7584221B2`

- Score title, body, scope labels, and learned anchor vocabulary separately.
- Add bounded field-level weighting and expose diagnostics/tuning.

---

### FR-012 - Click-Distance Structural Prior
**Requested:** 2026-03-24
**Target phase:** Phase 15
**Priority:** Medium
**Patent inspiration:** `US8082246B2`

- Add a soft structural prior based on click distance / shortest-path depth.
- Store it separately from authority and expose diagnostics.

---

### FR-013 - Feedback-Driven Explore/Exploit Reranking
**Requested:** 2026-03-24
**Target phase:** Phase 16
**Priority:** Medium
**Patent inspiration:** `US10102292B2`

- Add a feature-flagged post-ranking reranker using review outcomes and later analytics.
- Limit exploration to a bounded top-N window and keep it explainable.

---

### FR-014 - Near-Duplicate Destination Clustering
**Requested:** 2026-03-24
**Target phase:** Phase 17
**Priority:** Medium
**Patent inspiration:** `US7698317B2`

- Cluster near-duplicate destinations with canonical preference, soft suppression, manual override, and confidence-aware behavior.
- Do not default to cross-source canonicalization.

---

### FR-015 - Final Slate Diversity Reranking
**Requested:** 2026-03-24
**Target phase:** Phase 18
**Priority:** Medium
**Patent inspiration:** `US20070294225A1`

- Apply a late diversity reranker only after hard constraints and duplicate-family normalization.
- Stay inside a close-score window and never override hard suppression rules.

## TEMPLATE ONLY

### FR-016 - Add your next request here

Template placeholder only. Not backlog scope.

```md
### FR-00X - Short title

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

*Last updated: 2026-03-24 (Phase 8 / FR-003 completed, locally verified, and frontend audit-clean; next real target remains Phase 9 / FR-006)*
