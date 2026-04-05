import { Component, DestroyRef, OnInit, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterOutlet, RouterLink, RouterLinkActive, Router, NavigationEnd } from '@angular/router';
import { CommonModule } from '@angular/common';
import { filter, map, startWith, timer, switchMap } from 'rxjs';
import { MatSidenavModule } from '@angular/material/sidenav';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatListModule } from '@angular/material/list';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatMenuModule } from '@angular/material/menu';
import { AlertDeliveryService } from './core/services/alert-delivery.service';
import { AppearanceService } from './core/services/appearance.service';
import { AuthService } from './core/services/auth.service';
import { HealthService } from './health/health.service';
import { DashboardService } from './dashboard/dashboard.service';
import { NotificationCenterComponent } from './notification-center/notification-center.component';
import { ThemeCustomizerComponent } from './theme-customizer/theme-customizer.component';
import { ScrollToTopComponent } from './scroll-to-top/scroll-to-top.component';
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
  ],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss'],
})
export class AppComponent implements OnInit {
  appearance = inject(AppearanceService);
  auth = inject(AuthService);
  private alertDelivery = inject(AlertDeliveryService);
  private healthService = inject(HealthService);
  private dashboardSvc = inject(DashboardService);
  private destroyRef = inject(DestroyRef);
  private router = inject(Router);

  currentUser$ = this.auth.currentUser$;

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
          route: '/system-health',
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
      ],
    },
  ];

  ngOnInit(): void {
    this.appearance.load();
    this.alertDelivery.start();
    
    // Fetch broken links count for badge
    this.dashboardSvc.data$
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((data: any) => {
        this.openBrokenLinks = data?.open_broken_links ?? 0;
      });
    
    this.dashboardSvc.refresh().subscribe({
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
        next: (summary: any) => this.systemStatus = summary.system_status,
        error: () => this.systemStatus = 'unknown'
      });
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
