import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { HealthService, ServiceHealth, HealthSummary } from './health.service';
import { finalize } from 'rxjs';

@Component({
  selector: 'app-health',
  standalone: true,
  imports: [
    CommonModule,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatTooltipModule,
    MatProgressBarModule,
  ],
  templateUrl: './health.component.html',
  styleUrls: ['./health.component.scss'],
})
export class HealthComponent implements OnInit {
  private healthService = inject(HealthService);

  summary: HealthSummary | null = null;
  services: ServiceHealth[] = [];
  loading = false;
  refreshing = false;

  // Track individual service refreshing
  refreshingServices = new Set<string>();

  ngOnInit(): void {
    this.loadData();
  }

  loadData(): void {
    this.loading = true;
    this.healthService.getHealthStatus()
      .pipe(finalize(() => this.loading = false))
      .subscribe({
        next: (data) => {
          this.services = data;
          this.updateSummary();
        },
        error: (err) => console.error('Error loading health status', err)
      });
  }

  updateSummary(): void {
    this.healthService.getSummary().subscribe(s => this.summary = s);
  }

  refreshAll(): void {
    this.refreshing = true;
    this.healthService.checkAll()
      .pipe(finalize(() => this.refreshing = false))
      .subscribe(() => this.loadData());
  }

  refreshService(serviceKey: string): void {
    this.refreshingServices.add(serviceKey);
    this.healthService.checkService(serviceKey)
      .pipe(finalize(() => this.refreshingServices.delete(serviceKey)))
      .subscribe(updated => {
        const idx = this.services.findIndex(s => s.service_key === serviceKey);
        if (idx !== -1) {
          this.services[idx] = updated;
        }
        this.updateSummary();
      });
  }

  getStatusIcon(status: string): string {
    switch (status) {
      case 'healthy': return 'check_circle';
      case 'warning': return 'warning';
      case 'error': return 'error';
      case 'down': return 'dangerous';
      case 'stale': return 'update';
      case 'not_configured': return 'settings';
      case 'not_enabled': return 'block';
      default: return 'help';
    }
  }

  getStatusClass(status: string): string {
    return `status-${status}`;
  }

  getServiceName(key: string): string {
    const names: { [key: string]: string } = {
      'ga4': 'Google Analytics 4',
      'gsc': 'Search Console',
      'xenforo': 'XenForo Community',
      'wordpress': 'WordPress Site',
      'http_worker': 'C# Analysis Worker',
      'celery': 'Task Queue (Celery)',
      'database': 'Main Database (PG)',
      'redis': 'Cache & Queue (Redis)',
      'pipeline': 'Ranking Pipeline',
      'matomo': 'Matomo Analytics',
      'embedding': 'Embedding Specialist',
      'scheduler': 'C# Scheduler',
      'diagnostics': 'Backend Services'
    };
    return names[key] || key.replace(/_/g, ' ').toUpperCase();
  }

  getServiceDescription(key: string): string {
    const descs: { [key: string]: string } = {
      'ga4': 'Tracks post-click traffic and conversion metrics.',
      'gsc': 'Monitors search impressions and organic clicks.',
      'xenforo': 'Source for threads, posts, and user content.',
      'wordpress': 'Source for cross-linkable blog and page content.',
      'http_worker': 'High-performance C# engine for heavy I/O.',
      'celery': 'Handles background processing and sync tasks.',
      'database': 'Canonical storage for links and knowledge graph.',
      'redis': 'Low-latency state management and task routing.',
      'pipeline': 'The core logic that generates link suggestions.',
      'matomo': 'Self-hosted privacy-focused web analytics.',
    };
    return descs[key] || '';
  }

  isStale(lastSuccess: string | null): boolean {
    if (!lastSuccess) return true;
    const hours = (Date.now() - new Date(lastSuccess).getTime()) / (1000 * 60 * 60);
    return hours > 72; // Generic stale threshold if not reported by backend
  }
}
