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

  getServiceName(service: ServiceHealth): string {
    return service.service_name || service.service_key.replace(/_/g, ' ').toUpperCase();
  }

  getServiceDescription(service: ServiceHealth): string {
    return service.service_description || '';
  }

  isStale(lastSuccess: string | null): boolean {
    if (!lastSuccess) return true;
    const hours = (Date.now() - new Date(lastSuccess).getTime()) / (1000 * 60 * 60);
    return hours > 72; // Generic stale threshold if not reported by backend
  }
}
