import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { catchError, EMPTY, finalize } from 'rxjs';

import { EmptyStateComponent } from '../../shared/empty-state/empty-state.component';
import {
  HelperNodeCreatePayload,
  HelperNodeSettingsRecord,
  SiloSettingsService,
} from '../silo-settings.service';

@Component({
  selector: 'app-helpers-settings',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatCardModule,
    MatChipsModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatSnackBarModule,
    MatTooltipModule,
    EmptyStateComponent,
  ],
  template: `
    <section class="helpers-section" id="helpers">
      <header class="helpers-header">
        <div class="helpers-title-row">
          <mat-icon class="helpers-title-icon">device_hub</mat-icon>
          <div>
            <h2 class="helpers-title">Helper nodes</h2>
            <p class="helpers-subtitle">
              Secondary machines can contribute CPU, RAM, and optional GPU work. Intake pause,
              liveness, warmed models, and live pressure all come from the existing helper registry.
            </p>
          </div>
        </div>
        <button mat-stroked-button type="button" (click)="reload()" [disabled]="loading()">
          <mat-icon>refresh</mat-icon>
          Refresh
        </button>
      </header>

      <div class="summary-grid" *ngIf="nodes().length > 0">
        <mat-card class="summary-card">
          <mat-card-content>
            <span class="summary-label">Online</span>
            <strong>{{ counts().online }}</strong>
          </mat-card-content>
        </mat-card>
        <mat-card class="summary-card">
          <mat-card-content>
            <span class="summary-label">Busy</span>
            <strong>{{ counts().busy }}</strong>
          </mat-card-content>
        </mat-card>
        <mat-card class="summary-card">
          <mat-card-content>
            <span class="summary-label">Stale</span>
            <strong>{{ counts().stale }}</strong>
          </mat-card-content>
        </mat-card>
        <mat-card class="summary-card">
          <mat-card-content>
            <span class="summary-label">Offline</span>
            <strong>{{ counts().offline }}</strong>
          </mat-card-content>
        </mat-card>
      </div>

      <mat-card class="register-card" id="helpers-registration">
        <mat-card-header>
          <mat-card-title>Register helper node</mat-card-title>
          <mat-card-subtitle>Add a secondary machine without leaving the existing helper registry flow.</mat-card-subtitle>
        </mat-card-header>
        <mat-card-content>
          <div class="register-grid">
            <mat-form-field appearance="outline">
              <mat-label>Name</mat-label>
              <input matInput autocomplete="off" [(ngModel)]="draft.name" />
            </mat-form-field>
            <mat-form-field appearance="outline">
              <mat-label>Token</mat-label>
              <input matInput autocomplete="off" [(ngModel)]="draft.token" />
            </mat-form-field>
            <mat-form-field appearance="outline">
              <mat-label>Role</mat-label>
              <mat-select [(ngModel)]="draft.role">
                <mat-option value="worker">Worker</mat-option>
                <mat-option value="gpu">GPU worker</mat-option>
                <mat-option value="crawler">Crawler</mat-option>
              </mat-select>
            </mat-form-field>
            <mat-form-field appearance="outline">
              <mat-label>Time policy</mat-label>
              <mat-select [(ngModel)]="draft.time_policy">
                <mat-option value="anytime">Anytime</mat-option>
                <mat-option value="nighttime">Nighttime</mat-option>
                <mat-option value="maintenance">Maintenance window</mat-option>
              </mat-select>
            </mat-form-field>
            <mat-form-field appearance="outline">
              <mat-label>Max concurrency</mat-label>
              <input matInput autocomplete="off" type="number" min="1" step="1" [(ngModel)]="draft.max_concurrency" />
            </mat-form-field>
            <mat-form-field appearance="outline">
              <mat-label>CPU cap %</mat-label>
              <input matInput autocomplete="off" type="number" min="10" max="100" step="5" [(ngModel)]="draft.cpu_cap_pct" />
            </mat-form-field>
            <mat-form-field appearance="outline">
              <mat-label>RAM cap %</mat-label>
              <input matInput autocomplete="off" type="number" min="10" max="100" step="5" [(ngModel)]="draft.ram_cap_pct" />
            </mat-form-field>
            <mat-form-field appearance="outline">
              <mat-label>Accepting work</mat-label>
              <mat-select [(ngModel)]="draft.accepting_work">
                <mat-option [value]="true">Yes</mat-option>
                <mat-option [value]="false">No</mat-option>
              </mat-select>
            </mat-form-field>
          </div>
          <div class="button-row">
            <button mat-flat-button color="primary" type="button" (click)="createHelper()" [disabled]="creating() || !draft.name.trim() || !draft.token.trim()">
              <mat-icon>{{ creating() ? 'sync' : 'add' }}</mat-icon>
              {{ creating() ? 'Registering…' : 'Register helper' }}
            </button>
          </div>
        </mat-card-content>
      </mat-card>

      @if (loading()) {
        <div class="helpers-center">
          <mat-spinner diameter="24"></mat-spinner>
        </div>
      } @else if (nodes().length === 0) {
        <app-empty-state
          icon="device_hub"
          heading="No helper nodes registered"
          body="The main machine is handling everything solo. Register a helper here if you want to offload RAM-heavy or GPU-heavy background work."
        />
      } @else {
        <div class="helpers-grid">
          @for (node of nodes(); track node.id) {
            <mat-card class="helper-card">
              <div class="helper-card-head">
                <div class="helper-name-row">
                  <span class="helper-status-dot" [ngClass]="'status-' + node.derived_state"
                        [matTooltip]="statusTooltip(node.derived_state)"
                        matTooltipPosition="right"></span>
                  <span class="helper-name">{{ node.name }}</span>
                  <mat-chip class="helper-role-chip" disableRipple>{{ node.role }}</mat-chip>
                  <mat-chip class="helper-accepting-chip" disableRipple [class.helper-accepting-chip--paused]="!node.accepting_work">
                    {{ node.accepting_work ? 'Accepting work' : 'Paused intake' }}
                  </mat-chip>
                </div>
                <span class="helper-heartbeat">
                  {{ node.last_heartbeat ? ('Last seen ' + (node.last_heartbeat | date:'short')) : 'Never seen' }}
                </span>
              </div>

              <div class="helper-metrics">
                <div class="metric-pill">
                  <span class="metric-pill__label">Jobs</span>
                  <span class="metric-pill__value">{{ node.active_jobs }} active • {{ node.queued_jobs }} queued</span>
                </div>
                <div class="metric-pill">
                  <span class="metric-pill__label">CPU</span>
                  <span class="metric-pill__value">{{ node.cpu_pct || 0 }}% of {{ node.cpu_cap_pct }}%</span>
                </div>
                <div class="metric-pill">
                  <span class="metric-pill__label">RAM</span>
                  <span class="metric-pill__value">{{ node.ram_pct || 0 }}% of {{ node.ram_cap_pct }}%</span>
                </div>
                <div class="metric-pill" *ngIf="node.gpu_util_pct !== null || node.gpu_vram_total_mb !== null">
                  <span class="metric-pill__label">GPU</span>
                  <span class="metric-pill__value">
                    {{ node.gpu_util_pct ?? 0 }}% util
                    <span class="meta-sep"> • </span>
                    {{ node.gpu_vram_used_mb ?? 0 }}/{{ node.gpu_vram_total_mb ?? 0 }} MB
                  </span>
                </div>
                <div class="metric-pill">
                  <span class="metric-pill__label">Network</span>
                  <span class="metric-pill__value">{{ node.network_rtt_ms ?? 0 }} ms RTT</span>
                </div>
                <div class="metric-pill">
                  <span class="metric-pill__label">Native kernels</span>
                  <span class="metric-pill__value">{{ node.native_kernels_healthy ? 'Healthy' : 'Unavailable' }}</span>
                </div>
              </div>

              <div class="helper-meta">
                <div class="helper-meta-row">
                  <span class="meta-label">Capabilities</span>
                  <span class="meta-value">{{ formatCapabilities(node.capabilities) }}</span>
                </div>
                <div class="helper-meta-row">
                  <span class="meta-label">Queues</span>
                  <span class="meta-value">{{ formatList(node.allowed_queues, 'any') }}</span>
                </div>
                <div class="helper-meta-row">
                  <span class="meta-label">Job lanes</span>
                  <span class="meta-value">{{ formatList(node.allowed_job_types, 'any') }}</span>
                </div>
                <div class="helper-meta-row">
                  <span class="meta-label">Warmed models</span>
                  <span class="meta-value">{{ formatList(node.warmed_model_keys, 'none reported') }}</span>
                </div>
                <div class="helper-meta-row">
                  <span class="meta-label">Policy</span>
                  <span class="meta-value">
                    {{ policyDisplay(node.time_policy) }}
                    <span class="meta-sep"> • </span>
                    Concurrency {{ node.max_concurrency }}
                  </span>
                </div>
              </div>

              <div class="button-row">
                <button mat-stroked-button type="button" (click)="toggleAcceptingWork(node)" [disabled]="updatingNodeId() === node.id">
                  <mat-icon>{{ node.accepting_work ? 'pause_circle' : 'play_circle' }}</mat-icon>
                  {{ node.accepting_work ? 'Pause intake' : 'Resume intake' }}
                </button>
                <button mat-stroked-button color="warn" type="button" (click)="deleteHelper(node)" [disabled]="updatingNodeId() === node.id">
                  <mat-icon>delete</mat-icon>
                  Remove helper
                </button>
              </div>
            </mat-card>
          }
        </div>
      }
    </section>
  `,
  styles: [`
    .helpers-section {
      display: flex;
      flex-direction: column;
      gap: var(--space-lg);
      padding: var(--space-md);
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
      max-width: 720px;
      line-height: 1.5;
    }
    .summary-grid,
    .register-grid,
    .helpers-grid,
    .helper-metrics {
      display: grid;
      gap: var(--space-md);
    }
    .summary-grid {
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    }
    .summary-card {
      border: var(--card-border);
    }
    .summary-card mat-card-content {
      display: flex;
      flex-direction: column;
      gap: 6px;
      padding: var(--space-md);
    }
    .summary-label {
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--color-text-muted);
    }
    .summary-card strong {
      font-size: 22px;
      color: var(--color-text-primary);
    }
    .register-card {
      border: var(--card-border);
    }
    .register-grid {
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    }
    .helpers-center {
      display: flex;
      justify-content: center;
      padding: var(--space-xl);
    }
    .helpers-grid {
      grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
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
      flex-wrap: wrap;
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
    .helper-status-dot.status-stale { background: var(--color-primary); }
    .helper-status-dot.status-offline { background: var(--color-text-muted); }
    .helper-name {
      font-weight: 600;
      color: var(--color-text-primary);
      font-size: 14px;
    }
    .helper-role-chip,
    .helper-accepting-chip {
      font-size: 10px;
      font-weight: 600;
      letter-spacing: 0.05em;
    }
    .helper-accepting-chip--paused {
      --mdc-chip-elevated-container-color: var(--color-blue-50);
    }
    .helper-heartbeat {
      font-size: 11px;
      color: var(--color-text-muted);
    }
    .helper-metrics {
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    }
    .metric-pill {
      border: var(--card-border);
      border-radius: var(--card-border-radius);
      padding: var(--space-sm);
      background: var(--color-bg-faint);
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .metric-pill__label {
      font-size: 11px;
      color: var(--color-text-muted);
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    .metric-pill__value {
      font-size: 12px;
      color: var(--color-text-primary);
      line-height: 1.4;
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
      line-height: 1.5;
    }
    .meta-label {
      min-width: 104px;
      color: var(--color-text-muted);
      font-weight: 500;
    }
    .meta-value {
      flex: 1;
      color: var(--color-text-primary);
    }
    .meta-sep {
      color: var(--color-text-muted);
    }
    .button-row {
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-sm);
    }
    @media (max-width: 900px) {
      .helpers-header {
        flex-direction: column;
      }
      .button-row {
        flex-direction: column;
      }
      .button-row button {
        width: 100%;
      }
      .helper-meta-row {
        flex-direction: column;
        gap: 4px;
      }
      .meta-label {
        min-width: 0;
      }
    }
  `],
})
export class HelpersSettingsComponent implements OnInit {
  private siloSettings = inject(SiloSettingsService);
  private snack = inject(MatSnackBar);
  private destroyRef = inject(DestroyRef);

  readonly loading = signal(true);
  readonly creating = signal(false);
  readonly updatingNodeId = signal<number | null>(null);
  readonly nodes = signal<HelperNodeSettingsRecord[]>([]);

  readonly counts = computed(() => {
    const next = { online: 0, busy: 0, stale: 0, offline: 0 };
    for (const node of this.nodes()) {
      const key = node.derived_state as keyof typeof next;
      if (key in next) {
        next[key] += 1;
      }
    }
    return next;
  });

  draft: HelperNodeCreatePayload = {
    name: '',
    token: '',
    role: 'worker',
    time_policy: 'anytime',
    max_concurrency: 2,
    cpu_cap_pct: 60,
    ram_cap_pct: 60,
    accepting_work: true,
  };

  ngOnInit(): void {
    this.reload();
  }

  reload(): void {
    this.loading.set(true);
    this.siloSettings.listHelpers()
      .pipe(
        finalize(() => this.loading.set(false)),
        catchError(() => {
          this.snack.open('Could not load helper nodes.', 'Dismiss', { duration: 4000 });
          return EMPTY;
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((nodes) => this.nodes.set(nodes));
  }

  createHelper(): void {
    if (!this.draft.name?.trim() || !this.draft.token?.trim()) {
      this.snack.open('Helper name and token are required.', 'Dismiss', { duration: 3000 });
      return;
    }

    this.creating.set(true);
    this.siloSettings.createHelper({
      ...this.draft,
      name: this.draft.name.trim(),
      token: this.draft.token.trim(),
    })
      .pipe(
        finalize(() => this.creating.set(false)),
        catchError((error) => {
          this.snack.open(error?.error?.error || 'Could not register helper node.', 'Dismiss', { duration: 4500 });
          return EMPTY;
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => {
        this.snack.open('Helper node registered.', 'Dismiss', { duration: 3000 });
        this.draft = {
          name: '',
          token: '',
          role: 'worker',
          time_policy: 'anytime',
          max_concurrency: 2,
          cpu_cap_pct: 60,
          ram_cap_pct: 60,
          accepting_work: true,
        };
        this.reload();
      });
  }

  toggleAcceptingWork(node: HelperNodeSettingsRecord): void {
    this.updatingNodeId.set(node.id);
    this.siloSettings.updateHelper(node.id, { accepting_work: !node.accepting_work })
      .pipe(
        finalize(() => this.updatingNodeId.set(null)),
        catchError((error) => {
          this.snack.open(error?.error?.error || 'Could not update helper state.', 'Dismiss', { duration: 4500 });
          return EMPTY;
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((updated) => {
        this.nodes.set(this.nodes().map((item) => item.id === updated.id ? updated : item));
        this.snack.open(
          updated.accepting_work ? 'Helper intake resumed.' : 'Helper intake paused.',
          'Dismiss',
          { duration: 3000 },
        );
      });
  }

  deleteHelper(node: HelperNodeSettingsRecord): void {
    this.updatingNodeId.set(node.id);
    this.siloSettings.deleteHelper(node.id)
      .pipe(
        finalize(() => this.updatingNodeId.set(null)),
        catchError((error) => {
          this.snack.open(error?.error?.error || 'Could not remove helper node.', 'Dismiss', { duration: 4500 });
          return EMPTY;
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => {
        this.nodes.set(this.nodes().filter((item) => item.id !== node.id));
        this.snack.open('Helper removed.', 'Dismiss', { duration: 3000 });
      });
  }

  formatCapabilities(caps: Record<string, unknown> | null | undefined): string {
    if (!caps || Object.keys(caps).length === 0) return 'Not reported';
    const parts: string[] = [];
    const cpuCores = caps['cpu_cores'];
    const ramGb = caps['ram_gb'];
    const gpuVramGb = caps['gpu_vram_gb'];
    const gpuName = caps['gpu_name'];
    if (cpuCores != null) parts.push(`${cpuCores} CPU cores`);
    if (ramGb != null) parts.push(`${ramGb} GB RAM`);
    if (gpuName) parts.push(String(gpuName));
    if (gpuVramGb != null) parts.push(`${gpuVramGb} GB VRAM`);
    return parts.length > 0 ? parts.join(' • ') : 'Not reported';
  }

  formatList(values: string[] | null | undefined, emptyLabel: string): string {
    return values && values.length > 0 ? values.join(' • ') : emptyLabel;
  }

  policyDisplay(policy: string): string {
    switch (policy) {
      case 'anytime':
        return 'Available anytime';
      case 'nighttime':
        return 'Nighttime only';
      case 'maintenance':
        return 'Maintenance window only';
      default:
        return policy;
    }
  }

  statusTooltip(status: string): string {
    switch (status) {
      case 'online':
        return 'Healthy and ready for more work.';
      case 'busy':
        return 'Healthy and actively running work.';
      case 'stale':
        return 'Heartbeat is old enough that routing should be cautious.';
      case 'offline':
        return 'No recent heartbeat from this helper.';
      default:
        return status;
    }
  }
}
