import { Component, Input, Output, EventEmitter, ChangeDetectionStrategy, OnInit, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { PerformanceModeService, PerformanceExpiry } from '../../core/services/performance-mode.service';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatChipsModule } from '@angular/material/chips';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatExpansionModule } from '@angular/material/expansion';
import { catchError, EMPTY } from 'rxjs';

interface PerformanceOption {
  key: string;
  label: string;
  icon: string;
  description: string;
  tooltip: string;
}

const MODES: PerformanceOption[] = [
  {
    key: 'safe',
    label: 'Safe While I Work',
    icon: 'shield',
    description: 'Quietest. Keep working.',
    tooltip: 'Quietest mode. Uses about 25% of GPU memory so you can keep using your computer while the linker runs in the background.',
  },
  {
    key: 'balanced',
    label: 'Balanced',
    icon: 'balance',
    description: 'Default. Good speed.',
    tooltip: 'Default mode. Good speed without hogging your computer. Mostly runs on the CPU.',
  },
  {
    key: 'high',
    label: 'High Performance Now',
    icon: 'speed',
    description: 'Fastest. Heavy GPU use.',
    tooltip: 'Fastest mode. Uses up to 60% of GPU memory (~3.6 GB on your RTX 3050). Close Chrome tabs first or the browser may slow down.',
  },
];

@Component({
  selector: 'app-performance-mode',
  standalone: true,
  imports: [
    MatButtonModule,
    MatCardModule,
    MatIconModule,
    MatChipsModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    MatTooltipModule,
    MatDialogModule,
    MatExpansionModule,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <mat-card id="performance-mode">
      <mat-card-header>
        <mat-icon mat-card-avatar>speed</mat-icon>
        <mat-card-title>Performance Mode</mat-card-title>
      </mat-card-header>
      <mat-card-content>
        <div class="mode-options">
          @for (opt of modes; track opt.key) {
            <button type="button"
                    class="mode-button"
                    [class.active]="currentMode === opt.key"
                    [class.pending]="pending() === opt.key"
                    [disabled]="pending() !== null"
                    [matTooltip]="opt.tooltip"
                    matTooltipPosition="right"
                    matTooltipShowDelay="250"
                    (click)="selectMode(opt.key)">
              @if (pending() === opt.key) {
                <mat-progress-spinner diameter="20" mode="indeterminate"></mat-progress-spinner>
              } @else {
                <mat-icon>{{ opt.icon }}</mat-icon>
              }
              <span class="mode-label">{{ opt.label }}</span>
              <span class="mode-desc">{{ opt.description }}</span>
            </button>
          }
        </div>

        <!-- Time-bound auto-revert chips — shown only for High Performance mode -->
        @if (currentMode === 'high') {
          <div class="expiry-row" role="radiogroup" aria-label="Auto-revert timer">
            <span class="expiry-label">Auto-revert to Balanced:</span>
            <div class="expiry-chips">
              <button type="button"
                      class="expiry-chip"
                      role="radio"
                      [attr.aria-checked]="expiry() === 'none'"
                      [class.active]="expiry() === 'none'"
                      (click)="setExpiry('none')"
                      matTooltip="Stay in High Performance until you change it manually">
                <mat-icon class="expiry-icon">all_inclusive</mat-icon>
                Stay on
              </button>
              <button type="button"
                      class="expiry-chip"
                      role="radio"
                      [attr.aria-checked]="expiry() === 'activity'"
                      [class.active]="expiry() === 'activity'"
                      (click)="setExpiry('activity')"
                      matTooltip="Revert to Balanced the moment you start using keyboard or mouse again">
                <mat-icon class="expiry-icon">directions_walk</mat-icon>
                Until I come back
              </button>
              <button type="button"
                      class="expiry-chip"
                      role="radio"
                      [attr.aria-checked]="expiry() === 'night'"
                      [class.active]="expiry() === 'night'"
                      (click)="setExpiry('night')"
                      matTooltip="Revert to Balanced at 6:00 AM local time">
                <mat-icon class="expiry-icon">bedtime</mat-icon>
                Until tonight ends
              </button>
            </div>
            @if (expiry() !== 'none') {
              <span class="expiry-hint">
                <mat-icon class="expiry-hint-icon">info</mat-icon>
                Backend enforcement ships with the scheduler update. For now this preference is saved locally.
              </span>
            }
          </div>
        }
      </mat-card-content>
      <mat-accordion class="help-accordion">
        <mat-expansion-panel class="help-panel">
          <mat-expansion-panel-header>
            <mat-panel-title>
              <mat-icon class="help-icon">help_outline</mat-icon>
              What do these mean?
            </mat-panel-title>
          </mat-expansion-panel-header>
          <dl class="glossary">
            <dt>Safe While I Work</dt>
            <dd>Uses about 25% of your graphics card memory. You can keep browsing and working while the linker runs quietly in the background.</dd>

            <dt>Balanced (default)</dt>
            <dd>Good speed without hogging your computer. Mostly uses the CPU; a smart choice most of the time.</dd>

            <dt>High Performance</dt>
            <dd>Goes full throttle. Uses up to 60% of your graphics card memory (around 3.6 GB on your RTX 3050). Close Chrome tabs before switching.</dd>

            <dt>CPU vs GPU</dt>
            <dd>The CPU (processor) is the general-purpose brain; the GPU (graphics card) is a specialist that is much faster at the kind of number-crunching the linker does. GPU mode is faster, but needs memory.</dd>

            <dt>VRAM</dt>
            <dd>The graphics card's own memory. Separate from your main RAM. Measured here in megabytes (MB).</dd>

            <dt>Batch size</dt>
            <dd>How many paragraphs the linker processes at the same time. Bigger batch = faster, but uses more memory. Adjustable in Settings → Performance.</dd>

            <dt>GPU temperature</dt>
            <dd>If your graphics card hits 76°C, the linker automatically pauses heavy work until it cools back down to 68°C. This protects the hardware.</dd>

            <dt>Worker</dt>
            <dd>A helper process that runs background jobs (imports, scoring, etc). More workers = more things in parallel, but also more memory used. Changes need a restart to apply.</dd>
          </dl>
        </mat-expansion-panel>
      </mat-accordion>

      <mat-card-actions align="end" class="card-actions dashboard-action-row">
        <button mat-stroked-button
                type="button"
                [disabled]="pending() !== null || bootArmed() || currentMode === 'safe'"
                matTooltip="Sets the next backend restart to force Safe mode. Use only if the app is misbehaving."
                (click)="armSafeModeBoot()">
          <mat-icon>lifebuoy</mat-icon>
          {{ bootArmed() ? 'Safe Boot Armed' : 'Safe Boot on Restart' }}
        </button>
        <button mat-stroked-button
                type="button"
                [disabled]="pending() !== null || currentMode === 'balanced'"
                matTooltip="One-click escape. Returns to the default mode."
                (click)="selectMode('balanced')">
          <mat-icon>restart_alt</mat-icon>
          Reset to Balanced
        </button>
      </mat-card-actions>
    </mat-card>
  `,
  styles: [`
    mat-card { padding: var(--spacing-card); }
    mat-card-header { margin-bottom: var(--space-md); }
    mat-card-actions { padding: var(--space-md) 0 0 0; }
    .mode-options { display: flex; gap: var(--space-sm); flex-wrap: wrap; }
    .mode-button {
      flex: 1; min-width: 120px;
      display: flex; flex-direction: column; align-items: center;
      gap: var(--space-xs);
      padding: var(--space-md);
      border: 1px solid var(--color-border);
      border-radius: var(--radius-md);
      background: var(--color-bg-white);
      cursor: pointer;
      transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .mode-button:hover:not(:disabled) {
      border-color: var(--color-primary);
      box-shadow: var(--shadow-hover);
    }
    .mode-button.active {
      border-color: var(--color-primary);
      background: var(--color-blue-50);
    }
    .mode-button:disabled {
      cursor: not-allowed;
      opacity: 0.6;
    }
    .mode-button.pending {
      opacity: 1;
    }
    .mode-button.active mat-icon { color: var(--color-primary); }
    .mode-button mat-icon { color: var(--color-text-muted); }
    .mode-label { font-size: 13px; font-weight: 500; color: var(--color-text-primary); }
    .mode-desc { font-size: 11px; color: var(--color-text-muted); text-align: center; }
    .help-accordion { margin-top: var(--space-md); box-shadow: none; }
    .help-panel {
      box-shadow: none !important;
      border: var(--card-border);
      border-radius: var(--radius-md, 8px) !important;
    }
    .help-icon { font-size: 16px; width: 16px; height: 16px; margin-right: var(--space-xs); color: var(--color-primary); }
    .glossary {
      margin: 0;
      padding: 0;
      font-size: 12px;
      color: var(--color-text-secondary);
    }
    .glossary dt {
      font-weight: 600;
      color: var(--color-text-primary);
      margin-top: var(--space-sm);
    }
    .glossary dt:first-child { margin-top: 0; }
    .glossary dd {
      margin: 2px 0 0 0;
      line-height: 1.5;
    }
    .card-actions {
      padding: var(--space-md) 0 0 0;
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-xs);
      justify-content: flex-end;
    }
    /* Time-bound auto-revert chip row — shown only for High Performance mode. */
    .expiry-row {
      display: flex;
      flex-direction: column;
      gap: var(--space-sm);
      margin-top: var(--space-md);
      padding-top: var(--space-md);
      border-top: var(--card-border);
    }
    .expiry-label {
      font-size: 12px;
      font-weight: 500;
      color: var(--color-text-secondary);
    }
    .expiry-chips {
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-sm);
    }
    .expiry-chip {
      display: inline-flex;
      align-items: center;
      gap: var(--space-xs);
      height: 32px;
      padding: 0 12px;
      border: 1px solid var(--color-border);
      border-radius: var(--radius-pill);
      background: var(--color-bg-white);
      color: var(--color-text-secondary);
      font-family: inherit;
      font-size: 12px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .expiry-chip:hover {
      border-color: var(--color-primary);
      color: var(--color-primary);
    }
    .expiry-chip.active {
      background: var(--color-blue-50);
      border-color: var(--color-primary);
      color: var(--color-primary);
    }
    .expiry-chip.active .expiry-icon {
      color: var(--color-primary);
    }
    .expiry-icon {
      font-size: 16px;
      width: 16px;
      height: 16px;
      color: var(--color-text-muted);
    }
    .expiry-hint {
      display: inline-flex;
      align-items: flex-start;
      gap: var(--space-xs);
      padding: var(--space-xs) var(--space-sm);
      background: var(--color-blue-50);
      border-radius: var(--radius-sm);
      font-size: 11px;
      color: var(--color-text-secondary);
      line-height: 1.4;
    }
    .expiry-hint-icon {
      font-size: 14px;
      width: 14px;
      height: 14px;
      color: var(--color-primary);
      margin-top: 2px;
      flex-shrink: 0;
    }
  `],
})
export class PerformanceModeComponent implements OnInit {
  private http = inject(HttpClient);
  private snack = inject(MatSnackBar);
  private dialog = inject(MatDialog);
  private perfMode = inject(PerformanceModeService);

  @Input() currentMode = 'balanced';
  @Output() modeChange = new EventEmitter<string>();

  readonly modes = MODES;
  readonly pending = signal<string | null>(null);
  readonly bootArmed = signal<boolean>(false);

  /**
   * Auto-revert expiry for High Performance mode. Sourced from the backend via
   * PerformanceModeService so the selection is shared across tabs and survives
   * restarts. Backend enforcement is plan items 12-14 (auto_revert_performance_mode).
   */
  readonly expiry = this.perfMode.expiry;

  ngOnInit(): void {
    this.http.get<{ armed: boolean }>('/api/system/safe-mode-boot/')
      .pipe(catchError(() => EMPTY))
      .subscribe((r) => this.bootArmed.set(!!r?.armed));

    // Hydrate mode + expiry from the backend so the chip state is consistent
    // across tabs.
    this.perfMode.refresh().subscribe();
  }

  setExpiry(next: PerformanceExpiry): void {
    // For 'night' we pass the next 6 AM local timestamp so the backend knows
    // exactly when to trip the revert. 'activity' just persists the intent.
    const expiresAt = next === 'night' ? this.next6AmLocalIso() : '';
    this.perfMode.setExpiry(next, expiresAt).pipe(
      catchError(() => {
        this.snack.open('Could not save revert timer. Try again.', 'OK', { duration: 4000 });
        return EMPTY;
      }),
    ).subscribe();
  }

  /** Returns the next 6:00 AM local time as an ISO 8601 string. */
  private next6AmLocalIso(): string {
    const d = new Date();
    const target = new Date(d);
    target.setHours(6, 0, 0, 0);
    if (target.getTime() <= d.getTime()) {
      target.setDate(target.getDate() + 1);
    }
    return target.toISOString();
  }

  armSafeModeBoot(): void {
    this.http.post<{ armed: boolean }>('/api/system/safe-mode-boot/', {})
      .pipe(
        catchError(() => {
          this.snack.open('Could not arm safe-mode boot. Try again.', 'OK', { duration: 4000 });
          return EMPTY;
        }),
      )
      .subscribe(() => {
        this.bootArmed.set(true);
        this.snack.open(
          'Safe Boot armed. The next backend restart will force Safe mode.',
          'OK',
          { duration: 4000 },
        );
      });
  }

  selectMode(key: string): void {
    if (key === this.currentMode || this.pending() !== null) return;

    if (key === 'high') {
      const ref = this.dialog.open(ConfirmHighPerformanceDialogComponent, {
        width: '480px',
        autoFocus: false,
      });
      ref.afterClosed().subscribe((confirmed) => {
        if (confirmed) {
          this.applyMode(key);
        }
      });
      return;
    }

    this.applyMode(key);
  }

  private applyMode(key: string): void {
    const opt = this.modes.find((m) => m.key === key);
    this.pending.set(key);
    this.http.post<void>('/api/settings/runtime/switch/', { mode: key })
      .pipe(
        catchError(() => {
          this.pending.set(null);
          this.snack.open('Could not switch mode. Try again.', 'OK', { duration: 4000 });
          return EMPTY;
        }),
      )
      .subscribe(() => {
        this.pending.set(null);
        this.currentMode = key;
        this.modeChange.emit(key);
        if (opt) {
          this.snack.open(`Switched to ${opt.label}`, 'OK', { duration: 2500 });
        }
      });
  }
}

@Component({
  selector: 'app-confirm-high-performance-dialog',
  standalone: true,
  imports: [MatButtonModule, MatDialogModule, MatIconModule],
  template: `
    <h2 mat-dialog-title>
      <mat-icon class="warn-icon">warning_amber</mat-icon>
      Switch to High Performance?
    </h2>
    <mat-dialog-content>
      <p>
        This mode uses up to <strong>60% of GPU memory</strong> (about 3.6 GB on your RTX 3050).
      </p>
      <p>
        If your browser or other apps need the GPU at the same time, they may slow down or stutter.
        It is best to close most Chrome tabs before switching.
      </p>
      <p>Continue?</p>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button type="button" [mat-dialog-close]="false">Cancel</button>
      <button mat-raised-button color="primary" type="button" [mat-dialog-close]="true">
        Yes, switch
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    .warn-icon {
      color: var(--color-warning, #f9ab00);
      vertical-align: middle;
      margin-right: var(--space-xs, 4px);
    }
    mat-dialog-content p { margin: 0 0 var(--space-sm, 8px) 0; }
  `],
})
export class ConfirmHighPerformanceDialogComponent {}
