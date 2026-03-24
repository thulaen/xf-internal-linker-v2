# Feature Requests - XF Internal Linker V2

This file tracks UI/UX feature requests from the developer.

## How this file works

| Section | What goes here |
|---|---|
| **PENDING** | Requested but not yet built. AI must surface these at every session start. |
| **IN PROGRESS** | Currently being implemented in the active phase. |
| **COMPLETED** | Done. AI must check this before implementing anything new to avoid duplication. |

**Rule:** Keep `AI-CONTEXT.md` for architecture facts. Keep this file for feature wishes.

---

## COMPLETED

### FR-005 - Link Siloing & Topical Authority Enforcement
**Completed:** 2026-03-24

- [x] `SiloGroup` model added and `ScopeItem.silo_group` now uses nullable `SET_NULL` semantics.
- [x] Silo ranking settings are persisted through `AppSetting` and exposed at `GET/PUT /api/settings/silos/`.
- [x] Pipeline ranking supports `disabled`, `prefer_same_silo`, and `strict_same_silo`.
- [x] Strict-mode suppression emits `cross_silo_blocked` diagnostics.
- [x] Backend CRUD endpoints added for silo groups, plus a safe scope-assignment patch flow.
- [x] Angular Settings now manages silo groups, scope assignments, and ranking controls.
- [x] Angular Review now shows host/destination silo labels and supports a same-silo-only filter.

---

### FR-004 - Broken Link Detection
**Completed:** 2026-03-24

- [x] `BrokenLink` model added in `apps/graph/` with UUID PK, source-content FK, URL, HTTP status, redirect URL, timestamps, reviewer status, and notes.
- [x] Migration added at `backend/apps/graph/migrations/0002_brokenlink.py`.
- [x] Broken Links admin registered with filters/search and added to the admin sidebar.
- [x] `scan_broken_links` Celery task added with:
  - HEAD -> GET fallback
  - 0.5s request throttle
  - 10,000 URL safety cap
  - `update_or_create()` persistence keyed by source content + URL
  - WebSocket progress updates on `ws/jobs/<job_id>/`
- [x] `BrokenLinkSerializer` + `BrokenLinkViewSet` added with:
  - `GET /api/broken-links/`
  - `PATCH /api/broken-links/{id}/`
  - `POST /api/broken-links/scan/`
  - `GET /api/broken-links/export-csv/`
- [x] Dashboard API now includes `open_broken_links`.
- [x] Angular `/link-health` page added with live scan progress, summary counts, status/http-status filters, paginated Material table, row actions, CSV export, and empty state.
- [x] Dashboard warning stat card and sidebar nav badge now surface open broken-link count and link to Link Health.

---

### FR-002 - Jobs Page: JSONL File Import UI
**Completed:** 2026-03-24

- Drag-and-drop zone (or click to browse) accepting `.jsonl` files only.
- Import mode selector: Full / Titles / Quick.
- "Start Import" button enabled only when a file is selected.
- Live progress bar + status message via WebSocket (`ws/jobs/<job_id>/`).
- Green success / red failure result banners.
- Recent Activity history table (source, mode, status, items synced).
- Backend: `POST /api/import/upload/` saves file, creates `SyncJob`, dispatches `import_content`.
- Backend: `GET /api/sync-jobs/` provides import job history.
- `SyncJob` model + migration added in `apps/sync/`.
- `SyncService` Angular service added in `frontend/src/app/jobs/`.

---

### FR-001 - Angular Frontend: Light Theme Default + Full Theme Customizer
**Completed:** 2026-03-24

- [x] Light theme default retained.
- [x] `AppearanceService` loads/saves config from `/api/settings/appearance/` and applies CSS vars live.
- [x] Backend `AppearanceSettingsView` added at `GET/PUT /api/settings/appearance/`.
- [x] `ThemeCustomizerComponent` implemented with:
  - primary/accent/header colors
  - font size, layout width, sidebar width, density
  - site name, footer text/toggle/color
  - logo upload + favicon upload
  - scroll-to-top toggle
  - named presets
- [x] `ScrollToTopComponent` added.
- [x] App shell wired to appearance settings, including logo/favicon behavior.
- [x] Backend logo/favicon upload endpoints added.

---

## PENDING

### FR-003 - WordPress Cross-Linking

**Requested:** 2026-03-24
**Target phase:** Phase 5 (after XenForo sync is stable)
**Priority:** Medium

### What's wanted
Suggest internal links between XenForo threads/resources and WordPress posts/pages.
A forum thread about a product should be able to link to the WordPress review of that
product, and vice versa. All suggestions go through the same manual review workflow -
nothing is applied automatically.

### Specific controls / behaviour
- WordPress content appears in the same scope/content browser as XenForo content.
- Suggestions can cross site boundaries (XF -> WP and WP -> XF).
- Scope selector clearly labels content source (XenForo / WordPress).
- Import settings page has a WordPress section: base URL + Application Password.
- Sync can be triggered manually or on a schedule.
- Public WordPress content requires no credentials; private content uses Application Password.

### Implementation notes for the AI
- `apps/sync/services/wordpress_api.py` - WP REST API client
  - `GET /wp-json/wp/v2/posts`
  - `GET /wp-json/wp/v2/pages`
  - Basic auth using username + application password
- WordPress posts/pages map to `ContentItem(content_type="wp_post"/"wp_page")`.
- Sentence splitting, distillation, and embedding pipeline stays the same.
- Existing-link graph must include WP -> XF and XF -> WP edges.
- Add `WORDPRESS_BASE_URL`, `WORDPRESS_USERNAME`, and `WORDPRESS_APP_PASSWORD` to `.env.example`.

---

### FR-006 - Add your next request here

Use the template below. Copy it and replace the placeholder text.

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
[any technical hints]
```

---

*Last updated: 2026-03-24 (FR-005 completed; FR-003 is next)*
