# Claude Instructions

When responding to the user in this repository:

- Talk in plain English.
- Explain things like the user is five.
- Give the simple explanation first.
- Prefer short sentences and everyday words.
- Define technical terms immediately if they are needed.

# Design System Rules — No Exceptions

This app uses a pixel-accurate Google Analytics 4 (GA4) visual identity. Every AI session must protect it.

## The One File That Controls Everything

`frontend/src/styles/default-theme.scss` is the single source of truth for all colours, spacing, shadows, and typography. Before touching any style anywhere, read that file first.

## Colour Rules

- **Never hardcode a hex colour** in any component `.scss` file. Always use a CSS variable (`var(--color-primary)`, `var(--cf-blue-5)`, etc.).
- **Never use orange** (`#f6821f`, `#ee730a`, `#ff6600`, or any orange shade). The primary colour is GA4 blue `#1a73e8`. It lives in `var(--color-primary)` and `var(--cf-orange-6)` (which has been remapped to blue intentionally — do not undo this).
- **Never add a `linear-gradient` or `radial-gradient`** to any UI element. GA4 uses flat colours only.

## Card & Shadow Rules

- Cards use **border only**: `border: var(--card-border)` which equals `0.8px solid #dadce0`.
- `box-shadow: none` on all cards. Do not add shadows to cards.
- Hover states may use `var(--shadow-md)` (`0 2px 6px rgba(60,64,67,0.15)`) — only on hover, never as a resting state.

## Typography Rules

- Font: `var(--font-family)` — system stack (`-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif`). Never import Google Fonts or Inter.
- Base size: `13px`. Title sizes go up to `22px` for page titles. Never use `rem` values above `1.7rem` for body content.

## Token Hierarchy — Use Semantic Tokens First

Prefer semantic tokens over raw palette tokens:
- Use `var(--color-primary)` not `var(--cf-orange-6)` (even though they resolve to the same value)
- Use `var(--color-text-secondary)` not `var(--cf-gray-4)`
- Use `var(--color-border)` not `#dadce0` directly
- Use `var(--card-border)` for card borders
- Use `var(--card-border-radius)` (`8px`) for card corner rounding

## Navigation Rules

- Nav item shape: `border-radius: 0 44px 44px 0` (flat left, pill right — GA4 style). Do not change this.
- Active nav: `background: #e8f0fe`, `color: #1967d2`. No left-side bar or `::before` pseudo-element.
- Sidenav width: `var(--sidenav-width)` = `256px`.

## What Requires a Design Review Before Changing

These files are high-impact. Ask before editing them:
- `frontend/src/styles/default-theme.scss` — changes here affect every component
- `frontend/src/styles.scss` — global overrides for Angular Material
- `frontend/src/app/app.component.scss` — shell layout and navigation

# Docker Rules — No Exceptions

Every AI session must follow these rules to prevent Docker disk bloat:

- Never add a `build:` block to a service that can reuse an existing image. Use `image:` instead.
- The build-once pattern is mandatory: `xf-linker-backend:latest` is shared by backend, celery-worker, and celery-beat. `xf-linker-http-worker:latest` is shared by http-worker-api and http-worker-queue. Do not break this.
- After any `docker-compose build`, immediately run `docker image prune -f` to remove dangling images (old leftover copies).
- Never run `docker-compose down -v` — the `-v` flag deletes the database and all embeddings. Use `docker-compose down` only (no `-v`).
