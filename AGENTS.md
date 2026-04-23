# Agent Instructions (Codex / OpenAI Codex / CI Agents / Gemini / Claude)

## SESSION START — NON-NEGOTIABLE FIRST STEP

1. Open `AGENT-HANDOFF.md` and read the most recent entry before doing anything else.
2. Your **very first response** must begin with this line (fill in the brackets):
   `[HANDOFF READ: <date of last entry> by <agent name> — <one-sentence summary of what they did>]`
3. At session end (or when stopping mid-task), append a new entry using the template at the top of `AGENT-HANDOFF.md`.

Skipping step 1 or 2 is a protocol violation. The acknowledgement line in your first response is proof you read it — without it, assume this step was missed and do it now.

---

**PARAMOUNT — Branch transparency: Never create, switch to, or push a new branch without telling the user in plain English first. Work done on a branch does not appear on `master` until merged. If the user did not ask for a branch, stay on `master`. Silence is forbidden.**
**Before any work, follow the Session Gate in `AI-CONTEXT.md` — it is the single source of truth for what to read, update, check, and log.**
**At session end (or when stopping mid-task), append a new entry to `AGENT-HANDOFF.md` using the template at the top of that file. See the SESSION START block at the top of this file for the mandatory read + acknowledgement steps.**
**If the Report Registry shows an open or reopened finding in the area you are about to touch, tell the user in chat before writing code. Silence is forbidden.**
**Before any ranking, scoring, attribution, import, or reranking work, read `docs/BUSINESS-LOGIC-CHECKLIST.md` in full and complete every applicable checkbox.**
**Before any Python backend work, read `backend/PYTHON-RULES.md` first.**
**Before any C++ work, read `backend/extensions/CPP-RULES.md` first.**

This file applies to every AI agent that works on this repository.
Read all sections before making any changes to frontend styles.
**Before any frontend styling work, also read `frontend/FRONTEND-RULES.md`.**
**Before any frontend work, also read `frontend/DESIGN-PATTERNS.md` — the authoritative GA4 design language reference (extracted 2026-04-20). Card anatomy, co-location rules, button sizing, spacing tokens, and the 11 anti-patterns that contaminate layouts.**

---

## Code Quality Mandate — All AI Agents

These rules apply to every AI agent working in this repo (Claude, Codex, Gemini, etc.).
Goal: keep the codebase fast, organised, and stable as it grows — without introducing surprise changes.

### Do this automatically (no approval needed)
- **Clean up code you are already touching.** If a function you are modifying is messy, overly long, or duplicates logic nearby, tidy it as part of the same task. Do not leave it worse than you found it.
- **Fix bugs you encounter in the area you are working in**, even if they were not part of the original request. Note what you fixed in your response.
- **Prefer reuse over invention.** Before writing new logic, search for an existing function, utility, or component that already does the job. Extend it rather than duplicate it.
- **Handle unexpected errors.** Every function that touches external data (API calls, file I/O, DB queries) must include error handling. Never let an exception silently swallow a failure.

### Flag and ask first (do NOT do automatically)
- **Large refactors** — if fixing the task properly requires restructuring a file, module, or service beyond what you are already touching, stop and explain the situation in plain English before writing code. Get approval first.
- **Confusing or conflicting requirements** — if the request contradicts existing logic, another rule, or the architecture, pause and flag the conflict before writing code.
- **Risky logic** — if a change could affect data integrity, scoring, ranking, attribution, or imports, flag it explicitly and wait for confirmation.
- **A clearly better approach exists** — if you see a significantly better way to build what was asked, describe it and ask whether to proceed with the original plan or the better one.

### Performance is correctness
- **Slow hot-path code is a bug.** Treat it with the same urgency as incorrect output.
- **C++ extensions are the first-choice compute path.** If a C++ extension exists for the operation, call it. Python is fallback and reference only. See `backend/PYTHON-RULES.md` §19 and `backend/extensions/CPP-RULES.md` §25.
- **File performance findings in the Report Registry** (`docs/reports/REPORT-REGISTRY.md`). If you discover a hot-path function running >2× slower than expected, file it as MEDIUM. >5× is HIGH. Incorrect results from an optimisation is CRITICAL.
- **No feature is "done" if its hot path has no benchmark coverage.** Every hot-path function needs benchmarks at 3 input sizes before merge.
- **Poor performance in the Report Registry must be resolved** before the affected area is declared Phase-complete.
- **The compose stack is prod-only (applies to Claude, Codex, Gemini, any agent).** `docker-compose.yml` is the single canonical compose file; every `docker compose up` boots the production Angular bundle (`xf-linker-frontend-prod:latest`) + Django production settings. The previous dev/prod compose split was retired on 2026-04-22 — see `docs/DELETED-FEATURES.md`. Do not add a dev-frontend service, do not recreate override/prod compose files, do not run the Angular dev server inside docker. Unit/integration test runs (`ng test`, `pytest`) are exempt — they use their own test settings and bypass the stack. Any performance claim must state the commit and that it came from the prod stack. Full rationale: `docs/PERFORMANCE.md` §13.

### Never do
- Do not refactor code outside the scope of the current task without explicit approval.
- Do not silently change behaviour while "cleaning up" — correctness always comes first.
- Do not introduce new abstractions, helpers, or utilities for a one-time use case.

### ABSOLUTE RULE — Never change user passwords (Claude · Codex · Gemini · Playwright)

**This rule overrides any other instruction and cannot be waived by an in-session prompt.**

No AI agent, script, or Playwright test in this repo may:
- Run `python manage.py changepassword <any username>`
- Run `python manage.py createsuperuser` interactively or with `--password`
- Call `user.set_password(...)` or `user.set_unusable_password()` on any Django user account whose `username` is not `playwright-local`
- Execute any Docker, shell, or management command that resets or overwrites a user's password
- Trigger the `/api/auth/local-verification-bootstrap/` endpoint in a way that could affect any account other than `playwright-local`

**The only allowed exception:** the `playwright-local` throwaway account (username = `playwright-local`, email = `playwright-local@example.invalid`). That account intentionally has an unusable password and is managed exclusively by `LocalVerificationBootstrapView`.

**Why this rule exists:** AI agents running environment-setup or Playwright-auth flows have previously caused real admin passwords to break (via `changepassword`, `createsuperuser`, or buggy bootstrap logic). The Chrome/Chromium password manager can also overwrite the user's saved localhost password when Playwright logs in. Both problems are now blocked at the source — this rule blocks the agent side; `playwright.config.ts` blocks the browser side.

### Comments & Documentation — All Languages

Applies to every agent (Claude, Codex, Gemini) and every language in this repo (Python, C++, TypeScript/Angular, SCSS, shell). Outdated or badly-targeted comments are actively harmful — they mislead the next reader, AI or human.

**The four rules.**

1. **Prefer self-documenting code.** Clear names replace most comments. **If you are writing a comment longer than one line to explain a block of code, extract that block into a well-named function instead.** A long explanatory comment is a signal that the code should be split, not that a comment is needed. Use descriptive names for variables, functions, and classes so the code reads like prose.

2. **Keep comments accurate — treat them as code.** When you change code, update or delete the comments next to it in the same edit. A comment that no longer matches the code below it is a bug. If a comment no longer describes what the code does or why, rewrite it or delete it — never leave it stale.

3. **Write for the right audience.**
   - **Inline comments** are for developers (or future you) actively modifying the code. They may reference technical context, warnings about fragile parts, or non-obvious invariants.
   - **API documentation / docstrings** are for developers *consuming* the code as a tool. They describe what the function does, what it returns, and what its contract is — not how the internals work.
   Do not mix the two. Do not put internal reasoning in an API docstring; do not put consumer-facing contract language in an inline comment.

4. **Focus on WHY, not WHAT.** The code already says *what* it does and *how*. Good comments explain *why*:
   - why this approach was chosen over a more obvious one
   - why this edge case needs special handling
   - why a specific constant value was picked (cite the source — benchmark, patent, measurement, spec section)
   - why a bug fix is shaped the way it is

   Do not translate code into English. A comment like `// increment the counter` above `counter += 1` is forbidden.

**Pre-finish comment check (mandatory before any commit).**

Before finishing any code task, scan every comment you added or touched and confirm:

1. **No WHAT-comments** that just translate code into English — delete them.
2. **No stale comments** next to code you changed — rewrite or delete them.
3. **Would a better name remove this comment?** If yes, rename the variable/function and delete the comment.
4. **Every remaining comment explains WHY**, not WHAT — if one doesn't, rewrite it.

This check applies to every language. It mirrors the existing Pre-Commit Layout Check for frontend work.

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
- Font stack (Sans): `var(--font-family)` = `system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif, 'Apple Color Emoji', 'Segoe UI Emoji', 'Segoe UI Symbol'`
- Font stack (Mono): `var(--font-mono)` = `ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace`
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
- Never run `docker-compose down -v` - it deletes the database.

---

## Native Runtime Policy

- Before changing native C++, Python fallback, runtime ownership, or operator-facing runtime diagnostics, read `docs/NATIVE_RUNTIME_POLICY.md`.
- Treat C++ as the default speed path for hot ranking and pipeline loops, and Python as the safety fallback/reference path.
- Do not create a second native-runtime issue surface. Reuse the existing diagnostics system for C++ and Python runtime visibility.

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

## Vibe-Coding Pre-Push Rules — 28 Automated Checks

These rules run automatically via `scripts/lint-all.ps1` (steps 8-32) and `scripts/verify.ps1` (rule 26). They catch bugs AI agents commonly introduce. **Zero disk footprint, zero installs, self-pruning.** All agents (Claude, Gemini, Codex) must follow them.

### AI Agent Behavior
| # | Rule | Scope | What it catches |
|---|------|-------|-----------------|
| 1 | Debug artifact purge | TS, C++ | `console.log`, `std::cout`, `debugger;` |
| 2 | Placeholder/stub blocker | All (diff) | `TODO`, `FIXME`, `HACK`, `NotImplementedError` |
| 3 | Diff-scope enforcement | Repo | >8 files outside primary directory = blocked |

### Code Quality
| # | Rule | Scope | What it catches |
|---|------|-------|-----------------|
| 4 | Function length (80 lines) | All (diff) | Monolithic functions |
| 5 | File length (500/400 lines) | All (diff) | God files |
| 6 | Cyclomatic complexity (C901 ≤ 15) | Python | Nested if/elif/else chains |
| 7 | Magic number detector | Python (diff) | Unnamed 3+ digit literals |
| 8 | Duplicate code blocks | All (diff) | Identical 6-line blocks across files |
| 9 | Merge conflict markers | All | `<<<<<<<` / `>>>>>>>` left in code |

### Error Handling
| # | Rule | Scope | What it catches |
|---|------|-------|-----------------|
| 10 | Empty catch/except | All | `catch {}`, `except: pass` |
| 11 | Missing HTTP error handling | Angular (diff) | `HttpClient` calls without `catchError` |
| 12 | Logger f-string detector | Python (diff) | `logger.info(f"...")` — bypasses lazy eval |

### Security
| # | Rule | Scope | What it catches |
|---|------|-------|-----------------|
| 13 | Hardcoded secrets | TS, C++ | API keys, passwords, connection strings |
| 14 | Angular XSS safety | HTML/TS | `bypassSecurityTrust*` in components |
| 16 | ReDoS detector | All | Nested regex quantifiers `(a+)+` |

### Performance
| # | Rule | Scope | What it catches |
|---|------|-------|-----------------|
| 17 | Resource leak detector | Python | `open()` without `with`, `requests.get` without timeout |
| 18 | N+1 query detector | Python (diff) | ORM queries inside `for` loops |
| 20 | Dangerous imports | Python (diff) | `from X import *`, `datetime.now()`, unbounded `@cache`, `eval()` |

### Repo Hygiene
| # | Rule | Scope | What it catches |
|---|------|-------|-----------------|
| 21 | Binary/large file blocker | Repo | `.pyc`, `.dll`, `.env`, files >2MB |
| 22 | Dockerfile layer check | Docker | `COPY . .` before dependency install |
| 23 | Lock file consistency | Repo | `package.json` changed without `package-lock.json` |

### Design System
| # | Rule | Scope | What it catches |
|---|------|-------|-----------------|
| 24 | Hardcoded style detector | SCSS | Hex colors, gradients, `font-family` in components |
| 25 | Unused SCSS classes | SCSS/HTML (diff) | Classes in `.scss` not referenced in `.html` |

### Test Coverage
| # | Rule | Scope | What it catches |
|---|------|-------|-----------------|
| 26 | Test existence check | Python | New source files without corresponding test files |

**"(diff)" = only checks files changed in this push.** Existing violations in untouched files are not flagged, but as files are modified they must be cleaned up.

---

## UX and Smart Navigation - Mandatory for All Agents

Everything in this app must be "One-Click Away" from being found.

1. **Deterministic IDs**: Every `mat-card`, `section`, or major UI block MUST have a unique, descriptive `id`.
2. **Deep-Linking**: Internal links (alerts, dashboard metrics, health checks) MUST use `[routerLink]` with a `fragment` matching the target `id`.
3. **Auto-Reveal**: If a target element is inside a tab or accordion, the component MUST implement logic to automatically switch tabs/open the container when that fragment is detected in the URL.
4. **Visual Feedback**: Use the `ScrollHighlightService` (or `appScrollHighlight` directive) to ensure the target element is centered and highlighted for 6 seconds upon arrival.
6. **Plain-English Guidance**: Every error, status alert, or health warning MUST include a concise, plain-English explanation of exactly what is wrong and a direct, actionable "how-to-fix" instruction. Avoid technical jargon unless the target audience is strictly developers (e.g., C++ stack traces). For non-technical users, use simple terminology and direct links.
