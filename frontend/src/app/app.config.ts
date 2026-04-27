/**
 * Root application configuration for XF Internal Linker V2.
 *
 * Sets up routing, HTTP client, and Angular Material animations.
 * Uses Angular 19 standalone API — no NgModule required.
 */

import { ApplicationConfig, ErrorHandler, provideZonelessChangeDetection, isDevMode } from '@angular/core';
import { provideRouter, withInMemoryScrolling, withRouterConfig, withViewTransitions } from '@angular/router';
import { provideHttpClient, withFetch, withInterceptors, withXsrfConfiguration } from '@angular/common/http';
import { provideAnimationsAsync } from '@angular/platform-browser/animations/async';
import { provideServiceWorker } from '@angular/service-worker';
import * as Sentry from '@sentry/angular';
import { routes } from './app.routes';
import { authInterceptor } from './core/interceptors/auth.interceptor';
import { coalesceInterceptor } from './core/interceptors/coalesce.interceptor';
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
    provideZonelessChangeDetection(),
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
      // Phase F1 / Gap 79 — native View Transitions API for route
      // crossfades. Angular's built-in helper handles the race
      // conditions (skipTransition on rapid navigation, cleanup on
      // NavigationCancel/Error) that our custom service got wrong.
      // No-op on browsers without the API (Firefox, older Safari).
      withViewTransitions({ skipInitialTransition: true }),
    ),
    provideHttpClient(
      // Use the modern fetch backend instead of the legacy XHR. fetch
      // supports HTTP/2 multiplexing more cleanly, streams responses
      // (no full-buffering before parse), uses less memory on large
      // payloads, and is the recommended Angular default since v18.
      // Non-breaking — existing interceptors keep working.
      withFetch(),
      // Order matters:
      //   1. coalesce — collapse concurrent GETs to one roundtrip.
      //                 Sits at the top so dedupe happens before we
      //                 spend cycles building trace IDs / auth headers
      //                 for the second-Nth callers we'll never send.
      //   2. traceparent — must run BEFORE auth so the trace header
      //                    shows up in every outbound request,
      //                    including token exchanges.
      //   3. auth, error — request mutation, then response handling.
      withInterceptors([coalesceInterceptor, traceparentInterceptor, authInterceptor, errorInterceptor]),
      withXsrfConfiguration({ cookieName: 'csrftoken', headerName: 'X-CSRFToken' }),
    ),
    provideAnimationsAsync(),
    ...errorHandlerProviders,
    // Progressive Web App / Angular Service Worker — production builds only.
    // ngsw-config.json caches app-shell static assets only. Authenticated
    // API responses are NEVER cached and are always served fresh from the
    // network — preventing phantom-stale dashboards and security smells.
    provideServiceWorker('ngsw-worker.js', {
      enabled: !isDevMode(),
      registrationStrategy: 'registerWhenStable:5000',
    }),
  ],
};
