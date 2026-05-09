import {
  AfterViewInit,
  Directive,
  Host,
  inject,
  Input,
  OnDestroy,
  Optional,
} from '@angular/core';
import { ActivatedRoute, Router, NavigationEnd } from '@angular/router';
import { MatTabGroup } from '@angular/material/tabs';
import { Subject } from 'rxjs';
import { filter, takeUntil } from 'rxjs/operators';

/**
 * Drop on any `<mat-tab-group appTabFragment [tabFragmentMap]="{...}">`
 * to switch tabs whenever the URL fragment OR the `?tab=` query parameter
 * matches one of the keys in the supplied map.
 *
 * Example:
 *   <mat-tab-group
 *     appTabFragment
 *     [tabFragmentMap]="{ internal: 0, glitchtip: 1, all: 2,
 *                          'auto-issues': 3, pyroscope: 4 }">
 *
 * Now visiting `/error-log#auto-issues` or `/error-log?tab=auto-issues`
 * activates the Auto-Issues tab. Combine freely with `appPersistTab`
 * for localStorage-style persistence.
 *
 * Why both `?tab=` and `#fragment`? `?tab=` is what
 * `GlobalLinkInterceptorService.resolveDeepLinkParam()` writes when it
 * resolves a `?dl=<key>` deep link. `#fragment` is what a hand-typed or
 * shared link uses. Either one works.
 */
@Directive({
  selector: 'mat-tab-group[appTabFragment]',
  standalone: true,
})
export class TabFragmentRouterDirective implements AfterViewInit, OnDestroy {
  @Input() tabFragmentMap: Record<string, number> = {};

  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private destroy$ = new Subject<void>();

  constructor(@Host() @Optional() private host: MatTabGroup | null) {}

  ngAfterViewInit(): void {
    if (!this.host) {
      console.warn('[appTabFragment] host is not a MatTabGroup — directive is a no-op.');
      return;
    }

    this.applyFromCurrentUrl();

    this.router.events
      .pipe(
        filter((e) => e instanceof NavigationEnd),
        takeUntil(this.destroy$),
      )
      .subscribe(() => this.applyFromCurrentUrl());
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  private applyFromCurrentUrl(): void {
    if (!this.host) return;
    const snapshot = this.route.snapshot;
    const queryTab = snapshot.queryParamMap.get('tab');
    const fragment = snapshot.fragment ?? '';

    const key = queryTab || fragment;
    if (!key) return;

    const target = this.tabFragmentMap[key];
    if (typeof target !== 'number') return;
    if (this.host.selectedIndex === target) return;

    queueMicrotask(() => {
      if (!this.host) return;
      const max = (this.host._tabs?.length ?? 0) - 1;
      this.host.selectedIndex = Math.min(target, Math.max(0, max));
    });
  }
}
