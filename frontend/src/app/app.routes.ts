/**
 * Application routes for XF Internal Linker V2.
 *
 * All routes are lazy-loaded for optimal performance.
 * authGuard protects all routes except /login.
 */

import { Routes } from '@angular/router';
import { provideCharts, withDefaultRegisterables } from 'ng2-charts';
import { authGuard } from './core/guards/auth.guard';
import { unsavedChangesGuard } from './core/guards/unsaved-changes.guard';

export const routes: Routes = [
  {
    path: 'login',
    loadComponent: () =>
      import('./login/login.component').then((m) => m.LoginComponent),
    title: 'Sign in — XF Internal Linker',
  },
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
    canActivate: [authGuard],
  },
  {
    path: 'review',
    loadComponent: () =>
      import('./review/review.component').then((m) => m.ReviewComponent),
    title: 'Review Suggestions — XF Internal Linker',
    canActivate: [authGuard],
  },
  {
    path: 'link-health',
    loadComponent: () =>
      import('./link-health/link-health.component').then((m) => m.LinkHealthComponent),
    title: 'Link Health — XF Internal Linker',
    canActivate: [authGuard],
  },
  {
    path: 'graph',
    loadComponent: () =>
      import('./graph/graph.component').then((m) => m.GraphComponent),
    providers: [provideCharts(withDefaultRegisterables())],
    title: 'Link Graph — XF Internal Linker',
    canActivate: [authGuard],
  },
  {
    path: 'analytics',
    loadComponent: () =>
      import('./analytics/analytics.component').then((m) => m.AnalyticsComponent),
    providers: [provideCharts(withDefaultRegisterables())],
    title: 'Analytics — XF Internal Linker',
    canActivate: [authGuard],
  },
  {
    path: 'jobs',
    loadComponent: () =>
      import('./jobs/jobs.component').then((m) => m.JobsComponent),
    title: 'Jobs — XF Internal Linker',
    canActivate: [authGuard],
  },
  {
    path: 'settings',
    loadComponent: () =>
      import('./settings/settings.component').then((m) => m.SettingsComponent),
    title: 'Settings — XF Internal Linker',
    canActivate: [authGuard],
    canDeactivate: [unsavedChangesGuard],
  },
  {
    path: 'health',
    loadComponent: () =>
      import('./health/health.component').then((m) => m.HealthComponent),
    title: 'System Health — XF Internal Linker',
    canActivate: [authGuard],
  },
  {
    path: 'diagnostics',
    loadComponent: () =>
      import('./diagnostics/diagnostics.component').then((m) => m.DiagnosticsComponent),
    title: 'Technical Diagnostics — XF Internal Linker',
    canActivate: [authGuard],
  },
  {
    path: 'alerts',
    loadComponent: () =>
      import('./alerts/alerts.component').then((m) => m.AlertsComponent),
    title: 'Alerts — XF Internal Linker',
    canActivate: [authGuard],
  },
  {
    path: 'behavioral-hubs',
    loadComponent: () =>
      import('./behavioral-hubs/behavioral-hubs.component').then((m) => m.BehavioralHubsComponent),
    title: 'Behavioral Hubs — XF Internal Linker',
    canActivate: [authGuard],
  },
  {
    path: 'error-log',
    loadComponent: () =>
      import('./error-log/error-log.component').then((m) => m.ErrorLogComponent),
    title: 'Error Log — XF Internal Linker',
    canActivate: [authGuard],
  },
  {
    path: '**',
    redirectTo: '/dashboard',
  },
];
