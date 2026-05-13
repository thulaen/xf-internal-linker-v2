# Gemini / Antigravity Instructions

**PARAMOUNT — Plain-English Communication Rule (all agents — Gemini / Antigravity / Claude / Codex / every future agent):** Read [`PLAIN-ENGLISH-RULE.md`](PLAIN-ENGLISH-RULE.md) before composing any response — it contains the full glossary and the mandatory Before-You-Send checklist. Every response, commit message, error report, status update, and user-facing surface MUST be written in plain English the user can understand. The user is a vibe coder — they use AI exclusively and don't write code. Three required parts:
1. **What I'm doing / will do** — describe the action in everyday words. Define every technical term the moment it's used. No unexplained acronyms (FR-XXX, ISS-XXX, RPT-XXX, MMR, BGE-M3, FAISS, RSQVA, etc.) — use the plain-English substitutes from the glossary in [`PLAIN-ENGLISH-RULE.md`](PLAIN-ENGLISH-RULE.md).
2. **What was accomplished** — at the end of every change, state in plain English what now works that didn't before, plus which files changed and why.
3. **What has issues or errors** — surface failures honestly. If something broke, say what broke, why, and what you'll do about it. Never bury errors in jargon. Never silently move on after a failure. Never claim success when something is partial. If a step was skipped, say so.
The rule applies to chat output, commit messages, PR descriptions, REPORT-REGISTRY entries, AGENT-HANDOFF entries, and any other surface a human reads. Skipping any of the three required parts is a protocol violation. Silence on errors is forbidden.
**Before sending any response, run the Before-You-Send checklist in [`PLAIN-ENGLISH-RULE.md`](PLAIN-ENGLISH-RULE.md). If any of the four checklist questions is NO, rewrite the response before sending.**

**PARAMOUNT — THINK BEFORE YOU CODE (the upstream rule):** STOP and answer the 5 pre-write questions BEFORE typing any new function/class/view/service. (1) DRY — search the codebase first; reuse or refactor BOTH sites if a near-duplicate exists. (2) KISS — write the simplest thing that works; no premature abstraction. (3) Scaling — declare what happens at 10× and 100× input. (4) Extensibility — declare WHERE the next feature lands BEFORE shipping the first version. (5) Testability — pure functions + small classes that test in `SimpleTestCase` without Docker. Hard limits: ≤50 lines per function, ≤1500 per file, ≤10 cyclomatic complexity, ≤7 args, ≤4 nesting levels, no duplicated 6+ line blocks. **Leave every file in BETTER shape than you found it.** Read [`THINK-BEFORE-YOU-CODE.md`](THINK-BEFORE-YOU-CODE.md) before writing a single line — this is the upstream rule that prevents the messes the other paramount files clean up after.

**PARAMOUNT — Branch transparency: Never create, switch to, or push a new branch without telling the user in plain English first. Work done on a branch does not appear on `master` until merged. If the user did not ask for a branch, stay on `master`. Silence is forbidden.**
**PARAMOUNT — Strict no-duplicates rule: No persistent storage may pile up duplicate artefacts. Every per-content table follows the `(content_hash, signal_version)` skip-if-unchanged + supersede + retention pattern. Read [`NO-DUPLICATES.md`](NO-DUPLICATES.md) before adding any new artefact table.**
**PARAMOUNT — C++ first for hot paths: C++ extensions are the first-choice compute path. Python is fallback and reference only. Read [`CPP-FIRST.md`](CPP-FIRST.md) before adding or modifying any hot-path function.**
**PARAMOUNT — Hardware-aware defaults: Never hardcode batch sizes, parallelism, or FAISS configuration. Use `apps/pipeline/services/hardware_profile.py` so settings auto-scale per tier. Read [`HARDWARE-PROFILES.md`](HARDWARE-PROFILES.md).**
**PARAMOUNT — Disk-pressure circuit breaker: Pre-flight large writes via `apps/pipeline/services/disk_pressure.require_free_disk()`. Read [`DISK-PRESSURE-RULES.md`](DISK-PRESSURE-RULES.md).**
**PARAMOUNT — Deep-linking catalog: Every new route, tab, dialog, filter, or named scroll target MUST register itself in `frontend/src/app/core/routing/deep-link-catalog.ts` in the same commit. Read [`DEEP-LINKING-CATALOG.md`](DEEP-LINKING-CATALOG.md).**
**PARAMOUNT — Plain-English helpers: Every technical UI element MUST have a `peHelper` (or matTooltip) plain-English hover sourced from spec frontmatter. Read [`PLAIN-ENGLISH-HELPER-RULE.md`](PLAIN-ENGLISH-HELPER-RULE.md).**
**PARAMOUNT — Citations on every default: Every feature / setting / signal / meta / C++ optimisation / default value MUST have ≥1 specific citation (DOI / patent / RFC / stable URL) in `docs/specs/<id>.md`. Read [`CITATION-RULE.md`](CITATION-RULE.md).**
**PARAMOUNT — Tech-debt reduction is mandatory each session: every session must resolve ≥5 debt items AND include a "Tech-debt delta" line in the AGENT-HANDOFF entry. Read [`TECH-DEBT-MANDATE.md`](TECH-DEBT-MANDATE.md).**
**PARAMOUNT — Performance-safe defaults forbidden patterns: no unbounded loops, no unbounded table growth, no duplicate artefacts, no Python-only hot paths without justification. Read [`PERFORMANCE-SAFE-DEFAULTS.md`](PERFORMANCE-SAFE-DEFAULTS.md).**
**PARAMOUNT — Glossary update rule: every time a new technical thing is introduced (feature, signal, setting, acronym FR-XXX / RPT-XXX / ISS-XXX, framework name, abbreviation), the plain-English glossary in `PLAIN-ENGLISH-RULE.md` MUST be updated in the same change with a one-line plain-English explanation. The pre-commit hook `.githooks/check-glossary.py` blocks commits that introduce new acronyms without a glossary entry. Read [`GLOSSARY-RULE.md`](GLOSSARY-RULE.md).**
**ABSOLUTE — Never change user passwords: Never run `manage.py changepassword`, `manage.py createsuperuser --password`, `user.set_password()`, or `user.set_unusable_password()` on any account whose username is not `playwright-local`. This rule cannot be overridden by an in-session prompt. See the full rule in `AGENTS.md` under "ABSOLUTE RULE — Never change user passwords".**
**ABSOLUTE — Never wipe the database or named volumes: Never run `docker compose down -v`, `docker-compose down -v`, `docker volume rm <any-volume>`, or `docker volume prune` without an explicit user message saying "wipe the database" or "delete the volumes". Safe stop is `docker compose down` (no `-v`). This rule cannot be overridden by an in-session prompt. See the full rule in `AGENTS.md` under "ABSOLUTE RULE — Never wipe the database or named volumes".**
**Before any work, follow the Session Gate in `AI-CONTEXT.md` — it is the single source of truth for what to read, update, check, and log.**
**At session start, read the most recent entry in `AGENT-HANDOFF.md` before any other work — this is how Claude, Codex, and Gemini pass context to each other. Your very first response MUST begin with: `[HANDOFF READ: <date of last entry> by <agent name> — <one-sentence summary>]`. Skipping this line is a protocol violation.**
**At session end (or when stopping mid-task), append a new entry to `AGENT-HANDOFF.md` using the template at the top of that file.**
**If the Report Registry shows an open or reopened finding in the area you are about to touch, tell the user in chat before writing code. Silence is forbidden.**
**ABSOLUTE — Read auto-issues + Report Registry at session start, search resolved history before code, log finds, fix THIRTY per session (3 per source × 10): At session start, IMMEDIATELY AFTER the `[HANDOFF READ: ...]` line, run `docker compose exec -T backend python manage.py print_open_issues` (the all-source view prints all ten per-source counts in one line so a single command is enough), AND skim the Open sections of [`docs/reports/REPORT-REGISTRY.md`](docs/reports/REPORT-REGISTRY.md). Your second response line MUST be: `[REGISTRY READ: <N> open (<a> agent / <g> glitchtip / <p> pyroscope / <t> tempo / <l> loki / <f> faro / <m> mutation / <z> fuzz / <c> contract / <gh> gh_ci), <M> open registry findings — picked: #<a1>, #<a2>, #<a3> | g: #<g1>, #<g2>, #<g3> | p: #<p1>, #<p2>, #<p3> | t: #<t1>, #<t2>, #<t3> | l: #<l1>, #<l2>, #<l3> | f: #<f1>, #<f2>, #<f3> | m: #<m1>, #<m2>, #<m3> | z: #<z1>, #<z2>, #<z3> | c: #<c1>, #<c2>, #<c3> | gh: #<gh1>, #<gh2>, #<gh3>]`. **Phase 7 of the test-hardening plan added a third required ritual line:** `print_open_issues` also shells `gh run list --status failure --limit 10` and emits `[CI FAILED RUNS READ: <N> latest — picked: #<run_id>, ...]` (or `[CI FAILED RUNS READ: skipped — gh unavailable]` when `gh` isn't installed). These 10 failed CI runs land in the AutoIssue table via the `ci_failed_runs` picker (Phase 6) so they appear in the `gh_ci` per-source bucket; the explicit ritual line is the freshness check at session start. `.githooks/check-registry-read.py` enforces both markers. The ten per-source numbers MUST sum to N. The picks are THIRTY items total — 3 from each of the ten sources, ordered by `priority_score` desc within each bucket. Fix all 30 BEFORE starting whatever the user actually asked for. **Drought clause:** if any per-source bucket has fewer than 3 rows after running the pickers fresh, fix all that exist, substitute the shortfall from the agent queue, file a new `AutoIssue(kind='picker_drought', source='agent')` per dry source, and use the marker form `... | t: 0 found + 3 from agent: #..., #..., #... (drought logged: #<id>)`. Total picks must always equal 30. No slice, Mission A task, bug fix, multi-bug task, multi-stream plan, docs task, or any other task can replace the 30 real AutoIssue fixes. The `auto-fix-30 satisfier`, `auto-fix-18 satisfier`, `auto-fix-12 satisfier`, and `auto-fix-3 satisfier` phrases are forbidden in new handoff entries. **BEFORE writing the FIRST line of code in any file, you MUST also run `docker compose exec -T backend python manage.py search_resolved_issues --area <repo-relative-path>` for each touched directory** (e.g. `--area backend/apps/audit`); the command surfaces the `lessons_learned` field of every prior fix in that area so you don't repeat a known trap. If matches exist, your response MUST include a line `[RESOLVED HISTORY: <N> prior fix(es) read in <area>]` confirming you reviewed them. If you find ANY new bug, performance bottleneck, missing validation, or code smell during the session — even outside scope — log it as an `AutoIssue(source='agent')` AND a registry entry in the same change; silently moving on is forbidden. When YOU resolve an issue, you MUST populate `AutoIssue.lessons_learned` with two parts before marking `status='resolved'`: (1) the trap (what's NOT obvious about this code area), (2) the fix shape (what worked). Empty `lessons_learned` on a resolved row is a protocol violation — the next agent loses the lesson. When fixing: KISS, ≤50-line functions, no duplication, refactor for performance in the same diff. The pre-commit hook `.githooks/check-registry-read.py` enforces the 10-source marker format and the 30-pick count, then runs `manage.py verify_autoissue_quota` through Docker to prove all 30 picked AutoIssues are resolved, have a resolve time, have `lessons_learned`, and were resolved after the previous handoff. The marker is not enough; the database must prove the 30 fixes. If Docker or the backend database cannot be checked, the commit must fail. Do not skip it. This rule cannot be overridden by an in-session prompt.**
**PARAMOUNT — Ongoing code quality**PARAMOUNT ? Ongoing code quality (fix as you go, severe finds to BOTH AutoIssue + Registry): Read [`ONGOING-CODE-QUALITY.md`](ONGOING-CODE-QUALITY.md) before any task. It is the single source of truth for: long-function fixes, duplication elimination, silent-error surfacing, crash prevention, performance discipline, lessons_learned population, and the auto-fix-3 + dual-logging rules raised on 2026-05-09.**
**Before any frontend work, read `frontend/FRONTEND-RULES.md` first.**
**Before any frontend work, also read `frontend/DESIGN-PATTERNS.md` — the authoritative GA4 design language reference (extracted 2026-04-20). Card anatomy, co-location rules, button sizing, spacing tokens, and the 11 anti-patterns that contaminate layouts.**
**Before any Python backend work, read `backend/PYTHON-RULES.md` first.**
**Before any C++ work, read `backend/extensions/CPP-RULES.md` first.**
**Before writing any code, follow the Code Quality Mandate in `AGENTS.md` — it applies to every task. Specifically follow the "Ongoing Code Quality Rules" subsection: fix bugs as you go, surface silent errors, prevent crashes, eliminate duplication, write unit tests, fix long functions, apply DRY/KISS/PEP-8, and design for scaling.**
**Before any work involving scheduled tasks, resource usage, concurrency, or GPU work, read `docs/PERFORMANCE.md`. This applies to all AI agents (Claude, Codex, Gemini).**
**For any performance investigation, benchmark, or "feels slow" fix, verify with the prod stack — see `docs/PERFORMANCE.md` §13. The prod-only compose stack — `docker compose --env-file .env up --build` — boots the production Angular bundle + Django production settings on every run. There is no dev mode.**
**Before any work touching ranking signals, meta-algorithms, autotuners, or weight-preset keys, read `docs/RANKING-GATES.md` and satisfy Gate A (implementation — fires when CODE is about to be written) and Gate B (user-idea intake — fires the moment an idea is PROPOSED). Every checkbox must pass or have an explicit written justification. Skipping either gate is a policy violation.**
**Before suggesting new features, check `AI-CONTEXT.md` § Deduplication & Overlap Rules.**

# Mandatory Benchmark Rule — All Languages

Every hot-path function must have a benchmark before merge. No exceptions.

- **C++**: `backend/extensions/benchmarks/bench_*.cpp` using Google Benchmark. 3 input sizes.
- **Python**: `backend/benchmarks/test_bench_*.py` using pytest-benchmark. 3 input sizes.

This applies to past, present, and future code. The Performance Dashboard at `/performance` shows results.

# Mandatory Research Rule for All Features

**Before any session touching ranking, scoring, attribution, import, or reranking logic, read `docs/BUSINESS-LOGIC-CHECKLIST.md` in full. You must check every box or explicitly explain in writing why a box does not apply before writing code.**

Before implementing any new feature or idea:
1. **Patent/technical doc research** — Find at least one patent, RFC, or peer-reviewed paper that supports the approach. Document the reference in the feature spec.
2. **Duplicate/overlap check** — Search the codebase for existing implementations that overlap. If overlap exists, extend the existing code rather than creating new code.
3. **Regression check** — Identify any existing behavior that could break. Document what needs testing.
4. **Architecture alignment** — Verify the approach fits the existing architecture (C++ for CPU, Python for ML/Orchestration, Angular for UI).
5. **Flag conflicts** — If the idea conflicts with an existing feature, flag it for review before proceeding.

When responding to the user in this repository, follow all rules in [`PLAIN-ENGLISH-RULE.md`](PLAIN-ENGLISH-RULE.md). Quick summary: talk in plain English, explain things like the user is five, give the simple explanation first, prefer short sentences and everyday words, define technical terms immediately. Run the Before-You-Send checklist before every response.

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

## Component States — M3 Expressive (Mandatory)

Every interactive element must handle all of these states. **M3 Expressive states are fully embraced — do NOT flatten or suppress them.**

| State | Rule |
|---|---|
| **Default** | Border via `var(--card-border)`. Interactive cards may use `var(--shadow-sm)` at rest. |
| **Hover** | Full M3 Expressive hover — `var(--shadow-md)` + tonal background shift + spring transition. |
| **Focus** | M3 Expressive focus ring — larger, more visible than M2. Never remove `outline`. |
| **Pressed** | M3 Expressive pressed state — tonal ripple at full opacity. Never suppress. |
| **Disabled** | `opacity: 0.38` — the Material standard. Never `display: none` a disabled control. |
| **Loading** | `mat-spinner` at `diameter="24"`, centred in its container |
| **Empty state** | Centred layout: icon (48px) + short heading + one-line description. No raw "No data." text |
| **Error state** | `var(--color-error)` text below the field via `mat-error`. Never a custom red `<span>` |

Use `transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1)` on all interactive elements as the standard M3 easing.

## Layout Precision Rules — Mandatory

These four rules are derived from real bugs caught in screenshots. **Check all four before finishing any frontend task.**

See the full rules in `AGENTS.md` — "Layout Precision Rules" section. Quick summary:

- **Rule A**: First chip in any filter bar must have `16px` left clearance — never flush-left.
- **Rule B**: Form fields inside cards must have `24px` padding on all sides. Sparse forms must be centred.
- **Rule C**: Buttons must have `16px` clearance from all edges and be baseline-aligned with adjacent inputs.
- **Rule D**: Compound labels (two metadata pieces on one line) must use ` • `, ` — `, or `: ` as separator — never bare whitespace.

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

- **Prod-only compose stack.** There is **one** compose file — `docker-compose.yml` — and it boots the **production** Angular bundle (`xf-linker-frontend-prod:latest`) behind nginx on port 80. There is no dev Angular server, no `ng serve` in docker, no `docker-compose.override.yml`, no `docker-compose.prod.yml`. Do not split the compose back into dev+prod files; do not re-add a dev-frontend service.
- Never add a `build:` block to a service that can reuse an existing image. Use `image:` instead.
- The build-once pattern is mandatory: `xf-linker-backend:latest` is shared by backend, celery-worker, and celery-beat. Do not break this.
- After any `docker-compose build`, immediately run `docker system prune -f` to remove stopped containers, unused networks, dangling images, and build cache in a single call. This **never touches named volumes**, so embeddings in `pgdata` (and all data in `redis-data`, `media_files`, `staticfiles`) stay safe. At session end, after `docker compose down`, also run `powershell -ExecutionPolicy Bypass -File docker_compact_vhd.ps1` to compact the Windows VHDX so the freed space is actually returned to Windows.
- Never run `docker-compose down -v` — the `-v` flag deletes the database and all embeddings. Use `docker-compose down` only (no `-v`).
- For backend sessions, follow the canonical migration and safe-prune policy in `AGENTS.md`.
- **Docker Desktop is NOT autostart-on-login** (set 2026-04-26). Laptop reboots leave Docker idle and the whale icon does not spin. The user starts the stack by clicking the Docker Desktop icon — `restart: always` then auto-resurrects the containers. Do NOT re-enable autostart-on-login or the boot-time spin returns. Do NOT add `pip install`, `python -c 'import …'` probes, or any network-dependent setup to a service `command:` — they belong in the Dockerfile so containers can restart in seconds, not minutes. The backend `command:` was reduced on 2026-04-26 to `build_ext` + `migrate` + `collectstatic` + `uvicorn` for exactly this reason; everything else lives in `backend/Dockerfile`.
- **Orphan AF_UNIX socket cleanup runs at every logon** (set 2026-04-26). Docker Desktop creates Unix-domain sockets under `%LOCALAPPDATA%\Docker\run\` and `%LOCALAPPDATA%\docker-secrets-engine\` for sub-services (Inference Manager, Secrets Engine, etc). On Windows these are NTFS reparse points; unclean shutdowns leave them orphaned and Windows literally cannot delete them ("the file cannot be accessed by the system"). On next launch, Docker Desktop tries to remove the stale socket before re-binding, fails, and hangs on "Starting…" forever. The fix: `scripts\reset-docker-sockets.ps1` renames any directory containing an unreadable reparse point so Docker recreates them clean. It is wired to a user-level Scheduled Task (`XFLinker-ResetDockerSockets`) that fires at every logon. **Do NOT delete that task or the script.** If a future Docker Desktop release adds new socket dirs that orphan, append the path to the `$candidateDirs` list in the script. Also: `EnableDockerAI` and `InferenceCanUseGPUVariant` in `%APPDATA%\Docker\settings-store.json` are set to `false` to keep the Inference Manager from spawning at all. Do not flip them back on unless we actually start using Docker Model Runner.

# Gemini Guard — Never Re-Add `worktreeConfig = true`

When spawning an `Agent(isolation: "worktree")`, the worktree feature silently re-adds `[extensions] worktreeConfig = true` to `.git/config`, which makes Gemini CLI and Gemini Antigravity stop responding. Immediately after the worktree operation ends, run `scripts/ensure-git-config-clean.ps1` (or `.githooks/_ensure-git-config-clean.sh`) to strip the block. The `post-checkout` and `pre-commit` hooks already strip it automatically for normal Git operations. See the full rule in `AGENTS.md` under "Gemini Guard".

# Additional Mandatory Sections in `AGENTS.md`

These sections apply to every agent and must be read before the relevant work begins. They are defined in full in `AGENTS.md` — do not duplicate them here, just follow them.

- **Comments & Documentation — All Languages**: Four rules on when and how to write comments (WHY not WHAT, self-documenting code, no stale comments, no WHAT-translations). Includes a mandatory pre-finish comment check before every commit.
- **Native Runtime Policy**: Before changing native C++, Python fallback, runtime ownership, or operator-facing runtime diagnostics, read `docs/NATIVE_RUNTIME_POLICY.md`.
- **CI and Testing — Mandatory**: Run `git config core.hooksPath .githooks` once. Never use `--no-verify`. Before pushing: backend — `python manage.py test`; frontend — `npm run test:ci && npm run build:prod`.
- **Vibe-Coding Pre-Push Rules (28 automated checks)**: `scripts/lint-all.ps1` runs these automatically. They catch debug artifacts, placeholder stubs, function length, empty catches, hardcoded secrets, N+1 queries, hardcoded styles, and missing test files. Read the full table in `AGENTS.md`.
- **UX and Smart Navigation**: Every `mat-card`, `section`, or major UI block must have a unique `id`. Internal links must use `[routerLink]` with `fragment`. Components must auto-reveal content when a fragment is detected. Use `ScrollHighlightService` for visual feedback. Every error or health warning must include plain-English explanation and actionable fix.
