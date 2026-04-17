# UI Audit — Phase GK2 (Gaps 233-241)

Gaps 233-241 in the master plan cover *audit* work, not new components.
This document records how each rule is enforced and the convention any
AI session must follow going forward.

## Gap 233 — Screen-reader form-error announcements

**Rule:** every Angular form validation error must be readable by a
screen reader as soon as it surfaces.

- Angular Material's `<mat-error>` already sets `aria-live="polite"`
  on its host. Use `<mat-error>`, never a raw `<div class="error">`.
- When validation messages are rendered outside a form field (page-top
  summaries, Gap 111), wrap them in
  `<div role="alert" aria-live="polite">`.
- `CLAUDE.md` "Validation Messages" section is the code-rule anchor.

## Gap 234 — Aria-label on icon-only buttons

**Rule:** every `<button mat-icon-button>` or `<button><mat-icon>…</mat-icon></button>`
must carry an `aria-label` OR the surrounding element must supply an
accessible name (e.g. `matTooltip` with `aria-describedby`).

- `matTooltip` alone is NOT enough — it provides a description, not an
  accessible name. Always add `aria-label` when the button has no
  visible text.
- Enforced by `axe-core` in the Phase A1 CI gate
  (`apps/suggestions/tests/test_a11y.py` equivalent on the frontend).

## Gap 235 — Visible keyboard-focus styles

**Rule:** every interactive element must paint a visible focus ring
when reached via keyboard.

- `styles/default-theme.scss` sets a global `:focus-visible { outline:
  2px solid var(--color-primary); outline-offset: 2px; }`.
- Components never `outline: none` without replacing the ring with an
  equivalent box-shadow.
- `prefers-reduced-motion` does not disable focus rings — motion
  preferences only affect animations.

## Gap 236 — Minimum 14px body text

**Rule:** no body text below 14px. Exceptions: chip labels (11px),
tabular numerals in status strips (11px), footer metadata (11px).

- CSS custom properties `--font-size-body-md: 13px` exists for
  Material-default density; all visible copy uses `--font-size-body-md`
  or larger.
- Phase A1 Gap 99 multiplies the base via the 90/100/115/130
  user toggle — a 130% user sees 16.9px body, well past WCAG AA.

## Gap 237 — Consistent iconography

**Rule:** Material Icons ligature names only. No Font Awesome, no
Heroicons, no raw SVG files, no emoji used AS UI.

- Enforced by `CLAUDE.md` "Icons — Material Icons Only" clause.
- Emoji are permitted in user-supplied text (comments, feature
  requests) but never in app chrome.

## Gap 238 — 4px spacing grid

**Rule:** every margin/padding value is a multiple of 4px.

- Allowed scale: 4 · 8 · 12 · 16 · 24 · 32 · 48 · 64. See `CLAUDE.md`
  "Spacing — 4px Grid Only".
- CSS variables `--space-xs`..`--space-xl` mirror the scale.
- Values like 5/10/15/18/20 are forbidden even when copying from a
  GA4 reference — round to the nearest 4px.

## Gap 239 — Button hierarchy

**Rule:** at most one primary button per view. Secondary actions use
`mat-stroked-button` (outline) or `mat-button` (text).

- The primary is the action the page asks the operator to take —
  "Save", "Run pipeline", "Approve". Everything else steps down a
  tier.
- A destructive action uses `color="warn"` on either tier; it is still
  counted toward the single-primary limit only when it is the page's
  main action (e.g. a dedicated "Delete account" page).

## Gap 240 — Consistent terminology glossary

**Rule:** the same thing has the same name across the app. See
`docs/GLOSSARY.md` (generated via the Gap 69 drawer).

Canonical names:

| Concept | Canonical term | Never say |
|---|---|---|
| Suggestion row awaiting review | "Pending suggestion" | Proposal, draft |
| Worker process | "Worker" | Job, task-runner |
| Backend-initiated batch job | "Sync job" | Import job (unless specifically `import`) |
| Approval action | "Approve" | Accept, okay |
| Rejection action | "Reject" | Deny, trash |
| Plain-English summary shown at top | "Status Story" | Overview, dashboard blurb |

Enforcement: manual PR review + a pytest scan of every Angular
template for banned strings.

## Gap 241 — Graceful no-JS fallback

**Rule:** when JavaScript is disabled, the shell must render a
one-line message directing the operator to enable JS, not a blank
page.

- Implemented in `src/index.html`:
  ```html
  <noscript>
    <div style="padding:24px;font:14px sans-serif">
      This tool requires JavaScript. Please enable it and refresh.
    </div>
  </noscript>
  ```
- Screen readers read the noscript content when JS is off.

---

*Gaps 227, 228, 230-232 (per-table freshness, per-card last-refreshed,
column freezing, column reordering, column customisation dialog) are
implementation items — see `FreshnessBadgeComponent`,
`table-preferences.service.ts`, `TableColumnFreezeDirective` (pending),
and the existing Gap 36 persistence layer.*

*Gap 242, 243 (retry buttons) are implemented via the shared
`ErrorCardComponent` "Try again" button + a manual "Retry" icon-button
on every error surface.*
