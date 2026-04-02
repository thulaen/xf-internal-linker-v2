/**
 * Application routes for XF Internal Linker V2.
 *
 * All routes are lazy-loaded for optimal performance.
 * Auth guard protects all routes except login (added in Phase 4).
 */

import { Routes } from '@angular/router';
import { provideCharts, withDefaultRegisterables } from 'ng2-charts';

export const routes: Routes = [
  {
    path: '',
    redirectTo: '/dashboard',
    pathMatch: 'full',
  },
  {
    path: 'dashboard',
    loadComponent: () =>
      import('./dashboard/dashboard.component').then((m) => m.DashboardComponent),
    title: 'Dashboard — XF Internal Linker',
  },
  {
    path: 'review',
    loadComponent: () =>
      import('./review/review.component').then((m) => m.ReviewComponent),
    title: 'Review Suggestions — XF Internal Linker',
  },
  {
    path: 'link-health',
    loadComponent: () =>
      import('./link-health/link-health.component').then((m) => m.LinkHealthComponent),
    title: 'Link Health — XF Internal Linker',
  },
  {
    path: 'graph',
    loadComponent: () =>
      import('./graph/graph.component').then((m) => m.GraphComponent),
    title: 'Link Graph — XF Internal Linker',
  },
  {
    path: 'analytics',
    loadComponent: () =>
      import('./analytics/analytics.component').then((m) => m.AnalyticsComponent),
    providers: [provideCharts(withDefaultRegisterables())],
    title: 'Analytics — XF Internal Linker',
  },
  {
    path: 'jobs',
    loadComponent: () =>
      import('./jobs/jobs.component').then((m) => m.JobsComponent),
    title: 'Jobs — XF Internal Linker',
  },
  {
    path: 'settings',
    loadComponent: () =>
      import('./settings/settings.component').then((m) => m.SettingsComponent),
    title: 'Settings — XF Internal Linker',
  },
  {
    path: 'system-health',
    loadComponent: () =>
      import('./diagnostics/diagnostics.component').then((m) => m.DiagnosticsComponent),
    title: 'System Health — XF Internal Linker',
  },
  {
    path: '**',
    redirectTo: '/dashboard',
  },
];
