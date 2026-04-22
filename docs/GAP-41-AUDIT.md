# Gap 41 — `takeUntilDestroyed()` audit

Phase E2 / Gap 41. Every HTTP `.subscribe(...)` inside a component must be
piped through `takeUntilDestroyed(destroyRef)` so the request is cancelled
(and the callback chain unregistered) when the component is destroyed.

## The fix pattern

```typescript
import { Component, DestroyRef, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

@Component({ /* ... */ })
export class SomeComponent {
  private destroyRef = inject(DestroyRef);
  private api = inject(ApiService);

  loadData(): void {
    this.api.get('/thing/')
      .pipe(takeUntilDestroyed(this.destroyRef))   // ← the only change
      .subscribe(data => this.data = data);
  }
}
```

If the observable already has `.pipe(...)`, add `takeUntilDestroyed` as the
**last** operator in the chain (after `finalize`, `catchError`, etc.) so it
can cancel the entire pipeline.

## Why it matters

Without teardown, a user clicking "Dashboard → Settings" while the dashboard
is mid-fetch will:

- keep the XHR running until the server responds (wastes backend cycles),
- execute the `.subscribe(next)` callback against a destroyed component,
- pin the component instance + callback closure in memory until GC.

On a slow connection this compounds — rapid nav creates zombie subscriptions.

## Components already fixed

| File | Gap 41 status |
|---|---|
| `app.component.ts` | ✅ already using `takeUntilDestroyed` |
| `shared/nav-progress-bar/nav-progress-bar.component.ts` | ✅ |
| `dashboard/dashboard.component.ts` | ✅ |
| `dashboard/components/webhook-log/webhook-log.component.ts` | ✅ |
| `dashboard/system-metrics/system-metrics.component.ts` | ✅ |
| `crawler/crawler.component.ts` | ✅ |
| `analytics/analytics.component.ts` | ✅ |
| `review/review.component.ts` | ✅ |
| `notification-center/notification-center.component.ts` | ✅ |
| `login/login.component.ts` | ✅ |
| `graph/graph.component.ts` | ✅ |
| `alerts/alerts.component.ts` | ✅ |
| `health/health.component.ts` | ✅ fixed in this phase (reference pattern) |

## Audit result — all files fixed

As of Phase E2 completion, every `.subscribe(...)` in every `*.component.ts`
file is protected by one of:
- `.pipe(takeUntilDestroyed(this.destroyRef))` (Angular 16+ pattern), OR
- `.pipe(takeUntil(this.destroy$))` (older Subject-based pattern, used where
  the file already had `destroy$: Subject` + `ngOnDestroy` infrastructure),
- OR the `async` pipe in the template (no ts subscribe at all).

Verification command:

```bash
cd frontend/src/app
for f in $(grep -lr "\.subscribe(" . --include="*.component.ts"); do
  awk '
    /\.subscribe\(/ {
      window = ""
      for (i = max(0, NR-10); i < NR; i++) window = window "\n" prev[i]
      if (window ~ /takeUntil/ || $0 ~ /takeUntil/ || $0 ~ /\|\s*async/) next
      print FILENAME ":" NR
    }
    function max(a, b) { return a > b ? a : b }
    { prev[NR] = $0 }
  ' "$f"
done
```

Expected output: empty. Any line printed is a new leak that must be fixed
before merge.

### Files touched (Phase E2 / Gap 41)

Component files where `takeUntilDestroyed` or `takeUntil(destroy$)` was
added in this phase:

- `health/health.component.ts` (reference implementation)
- `error-log/error-log.component.ts`
- `link-health/link-health.component.ts`
- `performance/performance.component.ts`
- `behavioral-hubs/behavioral-hubs.component.ts`
- `crawler/crawler.component.ts`
- `dashboard/dashboard.component.ts`
- `dashboard/components/webhook-log/webhook-log.component.ts`
- `dashboard/performance-mode/performance-mode.component.ts`
- `graph/graph.component.ts`
- `login/login.component.ts`
- `notification-center/notification-center.component.ts`
- `theme-customizer/theme-customizer.component.ts`
- `analytics/watched-pages/watched-pages.component.ts`
- `analytics/under-linked/under-linked.component.ts`
- `analytics/impact-diary/impact-diary.component.ts`
- `analytics/query-mismatch/query-mismatch.component.ts`
- `settings/settings.component.ts`
- `settings/helpers-settings/helpers-settings.component.ts`
- `settings/performance-settings/performance-settings.component.ts`
- `settings/weight-diagnostics-card/weight-diagnostics-card.component.ts`
- `health/safe-prune-card/safe-prune-card.component.ts`
- `jobs/jobs.component.ts`
- `core/services/session-reauth-dialog.component.ts`
- `jobs/sync-preview-dialog/sync-preview-dialog.component.ts`
- `shared/runbooks/runbook-dialog/runbook-dialog.component.ts`
- `alerts/alert-detail/alert-detail.component.ts`
- `review/suggestion-detail-dialog.component.ts`

Files that were already fully protected (no changes needed):

- `diagnostics/diagnostics.component.ts` (via `destroy$: Subject`)

## Verification

After fixing, in each file:

1. Confirm `DestroyRef` is imported and injected once.
2. Confirm `takeUntilDestroyed` appears at the tail of every `.pipe(...)`
   feeding an HTTP `.subscribe(...)`.
3. Search the file for `.subscribe(` — every hit should either be inside
   a `.pipe(...takeUntilDestroyed...)` chain, or commented as intentionally
   long-lived.

## CI guard (future follow-up)

An ESLint rule `rxjs/no-ignored-takeuntil` (via `eslint-plugin-rxjs-angular`)
can fail CI when a new HTTP subscription is added without teardown. That
guard is out of scope for this phase but recommended as a GK2 follow-up.
