import { Injectable, inject } from '@angular/core';
import { Title } from '@angular/platform-browser';
import { Router, NavigationEnd } from '@angular/router';
import { filter } from 'rxjs/operators';

/**
 * Phase E1 / Gap 33 — Dirty-tab title indicator.
 *
 * Two responsibilities:
 * 1. Sets a meaningful document title on every route change so browser
 *    tabs and screen readers announce the current page.
 * 2. Exposes `setDirty(true/false)` so form components can prepend " •"
 *    to the title when they have unsaved changes — a common browser pattern
 *    (e.g. GitHub, Google Docs) that warns users before they close the tab.
 *
 * Usage in a form component:
 *
 *   private titleSvc = inject(PageTitleService);
 *
 *   onFormChange() {
 *     this.titleSvc.setDirty(this.form.dirty);
 *   }
 *
 *   ngOnDestroy() {
 *     this.titleSvc.setDirty(false); // clean up on leave
 *   }
 *
 * The dirty indicator is automatically cleared on every NavigationEnd so
 * a page transition always shows a clean title.
 */
@Injectable({ providedIn: 'root' })
export class PageTitleService {
  private title = inject(Title);
  private router = inject(Router);

  private baseTitle = 'XF Internal Linker';
  private isDirty = false;

  constructor() {
    // Clear the dirty flag and update the title on every route change.
    this.router.events
      .pipe(filter((e) => e instanceof NavigationEnd))
      .subscribe(() => {
        this.isDirty = false;
        this.apply();
      });
  }

  /**
   * Mark the current page as having unsaved changes.
   * Prepends " •" to the document title when dirty === true.
   */
  setDirty(dirty: boolean): void {
    if (this.isDirty === dirty) return;
    this.isDirty = dirty;
    this.apply();
  }

  /** Override the base page name (e.g. from the route data). */
  setPageName(name: string): void {
    this.baseTitle = name ? `${name} — XF Internal Linker` : 'XF Internal Linker';
    this.apply();
  }

  private apply(): void {
    const prefix = this.isDirty ? '• ' : '';
    this.title.setTitle(`${prefix}${this.baseTitle}`);
  }
}
