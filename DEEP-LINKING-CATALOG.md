# DEEP-LINKING-CATALOG.md — Every Surface Has A Linkable URL

**Status:** PARAMOUNT for any frontend change that adds a new route, tab, dialog, filter, or named scroll target.

## The Rule

Every page, widget, tab state, dialog, filter, or named section MUST register itself in [`frontend/src/app/core/routing/deep-link-catalog.ts`](frontend/src/app/core/routing/deep-link-catalog.ts) **in the same commit that creates it**. The CI gate at [`scripts/verify_deep_links.py`](scripts/verify_deep_links.py) walks the Angular route tree, every `MatTabGroup` child, and every `MatDialog.open()` call site, and fails the build if any is missing from the catalog.

## Why

The user is a vibe coder. Without a catalog they can't find the screen they saw yesterday. With a catalog:
- The in-app `⌘K` quick-search bar (Gap 157) finds any screen by plain-English label
- The "Copy link to this view" button (Phase 0.15 directive) produces stable, shareable URLs
- The breadcrumb component reads labels from the catalog
- A deep link to a screen that needs a missing prerequisite shows the friendly "Almost there" dialog instead of a 404
- Permission-aware fallback offers the closest accessible page when the operator hits a forbidden link

## Catalog Entry Shape

```ts
export interface DeepLinkEntry {
  /** Stable key used by quick-search and the URL ?dl= param. */
  key: string;
  /** Plain-English label shown in search results and breadcrumbs. */
  label: string;
  /** One-line subtitle explaining what the page does. */
  subtitle: string;
  /** Angular route, e.g. '/diagnostics' */
  route: string;
  /** Optional tab key inside the route (matches MatTabGroup persistKey). */
  tab?: string;
  /** Optional dialog component name to open. */
  dialog?: string;
  /** Optional named section to scroll into focus. */
  scrollTarget?: string;
  /** Search keywords beyond the label (synonyms, error messages, etc.). */
  searchTerms: string[];
  /** Required permissions (empty = anyone authenticated). */
  requires?: string[];
  /** Friendly fallback when a required prereq is missing. */
  prereqHint?: { label: string; instructions: string[]; navigateTo: string };
}
```

## Pattern

When you add `frontend/src/app/foo/foo.component.ts` with route `/foo`:

```ts
// in deep-link-catalog.ts
export const DEEP_LINK_CATALOG: DeepLinkEntry[] = [
  // … existing entries …
  {
    key: 'foo.main',
    label: 'Foo dashboard',
    subtitle: 'Visualises foo events over the last 24h',
    route: '/foo',
    searchTerms: ['foo', 'foo dashboard', 'event timeline'],
  },
];
```

Then add the `[appCopyLinkToView]` button to the page header so the operator can share the URL:

```html
<header class="page-header">
  <h1>Foo dashboard</h1>
  <button
    mat-icon-button
    appCopyLinkToView
    matTooltip="Copy link to this view"
    aria-label="Copy link to this view">
    <mat-icon>link</mat-icon>
  </button>
</header>
```

## Forbidden Patterns

- ❌ Adding a route without a catalog entry (CI fails)
- ❌ Hardcoding the page title in two places (header + catalog) — the breadcrumb reads from catalog
- ❌ Opening `MatDialog` from a button without a catalog entry referencing the dialog name
- ❌ A tab inside `MatTabGroup` that has no `appPersistTab` directive AND no catalog entry
- ❌ A 404 fallback for a known-but-prereq-missing route — use `MissingPrereqDialogComponent` instead
