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

*Nothing completed yet — FRs are promoted here once fully implemented and committed.*

---

## 🔄 IN PROGRESS

*None currently in progress.*

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

### FR-002 — Add your next request here

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

*Last updated: 2026-03-23*
