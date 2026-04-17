import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { catchError, of } from 'rxjs';
import { EmptyStateComponent } from '../../shared/empty-state/empty-state.component';

interface HelperNode {
  id: number;
  name: string;
  role: string;
  status: 'online' | 'busy' | 'unhealthy' | 'offline';
  capabilities: Record<string, any>;
  allowed_queues: string[];
  allowed_job_types: string[];
  time_policy: 'anytime' | 'nighttime' | 'maintenance';
  max_concurrency: number;
  cpu_cap_pct: number;
  ram_cap_pct: number;
  last_heartbeat: string | null;
}

/**
 * Helper-node registry + policy view (plan item 22).
 *
 * Deep-link target: /settings#helpers. Lists all registered HelperNodes, shows
 * each node's capabilities + policy + cap defaults, and links out to the
 * Jobs helper-summary for live routing state.
 *
 * Management (add / rotate token / remove) ships in a follow-up; today the
 * component is a read + policy surface so operators can at least *see*
 * what's registered and what it can take.
 */
@Component({
  selector: 'app-helpers-settings',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    MatButtonModule,
    MatCardModule,
    MatChipsModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatTooltipModule,
    EmptyStateComponent,
  ],
  template: `
    <section class="helpers-section">
      <header class="helpers-header">
        <div class="helpers-title-row">
          <mat-icon class="helpers-title-icon">device_hub</mat-icon>
          <div>
            <h2 class="helpers-title">Helper nodes</h2>
            <p class="helpers-subtitle">
              Secondary machines that share the heavy work. The main coordinator stays in charge of
              checkpoints and leases — helpers just run the jobs they are allowed to.
            </p>
          </div>
        </div>
        <button mat-stroked-button (click)="reload()" [disabled]="loading()">
          <mat-icon>refresh</mat-icon>
          Refresh
        </button>
      </header>

      @if (loading()) {
        <div class="helpers-center">
          <mat-spinner diameter="24"></mat-spinner>
        </div>
      } @else if (nodes().length === 0) {
        <app-empty-state
          icon="device_hub"
          heading="No helper nodes registered"
          body="The main coordinator is handling everything solo. Register a helper machine here when you want to share heavy jobs like embedding or nightly syncs."
        />
      } @else {
        <div class="helpers-grid">
          @for (n of nodes(); track n.id) {
            <mat-card class="helper-card" data-ga4-panel>
              <div class="helper-card-head">
                <div class="helper-name-row">
                  <span class="helper-status-dot" [ngClass]="'status-' + n.status"
                        [matTooltip]="statusTooltip(n.status)"
                        matTooltipPosition="right"></span>
                  <span class="helper-name">{{ n.name }}</span>
                  <mat-chip class="helper-role-chip" disableRipple>{{ n.role }}</mat-chip>
                </div>
                <span class="helper-heartbeat">
                  {{ n.last_heartbeat ? ('Last seen ' + (n.last_heartbeat | date:'short')) : 'Never seen' }}
                </span>
              </div>

              <div class="helper-meta">
                <div class="helper-meta-row">
                  <span class="meta-label">Capabilities</span>
                  <span class="meta-value">{{ formatCapabilities(n.capabilities) }}</span>
                </div>
                <div class="helper-meta-row">
                  <span class="meta-label">Allowed queues</span>
                  <span class="meta-value">
                    @if (n.allowed_queues.length === 0) {
                      <em class="meta-empty">any</em>
                    } @else {
                      @for (q of n.allowed_queues; track q) {
                        <mat-chip class="meta-chip" disableRipple>{{ q }}</mat-chip>
                      }
                    }
                  </span>
                </div>
                <div class="helper-meta-row">
                  <span class="meta-label">Allowed job types</span>
                  <span class="meta-value">
                    @if (n.allowed_job_types.length === 0) {
                      <em class="meta-empty">any</em>
                    } @else {
                      @for (t of n.allowed_job_types; track t) {
                        <mat-chip class="meta-chip" disableRipple>{{ t }}</mat-chip>
                      }
                    }
                  </span>
                </div>
                <div class="helper-meta-row">
                  <span class="meta-label">Time policy</span>
                  <span class="meta-value">{{ policyDisplay(n.time_policy) }}</span>
                </div>
                <div class="helper-meta-row">
                  <span class="meta-label">Caps</span>
                  <span class="meta-value">
                    CPU {{ n.cpu_cap_pct }}% · RAM {{ n.ram_cap_pct }}% · Concurrency {{ n.max_concurrency }}
                  </span>
                </div>
              </div>
            </mat-card>
          }
        </div>
      }

      <aside class="helpers-policy">
        <h3 class="helpers-policy-title">
          <mat-icon>shield</mat-icon>
          Safety defaults
        </h3>
        <p>
          New helpers default to <strong>60% CPU</strong> and <strong>60% RAM</strong> caps. These are
          <em>safety defaults</em>, not suggestions — raising them risks making the helper unusable for the
          user who owns that machine. The main coordinator keeps checkpoints and leases, so if a helper
          stops responding the work is returned to a resumable state rather than lost.
        </p>
      </aside>
    </section>
  `,
  styles: [`
    .helpers-section {
      display: flex;
      flex-direction: column;
      gap: var(--space-lg);
    }
    .helpers-header {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: var(--space-lg);
    }
    .helpers-title-row {
      display: flex;
      align-items: flex-start;
      gap: var(--space-md);
    }
    .helpers-title-icon {
      font-size: 32px;
      width: 32px;
      height: 32px;
      color: var(--color-primary);
    }
    .helpers-title {
      font-size: 18px;
      font-weight: 600;
      margin: 0;
      color: var(--color-text-primary);
    }
    .helpers-subtitle {
      font-size: 13px;
      color: var(--color-text-secondary);
      margin: 4px 0 0;
      max-width: 640px;
      line-height: 1.5;
    }
    .helpers-center {
      display: flex;
      justify-content: center;
      padding: var(--space-xl);
    }
    .helpers-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
      gap: var(--space-md);
    }
    .helper-card {
      padding: var(--spacing-card);
      display: flex;
      flex-direction: column;
      gap: var(--space-md);
    }
    .helper-card-head {
      display: flex;
      flex-direction: column;
      gap: var(--space-xs);
    }
    .helper-name-row {
      display: flex;
      align-items: center;
      gap: var(--space-sm);
    }
    .helper-status-dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      flex-shrink: 0;
      background: var(--color-border);
    }
    .helper-status-dot.status-online { background: var(--color-success); }
    .helper-status-dot.status-busy { background: var(--color-warning); }
    .helper-status-dot.status-unhealthy { background: var(--color-error); }
    .helper-status-dot.status-offline { background: var(--color-text-muted); }
    .helper-name {
      font-weight: 600;
      color: var(--color-text-primary);
      font-size: 14px;
    }
    .helper-role-chip {
      font-size: 10px;
      text-transform: uppercase;
      font-weight: 600;
      letter-spacing: 0.05em;
    }
    .helper-heartbeat {
      font-size: 11px;
      color: var(--color-text-muted);
    }
    .helper-meta {
      display: flex;
      flex-direction: column;
      gap: var(--space-sm);
    }
    .helper-meta-row {
      display: flex;
      gap: var(--space-md);
      font-size: 12px;
      line-height: 1.4;
    }
    .meta-label {
      min-width: 128px;
      color: var(--color-text-muted);
      font-weight: 500;
    }
    .meta-value {
      flex: 1;
      color: var(--color-text-primary);
      display: inline-flex;
      flex-wrap: wrap;
      gap: 4px;
      align-items: center;
    }
    .meta-chip {
      font-size: 11px;
      height: 22px;
      --mdc-chip-elevated-container-color: var(--color-bg-faint);
    }
    .meta-empty {
      color: var(--color-text-muted);
      font-style: italic;
    }
    .helpers-policy {
      border: var(--card-border);
      border-radius: var(--card-border-radius);
      padding: var(--spacing-card);
      background: var(--color-bg-faint);
    }
    .helpers-policy-title {
      display: flex;
      align-items: center;
      gap: var(--space-sm);
      margin: 0 0 var(--space-sm);
      font-size: 14px;
      font-weight: 600;
      color: var(--color-text-primary);
    }
    .helpers-policy-title mat-icon {
      color: var(--color-primary);
    }
    .helpers-policy p {
      margin: 0;
      font-size: 13px;
      color: var(--color-text-secondary);
      line-height: 1.6;
    }
    .helpers-policy strong { color: var(--color-text-primary); }
  `],
})
export class HelpersSettingsComponent implements OnInit {
  private http = inject(HttpClient);
  // Phase E2 / Gap 41 — cancel in-flight HTTP on destroy.
  private destroyRef = inject(DestroyRef);

  readonly loading = signal(true);
  readonly nodes = signal<HelperNode[]>([]);

  ngOnInit(): void {
    this.reload();
  }

  reload(): void {
    this.loading.set(true);
    this.http
      .get<HelperNode[] | { results: HelperNode[] }>('/api/settings/helpers/')
      .pipe(catchError(() => of<HelperNode[]>([])), takeUntilDestroyed(this.destroyRef))
      .subscribe((res) => {
        const list = Array.isArray(res) ? res : (res?.results ?? []);
        this.nodes.set(list);
        this.loading.set(false);
      });
  }

  formatCapabilities(caps: Record<string, any> | null | undefined): string {
    if (!caps || Object.keys(caps).length === 0) return 'Not reported';
    const parts: string[] = [];
    if (caps['cpu_cores'] != null) parts.push(`${caps['cpu_cores']} CPU cores`);
    if (caps['ram_gb'] != null) parts.push(`${caps['ram_gb']} GB RAM`);
    if (caps['gpu_vram_gb'] != null) parts.push(`${caps['gpu_vram_gb']} GB VRAM`);
    if (caps['network_quality']) parts.push(`network: ${caps['network_quality']}`);
    return parts.length > 0 ? parts.join(' \u00B7 ') : 'Not reported';
  }

  policyDisplay(policy: string): string {
    switch (policy) {
      case 'anytime': return 'Available anytime';
      case 'nighttime': return 'Nighttime only (21:00–06:00 UTC)';
      case 'maintenance': return 'Maintenance windows only';
      default: return policy;
    }
  }

  statusTooltip(status: string): string {
    switch (status) {
      case 'online': return 'Healthy and ready for work';
      case 'busy': return 'Healthy and actively running a job';
      case 'unhealthy': return 'Responding but something is wrong';
      case 'offline': return 'No recent heartbeat';
      default: return status;
    }
  }
}
