# Agent Instructions (Codex / OpenAI Codex / CI Agents / Gemini / Claude)

This file applies to every AI agent that works on this repository.
Read all sections before making any changes to frontend styles.

---

## Design System - GA4 Visual Identity

This app is styled to match **Google Analytics 4 pixel-for-pixel** as of 2026-04-03.
Design uniformity is paramount. Do not drift from the design system.

### The Single Source of Truth

`frontend/src/styles/default-theme.scss`

All colours, spacing, shadows, fonts, and radius values are defined there as CSS custom properties (variables). Every component inherits from it. Read it before touching any `.scss` file.

---

## Hard Rules - Never Break These

### Colours
- **No hardcoded hex colours** in component `.scss` files. Use `var(--token-name)`.
- **No orange**. The primary color is GA4 blue `#1a73e8`. It lives in `var(--color-primary)`.
- **No gradients** (`linear-gradient`, `radial-gradient`). GA4 uses flat colour only.

### Cards and Shadows
- Cards use `border: var(--card-border)` = `0.8px solid #dadce0`. No other border style.
- `box-shadow: none` at rest. Cards do not have drop shadows.
- Hover may use `var(--shadow-md)` only - never as a resting state.

### Typography
- Font stack: `var(--font-family)` = `-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif`
- Do not import Google Fonts, Inter, or any external font.
- Base font size: `13px`.

### Navigation
- Nav item shape: `border-radius: 0 44px 44px 0` (pill-right). Do not change.
- Active state: `background: #e8f0fe`, `color: #1967d2`. No `::before` left bar.

---

## Token Priority Order

When writing styles, prefer in this order:

1. Semantic tokens: `var(--color-primary)`, `var(--color-border)`, `var(--card-border)`, `var(--color-text-secondary)`
2. Component palette tokens: `var(--color-blue-50)`, `var(--color-bg-faint)`, `var(--color-success-light)`
3. Raw hex: **only** for values that genuinely have no token equivalent - and add a comment explaining why

---

## Files That Need Care

| File | Risk | Rule |
|---|---|---|
| `frontend/src/styles/default-theme.scss` | CRITICAL | Changing a token here changes every component. Audit usages before editing. |
| `frontend/src/styles.scss` | HIGH | Global Angular Material overrides. Changes affect all pages. |
| `frontend/src/app/app.component.scss` | HIGH | Shell layout, toolbar, sidebar. Structural changes break navigation. |
| Any `*.component.scss` | MEDIUM | Must use tokens only. No hardcoded hex, no shadows on cards, no gradients. |

---

## What Is Allowed

- Adding new CSS variables to `default-theme.scss` (at the bottom, with a clear comment)
- Using existing tokens in new component styles
- Adding new component SCSS using the token system
- Adjusting layout (grid columns, gap, padding) as long as colours/shadows/typography tokens are unchanged

## What Requires Human Review

- Any edit to `default-theme.scss` that changes an existing token value
- Any new `box-shadow` on a card element
- Any new font import
- Any `linear-gradient` or `radial-gradient`
- Changing the nav item `border-radius`

---

## Material Design 3 (M3) — Mandatory

This app uses **Angular Material v20 with Material Design 3 (M3)**.

- **Use M3 APIs only**: Use `mat.define-theme` (M3). Do NOT use `mat.m2-define-palette`, `mat.m2-define-light-theme`, or any `m2-` prefixed API.
- **Do NOT override M3 visual defaults** in order to match a different design system. Accept M3's expressive defaults for spacing, shape, and density.
- The GA4 branding (primary blue `#1a73e8`, flat cards, border system) still applies — but only via CSS custom property tokens, not by reversing M3 structural defaults.
- If a new component needs theming, derive it from M3 system tokens (`--mat-sys-primary`, `--mat-sys-surface`, etc.), not legacy M2 tokens.

---

## Spacing, Breathing Room & Edge Clearance — Mandatory for All Agents

The UI must feel **spacious but not cluttered**. Every agent must follow these rules on every new or modified view.

### Never-Touch Rules
- **Nothing touches an edge.** No button, chip, text, icon, or card may be flush against a page edge, card border, or container wall. Minimum clearance: `16px` from any container edge.
- **No element collisions.** Text, icons, and buttons must never overlap or be too close to read comfortably. Use `gap` on flex/grid layouts instead of `margin-right` on children.
- **No collapsed spacing.** If a component has zero `padding` or `margin`, add a comment explaining exactly why — otherwise it is a bug.
- **Filter bars and chip lists.** The first chip in any `mat-chip-listbox` must never be flush against the left container border. Minimum `padding-left: 4px` must exist on the listbox.

### Spacing Tokens (use these — never hardcode pixel values inside components)
| Context | Token | Value |
|---|---|---|
| Page outer padding | `--spacing-page` | `48px 64px` |
| Card inner padding | `--spacing-card` | `24px` |
| Section gap (grid of cards) | `--spacing-md` | `24px` |
| Inline gap (buttons, chips, icons) | `--spacing-sm` | `12px` |
| Form field bottom margin | `--spacing-field` | `16px` |

Add tokens to `_theme-vars.scss` if they do not already exist.

### Layout Rules
- Use `gap` on flex/grid, not `margin-right` on individual children.
- All page-level content lives inside `.page-content` which provides `48px 64px` outer padding. **Do NOT add extra outer padding inside a routed component** — you will double-pad.
- Paginator, chip rows, and action rows must never be clipped by an overflow container.

---

## Design Uniformity — Mandatory for All Agents

Every screen must look like it belongs to the **same application**. No custom one-off styles are allowed.

### Component Standardisation
- **Inputs**: Always use `mat-form-field` with `appearance="outline"`. Never use a raw `<input>` styled locally.
- **Buttons**: Use only `mat-button`, `mat-stroked-button`, or `mat-flat-button color="primary"`. Do NOT introduce custom button classes with hardcoded sizes.
- **Error messages**: Always use `<mat-error>` inside a `mat-form-field`, or the global `.error-banner` utility class. Never use a raw `<div>` with inline colour styling.
- **Cards**: Always use `mat-card` with the global GA4 card system (flat, border-only). Never use a `<div>` with a `box-shadow` to simulate a card.
- **Chips/Status Badges**: Always use the `ga4-chip` mixin or `.status-chip.status-{state}` classes. Never invent a new badge pattern.

### Anti-Patterns — Never Do These
- ❌ Inline `style="..."` on any element.
- ❌ Component-level hardcoded pixel values for padding/margin — always use spacing tokens.
- ❌ Duplicating the same component pattern in more than one place — abstract to a global utility class.
- ❌ Any font-size below `11px` — it becomes unreadable.
- ❌ Content areas that scroll horizontally on a 1280px viewport.

---

## Global Architecture & Override Policy (Zero-Override Mandate)

Act as a strict frontend architect. To maintain absolute design uniformity, we follow a **"Zero Local Overrides"** policy.

1. **Forbidden `::ng-deep`**: Never use `::ng-deep` or `:host ::ng-deep`. If a library (Material, etc.) requires it, the override MUST be global, not component-specific.
2. **Global Themes Only**: Shift all structural overrides to `src/styles/themes/` (e.g., `_data-tables.scss`). 
3. **Utility Classes**: Create reusable utility classes (e.g., `.ga4-standard-field`) in these global files. Define padding, row heights, and standard colors there.
4. **Clean Components**: Component `.scss` files MUST stay nearly empty (layout-only). Apply global utility classes directly in the HTML templates.
5. **Architectural Stop-And-Think**: If you need a specific CSS selector to "force" a design, you MUST abstract it into a global utility class instead.
6. **Cleanup-on-Sight**: When modifying an existing component, you are REQUIRED to "evacuate" any local overrides or `::ng-deep` blocks into the global theme architecture.

---


## Docker Rules (also apply to this agent)

- Never add a `build:` block to a service that can reuse an existing image.
- `xf-linker-backend:latest` is shared by backend, celery-worker, and celery-beat.
- `xf-linker-http-worker:latest` is shared by http-worker-api and http-worker-queue.
- After `docker-compose build`, run `docker image prune -f`.
- Never run `docker-compose down -v` - it deletes the database.

---

## Native Runtime Policy

- Before changing native C++, Python fallback, runtime ownership, or operator-facing runtime diagnostics, read `docs/NATIVE_RUNTIME_POLICY.md`.
- Treat C++ as the default speed path for hot ranking and pipeline loops, Python as the safety fallback/reference path, and C# as the preferred worker/orchestration runtime.
- Do not create a second native-runtime issue surface. Reuse the existing diagnostics system for C++, Python, and C# runtime visibility.

---

## CI and Testing - Mandatory for All Agents

To prevent breaking the build on GitHub, every AI agent MUST verify their changes locally before pushing.

1. **Local Git Hooks**: This repository uses a mandatory pre-push hook.
   - Run `git config core.hooksPath .githooks` once to enable it.
2. **Manual Verification**: If the hook is bypassed or unavailable, you MUST run these commands and ensure they pass:
   - **Backend**: `cd backend && python manage.py test`
   - **Frontend**: `cd frontend && npm run test:ci && npm run build:prod`
3. **Never `--no-verify`**: Under no circumstances should an agent use `--no-verify` to bypass the pre-push checks.
4. **Angular Peer Deps**: If you encounter peer dependency errors in the frontend, ensure `frontend/.npmrc` contains `legacy-peer-deps=true`.

---

## UX and Smart Navigation - Mandatory for All Agents

Everything in this app must be "One-Click Away" from being found.

1. **Deterministic IDs**: Every `mat-card`, `section`, or major UI block MUST have a unique, descriptive `id`.
2. **Deep-Linking**: Internal links (alerts, dashboard metrics, health checks) MUST use `[routerLink]` with a `fragment` matching the target `id`.
3. **Auto-Reveal**: If a target element is inside a tab or accordion, the component MUST implement logic to automatically switch tabs/open the container when that fragment is detected in the URL.
4. **Visual Feedback**: Use the `ScrollHighlightService` (or `appScrollHighlight` directive) to ensure the target element is centered and highlighted for 6 seconds upon arrival.
6. **Plain-English Guidance**: Every error, status alert, or health warning MUST include a concise, plain-English explanation of exactly what is wrong and a direct, actionable "how-to-fix" instruction. Avoid technical jargon unless the target audience is strictly developers (e.g., C++ stack traces). For non-technical users, use simple terminology and direct links.

