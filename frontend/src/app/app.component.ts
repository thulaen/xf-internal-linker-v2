import { Component, DestroyRef, OnInit, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';
import { CommonModule } from '@angular/common';
import { MatSidenavModule } from '@angular/material/sidenav';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatListModule } from '@angular/material/list';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatTooltipModule } from '@angular/material/tooltip';
import { AppearanceService } from './core/services/appearance.service';
import { DashboardService } from './dashboard/dashboard.service';
import { ThemeCustomizerComponent } from './theme-customizer/theme-customizer.component';
import { ScrollToTopComponent } from './scroll-to-top/scroll-to-top.component';

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
    ThemeCustomizerComponent,
    ScrollToTopComponent,
  ],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss'],
})
export class AppComponent implements OnInit {
  appearance = inject(AppearanceService);
  private dashboardSvc = inject(DashboardService);
  private destroyRef = inject(DestroyRef);

  customizerOpen = false;
  openBrokenLinks = 0;

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
          label: 'Settings',
          icon: 'settings',
          route: '/settings',
          tooltip: 'Theme, silo controls, and app settings',
        },
      ],
    },
  ];

  ngOnInit(): void {
    this.appearance.load();
    this.dashboardSvc.data$
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((data) => {
        this.openBrokenLinks = data?.open_broken_links ?? 0;
      });
    this.dashboardSvc.refresh().subscribe({
      error: () => {
        this.openBrokenLinks = 0;
      },
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
    window.open('/admin/', '_blank');
  }
}
