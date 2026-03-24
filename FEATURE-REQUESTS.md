# Feature Requests — XF Internal Linker V2

This file tracks UI/UX feature requests from the developer.

## How this file works

| Section | What goes here |
|---|---|
| **PENDING** | Requested but not yet built. AI must surface these at every session start. |
| **IN PROGRESS** | Currently being implemented in the active phase. |
| **COMPLETED** | Done. AI must check this before implementing anything new (avoid duplication). |

**Rule:** Keep AI-CONTEXT.md for architecture facts. Keep this file for feature wishes.

---

## ✅ COMPLETED FEATURES

### FR-002 — Jobs Page: JSONL File Import UI
**Completed:** 2026-03-24

- Drag-and-drop zone (or click to browse) accepting `.jsonl` files only
- Import mode selector: Full / Titles / Quick
- "Start Import" button enabled only when a file is selected
- Live progress bar + status message via WebSocket (`ws/jobs/<job_id>/`)
- Green success / red failure result banners
- Recent Activity history table (source, mode, status, items synced)
- Backend: `POST /api/import/upload/` — saves file, creates `SyncJob`, dispatches `import_content` Celery task
- Backend: `GET /api/sync-jobs/` — `SyncJobViewSet` for history
- `SyncJob` model + migration in `apps/sync/`
- `SyncService` Angular service in `frontend/src/app/jobs/`

---

## 🔄 IN PROGRESS

### FR-001 — Angular Frontend: Light Theme Default + Full Theme Customizer
**Started:** 2026-03-24

- [x] Light theme default (already light by default via `gsc-theme.scss`)
- [x] Dark mode via `data-theme="dark"` on `<html>` — full CSS var overrides
- [x] `AppearanceService` — loads/saves config from `/api/settings/appearance/`, applies CSS vars live
- [x] Backend `AppearanceSettingsView` — `GET/PUT /api/settings/appearance/`
- [x] `ThemeCustomizerComponent` — right-side Material drawer with all controls:
  - Light/Dark toggle, primary color, accent color, header background
  - Font size, layout width, sidebar width, density
  - Site name, footer text/toggle/color
  - Scroll-to-top toggle
  - Named presets (save / load / delete)
- [x] `ScrollToTopComponent` — floating FAB, appears after 300px scroll
- [x] App shell wired: customizer drawer, footer, site name from config
- [ ] Logo / favicon upload (Phase 4b)

---

## 📋 PENDING FEATURES

---

### FR-001 — Angular Frontend: Light Theme Default + Full Theme Customizer

**Requested:** 2026-03-23
**Target phase:** Phase 4 (Angular frontend core)
**Priority:** High — must be in place before first demo

### What's wanted

Inspired by WordPress Appearance → Customize panel (see `misc.goldmidi.com`).

The app must ship with a clean, professional **light theme by default**.
A sidebar-based customizer lets the user tweak the look without touching code.

### Specific controls needed

| Control | Description |
|---|---|
| **Light / Dark mode toggle** | Default = light. Dark mode available but not default. |
| **Primary color picker** | Default = GSC blue `#1a73e8`. User can change to any hex. |
| **Accent color picker** | Secondary highlight color. |
| **Font size** | Small / Medium / Large presets. |
| **Layout width** | Narrow / Standard / Wide (max-width on the main container). |
| **Sidebar width** | Adjustable sidebar (compact vs comfortable). |
| **Layout density** | Compact / Comfortable — affects padding/spacing throughout. |

### Header customization
- Upload a custom **logo** (replaces "XF Internal Linker" text)
- Set **site title** text (shown next to or instead of logo)
- Control header **background color** (default: white with blue accent)
- Toggle: show/hide navigation labels in the header

### Footer customization
- **Footer text** — default: "XF Internal Linker V2" + version number
- Toggle: show/hide the footer entirely
- Footer **background color** control

### Site Identity
- **Logo upload** — PNG/SVG, shown in header and browser tab
- **Favicon upload** — for browser tab icon
- **Site name** — used in page titles and admin header

### Scroll-to-top button
- Floating button in bottom-right corner (like `misc.goldmidi.com`)
- Appears after scrolling down ~300px
- Smooth scroll back to top on click
- Toggle: show/hide in customizer

### Theme presets
- Save current customization as a named preset (e.g. "My Dark Theme")
- Load any saved preset with one click
- Reset to default button

### Implementation notes for the AI
- Use Angular Material theming with CSS custom properties
- The customizer panel = a right-side drawer in Angular Material
- Settings saved via `POST /api/settings/` (AppSetting model, category='appearance')
- Live preview updates the page immediately without reload
- Themes persist across browser sessions (stored in DB, loaded on app init)

---

---

### FR-002 — Jobs Page: JSONL File Import UI

**Requested:** 2026-03-24
**Target phase:** Phase 3 (content import)
**Priority:** High — no command-line access; UI is the only import path

### What's wanted
A clean import card on the Jobs page that lets the user upload a `.jsonl` export file
from the XenForo server and watch the import progress live — no terminal, no Docker commands.

### Specific controls / behaviour
- Drag-and-drop zone (or click to browse) accepting `.jsonl` files only
- Import mode selector: **Full** (body + sentences + embeddings) / **Titles** (metadata only) / **Quick** (IDs + titles)
- "Start Import" button — enabled only when a file is selected
- Live progress bar + status message driven by WebSocket (`ws/jobs/<job_id>/`)
- Clear success state (green) and failure state (red) with message
- File name and size shown after selection

### Implementation notes for the AI
- Backend: `POST /api/import/upload/` accepts multipart file + mode param
- View saves file to `BASE_DIR/data/imports/<uuid>.jsonl`, generates a `job_id`, dispatches `import_content.delay(source="jsonl", ...)`
- `job_id` returned to Angular so it can subscribe to WebSocket before progress events arrive
- `import_content` task must accept an optional `job_id` kwarg
- Angular: standalone component, `HttpClient` for upload, native `WebSocket` for progress

---

### FR-003 — WordPress Cross-Linking

**Requested:** 2026-03-24
**Target phase:** Phase 5 (after XenForo sync is stable)
**Priority:** Medium

### What's wanted
Suggest internal links between XenForo threads/resources and WordPress posts/pages.
A forum thread about a product should be able to link to the WordPress review of that
product, and vice versa. All suggestions go through the same manual review workflow —
nothing is applied automatically.

### Specific controls / behaviour
- WordPress content appears in the same scope/content browser as XenForo content
- Suggestions can cross site boundaries (XF → WP and WP → XF)
- Scope selector in the UI clearly labels content source (XenForo / WordPress)
- Import settings page has a WordPress section: base URL + Application Password
- Sync can be triggered manually (UI button) or on a schedule (Celery Beat)
- Public WordPress content requires no credentials; private content uses Application Password

### Implementation notes for the AI
- `apps/sync/services/wordpress_api.py` — WP REST API client
  - `GET /wp-json/wp/v2/posts` + `/pages` (paginated)
  - Auth: `Authorization: Basic base64(username:application_password)` header
  - No plugin needed — built into WordPress since 5.6
- WordPress posts/pages map to `ContentItem(content_type="wp_post"/"wp_page")`
- Sentence splitting, distillation, and embedding pipeline is identical to XenForo
- ExistingLink graph includes WP → XF and XF → WP edges
- `WORDPRESS_BASE_URL` + `WORDPRESS_APP_PASSWORD` + `WORDPRESS_USERNAME` added to `.env.example`
- Pending configuration item 2 in AI-CONTEXT.md should be marked done when this FR is implemented

---

### FR-004 — Add your next request here

Use the template below. Copy it and replace the placeholder text.

```
### FR-00X — Short title

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

*Last updated: 2026-03-24 (Phase 5 — Review page complete)*
