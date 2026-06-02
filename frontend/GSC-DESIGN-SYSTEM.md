# GSC Design System — READ BEFORE TOUCHING FRONTEND UI

**Status: active redesign (2026-05-30). All agents (Claude / Codex / Gemini / Antigravity /
future) MUST read this before changing any frontend layout, dashboard, navigation, card, or
theme.** This protects an in-progress, user-approved redesign from being accidentally undone.

The full plan lives at `.claude/plans/first-tell-me-how-gentle-crab.md` (Parts 1–7). This file is
the short, durable summary of the *decisions* that must not be reverted.

## Stack decision (2026-05-30): migrating OFF Angular Material → Angular CDK + Tailwind

After an A/B spike, the user chose to move the whole frontend **off Angular Material** to
**Angular CDK + Tailwind** (no third-party UI library): CDK supplies headless behaviour +
accessibility, Tailwind supplies styling, and **we own every component's markup**. Tailwind is
installed with **preflight off** (`tailwind.config.js`) so it coexists with Material *during* the
migration. Colours/spacing still come from the existing CSS tokens (referenced via Tailwind
arbitrary values, e.g. `bg-[color:var(--color-primary)]`), so the token system stays the source of
truth.

**The quality bar — the result must be indistinguishable from a real shadcn/React app.** A user
inspecting the running UI should believe it was built with shadcn on React. Every primitive we own
must hit that level of polish: spacing rhythm, focus-visible rings, hover transitions, type scale,
and flat tokened surfaces. "Close enough" is not the bar — if a random user could tell it's not
shadcn/React, the work is not done.

**This supersedes the "Always Use Angular Material" mandate** in `CLAUDE.md`/`AGENTS.md` and means
the Material-based GSC primitives (`gsc-summary-card`, `gsc-metric-tiles`, `gsc-insight-card`,
`gsc-kpi`) will be rebuilt Material-free. The migration is phased; Material stays installed until
the last widget is converted, then the dependency is removed.

## The one decision: the app looks like Google Search Console (GSC)

The visual language is **Google Search Console**, confirmed by the user after a live comparison of
GSC vs Cloudflare vs SEMrush.

- **GSC = the reference** (calm, flat, lots of whitespace; report = metric tiles → chart → tabbed
  table; overview = stacked summary cards with "Full report ›").
- **Cloudflare = rejected** as the look (it is a dense multi-product control panel; its brand is
  **orange + gradients**, both already forbidden by `CLAUDE.md`).
## Measured GSC specs (computed CSS captured from live GSC, 2026-05-30)

Read off the live DOM via DevTools — these are the authoritative values, recorded as `--gsc-*`
tokens in `_theme-vars.scss`. Do NOT eyeball; use these.

| Element | Value |
|---|---|
| Primary / link blue | **`#4285f4`** (GSC brand blue) — **adopted app-wide**, replacing the earlier `#0b57d0` and legacy GA4 `#1a73e8` |
| Card corner radius | **12px** (`--card-border-radius`, was 8px) |
| Stacked-card gap | **24px** |
| Card title | **24px / line-height 32px / weight 400 / `#474747`** |
| "Full report" link | **14px / weight 500 / `#4285f4` / letter-spacing 0.15px** |
| Top-bar search field | **46px tall / 16px / `#474747`** |
| Metric tile | **min-width 180px / active fill `#4285f4` (clicks), purple (impressions) / white text** |
| Metric value (big number) | **32px / weight 400** |

**Brand-value change (user decision 2026-05-30, corrected same day):** the app's primary blue is
`#4285f4` (`rgb(66, 133, 244)` — GSC's brand blue, superseding the earlier `#0b57d0`) and card
radius 12px — adopting GSC's exact values. The legacy GA4 `#1a73e8` / 8px references in
`CLAUDE.md`, `FRONTEND-RULES.md`, and `DESIGN-PATTERNS.md` are superseded and must be updated to
match. Do the recolour ONLY via the source tokens in `_theme-vars.scss` (one place, whole app).

Two ideas borrowed (rendered in GSC's flat style, not the source's branding):
- From **Cloudflare**: group the long nav into labelled sections + a prominent `Ctrl-K` search.
- From **SEMrush**: one health-score gauge; one segmented status bar + legend (instead of many
  stat cards); a "How to fix" link per issue; a "start here" attention banner; deltas on every
  metric; KPI = big number + delta + sparkline.

## Use the GSC primitive components — do NOT reinvent

Reusable building blocks live in `frontend/src/app/shared/gsc/`. Compose pages from these; do not
hand-roll bespoke cards/tiles:

| Component | Use for |
|---|---|
| `app-gsc-summary-card` | A dashboard/overview section: title + optional "Full report ›" routed link + projected body |
| `app-gsc-kpi` | A labelled big number with a coloured up/down delta (`lowerIsBetter` inverts colour) |
| `app-gsc-insight-card` | The "start here" attention banner (tone info/warning/success + optional routed action) |
| `app-gsc-data-table` *(planned)* | Tabbed, sortable table with series-coloured numbers |
| `app-gsc-metric-tiles` *(planned)* | The fill-on-active metric tiles (Clicks/Impressions style) |
| `app-gsc-top-bar` *(planned)* | Centred search pill + right icon cluster |
| `app-gsc-chart` *(planned)* | Dual-axis line chart |

Each is standalone, `OnPush`, tokens-only, with a spec. Extend these or add new `gsc-*` primitives;
do not duplicate them per-page.

## Hard rules (already enforced or being enforced)

1. **No inline `style="..."` in templates.** Move styling to the component `.scss`/`styles` using
   tokens. (Being locked with the `@angular-eslint/template/no-inline-styles` rule.)
2. **Tokens only** — no hardcoded hex (stylelint blocks it), no orange, no gradients. New shared
   sizes/colours go in `frontend/src/styles/_theme-vars.scss` (the GSC `--series-*`,
   `--gsc-*` tokens already added there).
3. **4px spacing grid**, Angular Material components, `peHelper`/`matTooltip` on technical
   elements, and every new route/tab/dialog registered in
   `frontend/src/app/core/routing/deep-link-catalog.ts`.

## Spacing & rhythm — the breathing-room rules (no cramping)

Cramping (elements too close, no breathing room) is a design defect, not a detail.
Every component follows these, using tokens only — never eyeballed px:

- **Card padding:** content never touches a card edge. Use `var(--space-lg)` (24px) inside
  cards by default; `var(--space-md)` (16px) only for genuinely dense rows.
- **Icon ↔ text gap:** at least `var(--space-md)` (16px) between an icon and the text it labels.
  Icons are never jammed against text.
- **Stacked text rhythm:** a headline and its sub-line get a `var(--space-xs)`/`sm` gap **and**
  `line-height ≥ 1.4`. Two lines must never look like one block.
- **Between sibling blocks:** `var(--space-md)`+ (16px). No element touches another.
- **Buttons:** ≥16px clearance from every edge (usually satisfied by card padding).
- **Hierarchy:** a primary line is larger/heavier (`--font-size-xl`/`lg`, weight 500); secondary
  text is smaller and `--color-text-secondary`. Don't render everything at one weight/size.
- **Cards are flat white.** No tinted backgrounds, no coloured left-borders. Tone/severity is
  conveyed by the **icon colour** (and small coloured deltas), never a filled card — GSC cards are
  white. Colour in the app is reserved for icons, links, deltas, and chart series.

These live in the primitives (each primitive encapsulates its own refined spacing **once**) and in
the spacing tokens — so composing a page can't produce cramped UI. **Verify visually in the live
preview before declaring any component done.**

## Dashboard rule (the big one)

The dashboard is being cut from ~67 widgets to **~6 calm GSC summary cards** (attention banner →
Performance → Review queue → Content & sync → one System-health gauge → Recent activity). When
editing the dashboard:
- Do NOT re-add health widgets — there is **one** health gauge (the 5 old ones were merged).
- Mode/runtime/pause/emergency-stop controls live in **Settings**, not the dashboard.
- System metrics (CPU/RAM/GPU), RUM, webhook log live in **Diagnostics**.
- Educational/onboarding cards live on the **Learn** page (`/learn`), not the dashboard.
- Nothing is deleted — moved widgets are **re-homed**, keeping their logic.

## Navigation rule

Nav is grouped: **Dashboard / Review / Analytics / Diagnostics** + a **Settings** gear. The
previously-orphaned pages **FindBugs, Observability, Work Queue** are now wired (routes + nav +
deep-link catalog) under Diagnostics — do NOT remove their routes/links again. Flat route paths
(`/find-bugs`, `/observability`, `/work-queue`) match the existing convention.

## A/B comparison workflow (mandatory)

After each major UI change: screenshot the page **before**, build, screenshot **after**, and
compare both against the matching GSC reference. Keep the "before" shots as the regression
baseline. The running prod stack serves the *built* bundle, so capture "before" shots before
rebuilding.

## Live preview for development

`frontend/proxy.conf.json` routes the dev server's `/api` (etc.) to the running prod stack on
`localhost`. Run a hot-reloading preview with:

```
npm --prefix frontend start -- --proxy-config proxy.conf.json
```

Open `http://localhost:4200`. This is **host dev tooling only** — it does NOT add a frontend
service to `docker-compose.yml` (which remains prod-only per `CLAUDE.md`).

## Do-not-revert checklist

- The GSC `--series-*` / `--gsc-*` tokens in `_theme-vars.scss`.
- The `frontend/src/styles/_utilities.scss` layout helpers.
- The `frontend/src/app/shared/gsc/` primitives + their specs.
- The FindBugs / Observability / Work-Queue routes + nav links + the fixed `/observability` link.
- The `faro.module.ts` fix (`faroEndpoint`, not `faroUrl`).
