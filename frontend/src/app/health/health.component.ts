import { Component, DestroyRef, OnInit, OnDestroy, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatTabsModule } from '@angular/material/tabs';
import { HealthService, ServiceHealth, HealthSummary, ConfigTier, DiskHealth, GpuHealth } from './health.service';
import { SyncService, SyncJob } from '../jobs/sync.service';
import { ScrollHighlightDirective } from '../core/directives/scroll-highlight.directive';
import { HealthBannerComponent } from '../shared/health-banner/health-banner.component';
import { SafePruneCardComponent } from './safe-prune-card/safe-prune-card.component';
import { DeepLinkSpotlightDirective } from '../shared/directives/deep-link-spotlight.directive';
import { PersistTabDirective } from '../core/directives/persist-tab.directive';
import { finalize } from 'rxjs';

export interface ChecklistGroup {
  label: string;
  services: ServiceHealth[];
}

const SERVICE_GROUPS: { label: string; keys: string[] }[] = [
  { label: 'Infrastructure', keys: ['database', 'redis', 'celery', 'celery_queues', 'celery_beat', 'disk_space'] },
  { label: 'AI & Models', keys: ['ml_models', 'model_runtime', 'helper_nodes', 'native_scoring', 'gpu_faiss'] },
  { label: 'Analytics Credentials', keys: ['ga4', 'gsc', 'matomo'] },
  { label: 'Content Sources', keys: ['xenforo', 'wordpress', 'sitemaps'] },
  { label: 'Web Crawler', keys: ['crawler_status', 'crawler_storage'] },
  { label: 'Features', keys: ['knowledge_graph', 'weights_plugins', 'webhooks', 'pipeline_health'] },
  {
    label: 'Dev Tools',
    keys: [
      'dev_tools.asan_ci',
      'dev_tools.cpp_tests',
      'dev_tools.coverage_threshold_python',
      'dev_tools.coverage_threshold_angular',
      'dev_tools.openapi_schema',
      'dev_tools.pytest_ini',
      'dev_tools.responses_library',
      'dev_tools.clang_tidy',
      'dev_tools.clang_format',
      'dev_tools.prettier',
      'dev_tools.editorconfig',
      'dev_tools.glitchtip',
      'dev_tools.dependabot',
    ],
  },
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
    MatTabsModule,
    ScrollHighlightDirective,
    HealthBannerComponent,
    SafePruneCardComponent,
    DeepLinkSpotlightDirective,
    // Phase NV / Gap 145 — persist last-viewed tier tab.
    PersistTabDirective,
  ],
  templateUrl: './health.component.html',
  styleUrls: ['./health.component.scss'],
})
export class HealthComponent implements OnInit, OnDestroy {
  private healthService = inject(HealthService);
  private syncService = inject(SyncService);
  // Phase E2 / Gap 41 — cancel in-flight HTTP on route leave.
  private destroyRef = inject(DestroyRef);

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

  // Config-tier grouping (Stage 4)
  tierGroups: Record<ConfigTier, ServiceHealth[]> = {
    required_to_run: [],
    required_for_sync: [],
    required_for_analytics: [],
    optional: [],
  };
  readonly tierLabels: Record<ConfigTier, string> = {
    required_to_run: 'Required to Run',
    required_for_sync: 'Required for Sync',
    required_for_analytics: 'Required for Analytics',
    optional: 'Optional',
  };
  readonly tiers: ConfigTier[] = ['required_to_run', 'required_for_sync', 'required_for_analytics', 'optional'];

  // Disk + GPU (Stage 4)
  diskHealth: DiskHealth | null = null;
  gpuHealth: GpuHealth | null = null;

  ngOnInit(): void {
    this.loadData();
    this.loadActiveJobs();
    this.healthService.getDiskHealth()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(d => this.diskHealth = d);
    this.healthService.getGpuHealth()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(g => this.gpuHealth = g);
  }

  ngOnDestroy(): void {
    this.clearJobPoll();
  }

  loadData(): void {
    this.loading = true;
    this.healthService.getHealthStatus()
      .pipe(
        finalize(() => this.loading = false),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (data) => {
          this.services = [...data].sort(
            (a, b) => (STATUS_SORT_ORDER[a.status] ?? 9) - (STATUS_SORT_ORDER[b.status] ?? 9)
          );
          this.computeCounts();
          this.buildChecklistGroups();
          this.buildTierGroups();
          this.updateSummary();
        },
        error: (err) => console.error('Error loading health status', err)
      });
  }

  updateSummary(): void {
    this.healthService.getSummary()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(s => this.summary = s);
  }

  refreshAll(): void {
    this.refreshing = true;
    this.healthService.checkAll()
      .pipe(
        finalize(() => this.refreshing = false),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => this.loadData());
  }

  refreshService(serviceKey: string): void {
    this.refreshingServices.add(serviceKey);
    this.healthService.checkService(serviceKey)
      .pipe(
        finalize(() => this.refreshingServices.delete(serviceKey)),
        takeUntilDestroyed(this.destroyRef),
      )
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
    this.syncService.getJobs()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
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
      this.syncService.getJobs()
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe({
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

  private buildTierGroups(): void {
    this.tierGroups = {
      required_to_run: [],
      required_for_sync: [],
      required_for_analytics: [],
      optional: [],
    };
    for (const svc of this.services) {
      const tier = (svc.config_tier ?? 'optional') as ConfigTier;
      if (this.tierGroups[tier]) {
        this.tierGroups[tier].push(svc);
      } else {
        this.tierGroups.optional.push(svc);
      }
    }
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
      'webhooks': 'dashboard-webhooks',
      'ml_models': 'model-runtime',
      'model_runtime': 'model-runtime',
      'helper_nodes': 'helpers',
      'native_scoring': 'ranking-weights',
      'pipeline_health': 'pipeline-behaviour',
    };
    return map[serviceKey];
  }

  getInfraFixHint(serviceKey: string): string | undefined {
    const hints: Record<string, string> = {
      'database': 'Check that PostgreSQL is running: docker compose ps db',
      'redis': 'Check that Redis is running: docker compose ps redis',
      'celery': 'Restart Celery workers: docker compose restart celery-worker',
      'celery_queues': 'If queues are backed up, restart workers: docker compose restart celery-worker',
      'celery_beat': 'Restart the scheduler: docker compose restart celery-beat',
      'disk_space': 'Free up disk space by pruning Docker images: docker image prune -f',
      'gpu_faiss': 'Ensure FAISS is installed. CPU fallback is used automatically if no GPU is available.',
    };
    return hints[serviceKey];
  }

  trackByLabel(_: number, group: ChecklistGroup): string { return group.label; }
  trackByServiceKey(_: number, s: ServiceHealth): string { return s.service_key; }
  trackByIndex(index: number): number { return index; }
}
