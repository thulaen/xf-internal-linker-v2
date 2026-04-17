# Phase A1 / Gaps 102 + 103 — Heading hierarchy & landmark regions

## Gap 102 — Heading hierarchy

WCAG 1.3.1 requires that heading levels reflect the document outline:
each `<h2>` follows an `<h1>`; you don't skip from `<h1>` to `<h3>`;
each page has exactly one `<h1>`.

### Per-route audit (current state, 2026-04)

| Route | h1 count | Skipped levels? | Verdict |
|---|---|---|---|
| `/` (Dashboard) | 1 (`Dashboard`) | No | ✅ |
| `/login` | 1 (`Sign in`) | No | ✅ |
| `/review` | 1 (`Review queue`) | No | ✅ |
| `/jobs` | 1 (`Jobs`) | No | ✅ |
| `/health` | 1 (`System Health`) | No | ✅ |
| `/alerts` | 1 (`Alerts`) | No | ✅ |
| `/link-health` | 1 (`Link Health`) | No | ✅ |
| `/graph` | 1 (`Link Graph`) | No | ✅ |
| `/analytics` | 1 (`Analytics`) | No | ✅ |
| `/behavioral-hubs` | 1 (`Behavioral Hubs`) | No | ✅ |
| `/settings` | 1 (`Settings`) | No | ✅ |
| `/crawler` | 1 (`Web Crawler`) | No | ✅ |
| `/error-log` | 1 (`Error Log`) | No | ✅ |
| `/performance` | 1 (`Performance`) | No | ✅ |
| `/diagnostics` | 1 (`Diagnostics`) | No | ✅ |

### Verification

The Gap 96 axe-core gate enforces this automatically. Running it
manually:

```bash
cd frontend
npm run ui:test:a11y
```

`heading-order` is one of the WCAG2AA rules included by default; any
new component that introduces `h1 → h3` will fail the gate.

## Gap 103 — Landmark regions

WCAG 1.3.1 + WAI-ARIA Authoring Practices require ONE of each of:
`<header>`/`role=banner`, `<nav>`/`role=navigation`, `<main>`/`role=main`,
`<footer>`/`role=contentinfo`, plus optional complementary
(`<aside>`/`role=complementary`).

### App shell mapping (`app.component.html`)

| Landmark | Element | Notes |
|---|---|---|
| banner | `<mat-toolbar class="app-toolbar">` | The toolbar's role defaults to `toolbar`; we treat the toolbar AS the banner because it contains the page title + global controls. Add `role="banner"` if a screen reader test surfaces ambiguity. |
| navigation | `<mat-sidenav class="app-sidenav">` containing `<mat-nav-list>` | mat-nav-list emits `role="navigation"` automatically. |
| main | `<main id="main-content" tabindex="-1" class="page-content">` | Already correct (Phase E2 / Gap 40). |
| contentinfo | `<footer class="app-footer">` | Rendered when `config.showFooter` is on. |

### Drawers / dialogs

`<aside class="gd-panel">` (glossary) and `<aside class="fd-panel">` (FAQ)
already use the `<aside>` element; both add `role="dialog"` because they
trap focus while open. The `<aside>` element fallback satisfies
landmark counts when the drawer is closed.

### Verification

`landmark-one-main` and `region` are axe rules included in the WCAG 2A
ruleset and run by `npm run ui:test:a11y`.

## Reviewer checklist (per PR touching layout)

- [ ] At most one `<h1>` per route.
- [ ] No heading-level skips (h1 → h3, etc.).
- [ ] All page content lives inside the `<main>` landmark.
- [ ] `npm run ui:test:a11y` passes locally.
