import { Component, DestroyRef, Input, Output, EventEmitter, ChangeDetectionStrategy, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
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
    label: $localize`@@performanceMode.safeLabelShort:Safe While I Work`,
    icon: 'shield',
    description: $localize`@@performanceMode.safeDescShort:Quietest. Keep working.`,
    tooltip: $localize`@@performanceMode.safeTooltip:Quietest mode. Uses about 25% of GPU memory so you can keep using your computer while the linker runs in the background.`,
  },
  {
    key: 'balanced',
    label: $localize`@@performanceMode.balancedLabelShort:Balanced`,
    icon: 'balance',
    description: $localize`@@performanceMode.balancedDescShort:Default. Good speed.`,
    tooltip: $localize`@@performanceMode.balancedTooltip:Default mode. Good speed without hogging your computer. Mostly runs on the CPU.`,
  },
  {
    key: 'high',
    label: $localize`@@performanceMode.highLabelShort:High Performance Now`,
    icon: 'speed',
    description: $localize`@@performanceMode.highDescShort:Fastest. Heavy GPU use.`,
    tooltip: $localize`@@performanceMode.highTooltip:Fastest mode. Uses up to 80% of GPU memory (~4.8 GB on your RTX 3050). Close Chrome tabs first or the browser may slow down.`,
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
        <mat-card-title i18n="@@performanceMode.title">Performance Mode</mat-card-title>
      </mat-card-header>
      <mat-card-content>
        <div class="mode-options">
          @for (opt of modes; track opt.key) {
            <button type="button"
                    class="mode-button"
                    [class.active]="currentMode === opt.key"
                    [class.pending]="pending() === opt.key"
                    [class.unavailable]="opt.key === 'high' && !highCapable()"
                    [disabled]="pending() !== null || (opt.key === 'high' && !highCapable())"
                    [matTooltip]="(opt.key === 'high' && !highCapable()) ? unavailableTooltip() : opt.tooltip"
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
          <div class="expiry-row" role="radiogroup" aria-label="Auto-revert timer" i18n-aria-label="@@performanceMode.autoRevertTimerLabel">
            <span class="expiry-label" i18n="@@performanceMode.autoRevertLabel">Auto-revert to Balanced:</span>
            <div class="expiry-chips">
              <button type="button"
                      class="expiry-chip"
                      role="radio"
                      [attr.aria-checked]="expiry() === 'none'"
                      [class.active]="expiry() === 'none'"
                      (click)="setExpiry('none')"
                      matTooltip="Stay in High Performance until you change it manually"
                      i18n-matTooltip="@@performanceMode.stayOnTooltip">
                <mat-icon class="expiry-icon">all_inclusive</mat-icon>
                <ng-container i18n="@@performanceMode.stayOn">Stay on</ng-container>
              </button>
              <button type="button"
                      class="expiry-chip"
                      role="radio"
                      [attr.aria-checked]="expiry() === 'activity'"
                      [class.active]="expiry() === 'activity'"
                      (click)="setExpiry('activity')"
                      matTooltip="Revert to Balanced the moment you start using keyboard or mouse again"
                      i18n-matTooltip="@@performanceMode.untilIComeBackTooltip">
                <mat-icon class="expiry-icon">directions_walk</mat-icon>
                <ng-container i18n="@@performanceMode.untilIComeBack">Until I come back</ng-container>
              </button>
              <button type="button"
                      class="expiry-chip"
                      role="radio"
                      [attr.aria-checked]="expiry() === 'night'"
                      [class.active]="expiry() === 'night'"
                      (click)="setExpiry('night')"
                      matTooltip="Revert to Balanced at 6:00 AM local time"
                      i18n-matTooltip="@@performanceMode.untilTonightEndsTooltip">
                <mat-icon class="expiry-icon">bedtime</mat-icon>
                <ng-container i18n="@@performanceMode.untilTonightEnds">Until tonight ends</ng-container>
              </button>
            </div>
            @if (expiry() !== 'none') {
              <span class="expiry-hint" i18n="@@performanceMode.expiryHint">
                <mat-icon class="expiry-hint-icon">info</mat-icon>
                Saved on the backend as a performance preference. Active workers finish their current safe boundary.
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
              <ng-container i18n="@@performanceMode.helpTitle">What do these mean?</ng-container>
            </mat-panel-title>
          </mat-expansion-panel-header>
          <dl class="glossary">
            <dt i18n="@@performanceMode.safeLabel">Safe While I Work</dt>
            <dd i18n="@@performanceMode.safeDesc">Uses about 25% of your graphics card memory. You can keep browsing and working while the linker runs quietly in the background.</dd>

            <dt i18n="@@performanceMode.balancedLabel">Balanced (default)</dt>
            <dd i18n="@@performanceMode.balancedDesc">Good speed without hogging your computer. Mostly uses the CPU; a smart choice most of the time.</dd>

            <dt i18n="@@performanceMode.highLabel">High Performance</dt>
            <dd i18n="@@performanceMode.highDesc">Goes full throttle. Uses up to 80% of your graphics card memory (around 4.8 GB on your RTX 3050). Close Chrome tabs before switching.</dd>

            <dt i18n="@@performanceMode.cpuVsGpuLabel">CPU vs GPU</dt>
            <dd i18n="@@performanceMode.cpuVsGpuDesc">The CPU (processor) is the general-purpose brain; the GPU (graphics card) is a specialist that is much faster at the kind of number-crunching the linker does. GPU mode is faster, but needs memory.</dd>

            <dt i18n="@@performanceMode.vramLabel">VRAM</dt>
            <dd i18n="@@performanceMode.vramDesc">The graphics card's own memory. Separate from your main RAM. Measured here in megabytes (MB).</dd>

            <dt i18n="@@performanceMode.batchSizeLabel">Batch size</dt>
            <dd i18n="@@performanceMode.batchSizeDesc">How many paragraphs the linker processes at the same time. Bigger batch = faster, but uses more memory. Adjustable in Settings → Performance.</dd>

            <dt i18n="@@performanceMode.gpuTempLabel">GPU temperature</dt>
            <dd i18n="@@performanceMode.gpuTempDesc">If your graphics card hits 86°C, the linker automatically pauses heavy work until it cools back down to 78°C. This protects the hardware.</dd>

            <dt i18n="@@performanceMode.workerLabel">Worker</dt>
            <dd i18n="@@performanceMode.workerDesc">A helper process that runs background jobs (imports, scoring, etc). More workers = more things in parallel, but also more memory used. Changes need a restart to apply.</dd>
          </dl>
        </mat-expansion-panel>
      </mat-accordion>

      <mat-card-actions align="end" class="card-actions dashboard-action-row">
        <button mat-stroked-button
                type="button"
                [disabled]="pending() !== null || bootArmed() || currentMode === 'safe'"
                matTooltip="Sets the next backend restart to force Safe mode. Use only if the app is misbehaving."
                i18n-matTooltip="@@performanceMode.safeBootTooltip"
                (click)="armSafeModeBoot()">
          <mat-icon>lifebuoy</mat-icon>
          {{ safeBootLabel() }}
        </button>
        <button mat-stroked-button
                type="button"
                [disabled]="pending() !== null || currentMode === 'balanced'"
                matTooltip="One-click escape. Returns to the default mode."
                i18n-matTooltip="@@performanceMode.resetToBalancedTooltip"
                (click)="selectMode('balanced')">
          <mat-icon>restart_alt</mat-icon>
          <ng-container i18n="@@performanceMode.resetToBalanced">Reset to Balanced</ng-container>
        </button>
      </mat-card-actions>
    </mat-card>
  `,
  styles: [`
    mat-card { padding: var(--spacing-card); }
    mat-card-header { margin-bottom: var(--space-md); }
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
    /* Hardware-incapable state — distinct from generic disabled so the
       user can tell "you can't pick this on this machine" apart from
       "another switch is in flight". Strikethrough on the label
       communicates "permanently unavailable" at a glance. */
    .mode-button.unavailable {
      opacity: 0.45;
      border-style: dashed;
    }
    .mode-button.unavailable .mode-label { text-decoration: line-through; }
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
      margin-top: var(--space-lg);
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
  // Phase E2 / Gap 41 — cancel in-flight HTTP on destroy.
  private destroyRef = inject(DestroyRef);

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

  /**
   * Hardware-capability gate (added 2026-05-09 per AutoIssue #16). The
   * backend's `_runtime_settings_snapshot()` reports whether the host
   * has a CUDA-capable GPU with ≥4 GB VRAM. When false, the "High
   * Performance" button renders disabled with a tooltip explaining why
   * — instead of letting the user pick High and silently fall back to
   * CPU at runtime (the prior UX bug).
   */
  readonly highCapable = this.perfMode.highPerformanceCapable;
  readonly hardwareTier = this.perfMode.hardwareTier;
  readonly hardwareSummary = this.perfMode.hardwareSummary;
  readonly unavailableTooltip = () => {
    const summary = this.hardwareSummary();
    const tier = this.hardwareTier();
    if (summary) {
      return $localize`@@performanceMode.unavailableTooltipSummary:High Performance is unavailable on this hardware (${summary}:summary:). Needs a CUDA GPU with at least 4 GB of VRAM.`;
    }
    return $localize`@@performanceMode.unavailableTooltipTier:High Performance is unavailable on this hardware (tier=${tier}:tier:). Needs a CUDA GPU with at least 4 GB of VRAM.`;
  };

  readonly safeBootLabel = () => {
    return this.bootArmed()
      ? $localize`@@performanceMode.safeBootArmed:Safe Boot Armed`
      : $localize`@@performanceMode.safeBootOnRestart:Safe Boot on Restart`;
  };

  ngOnInit(): void {
    this.http.get<{ armed: boolean }>('/api/system/safe-mode-boot/')
      .pipe(catchError(() => EMPTY), takeUntilDestroyed(this.destroyRef))
      .subscribe((r) => this.bootArmed.set(!!r?.armed));

    // Hydrate mode + expiry from the backend so the chip state is consistent
    // across tabs.
    this.perfMode.refresh()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe();
  }

  setExpiry(next: PerformanceExpiry): void {
    // For 'night' we pass the next 6 AM local timestamp so the backend knows
    // exactly when to trip the revert. 'activity' just persists the intent.
    const expiresAt = next === 'night' ? this.next6AmLocalIso() : '';
    this.perfMode.setExpiry(next, expiresAt).pipe(
      catchError(() => {
        this.snack.open($localize`@@performanceMode.saveExpiryError:Could not save revert timer. Try again.`, $localize`@@common.ok:OK`, { duration: 4000 });
        return EMPTY;
      }),
      takeUntilDestroyed(this.destroyRef),
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
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => {
        this.bootArmed.set(true);
        this.snack.open(
          $localize`@@performanceMode.safeBootArmedMsg:Safe Boot armed. The next backend restart will force Safe mode.`,
          $localize`@@common.ok:OK`,
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
      ref.afterClosed()
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe((confirmed) => {
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
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => {
        this.pending.set(null);
        this.currentMode = key;
        this.modeChange.emit(key);
        if (opt) {
          const label = opt.label;
          this.snack.open($localize`@@performanceMode.switchedTo:Switched to ${label}:label:`, $localize`@@common.ok:OK`, { duration: 2500 });
        }
      });
  }
}

@Component({
  selector: 'app-confirm-high-performance-dialog',
  standalone: true,
  imports: [MatButtonModule, MatDialogModule, MatIconModule],
  template: `
    <h2 mat-dialog-title i18n="@@confirmHighPerformance.title">
      <mat-icon class="warn-icon">warning_amber</mat-icon>
      Switch to High Performance?
    </h2>
    <mat-dialog-content>
      <p i18n="@@confirmHighPerformance.memoryWarning">
        This mode uses up to <strong>80% of GPU memory</strong> (about 4.8 GB on your RTX 3050).
      </p>
      <p i18n="@@confirmHighPerformance.performanceWarning">
        If your browser or other apps need the GPU at the same time, they may slow down or stutter.
        It is best to close most Chrome tabs before switching.
      </p>
      <p i18n="@@confirmHighPerformance.continuePrompt">Continue?</p>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button type="button" [mat-dialog-close]="false" i18n="@@common.cancel">Cancel</button>
      <button mat-raised-button color="primary" type="button" [mat-dialog-close]="true" i18n="@@confirmHighPerformance.yesSwitch">
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
