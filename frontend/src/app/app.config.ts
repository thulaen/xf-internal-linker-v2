/**
 * Root application configuration for XF Internal Linker V2.
 *
 * Sets up routing, HTTP client, and Angular Material animations.
 * Uses Angular 19 standalone API — no NgModule required.
 */

import { ApplicationConfig, ErrorHandler, provideZoneChangeDetection, isDevMode } from '@angular/core';
import { provideRouter, withInMemoryScrolling, withRouterConfig } from '@angular/router';
import { provideHttpClient, withInterceptors, withXsrfConfiguration } from '@angular/common/http';
import { provideAnimationsAsync } from '@angular/platform-browser/animations/async';
import { provideServiceWorker } from '@angular/service-worker';
import * as Sentry from '@sentry/angular';
import { routes } from './app.routes';
import { authInterceptor } from './core/interceptors/auth.interceptor';
import { errorInterceptor } from './core/interceptors/error.interceptor';
import { traceparentInterceptor } from './core/interceptors/traceparent.interceptor';
import { GlobalErrorHandler } from './core/error/global-error-handler';
import { environment } from '../environments/environment';

// Phase GT Step 2 + Phase U1 / Gap 26 — ErrorHandler provider.
//   • When a Sentry/GlitchTip DSN is configured, route unhandled Angular
//     errors through Sentry's ErrorHandler so they land in the same
//     GlitchTip project as the backend errors.
//   • When the DSN is empty, fall through to our GlobalErrorHandler
//     which POSTs to /api/telemetry/client-errors/ so the operator has
//     a local record without setting up GlitchTip first.
const errorHandlerProviders = environment.glitchtipDsn
  ? [{ provide: ErrorHandler, useValue: Sentry.createErrorHandler() }]
  : [{ provide: ErrorHandler, useClass: GlobalErrorHandler }];

export const appConfig: ApplicationConfig = {
  providers: [
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideRouter(
      routes,
      // Disable Angular's built-in anchor scrolling — our GlobalLinkInterceptorService
      // replaces it with smooth scroll + highlight. scrollPositionRestoration: 'top'
      // ensures fresh page navigations always start at the top.
      withInMemoryScrolling({ anchorScrolling: 'disabled', scrollPositionRestoration: 'top' }),
      // Without onSameUrlNavigation:'reload' the router silently drops
      // any routerLink whose URL matches the current URL — even when
      // the fragment differs. That breaks every in-page anchor on the
      // dashboard (Runtime "Adjust Mode" → #performance-mode, etc.)
      // because the NavigationEnd event never fires and the fragment
      // scroller in GlobalLinkInterceptorService never runs.
      withRouterConfig({ onSameUrlNavigation: 'reload' }),
    ),
    provideHttpClient(
      // traceparent must run BEFORE auth so the header shows up in
      // every outbound request, including token exchanges.
      withInterceptors([traceparentInterceptor, authInterceptor, errorInterceptor]),
      withXsrfConfiguration({ cookieName: 'csrftoken', headerName: 'X-CSRFToken' }),
    ),
    provideAnimationsAsync(),
    ...errorHandlerProviders,
    // Phase E1 / Gap 29 — Progressive Web App / Angular Service Worker.
    // Only registered in production builds (isDevMode() returns true in dev).
    // In dev the service worker is skipped so HMR and live-reload work normally.
    // The ngsw-config.json at the project root controls:
    //   - App-shell assets: prefetch on install, update on new build.
    //   - API responses: freshness strategy (network-first) for dashboard /
    //     health; performance strategy (cache-first, 1h TTL) for analytics.
    provideServiceWorker('ngsw-worker.js', {
      enabled: !isDevMode(),
      registrationStrategy: 'registerWhenStable:30000',
    }),
  ],
};
