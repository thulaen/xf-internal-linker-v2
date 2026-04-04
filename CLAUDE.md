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

- **Never hardcode a hex colour** in any component `.scss` file. Always use a CSS variable (`var(--color-primary)`, `var(--color-blue-50)`, etc.).
- **Never use orange** (`#f6821f`, `#ee730a`, `#ff6600`, or any orange shade). The primary colour is GA4 blue `#1a73e8`. It lives in `var(--color-primary)`.
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
- Use `var(--color-primary)` for the main brand color
- Use `var(--color-text-secondary)` for secondary text
- Use `var(--color-border)` for standard borders
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

# Component Rules — No Exceptions

These rules apply to every AI agent working in this repo (Claude, Codex, Gemini, etc.).

## Always Use Angular Material

This app is built on Angular Material. Never write a custom version of something Material already provides.

- Buttons → `mat-button`, `mat-raised-button`, `mat-icon-button`, `mat-stroked-button`
- Cards → `mat-card` with `mat-card-header`, `mat-card-content`, `mat-card-actions`
- Tables → `mat-table` with `matSort` and `matPaginator`
- Form fields → `mat-form-field` wrapping `matInput`, `mat-select`, `mat-datepicker`
- Dialogs → `MatDialog.open()` — never a raw `<div>` overlay
- Tooltips → `matTooltip` directive — never a custom hover div
- Progress → `mat-spinner` or `mat-progress-bar` — never a custom spinner
- Chips/tags → `mat-chip-set` and `mat-chip`
- Menus → `mat-menu` — never a custom dropdown

If you are unsure whether Material has a component for something, check the Angular Material docs before building anything custom.

## Check for Existing Components First

Before building a new component, search `frontend/src/app/` for one that already does the job. Duplicate components are forbidden. If a close match exists, extend it rather than copy it.

## Spacing — 4px Grid Only

All margin and padding values must be multiples of 4px. The allowed scale is:

`4px · 8px · 12px · 16px · 24px · 32px · 48px · 64px`

Never use values like `5px`, `10px`, `15px`, `18px`, or `20px`. If the GA4 reference uses an odd value, round to the nearest 4px step.

Prefer CSS variables for common gaps:
- `var(--space-xs)` = 4px
- `var(--space-sm)` = 8px
- `var(--space-md)` = 16px
- `var(--space-lg)` = 24px
- `var(--space-xl)` = 32px

## Icons — Material Icons Only

Use `<mat-icon>` with Google Material Icons ligature names (e.g. `<mat-icon>search</mat-icon>`). Never use Font Awesome, Heroicons, SVG icon files, or emoji as UI icons. Icon size follows the surrounding text size — do not set a custom `font-size` on `<mat-icon>` unless matching a specific GA4 reference.

## Component States — Standard Patterns

Every interactive element must handle all of these states consistently:

| State | Rule |
|---|---|
| **Default** | Flat, no shadow, border via `var(--card-border)` |
| **Hover** | `var(--shadow-md)` + subtle background shift — never colour change alone |
| **Focus** | Angular Material's default focus ring — never remove `outline` |
| **Disabled** | `opacity: 0.38` — the Material standard. Never `display: none` a disabled control |
| **Loading** | `mat-spinner` at `diameter="24"`, centred in its container |
| **Empty state** | Centred layout: icon (48px) + short heading + one-line description. No raw "No data." text |
| **Error state** | `var(--color-error)` text below the field via `mat-error`. Never a custom red `<span>` |

## Validation Messages

Always use Angular Material's built-in validation flow:

```html
<mat-form-field>
  <input matInput [formControl]="myControl" />
  <mat-error *ngIf="myControl.hasError('required')">This field is required.</mat-error>
</mat-form-field>
```

Never render validation errors with a custom `<div class="error">` or inline style. Never show errors before the user has touched the field — use `{updateOn: 'blur'}` or check `control.touched`.

## Loading Indicators

- **Full-page load**: `mat-spinner` at `diameter="48"`, centred vertically and horizontally in the page content area.
- **In-card load**: `mat-spinner` at `diameter="24"`, centred inside the card.
- **Button action in progress**: `mat-spinner` at `diameter="18"` inline beside the button label, button disabled during load.
- Never use a custom CSS animation as a loading indicator.

## Dialog / Modal Patterns

- Open via `MatDialog.open(MyComponent, { width: '480px', disableClose: false })`.
- Dialog title goes in `<h2 mat-dialog-title>`.
- Body goes in `<mat-dialog-content>`.
- Buttons go in `<mat-dialog-actions align="end">` — Cancel on the left, confirm action on the right.
- The confirm button uses `mat-raised-button color="primary"`. Cancel uses `mat-button` (no colour).
- Never stack more than two actions in a dialog footer.

## Navigation Patterns

- Page transitions happen via Angular Router — never manipulate `window.location` directly.
- Active route is highlighted by the sidenav (already handled in `app.component`). Do not add a second active indicator inside page content.
- Breadcrumbs: if a page is more than one level deep, add a breadcrumb row at the top of the content area using plain `<a routerLink>` links separated by `/`. Do not use a third-party breadcrumb component.

# Docker Rules — No Exceptions

Every AI session must follow these rules to prevent Docker disk bloat:

- Never add a `build:` block to a service that can reuse an existing image. Use `image:` instead.
- The build-once pattern is mandatory: `xf-linker-backend:latest` is shared by backend, celery-worker, and celery-beat. `xf-linker-http-worker:latest` is shared by http-worker-api and http-worker-queue. Do not break this.
- After any `docker-compose build`, immediately run `docker image prune -f` to remove dangling images (old leftover copies).
- Never run `docker-compose down -v` — the `-v` flag deletes the database and all embeddings. Use `docker-compose down` only (no `-v`).
