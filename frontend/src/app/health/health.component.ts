import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, OnDestroy, computed, inject, signal } from '@angular/core';
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
import { Observable, Subscription, finalize, map, switchMap, timer } from 'rxjs';
import { VisibilityGateService } from '../core/util/visibility-gate.service';

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

const ACTIVE_STATUSES = new Set<string>(['running', 'pending']);

/**
 * Narrow the SyncService.getJobs() response to a flat array regardless
 * of whether the backend returns one (legacy shape) or a DRF paginated
 * envelope `{count, results}` (current shape). Replaces the previous
 * `(jobs as any).results` type-laundering smell.
 */
function asJobArray(payload: unknown): SyncJob[] {
  if (Array.isArray(payload)) return payload as SyncJob[];
  if (payload && typeof payload === 'object' && 'results' in payload) {
    const results = (payload as { results: unknown }).results;
    if (Array.isArray(results)) return results as SyncJob[];
  }
  return [];
}

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
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class HealthComponent implements OnInit, OnDestroy {
  private healthService = inject(HealthService);
  private syncService = inject(SyncService);
  private visibilityGate = inject(VisibilityGateService);
  // Phase E2 / Gap 41 — cancel in-flight HTTP on route leave.
  private destroyRef = inject(DestroyRef);

  readonly summary = signal<HealthSummary | null>(null);
  readonly services = signal<ServiceHealth[]>([]);
  readonly loading = signal(false);
  readonly refreshing = signal(false);
  /** Per-service refresh-in-progress flags. Immutable Set updates so
   *  the signal reference changes on add/delete and `(refreshingServices().has(key))`
   *  template reads stay reactive. */
  readonly refreshingServices = signal<ReadonlySet<string>>(new Set());

  readonly activeJobs = signal<SyncJob[]>([]);
  private jobPollSub: Subscription | null = null;

  // Disk + GPU (Stage 4)
  readonly diskHealth = signal<DiskHealth | null>(null);
  readonly gpuHealth = signal<GpuHealth | null>(null);

  // ── Derived state ────────────────────────────────────────────────
  // Replaces the previous imperative computeCounts() / buildChecklistGroups() /
  // buildTierGroups() methods, which had to be called from every loadData /
  // refreshService callback. Single source of truth: the `services` signal.

  readonly healthyCount = computed(() => this.services().filter(s => s.status === 'healthy').length);
  readonly warningCount = computed(() => this.services().filter(s => s.status === 'warning' || s.status === 'stale').length);
  readonly errorCount = computed(() => this.services().filter(s => s.status === 'error' || s.status === 'down').length);
  readonly notConfiguredCount = computed(() =>
    this.services().filter(s => s.status === 'not_configured' || s.status === 'not_enabled').length,
  );

  readonly checklistGroups = computed<ChecklistGroup[]>(() => {
    const byKey = new Map(this.services().map(s => [s.service_key, s]));
    return SERVICE_GROUPS
      .map(g => ({
        label: g.label,
        services: g.keys.map(k => byKey.get(k)).filter((s): s is ServiceHealth => !!s),
      }))
      .filter(g => g.services.length > 0);
  });

  readonly tierGroups = computed<Record<ConfigTier, ServiceHealth[]>>(() => {
    const groups: Record<ConfigTier, ServiceHealth[]> = {
      required_to_run: [],
      required_for_sync: [],
      required_for_analytics: [],
      optional: [],
    };
    for (const svc of this.services()) {
      const tier = (svc.config_tier ?? 'optional') as ConfigTier;
      if (groups[tier]) {
        groups[tier].push(svc);
      } else {
        groups.optional.push(svc);
      }
    }
    return groups;
  });

  readonly tierLabels: Record<ConfigTier, string> = {
    required_to_run: 'Required to Run',
    required_for_sync: 'Required for Sync',
    required_for_analytics: 'Required for Analytics',
    optional: 'Optional',
  };
  readonly tiers: readonly ConfigTier[] = ['required_to_run', 'required_for_sync', 'required_for_analytics', 'optional'];

  ngOnInit(): void {
    this.loadData();
    this.refreshActiveJobs();
    // Disk + GPU health calls have a service-level catchError that
    // returns a default object; wire an explicit error: branch as
    // belt-and-braces so an unexpected throw still logs a warning.
    this.healthService.getDiskHealth()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (d) => this.diskHealth.set(d),
        error: (err) => console.warn('getDiskHealth failed', err),
      });
    this.healthService.getGpuHealth()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (g) => this.gpuHealth.set(g),
        error: (err) => console.warn('getGpuHealth failed', err),
      });
  }

  ngOnDestroy(): void {
    this.clearJobPoll();
  }

  loadData(): void {
    this.loading.set(true);
    this.healthService.getHealthStatus()
      .pipe(
        finalize(() => this.loading.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (data) => {
          this.services.set([...data].sort(
            (a, b) => (STATUS_SORT_ORDER[a.status] ?? 9) - (STATUS_SORT_ORDER[b.status] ?? 9),
          ));
          this.updateSummary();
        },
        error: (err) => console.error('Error loading health status', err),
      });
  }

  updateSummary(): void {
    this.healthService.getSummary()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (s) => this.summary.set(s),
        error: (err) => console.warn('getSummary failed', err),
      });
  }

  refreshAll(): void {
    this.refreshing.set(true);
    this.healthService.checkAll()
      .pipe(
        finalize(() => this.refreshing.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: () => this.loadData(),
        error: (err) => {
          console.warn('checkAll failed', err);
          // Reload anyway so the UI shows whatever the cached state is
          // rather than leaving the user with a stale view + no signal.
          this.loadData();
        },
      });
  }

  refreshService(serviceKey: string): void {
    this.refreshingServices.update(s => {
      const next = new Set(s);
      next.add(serviceKey);
      return next;
    });
    this.healthService.checkService(serviceKey)
      .pipe(
        finalize(() => {
          this.refreshingServices.update(s => {
            const next = new Set(s);
            next.delete(serviceKey);
            return next;
          });
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(updated => {
        // Single atomic update — replace the matching service then re-sort,
        // all in one signal write. Counts/groups/tiers recompute automatically
        // because they're computed() over `services()`.
        this.services.update(arr => {
          const next = arr.map(s => s.service_key === serviceKey ? updated : s);
          return next.sort(
            (a, b) => (STATUS_SORT_ORDER[a.status] ?? 9) - (STATUS_SORT_ORDER[b.status] ?? 9),
          );
        });
        this.updateSummary();
      });
  }

  // ── Active Jobs ──────────────────────────────────────────────────

  /**
   * Single source of truth for fetching active jobs. Used by both the
   * initial load and the poll — eliminates the duplicated subscribe
   * handler that previously lived in `loadActiveJobs` and `startJobPoll`.
   * Returns an Observable so the caller decides whether to subscribe
   * once or wire it through a polling stream.
   */
  private fetchActiveJobs$(): Observable<SyncJob[]> {
    return this.syncService.getJobs().pipe(
      // The service typing claims `SyncJob[]` but the backend may return
      // a paginated envelope. `asJobArray` normalises both shapes.
      map(asJobArray),
      map(jobs => jobs.filter(j => ACTIVE_STATUSES.has(j.status))),
    );
  }

  private refreshActiveJobs(): void {
    this.fetchActiveJobs$()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (jobs) => {
          this.activeJobs.set(jobs);
          if (jobs.length > 0) {
            this.startJobPoll();
          }
        },
        error: (err) => { /* jobs widget is non-critical */ console.warn('health refreshActiveJobs failed', err); },
      });
  }

  private startJobPoll(): void {
    if (this.jobPollSub) return;
    // Polling pauses automatically when the tab is hidden or the user
    // signs out — VisibilityGateService swaps the inner timer for EMPTY.
    // See docs/PERFORMANCE.md §13.
    //
    // switchMap flattens the timer-of-fetches into a single stream. The
    // previous nested `subscribe(() => svc.getJobs().subscribe(...))` was
    // a textbook nested-subscribe smell — left a dangling inner sub if
    // the timer ticked again before the previous fetch resolved.
    this.jobPollSub = this.visibilityGate
      .whileLoggedInAndVisible(() => timer(5000, 5000))
      .pipe(
        switchMap(() => this.fetchActiveJobs$()),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (jobs) => {
          this.activeJobs.set(jobs);
          if (jobs.length === 0) {
            this.clearJobPoll();
          }
        },
        // Outer poll keeps ticking; log failures for dev visibility instead
        // of swallowing them silently.
        error: (err) => console.warn('health job poll fetch failed', err),
      });
  }

  private clearJobPoll(): void {
    this.jobPollSub?.unsubscribe();
    this.jobPollSub = null;
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
      'celery': 'Restart Celery workers: docker compose restart celery-worker-default celery-worker-pipeline',
      'celery_queues': 'If queues are backed up, restart workers: docker compose restart celery-worker-default celery-worker-pipeline',
      'celery_beat': 'Restart the scheduler: docker compose restart celery-beat',
      'disk_space': 'Free up disk space by pruning Docker images: docker image prune -f',
      'gpu_faiss': 'Ensure FAISS is installed. CPU fallback is used automatically if no GPU is available.',
    };
    return hints[serviceKey];
  }

  trackByLabel(_: number, group: ChecklistGroup): string { return group.label; }
  trackByServiceKey(_: number, s: ServiceHealth): string { return s.service_key; }
  trackByTier(_: number, tier: ConfigTier): string { return tier; }
  trackByIndex(index: number): number { return index; }
}
