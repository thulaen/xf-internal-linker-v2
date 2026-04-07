import { ChangeDetectionStrategy, Component, OnInit, OnDestroy, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { HealthService, ServiceHealth, HealthSummary } from './health.service';
import { SyncService, SyncJob } from '../jobs/sync.service';
import { ScrollHighlightDirective } from '../core/directives/scroll-highlight.directive';
import { finalize } from 'rxjs';

export interface ChecklistGroup {
  label: string;
  services: ServiceHealth[];
}

const SERVICE_GROUPS: { label: string; keys: string[] }[] = [
  { label: 'Infrastructure', keys: ['database', 'redis', 'celery', 'celery_queues', 'celery_beat', 'disk_space', 'http_worker'] },
  { label: 'AI & Models', keys: ['ml_models', 'native_scoring', 'gpu_faiss'] },
  { label: 'Analytics Credentials', keys: ['ga4', 'gsc', 'matomo'] },
  { label: 'Content Sources', keys: ['xenforo', 'wordpress'] },
  { label: 'Features', keys: ['knowledge_graph', 'weights_plugins', 'webhooks', 'pipeline_health'] },
];

const STATUS_SORT_ORDER: Record<string, number> = {
  down: 0,
  error: 1,
  warning: 2,
  stale: 3,
  not_configured: 4,
  not_enabled: 5,
  healthy: 6,
};

@Component({
  changeDetection: ChangeDetectionStrategy.OnPush,
  selector: 'app-health',
  standalone: true,
  imports: [
    CommonModule,
    RouterModule,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatTooltipModule,
    MatProgressBarModule,
    ScrollHighlightDirective,
  ],
  templateUrl: './health.component.html',
  styleUrls: ['./health.component.scss'],
})
export class HealthComponent implements OnInit, OnDestroy {
  private healthService = inject(HealthService);
  private syncService = inject(SyncService);

  summary: HealthSummary | null = null;
  services: ServiceHealth[] = [];
  loading = false;
  refreshing = false;
  refreshingServices = new Set<string>();

  activeJobs: SyncJob[] = [];
  private jobPollInterval: ReturnType<typeof setInterval> | null = null;

  // Computed counts (populated after services load)
  healthyCount = 0;
  warningCount = 0;
  errorCount = 0;
  notConfiguredCount = 0;

  // Checklist groups derived from services
  checklistGroups: ChecklistGroup[] = [];

  ngOnInit(): void {
    this.loadData();
    this.loadActiveJobs();
  }

  ngOnDestroy(): void {
    this.clearJobPoll();
  }

  loadData(): void {
    this.loading = true;
    this.healthService.getHealthStatus()
      .pipe(finalize(() => this.loading = false))
      .subscribe({
        next: (data) => {
          this.services = [...data].sort(
            (a, b) => (STATUS_SORT_ORDER[a.status] ?? 9) - (STATUS_SORT_ORDER[b.status] ?? 9)
          );
          this.computeCounts();
          this.buildChecklistGroups();
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
          this.services = [...this.services].sort(
            (a, b) => (STATUS_SORT_ORDER[a.status] ?? 9) - (STATUS_SORT_ORDER[b.status] ?? 9)
          );
        }
        this.computeCounts();
        this.buildChecklistGroups();
        this.updateSummary();
      });
  }

  // ── Active Jobs ──────────────────────────────────────────────────

  loadActiveJobs(): void {
    this.syncService.getJobs().subscribe({
      next: (jobs) => {
        const raw = Array.isArray(jobs) ? jobs : ((jobs as any).results ?? []);
        this.activeJobs = raw.filter((j: SyncJob) => j.status === 'running' || j.status === 'pending');
        if (this.activeJobs.length > 0) {
          this.startJobPoll();
        }
      },
      error: () => { /* jobs widget is non-critical */ }
    });
  }

  private startJobPoll(): void {
    if (this.jobPollInterval) return;
    this.jobPollInterval = setInterval(() => {
      this.syncService.getJobs().subscribe({
        next: (jobs) => {
          const raw = Array.isArray(jobs) ? jobs : ((jobs as any).results ?? []);
          this.activeJobs = raw.filter((j: SyncJob) => j.status === 'running' || j.status === 'pending');
          if (this.activeJobs.length === 0) {
            this.clearJobPoll();
          }
        },
        error: () => {}
      });
    }, 5000);
  }

  private clearJobPoll(): void {
    if (this.jobPollInterval) {
      clearInterval(this.jobPollInterval);
      this.jobPollInterval = null;
    }
  }

  // ── Computed helpers ─────────────────────────────────────────────

  private computeCounts(): void {
    this.healthyCount = this.services.filter(s => s.status === 'healthy').length;
    this.warningCount = this.services.filter(s => s.status === 'warning' || s.status === 'stale').length;
    this.errorCount = this.services.filter(s => s.status === 'error' || s.status === 'down').length;
    this.notConfiguredCount = this.services.filter(s => s.status === 'not_configured' || s.status === 'not_enabled').length;
  }

  private buildChecklistGroups(): void {
    const byKey = new Map(this.services.map(s => [s.service_key, s]));
    this.checklistGroups = SERVICE_GROUPS.map(g => ({
      label: g.label,
      services: g.keys.map(k => byKey.get(k)).filter((s): s is ServiceHealth => !!s),
    })).filter(g => g.services.length > 0);
  }

  // ── Template helpers ─────────────────────────────────────────────

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

  getJobSourceLabel(job: SyncJob): string {
    if (job.source === 'api') return 'XenForo Forum';
    if (job.source === 'wp') return 'WordPress';
    return 'File Upload';
  }

  getJobModeLabel(job: SyncJob): string {
    if (job.mode === 'full') return 'Full sync';
    if (job.mode === 'titles') return 'Titles only';
    if (job.mode === 'quick') return 'Quick sync';
    return job.mode;
  }

  getOverallProgress(job: SyncJob): number {
    return Math.round((job.progress ?? 0) * 100);
  }

  hasMLProgress(job: SyncJob): boolean {
    return (job.ml_items_queued ?? 0) > 0;
  }

  getSpacyProgress(job: SyncJob): number {
    return Math.round((job.spacy_progress ?? 0) * 100);
  }

  getEmbeddingProgress(job: SyncJob): number {
    return Math.round((job.embedding_progress ?? 0) * 100);
  }

  trackJobId(_index: number, job: SyncJob): string {
    return job.job_id;
  }

  /**
   * Maps a backend service key to the specific frontend element ID on the settings page.
   * Enables the "Smart Navigation" flow where clicking a health issue takes the user
   * exactly where they can fix it.
   */
  getSettingsFragment(serviceKey: string): string | undefined {
    const map: Record<string, string> = {
      'ga4': 'ga4-settings',
      'gsc': 'gsc-settings',
      'matomo': 'matomo-settings',
      'wordpress': 'wordpress-settings',
      'xenforo': 'xenforo-settings',
      'weights_plugins': 'ranking-weights',
      'knowledge_graph': 'silo-architecture',
      'webhooks': 'dashboard-webhooks'
    };
    return map[serviceKey];
  }

  trackByLabel(_: number, group: ChecklistGroup): string { return group.label; }
  trackByServiceKey(_: number, s: ServiceHealth): string { return s.service_key; }
  trackByIndex(index: number): number { return index; }
}
