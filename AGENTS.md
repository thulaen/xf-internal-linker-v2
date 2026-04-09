# Agent Instructions (Codex / OpenAI Codex / CI Agents / Gemini / Claude)

**Before suggesting new features, check `AI-CONTEXT.md` § Deduplication & Overlap Rules.**
**Before any Python backend work, read `backend/PYTHON-RULES.md` first.**
**Before any C++ work, read `backend/extensions/CPP-RULES.md` first.**
**Before any C# work, read `services/http-worker/CSHARP-RULES.md` first.**

This file applies to every AI agent that works on this repository.
Read all sections before making any changes to frontend styles.
**Before any frontend styling work, also read `frontend/FRONTEND-RULES.md`.**

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

### Cards and Elevation
- Cards use `border: var(--card-border)` = `0.8px solid #dadce0` as the default style.
- **M3 Expressive tonal elevation is allowed.** Interactive cards (those the user clicks or drags) MAY use `var(--shadow-sm)` at rest and `var(--shadow-md)` on hover to communicate interactivity.
- Static informational cards (metrics, stat boxes) use `box-shadow: none` at rest — border only.
- Never use `box-shadow` values outside the token set (`--shadow-sm`, `--shadow-md`, `--shadow-hover`).

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

## Material Design 3 (M3) Expressive — Mandatory

This app uses **Angular Material v20 with Material Design 3 (M3) Expressive**.

- **Use M3 APIs only**: Use `mat.define-theme` (M3) + `mat.theme($theme)` applied to `html {}`. Do NOT use `mat.m2-define-palette`, `mat.m2-define-light-theme`, `mat.all-component-themes`, or any `m2-` prefixed API.
- **Fully embrace M3 Expressive component states**: pronounced hover states, spring-motion transitions, expressive focus rings, and tonal surface elevation are all intentional and desired. Do NOT suppress or flatten them.
- Smooth transitions and motion are encouraged. Use `transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1)` as the standard easing across interactive elements.
- The GA4 primary brand colour (`#1a73e8`) is pinned via `--mat-sys-primary: var(--color-primary)` in `default-theme.scss`. Do not remove that override.
- New components must derive from M3 system tokens (`--mat-sys-primary`, `--mat-sys-surface`, `--mat-sys-on-surface`, etc.), not legacy M2/MDC private tokens.

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

## Layout Precision Rules — Mandatory for All Agents

These rules were derived from real screenshots of layout bugs. Every agent MUST check for all four before submitting any frontend change.

### Rule A — Filter Bars & Chip Lists: Always Padded
- The first chip in any filter bar or `mat-chip-listbox` MUST have at least `16px` left-padding clearance from the container wall. Never flush-left.
- Apply `padding-left: var(--space-md)` (16px) on the `mat-chip-listbox` host or its wrapping container.

### Rule B — Form Fields: Centred Within Their Card
- Form fields inside a card section MUST NEVER be flush against the card edge. The container must have `padding: var(--spacing-card)` (24px) on all sides.
- Sparse forms (fewer than 3 fields in a wide card section) MUST be horizontally AND vertically centred within the available space. Use `align-items: center; justify-content: center` on the wrapping flex container.

### Rule C — Action Buttons: Edge Clearance + Input Alignment
- No button may be flush against any container wall. Minimum `16px` clearance (`var(--space-md)`) on all sides.
- Buttons in the same row as input fields MUST share the same vertical baseline — use `align-items: center` on the flex row.
- "Create"-style inline buttons next to form groups are a common failure point. Always verify they align with and have clearance from adjacent inputs.

### Rule D — Compound Label Separators
- When two pieces of metadata appear on the same line (e.g., node name + post count, import mode + description), they MUST be separated by a visible separator.
- Allowed separators: ` • ` (bullet — preferred for secondary metadata), ` — ` (em-dash — for ranges/classifications), `: ` (colon-space — for label–value pairs).
- Never concatenate two strings with only whitespace — they will visually merge into one word when font weights differ.
- ✅ `Forum Node • 0 posts` &nbsp;&nbsp; ✅ `Full import: Body text, sentences, embeddings`
- ❌ `Forum Node0 posts` &nbsp;&nbsp; ❌ `Full importBody text, sentences`

### Pre-Commit Layout Check
Before finishing any frontend task, visually confirm:
1. No chip, text, button, or input is flush against a container edge.
2. Filter bars have visible left-padding before the first chip.
3. Inline button rows are baseline-aligned with adjacent form fields.
4. All compound labels use ` • `, ` — `, or `: ` as separators.

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

## Automatic Migration And Safe Artifact Prune

This is the canonical migration/prune policy for all AI agents in this repo, including Codex, Claude, Gemini, CI agents, and future tools. Do not duplicate the full policy in other instruction files; they should point back here.

### Mandatory backend-session migration flow

For every backend-related session (backend bugs, Django models, migrations, settings, runtime, APIs, management commands):

1. Run `docker compose exec backend python manage.py showmigrations`
2. If any migration is unapplied, run `docker compose exec backend python manage.py migrate --noinput`
3. Run `docker compose exec backend python manage.py makemigrations --check --dry-run`
4. If Django models or migration files changed during the session, run `docker compose exec backend python manage.py migrate --noinput` again
5. Before finishing, re-run `docker compose exec backend python manage.py showmigrations`
6. Before finishing, re-run `docker compose exec backend python manage.py makemigrations --check --dry-run`

Agents must not mark backend work complete while migrations are pending.

If Docker or the backend container is unavailable, agents must stop and record a clear blocker instead of guessing migration state.

### Mandatory safe artifact prune

After verification or at the end of the session, agents must run the approved cleanup command:

- `powershell -ExecutionPolicy Bypass -File scripts\\prune-verification-artifacts.ps1`

Safe prune means disposable caches and build artifacts only. This includes frontend build/cache output, backend test/lint caches, native extension build folders, .NET `bin`/`obj`, Docker builder cache, and dangling Docker images.

### Forbidden cleanup

- Never run `docker-compose down -v`
- Never prune database volumes
- Never prune Redis/runtime data
- Never prune embeddings
- Never prune `media/`
- Never prune checked-in files

Reuse the existing repo cleanup script and Docker prune policy above. Do not invent competing cleanup commands or duplicate this policy elsewhere.

---

## UX and Smart Navigation - Mandatory for All Agents

Everything in this app must be "One-Click Away" from being found.

1. **Deterministic IDs**: Every `mat-card`, `section`, or major UI block MUST have a unique, descriptive `id`.
2. **Deep-Linking**: Internal links (alerts, dashboard metrics, health checks) MUST use `[routerLink]` with a `fragment` matching the target `id`.
3. **Auto-Reveal**: If a target element is inside a tab or accordion, the component MUST implement logic to automatically switch tabs/open the container when that fragment is detected in the URL.
4. **Visual Feedback**: Use the `ScrollHighlightService` (or `appScrollHighlight` directive) to ensure the target element is centered and highlighted for 6 seconds upon arrival.
6. **Plain-English Guidance**: Every error, status alert, or health warning MUST include a concise, plain-English explanation of exactly what is wrong and a direct, actionable "how-to-fix" instruction. Avoid technical jargon unless the target audience is strictly developers (e.g., C++ stack traces). For non-technical users, use simple terminology and direct links.
