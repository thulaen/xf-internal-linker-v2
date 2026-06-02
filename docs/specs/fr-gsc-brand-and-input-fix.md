# FR — GSC brand colour correction + Material outlined-field input fix

[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]
[SPEC CITED: feature=gsc-brand-and-input-fix kind=technical_doc id=w3c-css-color-4 verified_at=2026-05-30]
[SPEC CITED: feature=gsc-brand-and-input-fix kind=technical_doc id=w3c-css-variables-1 verified_at=2026-05-30]
[SPEC CITED: feature=gsc-brand-and-input-fix kind=technical_doc id=w3c-css-backgrounds-3 verified_at=2026-05-30]

## Source of truth (citations)

- W3C CSS Color Module Level 4 — https://www.w3.org/TR/css-color-4/ (hex colour
  notation `#4285f4`).
- W3C CSS Custom Properties for Cascading Variables Level 1 —
  https://www.w3.org/TR/css-variables-1/ (single design token `--color-primary`
  as the one source of truth; components read `var(--color-primary)`).
- W3C CSS Backgrounds and Borders Module Level 3 —
  https://www.w3.org/TR/css-backgrounds-3/ (per-side `border-*-width`; the
  notched-outline fix forces the notch's left/right border width to 0).

## Behaviour (Given / When / Then)

**Brand colour.**
Given the application brand colour must equal Google Search Console's measured
blue `#4285f4` and must come from one design token,
When `--color-primary` is set in `frontend/src/styles/_theme-vars.scss` and the
two runtime defaults that can override it — `AppearanceService.DEFAULT_CONFIG`
(`frontend/src/app/core/services/appearance.service.ts`) and backend
`DEFAULT_APPEARANCE` (`backend/apps/core/views.py`) — are set to the same value,
Then the token governs app-wide, AppearanceService writes no inline override
(value equals default), and no surface shows a stale blue.

**Input fields.**
Given Tailwind's preflight is off and a global border reset gives every element
`border-style: solid`, which bleeds into Angular Material's outlined-field
"notch" (whose left/right borders are normally unset),
When `frontend/src/styles.scss` adds a scoped shim forcing
`.mat-mdc-notch-piece.mdc-notched-outline__notch { border-left-width: 0
!important; border-right-width: 0 !important; }`,
Then every outlined input renders cleanly with no stray vertical borders, at rest
and when focused, and a `tabindex="-1"` heading focused for screen-reader
announcement shows no stray focus box.

## Scope and follow-ups

This spec covers the brand-token correction and the notched-outline compat shim
only. The remaining Material→CDK rebuild of the GSC primitives, the legacy
`#1a73e8` component sweep, and an automated computed-style regression test are
tracked as paper-trail #268, #269, and #270 with test-case AutoIssues
#19985–#19987.

## Regression guard

`scripts/test_brand_and_inputfix.mjs` asserts the token value, the two runtime
defaults, and the notch shim are present; it fails (Red) when the fix is
reverted and passes (Green) when applied.
