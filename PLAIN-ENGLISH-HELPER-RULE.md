# PLAIN-ENGLISH-HELPER-RULE.md — Every UI Element Has A Hover Helper

**Status:** PARAMOUNT for any frontend change that adds a `<button>`, `<mat-checkbox>`, `<mat-slider>`, `<mat-form-field>`, `<mat-chip>`, or any other interactive element that surfaces a technical concept.

## The Rule

Every technical UI element MUST have a plain-English hover helper sourced from spec frontmatter. The CI gate at [`scripts/verify_helpers.py`](scripts/verify_helpers.py) scans Angular templates for technical elements and fails the build if any lacks a helper.

## Why

The user is a vibe coder. Without helpers, a settings page full of "RSQVA max_vocab_size = 25000" sliders is opaque. With helpers, hovering shows: "Reverse Search-Query Vocabulary Alignment — bigger number means more search terms remembered, at the cost of memory."

## The Helper Directive

[`frontend/src/app/core/directives/plain-english-helper.directive.ts`](frontend/src/app/core/directives/plain-english-helper.directive.ts) wraps `matTooltip` with a spec-link affordance:

```html
<mat-checkbox
  peHelper="Turns on the OPQ retrieval index — compresses each vector to 64 bytes for faster search"
  peSpec="docs/specs/fr053-passage-level-relevance.md">
  Enable OPQ index
</mat-checkbox>
```

When the user hovers the element they see the helper text. When they click the spec link icon they get the Material spec viewer dialog.

## Source Of Truth: Spec Frontmatter

Every spec at `docs/specs/<id>.md` has a `helper:` frontmatter field. One sentence. Plain English. Read at build time by [`scripts/build_helper_catalog.py`](scripts/build_helper_catalog.py) which produces [`frontend/src/app/generated/helper-catalog.ts`](frontend/src/app/generated/helper-catalog.ts).

```markdown
---
id: fr053
helper: "OPQ + IVF compress each passage embedding to 64 bytes so retrieval stays fast as the corpus grows."
---
```

## Pattern For Every Element Class

| Element | Helper required? | Notes |
|---|---|---|
| `<button mat-button>` named action | Yes | "Save" / "Cancel" exempt |
| `<button mat-icon-button>` | Yes | matTooltip on the icon |
| `<mat-checkbox>` | Yes | Above the label |
| `<mat-slide-toggle>` | Yes | Above the label |
| `<mat-form-field>` + matInput | Yes | Tooltip on the field, hint below |
| `<mat-chip>` filter | Yes | Tooltip explains the filter |
| `<mat-icon>` standalone | Yes | aria-label + matTooltip |
| `<mat-table>` column header | Yes | Tooltip explains the column |
| `<mat-tab-group>` tab label | Yes | Tooltip explains the tab |
| Decorative icon (visually hidden) | No | Allow-listed via comment |

## Forbidden Patterns

- ❌ A new technical element with no `peHelper` AND no `matTooltip`
- ❌ A helper text that uses jargon without immediate definition
- ❌ A helper longer than two short sentences (move to the spec viewer)
- ❌ A spec without a `helper:` frontmatter line (CI fails when `helper-catalog` build runs)
- ❌ A helper in the template instead of in the spec (rot risk — code and spec drift apart)

## Why "Plain English" Specifically

The user is not a developer. "Tunable retrieval recall via product-quantised lookup tables" is jargon stew. "Compresses each vector to 64 bytes so retrieval stays fast" is plain English. Helpers are the project's UX-level commitment to the Plain-English Communication Rule from CLAUDE.md.
