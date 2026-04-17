import { Injectable, DestroyRef, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { NavigationEnd, Router } from '@angular/router';
import { filter } from 'rxjs/operators';
import { Title } from '@angular/platform-browser';

import { environment } from '../../../environments/environment';

/**
 * Phase U2 / Gap 25 — SPA-aware page-view tracking.
 *
 * The app is a single-page Angular SPA, so a traditional "page view"
 * fires only on initial document load. This service listens to
 * `NavigationEnd` and fires a custom page-view event for every route
 * change so product analytics actually captures navigation patterns.
 *
 * Destinations:
 *   1. The project's own backend at `POST /api/telemetry/page-views/`
 *      — deferred to a follow-up session (needs its own model/endpoint;
 *      the send is conditional on `environment.pageViewTelemetryEnabled`
 *      which is `false` for now).
 *   2. `window.dataLayer.push(...)` — Google Tag Manager / GA4 integration.
 *      Fires if `window.dataLayer` exists (standard GTM install injects it).
 *   3. `window.gtag(...)` — direct GA4 call if `gtag` is defined.
 *   4. `window.paq.push(...)` — Matomo tracker, same pattern.
 *
 * All destinations are best-effort. Any thrown error is swallowed so a
 * broken analytics library can't cascade into a broken page.
 *
 * Privacy:
 *   - Only the route path + document title is sent.
 *   - No query params (they may contain session data like tokens).
 *   - No user id (the backend endpoints already have auth context when
 *     they need it).
 */
@Injectable({ providedIn: 'root' })
export class AnalyticsService {
  private readonly router = inject(Router);
  private readonly title = inject(Title);
  private readonly http = inject(HttpClient);
  private readonly destroyRef = inject(DestroyRef);

  private started = false;

  /** Call once from the root component. Safe to call multiple times. */
  start(): void {
    if (this.started) return;
    this.started = true;

    const sub = this.router.events
      .pipe(filter((e): e is NavigationEnd => e instanceof NavigationEnd))
      .subscribe((event) => {
        // urlAfterRedirects captures the final URL the user landed on,
        // so analytics sees the destination route — not the one that
        // bounced via a redirect.
        this.fire(event.urlAfterRedirects || event.url);
      });

    this.destroyRef.onDestroy(() => sub.unsubscribe());
  }

  private fire(url: string): void {
    const path = this.sanitisePath(url);
    const title = this.title.getTitle() || path;

    this.pushDataLayer(path, title);
    this.gtagPageView(path, title);
    this.matomoPageView(path, title);
    // Backend send deliberately left off until the endpoint + model
    // land. When it does, guard it behind:
    //   if (environment.pageViewTelemetryEnabled) { this.http.post(...) }
  }

  /** Strip the query + hash so we never export secrets/session state. */
  private sanitisePath(url: string): string {
    const [path] = url.split('?');
    return path.split('#')[0] || '/';
  }

  private pushDataLayer(path: string, title: string): void {
    try {
      const dl = (window as unknown as { dataLayer?: unknown[] }).dataLayer;
      if (Array.isArray(dl)) {
        dl.push({
          event: 'spa_page_view',
          page_path: path,
          page_title: title,
          app_version: environment.appVersion,
        });
      }
    } catch {
      // Silent — analytics failure must not break navigation.
    }
  }

  private gtagPageView(path: string, title: string): void {
    try {
      const gtag = (window as unknown as { gtag?: (...args: unknown[]) => void }).gtag;
      if (typeof gtag === 'function') {
        gtag('event', 'page_view', {
          page_location: window.location.origin + path,
          page_path: path,
          page_title: title,
        });
      }
    } catch {
      // Silent.
    }
  }

  private matomoPageView(path: string, title: string): void {
    try {
      const paq = (window as unknown as { _paq?: unknown[] })._paq;
      if (Array.isArray(paq)) {
        paq.push(['setCustomUrl', path]);
        paq.push(['setDocumentTitle', title]);
        paq.push(['trackPageView']);
      }
    } catch {
      // Silent.
    }
  }
}
