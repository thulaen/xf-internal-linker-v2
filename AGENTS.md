# Agent Instructions (Codex / OpenAI Codex / CI Agents)

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
