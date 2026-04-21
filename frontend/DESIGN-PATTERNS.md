# XF Internal Linker — Design Patterns

**Authoritative reference for all AI agents (Claude, Codex, Gemini) and human contributors.**
Extracted from the live Google Analytics 4 product on 2026-04-20. Every value here was measured directly from the GA4 DOM — not approximated.

Read this file before touching any frontend component. It is the single source of truth for component patterns, card anatomy, and spacing. `default-theme.scss` is the token file; this file is the *pattern* file.

---

## 1. GA4 Design Token Reference (Ground Truth)

These values were extracted from `analytics.google.com` on 2026-04-20 via `getComputedStyle` and `getBoundingClientRect`.

### Colours

| Token | Hex | Measured value | Use |
|---|---|---|---|
| `--color-primary` | `#1a73e8` | `rgb(26, 115, 232)` | Brand blue — buttons, links, active states |
| `--color-blue-50` | `#e8f0fe` | `rgb(232, 240, 254)` | Active surface tint — active nav, active mode-button |
| `--color-bg-page` | `#fafafa` | `rgb(250, 250, 250)` | Page background |
| `--color-bg-white` | `#ffffff` | `rgb(255, 255, 255)` | Card surface |
| `--color-text-primary` | `#202124` | `rgba(0, 0, 0, 0.87)` | Main body text |
| `--color-text-secondary` | `#3c4043` | `rgb(60, 64, 67)` | Secondary text, headings |
| `--color-text-muted` | `#5f6368` | `rgb(95, 99, 104)` | Captions, labels, hints |
| `--color-border` | `#dadce0` | `rgb(218, 220, 224)` | All borders and dividers |
| `--card-border` | `0.8px solid #dadce0` | Measured on `xap-card` | Card and stroked-button border |

### Typography

| Property | Value | Source |
|---|---|---|
| Font family | System stack (Roboto fallback) | `var(--font-family)` |
| Base font size | `13px` | `getComputedStyle(body).fontSize` |
| Button label size | `14px` | Measured on GA4 stroked buttons |
| Button font weight | `500` | Measured on GA4 stroked buttons |
| Section heading size | `16px` | Measured on GA4 tab labels |
| Page title size | `22px` | `var(--page-title-size)` |
| Metric/stat number | `22px–24px` | Measured on GA4 metric tiles |

### Cards

| Property | Value | Source |
|---|---|---|
| Border | `0.8px solid #dadce0` | Measured on `xap-card` |
| Border-radius | `8px` | Measured on `xap-card` |
| Box-shadow at rest | `none` | Measured on `xap-card` |
| Box-shadow on hover | `var(--shadow-hover)` = `0 1px 3px rgba(60,64,67,0.15)` | Extracted from shadow tokens |
| Background | `#ffffff` | Measured on `xap-card` |

### Navigation

| Property | Value | Source |
|---|---|---|
| Expanded nav width | `312px` (GA4) / `256px` (our app) | Measured |
| Nav item border-radius | `4px 44px 44px 4px` | Measured on GA4 nav item |
| Active nav background | `#e8f0fe` | Measured on GA4 active item |
| Nav item height | `36px` | Measured on GA4 nav item |
| Nav item padding | `8px 4px 8px 16px` | Measured on GA4 nav item |

### Buttons (stroked/outlined)

| Property | Value | Source |
|---|---|---|
| Height | `36px` | Measured on GA4 stroked buttons |
| Border at rest | `0.8px solid #dadce0` | Measured |
| Border-radius | `4px` (GA4 M2) | Measured — our M3 uses `var(--mdc-outlined-button-container-shape)` |
| Text colour | `#1a73e8` | Measured |
| Font size | `14px` | Measured |
| Font weight | `500` | Measured |
| Padding | `0px 23px` | Measured |
| Minimum width in action rows | `140px` | Rule enforced globally via `.dashboard-action-row` |

---

## 2. Card Anatomy — The Only Correct Structure

```
mat-card
  mat-card-header      ← mat-icon (avatar) + mat-card-title only
  mat-card-content     ← ALL body content:
                          · status chips
                          · co-located chip+button rows
                          · mode selectors
                          · text/data
                          · empty-state + companion CTA button
  mat-accordion        ← help/glossary panels only (optional)
  mat-card-actions     ← standalone footer buttons (.dashboard-action-row)
```

**What goes where:**
- `mat-card-header`: icon + title only. Never put content here.
- `mat-card-content`: everything else. This is where chips, mode buttons, data rows, and co-located chip+button pairs live.
- `mat-accordion`: only for "What do these mean?" / help text that the user can expand. Never for primary content.
- `mat-card-actions`: only for footer buttons that operate on the whole card (e.g. "View all", "Reset"). Always add `.dashboard-action-row`.

---

## 3. The Cardinal Rule: Co-location

**If a chip/badge and an action button belong to the same row, they must share one flex container inside `mat-card-content`. Never split them between `mat-card-content` and `mat-card-actions`.**

Splitting them causes the button to float at the bottom-right, visually disconnected from the content it operates on.

### Correct pattern

```html
<mat-card-content>
  <div class="[component]-header">
    <mat-chip class="engine-chip" disableRipple>
      <mat-icon matChipAvatar>psychology</mat-icon>
      Auto-tuner (Python L-BFGS)
    </mat-chip>
    <a mat-stroked-button routerLink="/settings" fragment="ranking-weights">
      <mat-icon>settings</mat-icon> Adjust Weights
    </a>
  </div>
  <!-- rest of card content below -->
</mat-card-content>
```

```scss
.[component]-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-md);           // 16px
  margin-bottom: var(--space-md); // 16px below the header row
}
```

### Wrong pattern (never do this)

```html
<!-- ❌ WRONG — chip and button in separate sections -->
<mat-card-content>
  <mat-chip>CPU Mode</mat-chip>
</mat-card-content>
<mat-card-actions>
  <a mat-stroked-button>Adjust Mode</a>  <!-- looks disconnected -->
</mat-card-actions>
```

---

## 4. Empty State + Companion CTA

When a card shows an empty state, its CTA button goes **inside `mat-card-content`**, directly below the empty state component, **centred**. It must never be in a separate `mat-card-actions` — that would push it to the bottom-right corner, away from the message it belongs to.

```html
<mat-card-content>
  @if (items.length === 0) {
    <app-empty-state
      icon="pause_circle"
      heading="No tasks running"
      body="Everything is idle." />
    <div class="idle-actions">
      <a mat-stroked-button routerLink="/jobs">
        <mat-icon>open_in_new</mat-icon>
        Open Jobs
      </a>
    </div>
  } @else {
    <!-- list items -->
  }
</mat-card-content>
```

```scss
.idle-actions {
  display: flex;
  justify-content: center;
  margin-top: var(--space-md);   // 16px below the empty state
}
```

---

## 5. `.dashboard-action-row` — Use It, Never Override It

Defined globally in `frontend/src/styles.scss`. Apply to every `mat-card-actions`.

**What it provides (don't re-implement these locally):**
- `display: flex; align-items: center; justify-content: flex-end`
- `gap: var(--space-sm)` — 8px between buttons
- `flex-wrap: wrap`
- `padding: var(--space-sm) var(--space-md)` — 8px top, 16px sides
- `border-top: var(--card-border)` — 0.8px solid #dadce0
- `min-height: 52px`
- `min-width: 140px` on all stroked buttons inside

**Usage:**
```html
<mat-card-actions align="end" class="dashboard-action-row">
  <button mat-stroked-button>Safe Boot on Restart</button>
  <button mat-stroked-button>Reset to Balanced</button>
</mat-card-actions>
```

**Never add these to a component's own `.scss` for mat-card-actions:**
```scss
/* ❌ Never override these — the global rule handles them */
mat-card-actions { padding: 16px; }
mat-card-actions { gap: 4px; }
mat-card-actions { display: flex; justify-content: flex-end; }
```

If a specific component needs extra top separation (e.g. when a `mat-accordion` precedes the actions), add only `margin-top`:
```scss
.my-actions { margin-top: var(--space-lg); }  // 24px — see Rule F below
```

---

## 6. Accordion Inside Cards

When `mat-accordion` sits inside a card, apply these rules without exception:

1. **Accordion itself:** `margin-top: var(--space-md)` (16px) to separate it from the preceding content.
2. **Following `mat-card-actions`:** Add `margin-top: var(--space-lg)` (24px) on the actions block. The `border-top` from `.dashboard-action-row` alone is not enough visual breathing room after an accordion.
3. **Panel styling:** Always `box-shadow: none !important; border: var(--card-border); border-radius: var(--radius-md, 8px)`.

```scss
.help-accordion { margin-top: var(--space-md); box-shadow: none; }
.help-panel { box-shadow: none !important; border: var(--card-border); border-radius: var(--radius-md, 8px) !important; }
.card-actions-after-accordion { margin-top: var(--space-lg); }
```

---

## 7. Mode-Selector Button Grid

Three-column flex grid for picking between modes (Safe / Balanced / High Performance):

```html
<div class="mode-options">
  @for (opt of modes; track opt.key) {
    <button class="mode-button" [class.active]="current === opt.key">
      <mat-icon>{{ opt.icon }}</mat-icon>
      <span class="mode-label">{{ opt.label }}</span>
      <span class="mode-desc">{{ opt.description }}</span>
    </button>
  }
</div>
```

```scss
.mode-options { display: flex; gap: var(--space-sm); flex-wrap: wrap; }
.mode-button {
  flex: 1; min-width: 120px;
  display: flex; flex-direction: column; align-items: center;
  gap: var(--space-xs); padding: var(--space-md);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-white);
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}
.mode-button:hover:not(:disabled) {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-hover);
}
.mode-button.active {
  border-color: var(--color-primary);
  background: var(--color-blue-50);  // #e8f0fe — GA4 active tint
}
.mode-button:disabled { opacity: 0.6; cursor: not-allowed; }
.mode-button.pending { opacity: 1; }  // keep visible while spinner shows
.mode-label { font-size: 13px; font-weight: 500; color: var(--color-text-primary); }
.mode-desc { font-size: 11px; color: var(--color-text-muted); text-align: center; }
```

---

## 8. Pill Filter Chips (Expiry / Toggle Chips)

For inline toggle buttons that look like chips:

```scss
.expiry-chip {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
  height: 32px;
  padding: 0 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-pill);
  background: var(--color-bg-white);
  color: var(--color-text-secondary);
  font-size: 12px; font-weight: 500;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}
.expiry-chip:hover { border-color: var(--color-primary); color: var(--color-primary); }
.expiry-chip.active {
  background: var(--color-blue-50);   // #e8f0fe
  border-color: var(--color-primary);
  color: var(--color-primary);
}
// Icon inside pill chip
.expiry-icon { font-size: 16px; width: 16px; height: 16px; }
// Group of pills
.pill-group { display: flex; flex-wrap: wrap; gap: var(--space-sm); }
```

---

## 9. Spacing Reference — 4px Grid, Always

| Token | Value | Use case |
|---|---|---|
| `--space-xs` | `4px` | Icon-to-label gap **inside** a single button or chip |
| `--space-sm` | `8px` | Gap between sibling buttons; gap between pills |
| `--space-md` | `16px` | Section gaps within a card; `margin-bottom` on header rows |
| `--space-lg` | `24px` | Major section separation; gap between accordion and actions |
| `--space-xl` | `32px` | Between separate cards on a page |
| `--spacing-card` | `24px` | `mat-card` inner padding |

**Never hardcode pixel values.** Use tokens. If you need a value not on this scale, round to the nearest 4px step.

---

## 10. Interactive States (Mandatory on Every Interactive Element)

| State | Rule |
|---|---|
| Default | `border: var(--card-border)` or `1px solid var(--color-border)`; `box-shadow: none` |
| Hover | `var(--shadow-hover)` + `border-color: var(--color-primary)` |
| Focus | M3 Expressive focus ring — **never** suppress `outline` or `outline-offset` |
| Active/pressed | Tonal ripple at full opacity — never suppress |
| Disabled | `opacity: 0.38`; `cursor: not-allowed` |
| Loading / pending | `mat-spinner` centred; keep label visible; button disabled while pending |
| Transition | **Required** on every interactive element: `all 0.2s cubic-bezier(0.4, 0, 0.2, 1)` |

---

## 11. What AI Agents Must Never Do

These are the exact mistakes that created the layout bugs this document was written to fix:

| Anti-pattern | Why it's wrong | Correct approach |
|---|---|---|
| `mat-card-actions { padding: var(--space-md); }` in a component | Overrides the global rule, causes inconsistent footers | Delete it — `.dashboard-action-row` handles padding globally |
| Chip in `mat-card-content`, button in `mat-card-actions` | They look disconnected | Put both in a flex wrapper inside `mat-card-content` |
| Empty-state text in content, CTA button in `mat-card-actions` | Button ends up far from the message it belongs to | Put the button inside content, centred below the empty state |
| `gap: var(--space-xs)` between sibling buttons | 4px is for icon-to-label spacing, not button-to-button | Use `gap: var(--space-sm)` (8px) minimum between buttons |
| Hardcoded `#e8f0fe` or `#1a73e8` in component SCSS | Drifts from the token system | Use `var(--color-blue-50)` and `var(--color-primary)` |
| `--color-blue-50: #c2e7ff` | Wrong — was measured as `#c2e7ff` but GA4 uses `#e8f0fe` | Corrected in `_theme-vars.scss` on 2026-04-20 |
