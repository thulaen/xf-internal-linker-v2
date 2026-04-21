# Frontend Visual Quality Rules

**Read `src/styles/_theme-vars.scss` before writing any SCSS. It is the single source of truth.**
**Read `DESIGN-PATTERNS.md` (sibling of this file) before touching any component — it is the authoritative GA4 design language reference (extracted 2026-04-20). Covers card anatomy, co-location rules, button sizing, spacing tokens, and the 11 anti-patterns that contaminate layouts. `_theme-vars.scss` is the token file; `DESIGN-PATTERNS.md` is the pattern file.**

Global Material overrides live in `src/styles.scss`. Never duplicate them in a component.

**For commenting rules, see `AGENTS.md § Code Quality Mandate > Comments & Documentation — All Languages`. Rules in this file extend that rule set; they do not replace it.**

---

## Spacing -- Hard Rules

All values must be multiples of 4px: `4 | 8 | 12 | 16 | 24 | 32 | 48 | 64`. No exceptions.

| Rule | Detail |
|---|---|
| **Min gap between siblings** | 8px. No element may touch another element. |
| **Min padding from container edge** | 16px. No content flush against a card, page edge, or section wall. |
| **Use `gap` on flex/grid** | Never use `margin-right` or `margin-bottom` on children for sibling spacing. |
| **No zero padding/margin** | Never set `padding: 0` or `margin: 0` on a visible container without a code comment explaining why. |

### Spacing Tokens -- Use These, Never Hardcode

| Token | Value | Use for |
|---|---|---|
| `var(--spacing-page)` | 48px 64px | Outer page padding |
| `var(--spacing-card)` | 24px | Card inner padding |
| `var(--spacing-md)` | 24px | Section gaps between cards |
| `var(--spacing-sm)` | 12px | Inline gaps: buttons, chips, icons |
| `var(--spacing-field)` | 16px | Form field bottom margin |
| `var(--space-xs)` | 4px | Tight spacing |
| `var(--space-sm)` | 8px | Small spacing |
| `var(--space-md)` | 16px | Medium spacing |
| `var(--space-lg)` | 24px | Large spacing |
| `var(--space-xl)` | 32px | Extra-large spacing |

---

## Colors & Typography -- Hard Rules

- **No hex colors** in `.component.scss`. Use `var(--color-*)` tokens only.
- **No `font-family`** in any component. Inherited from `var(--font-family)`.
- **No `font-size` below 11px.** Minimum readable size.
- **No gradients.** `linear-gradient` and `radial-gradient` are forbidden.
- **No `box-shadow` on cards at rest.** Hover only, via `var(--shadow-hover)`.

---

## Overflow & Truncation -- Hard Rules

- Truncated text must use `text-overflow: ellipsis` AND `matTooltip` with the full text.
- No `overflow: hidden` on a container unless you verify no child is clipped.
- No horizontal scroll at 1280px viewport width.

---

## Before You Finish — Checklist

Run this before completing any frontend task:

1. Does any element touch another element or a container edge? Fix it.
2. Are all spacing values multiples of 4px and using tokens? Fix it.
3. Are all colors using `var(--color-*)` CSS variables? Fix it.
4. Is any text truncated without a tooltip fallback? Fix it.
5. Does the page scroll horizontally at 1280px? Fix it.

---

## Layout Precision Rules — Mandatory

These rules come from real layout bugs found in screenshots. Check all four on every task.

### Rule A — Filter Chips: 16px Left Clearance
The first chip in any filter bar or `mat-chip-listbox` MUST have at least `16px` clearance from the left container wall.
```scss
// Correct
mat-chip-listbox { padding-left: var(--space-md); } // 16px
```
Never render a chip list flush-left against a card or page edge.

### Rule B — Form Fields: Centred and Padded Inside Cards
Every card section containing form fields MUST have `padding: var(--spacing-card)` (24px) on all four sides.
Sparse forms (1–2 fields in a wide section) MUST be centred both horizontally and vertically:
```scss
// Correct for sparse forms
.form-section {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-card);
}
```

### Rule C — Buttons: 16px Edge Clearance + Baseline Alignment
No button may be flush against any container wall. Always use `var(--space-md)` (16px) minimum clearance.
Buttons in a row with inputs MUST use `align-items: center` so they share the same baseline:
```scss
// Correct
.action-row {
  display: flex;
  align-items: center;
  gap: var(--space-md);
}
```

### Rule D — Compound Labels: Visible Separators
When two pieces of metadata appear on the same line, use a visible separator:
- ` • ` — for secondary meta (e.g., `Forum Node • 0 posts`)
- ` — ` — for ranges or classifications
- `: ` — for label–value pairs (e.g., `Full import: Body text, sentences`)

Never concatenate strings with only whitespace — they visually merge when font weights vary.

