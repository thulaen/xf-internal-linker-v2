import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatDividerModule } from '@angular/material/divider';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { MatSliderModule } from '@angular/material/slider';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { catchError, EMPTY, finalize } from 'rxjs';

import {
  HelperNodeSettingsRecord,
  RuntimeModelPlacement,
  RuntimeModelRegistryEntry,
  RuntimeSummaryPayload,
  SiloSettingsService,
} from '../silo-settings.service';

interface RuntimeConfig {
  embedding_batch_size: number;
  celery_concurrency: number;
  embedding_batch_size_range: [number, number];
  celery_concurrency_range: [number, number];
  celery_concurrency_requires_restart: boolean;
}

interface RuntimeRegistrationForm {
  model_name: string;
  model_family: string;
  dimension: number;
  device_target: string;
  batch_size: number;
  role: string;
  executor_type: string;
  helper_id: number | null;
}

@Component({
  selector: 'app-performance-settings',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatCardModule,
    MatDividerModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressBarModule,
    MatSelectModule,
    MatSliderModule,
    MatSnackBarModule,
    MatTooltipModule,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="perf-settings" id="performance-tunables">
      <mat-card class="setting-card" id="runtime-recommendations">
        <mat-card-header>
          <mat-icon mat-card-avatar>memory</mat-icon>
          <mat-card-title>Runtime profile recommendation</mat-card-title>
          <mat-card-subtitle>Upgrade-aware defaults based on the machine this app is running on.</mat-card-subtitle>
        </mat-card-header>
        <mat-card-content>
          @if (runtimeLoading()) {
            <div class="empty-row">
              <mat-icon>sync</mat-icon>
              <span>Loading runtime summary…</span>
            </div>
          } @else if (runtimeSummary(); as runtime) {
            <div class="runtime-banner" [class.runtime-banner--upgrade]="runtime.hardware.detected_upgrade">
              <mat-icon>{{ runtime.hardware.detected_upgrade ? 'upgrade' : 'verified' }}</mat-icon>
              <div class="runtime-banner-copy">
                <strong>{{ runtime.recommended_profile.profile | titlecase }} profile</strong>
                <p>{{ runtime.recommended_profile.reason }}</p>
              </div>
              <button mat-stroked-button color="primary" type="button" (click)="applyRecommendedProfile()">
                Apply suggested limits
              </button>
            </div>

            <div class="hardware-grid">
              <div class="hardware-pill">
                <span class="pill-label">CPU</span>
                <span class="pill-value">{{ runtime.hardware.cpu_cores }} cores</span>
              </div>
              <div class="hardware-pill">
                <span class="pill-label">RAM</span>
                <span class="pill-value">{{ runtime.hardware.ram_gb }} GB</span>
              </div>
              <div class="hardware-pill">
                <span class="pill-label">GPU</span>
                <span class="pill-value">{{ runtime.hardware.gpu_name || 'CPU-only' }}</span>
              </div>
              <div class="hardware-pill">
                <span class="pill-label">VRAM</span>
                <span class="pill-value">{{ runtime.hardware.gpu_vram_gb || 0 }} GB</span>
              </div>
              <div class="hardware-pill">
                <span class="pill-label">Disk free</span>
                <span class="pill-value">{{ runtime.hardware.disk_free_gb }} GB</span>
              </div>
              <div class="hardware-pill">
                <span class="pill-label">Native kernels</span>
                <span class="pill-value">{{ runtime.hardware.native_kernels_healthy ? 'Healthy' : 'Needs attention' }}</span>
              </div>
            </div>
          }
        </mat-card-content>
      </mat-card>

      <mat-card class="setting-card" id="model-runtime">
        <mat-card-header>
          <mat-icon mat-card-avatar>hub</mat-icon>
          <mat-card-title>Model runtime</mat-card-title>
          <mat-card-subtitle>FR-020 champion, candidate, placements, backfill, and hot-swap actions.</mat-card-subtitle>
        </mat-card-header>
        <mat-card-content>
          <div class="section-actions">
            <button mat-stroked-button type="button" (click)="reloadRuntime()" [disabled]="runtimeLoading()">
              <mat-icon>refresh</mat-icon>
              Refresh runtime
            </button>
          </div>

          @if (runtimeLoading()) {
            <div class="empty-row">
              <mat-icon>sync</mat-icon>
              <span>Loading model runtime…</span>
            </div>
          } @else if (runtimeSummary(); as runtime) {
            <div class="runtime-summary-grid">
              <mat-card class="mini-card">
                <mat-card-content>
                  <div class="mini-label">Active model</div>
                  <div class="mini-value">{{ runtime.model_runtime.active_model?.model_name || 'Not registered yet' }}</div>
                  <div class="mini-meta">
                    {{ runtime.model_runtime.active_model?.device_target || runtime.model_runtime.device }}
                    <span class="meta-sep"> • </span>
                    {{ runtime.model_runtime.active_model?.dimension || 1024 }} dims
                  </div>
                </mat-card-content>
              </mat-card>
              <mat-card class="mini-card">
                <mat-card-content>
                  <div class="mini-label">Candidate model</div>
                  <div class="mini-value">{{ runtime.model_runtime.candidate_model?.model_name || 'None queued' }}</div>
                  <div class="mini-meta">
                    {{ runtime.model_runtime.candidate_model?.status || 'Idle' }}
                  </div>
                </mat-card-content>
              </mat-card>
              <mat-card class="mini-card">
                <mat-card-content>
                  <div class="mini-label">Hot swap safety</div>
                  <div class="mini-value">{{ runtime.model_runtime.hot_swap_safe ? 'Safe' : 'Blocked' }}</div>
                  <div class="mini-meta">
                    Reclaimable disk {{ humanBytes(runtime.model_runtime.reclaimable_disk_bytes) }}
                  </div>
                </mat-card-content>
              </mat-card>
            </div>

            @if (runtime.model_runtime.backfill; as backfill) {
              <div class="backfill-panel">
                <div class="backfill-copy">
                  <strong>Backfill {{ backfill.status }}</strong>
                  <span>{{ backfill.compatibility_status }} compatibility</span>
                </div>
                <mat-progress-bar mode="determinate" [value]="backfill.progress_pct || 0"></mat-progress-bar>
              </div>
            }

            <div class="model-grid">
              <mat-card class="mini-card model-card" *ngIf="runtime.model_runtime.active_model as active">
                <mat-card-content>
                  <div class="model-card-head">
                    <div>
                      <div class="mini-label">Champion</div>
                      <div class="mini-value">{{ active.model_name }}</div>
                      <div class="mini-meta">{{ active.status }} • {{ active.device_target }} • batch {{ active.batch_size }}</div>
                    </div>
                    <span class="status-chip">{{ active.role }}</span>
                  </div>
                  <div class="button-row">
                    <button mat-stroked-button type="button" (click)="runModelAction(active, 'pause')" [disabled]="actionPending()">Pause</button>
                    <button mat-stroked-button type="button" (click)="runModelAction(active, 'resume')" [disabled]="actionPending()">Resume</button>
                    <button mat-stroked-button type="button" (click)="runModelAction(active, 'drain')" [disabled]="actionPending()">Drain</button>
                    <button mat-flat-button color="primary" type="button" (click)="runModelAction(active, 'rollback')" [disabled]="actionPending()">Rollback</button>
                  </div>
                </mat-card-content>
              </mat-card>

              <mat-card class="mini-card model-card" *ngIf="runtime.model_runtime.candidate_model as candidate">
                <mat-card-content>
                  <div class="model-card-head">
                    <div>
                      <div class="mini-label">Candidate</div>
                      <div class="mini-value">{{ candidate.model_name }}</div>
                      <div class="mini-meta">{{ candidate.status }} • {{ candidate.device_target }} • batch {{ candidate.batch_size }}</div>
                    </div>
                    <span class="status-chip status-chip--candidate">{{ candidate.role }}</span>
                  </div>
                  <div class="button-row">
                    <button mat-stroked-button type="button" (click)="runModelAction(candidate, 'download')" [disabled]="actionPending()">Download</button>
                    <button mat-stroked-button type="button" (click)="runModelAction(candidate, 'warm')" [disabled]="actionPending()">Warm</button>
                    <button mat-stroked-button type="button" (click)="runModelAction(candidate, 'pause')" [disabled]="actionPending()">Pause</button>
                    <button mat-stroked-button type="button" (click)="runModelAction(candidate, 'resume')" [disabled]="actionPending()">Resume</button>
                    <button mat-stroked-button type="button" (click)="runModelAction(candidate, 'drain')" [disabled]="actionPending()">Drain</button>
                    <button mat-flat-button color="primary" type="button" (click)="runModelAction(candidate, 'promote')" [disabled]="actionPending() || candidate.status !== 'ready'">Promote</button>
                  </div>
                </mat-card-content>
              </mat-card>
            </div>

            <mat-divider></mat-divider>

            <div class="register-grid">
              <mat-form-field appearance="outline">
                <mat-label>Model name</mat-label>
                <input matInput autocomplete="off" [(ngModel)]="registration.model_name" />
              </mat-form-field>
              <mat-form-field appearance="outline">
                <mat-label>Family</mat-label>
                <input matInput autocomplete="off" [(ngModel)]="registration.model_family" />
              </mat-form-field>
              <mat-form-field appearance="outline">
                <mat-label>Dimension</mat-label>
                <input matInput autocomplete="off" type="number" min="1" step="1" [(ngModel)]="registration.dimension" />
              </mat-form-field>
              <mat-form-field appearance="outline">
                <mat-label>Batch size</mat-label>
                <input matInput autocomplete="off" type="number" min="1" step="1" [(ngModel)]="registration.batch_size" />
              </mat-form-field>
              <mat-form-field appearance="outline">
                <mat-label>Device</mat-label>
                <mat-select [(ngModel)]="registration.device_target">
                  <mat-option value="cpu">CPU</mat-option>
                  <mat-option value="cuda">CUDA</mat-option>
                </mat-select>
              </mat-form-field>
              <mat-form-field appearance="outline">
                <mat-label>Role</mat-label>
                <mat-select [(ngModel)]="registration.role">
                  <mat-option value="candidate">Candidate</mat-option>
                  <mat-option value="retired">Retired</mat-option>
                </mat-select>
              </mat-form-field>
              <mat-form-field appearance="outline">
                <mat-label>Executor</mat-label>
                <mat-select [(ngModel)]="registration.executor_type">
                  <mat-option value="primary">Primary</mat-option>
                  <mat-option value="helper">Helper</mat-option>
                </mat-select>
              </mat-form-field>
              <mat-form-field appearance="outline" *ngIf="registration.executor_type === 'helper'">
                <mat-label>Helper node</mat-label>
                <mat-select [(ngModel)]="registration.helper_id">
                  <mat-option [value]="null">Choose helper</mat-option>
                  <mat-option *ngFor="let helper of helpers()" [value]="helper.id">{{ helper.name }}</mat-option>
                </mat-select>
              </mat-form-field>
            </div>

            <div class="section-actions">
              <button mat-flat-button color="primary" type="button" (click)="registerModel()" [disabled]="registering() || !registration.model_name.trim()">
                <mat-icon>{{ registering() ? 'sync' : 'add' }}</mat-icon>
                {{ registering() ? 'Registering…' : 'Register model candidate' }}
              </button>
            </div>

            <div class="placements-section">
              <h3 class="subheading">Placements & reclaimable disk</h3>
              @if (runtime.model_runtime.placements.length === 0) {
                <div class="empty-row">
                  <mat-icon>folder_open</mat-icon>
                  <span>No registered placements yet.</span>
                </div>
              } @else {
                <div class="placement-list">
                  <div class="placement-row" *ngFor="let placement of runtime.model_runtime.placements">
                    <div class="placement-copy">
                      <strong>{{ placement.model_name }}</strong>
                      <span>
                        {{ placement.executor_type === 'helper' ? ('Helper: ' + (placement.helper_name || 'unknown')) : 'Primary node' }}
                        <span class="meta-sep"> • </span>
                        {{ placement.status }}
                        <span class="meta-sep"> • </span>
                        {{ humanBytes(placement.disk_bytes) }}
                      </span>
                    </div>
                    <button
                      mat-stroked-button
                      color="warn"
                      type="button"
                      (click)="deletePlacement(placement)"
                      [disabled]="deletingPlacement() || !placement.deletable"
                    >
                      Delete old placement
                    </button>
                  </div>
                </div>
              }
            </div>

            <div class="audit-section">
              <h3 class="subheading">Runtime audit log</h3>
              @if ((runtime.model_runtime.recent_audit_log || []).length === 0) {
                <div class="empty-row">
                  <mat-icon>receipt_long</mat-icon>
                  <span>No runtime actions logged yet.</span>
                </div>
              } @else {
                <div class="audit-list">
                  <div class="audit-row" *ngFor="let entry of runtime.model_runtime.recent_audit_log">
                    <div class="audit-time">{{ entry.created_at | date:'MMM d, HH:mm' }}</div>
                    <div class="audit-message">{{ entry.message }}</div>
                  </div>
                </div>
              }
            </div>
          }
        </mat-card-content>
      </mat-card>

      <mat-card class="setting-card">
        <mat-card-header>
          <mat-icon mat-card-avatar>layers</mat-icon>
          <mat-card-title>Batch size</mat-card-title>
          <mat-card-subtitle>How many paragraphs the linker processes at once.</mat-card-subtitle>
        </mat-card-header>
        <mat-card-content>
          <p class="plain-text">
            Bigger batch = faster runs, but uses more memory. If the linker ever runs out of memory,
            drop this number. The default (32) is safe on most machines.
          </p>
          <div class="slider-row">
            <mat-slider
              [min]="batchMin()"
              [max]="batchMax()"
              [step]="8"
              discrete
              [displayWith]="labelWithMb">
              <input matSliderThumb
                     [ngModel]="batchSize()"
                     (ngModelChange)="batchSize.set($event)" />
            </mat-slider>
            <span class="slider-value">{{ batchSize() }}</span>
          </div>
          <div class="slider-ends">
            <span>{{ batchMin() }}</span>
            <span>{{ batchMax() }}</span>
          </div>
        </mat-card-content>
      </mat-card>

      <mat-card class="setting-card">
        <mat-card-header>
          <mat-icon mat-card-avatar>group_work</mat-icon>
          <mat-card-title>Worker count</mat-card-title>
          <mat-card-subtitle>Background helpers that run jobs in parallel.</mat-card-subtitle>
        </mat-card-header>
        <mat-card-content>
          <p class="plain-text">
            More workers = more things in parallel, but each one uses memory. The default (2) is safe.
            <strong>Takes effect after the next Docker restart.</strong>
          </p>
          <div class="slider-row">
            <mat-slider
              [min]="concMin()"
              [max]="concMax()"
              [step]="1"
              discrete>
              <input matSliderThumb
                     [ngModel]="concurrency()"
                     (ngModelChange)="concurrency.set($event)" />
            </mat-slider>
            <span class="slider-value">{{ concurrency() }}</span>
          </div>
          <div class="slider-ends">
            <span>{{ concMin() }}</span>
            <span>{{ concMax() }}</span>
          </div>
          @if (dirtyConcurrency()) {
            <div class="restart-banner" role="alert">
              <mat-icon>restart_alt</mat-icon>
              <span>
                Worker count changed. The new setting applies <strong>after a Docker restart</strong>
                so the current run stays stable.
              </span>
            </div>
          }
        </mat-card-content>
      </mat-card>

      <div class="actions">
        <button mat-stroked-button type="button" (click)="reset()" [disabled]="saving()">
          <mat-icon>refresh</mat-icon>
          Reset to defaults
        </button>
        <button mat-flat-button color="primary" type="button" (click)="save()" [disabled]="saving()">
          <mat-icon>{{ saving() ? 'sync' : 'save' }}</mat-icon>
          {{ saving() ? 'Saving…' : 'Save changes' }}
        </button>
      </div>
    </section>
  `,
  styles: [`
    .perf-settings {
      display: flex;
      flex-direction: column;
      gap: var(--space-md);
      padding: var(--space-md);
    }
    .setting-card {
      padding: var(--spacing-card);
    }
    .plain-text {
      font-size: 13px;
      color: var(--color-text-secondary);
      line-height: 1.5;
      margin: 0 0 var(--space-sm) 0;
    }
    .section-actions {
      display: flex;
      justify-content: flex-end;
      gap: var(--space-sm);
      margin-bottom: var(--space-md);
    }
    .runtime-banner {
      display: flex;
      align-items: flex-start;
      gap: var(--space-md);
      padding: var(--spacing-card);
      border: var(--card-border);
      border-radius: var(--card-border-radius);
      background: var(--color-bg-faint);
      margin-bottom: var(--space-md);
    }
    .runtime-banner--upgrade {
      background: var(--color-blue-50);
    }
    .runtime-banner mat-icon {
      color: var(--color-primary);
    }
    .runtime-banner-copy {
      flex: 1;
    }
    .runtime-banner-copy strong {
      display: block;
      margin-bottom: 4px;
      color: var(--color-text-primary);
    }
    .runtime-banner-copy p {
      margin: 0;
      color: var(--color-text-secondary);
      line-height: 1.5;
    }
    .hardware-grid,
    .runtime-summary-grid,
    .model-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: var(--space-sm);
    }
    .hardware-pill,
    .mini-card {
      border: var(--card-border);
      border-radius: var(--card-border-radius);
      padding: var(--space-md);
      background: var(--color-bg-faint);
    }
    .pill-label,
    .mini-label {
      display: block;
      font-size: 11px;
      color: var(--color-text-muted);
      text-transform: uppercase;
      letter-spacing: 0.04em;
      margin-bottom: 4px;
    }
    .pill-value,
    .mini-value {
      font-size: 15px;
      font-weight: 600;
      color: var(--color-text-primary);
    }
    .mini-meta {
      margin-top: 4px;
      font-size: 12px;
      color: var(--color-text-secondary);
      line-height: 1.4;
    }
    .backfill-panel {
      display: flex;
      flex-direction: column;
      gap: var(--space-sm);
      margin: var(--space-md) 0;
      padding: var(--space-md);
      border: var(--card-border);
      border-radius: var(--card-border-radius);
      background: var(--color-bg-faint);
    }
    .backfill-copy {
      display: flex;
      justify-content: space-between;
      gap: var(--space-sm);
      flex-wrap: wrap;
      font-size: 13px;
      color: var(--color-text-secondary);
    }
    .model-card {
      margin-top: var(--space-md);
    }
    .model-card-head {
      display: flex;
      justify-content: space-between;
      gap: var(--space-sm);
      align-items: flex-start;
      margin-bottom: var(--space-sm);
    }
    .status-chip {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 4px 8px;
      border-radius: 999px;
      background: var(--color-success-light);
      color: var(--color-success);
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
    }
    .status-chip--candidate {
      background: var(--color-blue-50);
      color: var(--color-primary);
    }
    .button-row {
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-sm);
    }
    .register-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: var(--space-sm);
      margin: var(--space-md) 0;
    }
    .placements-section,
    .audit-section {
      margin-top: var(--space-md);
    }
    .subheading {
      margin: 0 0 var(--space-sm);
      font-size: 14px;
      font-weight: 600;
      color: var(--color-text-primary);
    }
    .placement-list,
    .audit-list {
      display: flex;
      flex-direction: column;
      gap: var(--space-sm);
    }
    .placement-row,
    .audit-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: var(--space-md);
      padding: var(--space-md);
      border: var(--card-border);
      border-radius: var(--card-border-radius);
      background: var(--color-bg-faint);
    }
    .placement-copy,
    .audit-message {
      display: flex;
      flex-direction: column;
      gap: 4px;
      min-width: 0;
      color: var(--color-text-secondary);
      font-size: 12px;
    }
    .placement-copy strong {
      color: var(--color-text-primary);
      font-size: 13px;
    }
    .audit-time {
      min-width: 112px;
      color: var(--color-text-muted);
      font-size: 12px;
      font-variant-numeric: tabular-nums;
    }
    .meta-sep {
      color: var(--color-text-muted);
    }
    .empty-row {
      display: flex;
      align-items: center;
      gap: var(--space-sm);
      padding: var(--space-md);
      color: var(--color-text-secondary);
    }
    .slider-row {
      display: flex;
      align-items: center;
      gap: var(--space-sm);
    }
    .slider-row mat-slider {
      flex: 1;
    }
    .slider-value {
      font-size: 14px;
      font-weight: 600;
      min-width: 36px;
      text-align: right;
      font-variant-numeric: tabular-nums;
      color: var(--color-primary);
    }
    .slider-ends {
      display: flex;
      justify-content: space-between;
      margin-top: 4px;
      font-size: 11px;
      color: var(--color-text-muted);
      padding: 0 8px;
    }
    .restart-banner {
      margin-top: var(--space-sm);
      padding: var(--space-sm) var(--space-md);
      border: var(--card-border);
      border-radius: var(--card-border-radius);
      background: var(--color-bg-faint);
      display: flex;
      align-items: center;
      gap: var(--space-sm);
      font-size: 12px;
      color: var(--color-text-secondary);
    }
    .restart-banner mat-icon {
      color: var(--color-primary);
    }
    .actions {
      display: flex;
      justify-content: flex-end;
      gap: var(--space-sm);
    }
    @media (max-width: 900px) {
      .runtime-banner,
      .placement-row,
      .audit-row {
        flex-direction: column;
        align-items: stretch;
      }
      .section-actions,
      .actions {
        justify-content: stretch;
      }
      .section-actions button,
      .actions button {
        width: 100%;
      }
    }
  `],
})
export class PerformanceSettingsComponent implements OnInit {
  private http = inject(HttpClient);
  private siloSettings = inject(SiloSettingsService);
  private snack = inject(MatSnackBar);
  private destroyRef = inject(DestroyRef);

  readonly batchSize = signal<number>(32);
  readonly concurrency = signal<number>(2);
  readonly batchMin = signal<number>(8);
  readonly batchMax = signal<number>(128);
  readonly concMin = signal<number>(1);
  readonly concMax = signal<number>(8);
  readonly saving = signal<boolean>(false);
  readonly runtimeLoading = signal<boolean>(true);
  readonly registering = signal<boolean>(false);
  readonly actionPending = signal<boolean>(false);
  readonly deletingPlacement = signal<boolean>(false);
  readonly runtimeSummary = signal<RuntimeSummaryPayload | null>(null);
  readonly helpers = signal<HelperNodeSettingsRecord[]>([]);

  registration: RuntimeRegistrationForm = {
    model_name: '',
    model_family: 'sentence-transformers',
    dimension: 1024,
    device_target: 'cpu',
    batch_size: 32,
    role: 'candidate',
    executor_type: 'primary',
    helper_id: null,
  };

  private initialBatch = 32;
  private initialConcurrency = 2;

  readonly dirtyConcurrency = computed(() => this.concurrency() !== this.initialConcurrency);

  ngOnInit(): void {
    this.loadRuntimeConfig();
    this.reloadRuntime();
  }

  private loadRuntimeConfig(): void {
    this.http.get<RuntimeConfig>('/api/settings/runtime-config/')
      .pipe(catchError(() => EMPTY), takeUntilDestroyed(this.destroyRef))
      .subscribe((cfg) => {
        if (!cfg) return;
        this.batchSize.set(cfg.embedding_batch_size);
        this.concurrency.set(cfg.celery_concurrency);
        this.initialBatch = cfg.embedding_batch_size;
        this.initialConcurrency = cfg.celery_concurrency;
        this.batchMin.set(cfg.embedding_batch_size_range[0]);
        this.batchMax.set(cfg.embedding_batch_size_range[1]);
        this.concMin.set(cfg.celery_concurrency_range[0]);
        this.concMax.set(cfg.celery_concurrency_range[1]);
      });
  }

  reloadRuntime(): void {
    this.runtimeLoading.set(true);
    this.siloSettings.getRuntimeSummary()
      .pipe(
        finalize(() => this.runtimeLoading.set(false)),
        catchError(() => {
          this.snack.open('Could not load runtime summary.', 'Dismiss', { duration: 4000 });
          return EMPTY;
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((runtime) => {
        this.runtimeSummary.set(runtime);
        const suggestedDevice = runtime.model_runtime.active_model?.device_target
          || (runtime.hardware.gpu_name ? 'cuda' : 'cpu');
        this.registration.device_target = suggestedDevice;
        this.registration.batch_size = runtime.recommended_profile.suggested_batch_size;
      });

    this.siloSettings.listHelpers()
      .pipe(catchError(() => EMPTY), takeUntilDestroyed(this.destroyRef))
      .subscribe((helpers) => this.helpers.set(helpers));
  }

  applyRecommendedProfile(): void {
    const runtime = this.runtimeSummary();
    if (!runtime) return;
    this.batchSize.set(runtime.recommended_profile.suggested_batch_size);
    this.concurrency.set(runtime.recommended_profile.suggested_concurrency);
    this.snack.open(
      `${runtime.recommended_profile.profile} profile applied to the draft controls below.`,
      'Dismiss',
      { duration: 3500 },
    );
  }

  registerModel(): void {
    if (!this.registration.model_name.trim()) {
      this.snack.open('Model name is required.', 'Dismiss', { duration: 3000 });
      return;
    }
    if (this.registration.executor_type === 'helper' && !this.registration.helper_id) {
      this.snack.open('Choose a helper node for helper placements.', 'Dismiss', { duration: 3000 });
      return;
    }

    this.registering.set(true);
    this.siloSettings.registerRuntimeModel({
      task_type: 'embedding',
      model_name: this.registration.model_name.trim(),
      model_family: this.registration.model_family.trim(),
      dimension: Number(this.registration.dimension),
      device_target: this.registration.device_target,
      batch_size: Number(this.registration.batch_size),
      role: this.registration.role,
      executor_type: this.registration.executor_type,
      helper_id: this.registration.executor_type === 'helper' ? this.registration.helper_id : null,
    })
      .pipe(
        finalize(() => this.registering.set(false)),
        catchError((error) => {
          this.snack.open(error?.error?.error || 'Could not register model.', 'Dismiss', { duration: 4000 });
          return EMPTY;
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => {
        this.registration.model_name = '';
        this.registration.helper_id = null;
        this.snack.open('Runtime model registered.', 'Dismiss', { duration: 3000 });
        this.reloadRuntime();
      });
  }

  runModelAction(model: RuntimeModelRegistryEntry, action: 'download' | 'warm' | 'pause' | 'resume' | 'promote' | 'rollback' | 'drain'): void {
    this.actionPending.set(true);
    this.siloSettings.runRuntimeModelAction(model.id, { action })
      .pipe(
        finalize(() => this.actionPending.set(false)),
        catchError((error) => {
          this.snack.open(error?.error?.error || `Could not ${action} ${model.model_name}.`, 'Dismiss', { duration: 4500 });
          return EMPTY;
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => {
        this.snack.open(`${action} queued for ${model.model_name}.`, 'Dismiss', { duration: 3000 });
        this.reloadRuntime();
      });
  }

  deletePlacement(placement: RuntimeModelPlacement): void {
    this.deletingPlacement.set(true);
    this.siloSettings.deleteRuntimePlacement(placement.id)
      .pipe(
        finalize(() => this.deletingPlacement.set(false)),
        catchError((error) => {
          this.snack.open(error?.error?.error || 'Could not delete that placement yet.', 'Dismiss', { duration: 4500 });
          return EMPTY;
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((result) => {
        const reclaimed = result?.reclaimed_disk_bytes ? this.humanBytes(result.reclaimed_disk_bytes) : 'disk space';
        this.snack.open(`Placement deleted. Reclaimed ${reclaimed}.`, 'Dismiss', { duration: 3500 });
        this.reloadRuntime();
      });
  }

  save(): void {
    this.saving.set(true);
    this.http.post<{ updated: Record<string, number>; errors?: unknown }>(
      '/api/settings/runtime-config/',
      {
        embedding_batch_size: this.batchSize(),
        celery_concurrency: this.concurrency(),
      },
    )
      .pipe(
        catchError(() => {
          this.saving.set(false);
          this.snack.open('Could not save. Try again.', 'OK', { duration: 4000 });
          return EMPTY;
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => {
        this.saving.set(false);
        this.initialBatch = this.batchSize();
        this.initialConcurrency = this.concurrency();
        this.snack.open('Performance settings saved.', 'OK', { duration: 2500 });
      });
  }

  reset(): void {
    this.batchSize.set(32);
    this.concurrency.set(2);
  }

  humanBytes(bytes: number | null | undefined): string {
    const value = Number(bytes || 0);
    if (!Number.isFinite(value) || value <= 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let size = value;
    let unitIndex = 0;
    while (size >= 1024 && unitIndex < units.length - 1) {
      size /= 1024;
      unitIndex += 1;
    }
    return `${size.toFixed(size >= 10 || unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
  }

  labelWithMb = (v: number): string => `${v}`;
}
