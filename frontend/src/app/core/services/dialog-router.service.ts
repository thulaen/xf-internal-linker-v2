import { Injectable, Type, inject } from '@angular/core';
import { ActivatedRoute, NavigationEnd, Router } from '@angular/router';
import { MatDialog, MatDialogConfig, MatDialogRef } from '@angular/material/dialog';
import { filter } from 'rxjs';

/**
 * Phase E2 / Gap 45 — sync MatDialog state with the URL.
 *
 * Problem: a user clicks "Open filter", configures it, copies the page URL
 * to send to a teammate. The teammate opens the link — the dialog is gone.
 * The URL says nothing about dialog state.
 *
 * Solution: register a dialog by name, then:
 *   - `open(name)` opens it AND writes `?dialog=<name>` to the URL.
 *   - On page load, if `?dialog=<name>` matches a registered dialog, we
 *     open it automatically.
 *   - Closing the dialog (any path — backdrop, ESC, programmatic) removes
 *     the query param without triggering a new navigation entry.
 *
 * Scope limits (intentional):
 *   - Only one dialog can be URL-bound at a time. Stacking dialogs is rare
 *     and brings all of URL-as-state's hairball problems (nested dialogs,
 *     mis-aligned close order). A second `open()` call closes the first.
 *   - Dialog `data` is NOT serialized to the URL. If your dialog takes
 *     user IDs or filter values, encode them in your own query params and
 *     have the dialog read them via `ActivatedRoute`. This service only
 *     syncs the which-dialog-is-open flag.
 *
 * Usage:
 *   // In a component:
 *   private dialogRouter = inject(DialogRouterService);
 *
 *   ngOnInit(): void {
 *     this.dialogRouter.register('filter', FilterDialogComponent, {
 *       width: '480px',
 *     });
 *   }
 *
 *   openFilter(): void {
 *     this.dialogRouter.open('filter');
 *   }
 *
 *   // URL becomes ?dialog=filter. Closing the dialog removes it.
 */
@Injectable({ providedIn: 'root' })
export class DialogRouterService {
  private readonly dialog = inject(MatDialog);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  private readonly registrations = new Map<string, DialogRegistration<unknown>>();
  private activeName: string | null = null;
  private activeRef: MatDialogRef<unknown> | null = null;
  private started = false;

  /** Call once from a root component (e.g. `AppComponent.ngOnInit`) so we
   *  can listen for URL changes and reopen the matching dialog when the
   *  user navigates back or lands on a deep link. */
  start(): void {
    if (this.started) return;
    this.started = true;

    // Initial page load — react to whatever ?dialog= is already present.
    this.syncFromUrl();

    // React to subsequent navigations (back/forward, programmatic, etc.).
    this.router.events
      .pipe(filter((e) => e instanceof NavigationEnd))
      .subscribe(() => this.syncFromUrl());
  }

  /** Register a dialog under a URL-safe name. Safe to call repeatedly —
   *  re-registering the same name updates the component/config. */
  register<T>(
    name: string,
    component: Type<T>,
    config: MatDialogConfig = {},
  ): void {
    if (!/^[a-z0-9-]+$/i.test(name)) {
      throw new Error(
        `DialogRouterService: dialog name "${name}" must match /^[a-z0-9-]+$/i`,
      );
    }
    this.registrations.set(name, { component, config });
  }

  /** Open a registered dialog and write `?dialog=<name>` to the URL. */
  open(name: string): void {
    const reg = this.registrations.get(name);
    if (!reg) {
      console.warn(`DialogRouterService: unknown dialog "${name}"`);
      return;
    }
    if (this.activeName === name && this.activeRef) {
      return; // already open
    }
    // Close any previously-open URL-bound dialog first.
    if (this.activeRef) {
      this.activeRef.close();
      this.activeRef = null;
      this.activeName = null;
    }

    this.activeName = name;
    this.activeRef = this.dialog.open(reg.component, reg.config);
    this.writeUrl(name);

    this.activeRef.afterClosed().subscribe(() => {
      if (this.activeName === name) {
        this.activeRef = null;
        this.activeName = null;
        this.clearUrl();
      }
    });
  }

  /** Programmatic close. Same effect as the user hitting ESC. */
  close(): void {
    this.activeRef?.close();
  }

  // ── internals ───────────────────────────────────────────────────────

  private syncFromUrl(): void {
    const name = this.route.snapshot.queryParamMap.get('dialog');

    // URL says no dialog — close any open one.
    if (!name) {
      if (this.activeRef) this.activeRef.close();
      return;
    }

    // URL names an unknown dialog — ignore.
    if (!this.registrations.has(name)) return;

    // URL matches the already-open one — nothing to do.
    if (this.activeName === name) return;

    this.open(name);
  }

  private writeUrl(name: string): void {
    // `replaceUrl: true` — opening a dialog should not litter browser
    // history with a new entry. The back button should still go to the
    // previous route, not just close the dialog.
    this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { dialog: name },
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }

  private clearUrl(): void {
    this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { dialog: null },
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }
}

interface DialogRegistration<T> {
  component: Type<T>;
  config: MatDialogConfig;
}
