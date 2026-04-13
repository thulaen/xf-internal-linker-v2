import { Component, DestroyRef, OnInit, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterOutlet, RouterLink, RouterLinkActive, Router, NavigationEnd, ChildrenOutletContexts } from '@angular/router';
import { CommonModule } from '@angular/common';
import { filter, map, startWith, timer, switchMap } from 'rxjs';
import { MatSidenavModule } from '@angular/material/sidenav';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatListModule } from '@angular/material/list';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatMenuModule } from '@angular/material/menu';
import { MatBadgeModule } from '@angular/material/badge';
import { MatChipsModule } from '@angular/material/chips';
import { AlertDeliveryService } from './core/services/alert-delivery.service';
import { AppearanceService } from './core/services/appearance.service';
import { AuthService } from './core/services/auth.service';
import { GlobalLinkInterceptorService } from './core/services/global-link-interceptor.service';
import { HealthService, HealthSummary } from './health/health.service';
import { DashboardService, DashboardData } from './dashboard/dashboard.service';
import { PulseService, PulseState } from './core/services/pulse.service';
import { SuggestionService } from './review/suggestion.service';
import { NotificationCenterComponent } from './notification-center/notification-center.component';
import { ThemeCustomizerComponent } from './theme-customizer/theme-customizer.component';
import { ScrollToTopComponent } from './scroll-to-top/scroll-to-top.component';
import { ScrollHighlightDirective } from './core/directives/scroll-highlight.directive';
import { FreshnessBadgeComponent } from './shared/freshness-badge/freshness-badge.component';
import { routeTransitionAnimation } from './shared/animations/route-transition.animation';
import { environment } from '../environments/environment';

interface NavItem {
  label: string;
  icon: string;
  route: string;
  tooltip: string;
}

interface NavSection {
  label: string;
  items: NavItem[];
}

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    CommonModule,
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    MatSidenavModule,
    MatToolbarModule,
    MatListModule,
    MatIconModule,
    MatButtonModule,
    MatTooltipModule,
    MatMenuModule,
    NotificationCenterComponent,
    ThemeCustomizerComponent,
    ScrollToTopComponent,
    ScrollHighlightDirective,
    FreshnessBadgeComponent,
    MatBadgeModule,
    MatChipsModule,
  ],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss'],
  animations: [routeTransitionAnimation],
})
export class AppComponent implements OnInit {
  appearance = inject(AppearanceService);
  auth = inject(AuthService);
  private alertDelivery = inject(AlertDeliveryService);
  private healthService = inject(HealthService);
  private dashboardSvc = inject(DashboardService);
  private linkInterceptor = inject(GlobalLinkInterceptorService);
  private destroyRef = inject(DestroyRef);
  private router = inject(Router);
  private pulseService = inject(PulseService);
  private suggestionSvc = inject(SuggestionService);
  private contexts = inject(ChildrenOutletContexts);

  currentUser$ = this.auth.currentUser$;
  pulse: PulseState = { ok: false, status: 'unknown', lastBeatAt: 0, checks: {}, taskCount: 0 };

  // Freshness ribbon data
  lastSyncAt: string | null = null;
  lastAnalyticsAt: string | null = null;
  lastPipelineAt: string | null = null;
  runtimeMode = 'CPU';

  // Nav badge: pending suggestion count
  pendingSuggestionCount = 0;

  // Hide the app shell on the login page so it gets its own minimal layout
  isLoginPage$ = this.router.events.pipe(
    filter(e => e instanceof NavigationEnd),
    map((e: NavigationEnd) => e.urlAfterRedirects.startsWith('/login')),
    startWith(this.router.url.startsWith('/login'))
  );

  customizerOpen = false;
  notifPanelOpen = false;
  openBrokenLinks = 0;
  systemStatus: 'healthy' | 'degraded' | 'critical' | 'unknown' = 'unknown';

  navSections: NavSection[] = [
    {
      label: 'Main',
      items: [
        {
          label: 'Dashboard',
          icon: 'dashboard',
          route: '/dashboard',
          tooltip: 'Overview of jobs, suggestions, and key metrics',
        },
      ],
    },
    {
      label: 'Analysis',
      items: [
        {
          label: 'Review',
          icon: 'rate_review',
          route: '/review',
          tooltip: 'Review and approve link suggestions',
        },
        {
          label: 'Link Health',
          icon: 'link_off',
          route: '/link-health',
          tooltip: 'Broken link scanner and status tracker',
        },
        {
          label: 'Link Graph',
          icon: 'account_tree',
          route: '/graph',
          tooltip: 'Visualize the internal link graph',
        },
        {
          label: 'Behavioral Hubs',
          icon: 'hub',
          route: '/behavioral-hubs',
          tooltip: 'Co-navigation article clusters from GA4 session data',
        },
        {
          label: 'Analytics',
          icon: 'bar_chart',
          route: '/analytics',
          tooltip: 'SEO impact reports from GSC and GA4',
        },
      ],
    },
    {
      label: 'System',
      items: [
        {
          label: 'Jobs',
          icon: 'pending_actions',
          route: '/jobs',
          tooltip: 'Background job queue and history',
        },
        {
          label: 'System Health',
          icon: 'health_and_safety',
          route: '/health',
          tooltip: 'Real-time status of data sources and services',
        },
        {
          label: 'Settings',
          icon: 'settings',
          route: '/settings',
          tooltip: 'Theme, silo controls, and app settings',
        },
        {
          label: 'Alerts',
          icon: 'notifications',
          route: '/alerts',
          tooltip: 'Operator alert center',
        },
        {
          label: 'Web Crawler',
          icon: 'travel_explore',
          route: '/crawler',
          tooltip: 'Crawl your sites for SEO audit, broken links, and content discovery',
        },
        {
          label: 'Error Log',
          icon: 'bug_report',
          route: '/error-log',
          tooltip: 'Background job errors with plain-English explanations',
        },
        {
          label: 'Performance',
          icon: 'speed',
          route: '/performance',
          tooltip: 'Benchmark results for C++ and Python hot paths',
        },
      ],
    },
  ];

  ngOnInit(): void {
    this.appearance.load();
    this.alertDelivery.start();
    this.linkInterceptor.init();
    
    // Fetch broken links count for badge
    this.dashboardSvc.data$
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((data: DashboardData | null) => {
        this.openBrokenLinks = data?.open_broken_links ?? 0;
      });
    
    this.dashboardSvc.refresh()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        error: () => {
          this.openBrokenLinks = 0;
        },
      });

    // Fetch health summary for status dot plus 30-minute heart beat
    timer(0, 30 * 60 * 1000)
      .pipe(
        switchMap(() => this.healthService.getSummary()),
        takeUntilDestroyed(this.destroyRef)
      )
      .subscribe({
        next: (summary: HealthSummary) => this.systemStatus = summary.system_status,
        error: () => this.systemStatus = 'unknown'
      });

    // Subscribe to the real-time pulse for toolbar indicator.
    this.pulseService.pulse$
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((p) => (this.pulse = p));

    // Freshness ribbon: refresh every 15 minutes
    timer(0, 15 * 60 * 1000)
      .pipe(
        switchMap(() => this.dashboardSvc.refresh()),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (d: DashboardData) => {
          this.lastSyncAt = d.last_sync_at ?? null;
          this.lastPipelineAt = d.last_pipeline_at ?? null;
          this.lastAnalyticsAt = d.last_analytics_at ?? null;
          this.runtimeMode = d.runtime_mode ?? 'CPU';
        },
      });

    // Nav badge: pending suggestions count, refreshed every 5 minutes
    timer(0, 5 * 60 * 1000)
      .pipe(
        switchMap(() => this.suggestionSvc.getPendingCount()),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (count: number) => this.pendingSuggestionCount = count,
        error: () => this.pendingSuggestionCount = 0,
      });

  }

  getRouteAnimationData(): string {
    return this.contexts.getContext('primary')?.route?.snapshot?.url?.toString() ?? '';
  }

  get config() {
    return this.appearance.config;
  }

  get siteName(): string {
    return this.appearance.config.siteName;
  }

  goToAdmin(event: MouseEvent): void {
    event.preventDefault();
    window.open(environment.adminUrl, '_blank', 'noopener,noreferrer');
  }

  logout(): void {
    this.auth.logout();
  }
}
