/**
 * Root application component for XF Internal Linker V2.
 *
 * Provides the main shell: sidebar navigation + router outlet.
 * Uses Angular Material's sidenav for the navigation drawer.
 */

import { Component } from '@angular/core';
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';
import { MatSidenavModule } from '@angular/material/sidenav';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatListModule } from '@angular/material/list';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatTooltipModule } from '@angular/material/tooltip';

interface NavItem {
  label: string;
  icon: string;
  route: string;
  tooltip: string;
}

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    MatSidenavModule,
    MatToolbarModule,
    MatListModule,
    MatIconModule,
    MatButtonModule,
    MatTooltipModule,
  ],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss'],
})
export class AppComponent {
  title = 'XF Internal Linker';

  navItems: NavItem[] = [
    {
      label: 'Dashboard',
      icon: 'dashboard',
      route: '/dashboard',
      tooltip: 'Overview of jobs, suggestions, and key metrics',
    },
    {
      label: 'Review',
      icon: 'rate_review',
      route: '/review',
      tooltip: 'Review and approve link suggestions',
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
      tooltip: 'App settings, API keys, and theme',
    },
  ];
}
