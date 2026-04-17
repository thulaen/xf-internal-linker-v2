/**
 * Angular 20 application entry point.
 * Uses the standalone component API (no NgModules).
 *
 * Phase GT Step 2 — Sentry/GlitchTip SDK is initialised here, BEFORE
 * bootstrapApplication, so that any error thrown during bootstrap is
 * captured. When `environment.glitchtipDsn` is empty (the default in
 * dev), `Sentry.init` is never called — zero overhead, zero network.
 */

import { bootstrapApplication } from '@angular/platform-browser';
import * as Sentry from '@sentry/angular';
import { appConfig } from './app/app.config';
import { AppComponent } from './app/app.component';
import { environment } from './environments/environment';

if (environment.glitchtipDsn) {
  Sentry.init({
    dsn: environment.glitchtipDsn,
    environment: environment.production ? 'production' : 'development',
    release: environment.appVersion,
    // Browser-side traces are cheap and very useful for WebSocket / fetch
    // timing across the Diagnostics + Jobs pages. Keep the sample rate
    // low so sessions don't balloon the GlitchTip store.
    tracesSampleRate: 0.1,
    // Don't send PII — the backend is the source of truth for user data
    // and our error reports don't need to duplicate it.
    sendDefaultPii: false,
    // Stack the frontend release tag with a node-style origin hint so a
    // single GlitchTip project can host multiple environments cleanly.
    initialScope: {
      tags: {
        node_role: 'frontend',
      },
    },
  });
}

bootstrapApplication(AppComponent, appConfig).catch((err) =>
  console.error(err)
);
