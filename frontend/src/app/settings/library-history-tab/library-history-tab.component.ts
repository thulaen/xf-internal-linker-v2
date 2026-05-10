/**
 * LibraryHistoryTabComponent — Settings tab 4 (Library & History).
 *
 * Extracted from the legacy 4,583-line `SettingsComponent` (AutoIssue #32,
 * slice 3 of the prevention-cleanup tabs split). Mechanical move; behaviour
 * identical.
 *
 * The weight presets, weight history, and ranking challengers cards live
 * here. The parent component (`SettingsComponent`) keeps its own copies of
 * `weightPresets`, `weightHistory`, and `currentWeights` because cross-tab
 * tooltip rendering (`recommendedValueLabel`, `getFeatureSummary`,
 * `currentFeatureCount`, `currentOffFeatures`) and the fresh-install
 * auto-apply guard (`checkAndAutoApplyRecommended`) all read those fields
 * from the parent. This child duplicates that state internally for the
 * tab UI and owns its own load + save flow — same pattern Silo Architecture
 * tab uses.
 *
 * Two outputs let the parent stay in sync without re-rendering the cards:
 *   - `(dirtyChanged)` — same convention as Notifications + Silo tabs;
 *     keeps the existing `HasUnsavedChanges` guard firing.
 *   - `(presetApplied)` — fires on a successful `applyPreset(...)` or
 *     `rollbackWeights(...)`. The parent listens and runs its giant
 *     forkJoin reload of the 25+ settings endpoints, so values like
 *     `weightedAuthority.ranking_weight` re-hydrate from the server-of-
 *     truth post-apply. Payload is the preset name (or `null` for
 *     rollback) — kept simple because the parent's reload doesn't need
 *     to discriminate.
 */
import { ChangeDetectionStrategy, ChangeDetectorRef, Component, EventEmitter, Input, OnDestroy, OnInit, Output, inject, signal } from '@angular/core';
import { CommonModule, DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Subject, forkJoin } from 'rxjs';
import { takeUntil } from 'rxjs/operators';

import {
  RankingChallenger,
  SiloSettingsService,
  WeightAdjustmentHistory,
  WeightPreset,
} from '../silo-settings.service';

@Component({
  selector: 'app-library-history-tab',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    DatePipe,
    FormsModule,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    MatTooltipModule,
  ],
  templateUrl: './library-history-tab.component.html',
  styleUrls: ['./library-history-tab.component.scss'],
})
export class LibraryHistoryTabComponent implements OnInit, OnDestroy {
  private siloSvc = inject(SiloSettingsService);
  private snack = inject(MatSnackBar);
  private cdr = inject(ChangeDetectorRef);
  private destroy$ = new Subject<void>();

  /** Parent toggles its `isDirty` flag on `true`; resets on `false`. */
  @Output() dirtyChanged = new EventEmitter<boolean>();

  /**
   * Fires after a successful `applyPreset(...)` or `rollbackWeights(...)`.
   * Parent listens to trigger its forkJoin reload of the 25+ settings
   * endpoints so all weight cards re-hydrate from the server.
   * Payload is the preset name (or `null` for rollback) — informational
   * only; the parent's reload path is identical in both cases.
   */
  @Output() presetApplied = new EventEmitter<string | null>();

  /**
   * Parent's `isDirty` mirrored in for the apply-preset two-stage
   * confirmation. Keeps the original guard ("you have unsaved edits…
   * continue?") working after extraction. Parent passes its `isDirty`
   * flag in via `[parentIsDirty]` on every change-detection cycle.
   */
  @Input() parentIsDirty = false;

  readonly weightPresets = signal<WeightPreset[]>([]);
  readonly weightHistory = signal<WeightAdjustmentHistory[]>([]);
  readonly challengers = signal<RankingChallenger[]>([]);
  readonly currentWeights = signal<Record<string, string>>({});

  readonly loadingPresets = signal(false);
  readonly loadingHistory = signal(false);
  readonly loadingChallengers = signal(false);
  readonly applyingPreset = signal(false);
  readonly savingPreset = signal(false);
  readonly deletingPreset = signal(false);
  readonly rollingBack = signal(false);
  readonly triggeringWeightTune = signal(false);
  readonly evaluatingChallenger = signal(false);

  newPresetName = '';
  showSavePresetInput = false;

  ngOnInit(): void {
    this.reloadPresetsAndHistory();
    this.loadChallengers();
    this.refreshCurrentWeights();
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  // ── Derived ───────────────────────────────────────────────────────

  get recommendedPreset(): WeightPreset | null {
    return this.weightPresets().find(
      (preset) => preset.is_system && preset.name.toLowerCase().includes('recommended'),
    ) ?? null;
  }

  get matchedPreset(): WeightPreset | null {
    return this.weightPresets().find((preset) => this.presetMatchesCurrent(preset)) ?? null;
  }

  get pendingChallenger(): RankingChallenger | null {
    return this.challengers().find((c) => c.status === 'pending') ?? null;
  }

  // ── Load ──────────────────────────────────────────────────────────

  /**
   * Same forkJoin pattern as the original parent: presets + history must
   * settle together because the auto-apply guard reads both in lockstep.
   * Keeps the duplicate state in sync with the parent's own copies.
   */
  reloadPresetsAndHistory(): void {
    this.loadingPresets.set(true);
    this.loadingHistory.set(true);
    forkJoin({
      presets: this.siloSvc.listWeightPresets(),
      history: this.siloSvc.listWeightHistory(),
    }).pipe(takeUntil(this.destroy$)).subscribe({
      next: ({ presets, history }) => {
        this.weightPresets.set(presets);
        this.weightHistory.set(history);
        this.loadingPresets.set(false);
        this.loadingHistory.set(false);
        this.cdr.markForCheck();
      },
      error: () => {
        this.loadingPresets.set(false);
        this.loadingHistory.set(false);
        this.cdr.markForCheck();
      },
    });
  }

  loadChallengers(): void {
    this.loadingChallengers.set(true);
    this.siloSvc.listChallengers().pipe(takeUntil(this.destroy$)).subscribe({
      next: (challengers) => {
        this.challengers.set(challengers);
        this.loadingChallengers.set(false);
        this.cdr.markForCheck();
      },
      error: () => {
        this.loadingChallengers.set(false);
        this.cdr.markForCheck();
      },
    });
  }

  private refreshCurrentWeights(): void {
    this.siloSvc.getCurrentWeights().pipe(takeUntil(this.destroy$)).subscribe({
      next: (weights) => {
        this.currentWeights.set(weights);
        this.cdr.markForCheck();
      },
      error: (err) => console.warn('refreshCurrentWeights failed', err),
    });
  }

  /** Bound to every form-field `(ngModelChange)` so dirty signals propagate. */
  markDirty(): void {
    this.dirtyChanged.emit(true);
  }

  // ── Presets ───────────────────────────────────────────────────────

  /**
   * Two-stage confirmation when the user has unsaved edits on any
   * settings card. Without this, the parent's reload (triggered by the
   * `presetApplied` Output) would silently overwrite in-flight edits with
   * the post-apply server response — the AutoIssue #15 bug. The first
   * prompt is the historical "are you sure?"; the second is the
   * unsaved-changes warning.
   */
  applyPreset(preset: WeightPreset): void {
    if (!confirm(`Apply preset "${preset.name}"? This will overwrite all current weight settings.`)) return;
    if (this.parentIsDirty && !confirm(
      'You have unsaved edits on this page. Applying the preset will discard them and reload the saved values from the server. Continue?',
    )) return;
    this.applyingPreset.set(true);
    this.siloSvc.applyWeightPreset(preset.id).pipe(takeUntil(this.destroy$)).subscribe({
      next: () => {
        this.applyingPreset.set(false);
        this.snack.open(`Preset "${preset.name}" applied. Reloading settings...`, undefined, { duration: 3000 });
        // Apply path always reloads from server-of-truth post-apply; any
        // in-flight dirty bit is now stale.
        this.dirtyChanged.emit(false);
        this.presetApplied.emit(preset.name);
        // Refresh our own local copy too so the next preset-match check
        // reflects the new server state.
        this.refreshCurrentWeights();
        this.reloadPresetsAndHistory();
        this.cdr.markForCheck();
      },
      error: (err) => {
        this.applyingPreset.set(false);
        this.snack.open(err?.error?.detail || 'Failed to apply preset', 'Dismiss', { duration: 4000 });
        this.cdr.markForCheck();
      },
    });
  }

  saveCurrentAsPreset(): void {
    const name = this.newPresetName.trim();
    if (!name) return;
    this.savingPreset.set(true);
    this.siloSvc.getCurrentWeights().pipe(takeUntil(this.destroy$)).subscribe({
      next: (weights) => {
        this.siloSvc.createWeightPreset({ name, weights }).pipe(takeUntil(this.destroy$)).subscribe({
          next: () => {
            this.savingPreset.set(false);
            this.newPresetName = '';
            this.showSavePresetInput = false;
            this.snack.open(`Preset "${name}" saved.`, undefined, { duration: 2500 });
            this.reloadPresetsAndHistory();
            this.cdr.markForCheck();
          },
          error: (err) => {
            this.savingPreset.set(false);
            this.snack.open(err?.error?.detail || err?.error?.name?.[0] || 'Failed to save preset', 'Dismiss', { duration: 4000 });
            this.cdr.markForCheck();
          },
        });
      },
      error: () => {
        this.savingPreset.set(false);
        this.snack.open('Failed to read current weights', 'Dismiss', { duration: 4000 });
        this.cdr.markForCheck();
      },
    });
  }

  deletePreset(preset: WeightPreset): void {
    if (!confirm(`Delete preset "${preset.name}"? This cannot be undone.`)) return;
    this.deletingPreset.set(true);
    this.siloSvc.deleteWeightPreset(preset.id).pipe(takeUntil(this.destroy$)).subscribe({
      next: () => {
        this.deletingPreset.set(false);
        this.snack.open(`Preset "${preset.name}" deleted.`, undefined, { duration: 2500 });
        this.reloadPresetsAndHistory();
        this.cdr.markForCheck();
      },
      error: (err) => {
        this.deletingPreset.set(false);
        this.snack.open(err?.error?.detail || 'Failed to delete preset', 'Dismiss', { duration: 4000 });
        this.cdr.markForCheck();
      },
    });
  }

  // ── History ───────────────────────────────────────────────────────

  rollbackWeights(row: WeightAdjustmentHistory): void {
    const dateStr = new Date(row.created_at).toLocaleString();
    if (!confirm(`Roll back to weights from ${dateStr}? This will overwrite all current weight settings.`)) return;
    this.rollingBack.set(true);
    this.siloSvc.rollbackWeights(row.id).pipe(takeUntil(this.destroy$)).subscribe({
      next: () => {
        this.rollingBack.set(false);
        this.snack.open(`Rolled back to weights from ${dateStr}. Reloading...`, undefined, { duration: 3000 });
        // Rollback is conceptually identical to applying a preset for the
        // parent's reload path — same Output trigger, same forkJoin reload.
        this.dirtyChanged.emit(false);
        this.presetApplied.emit(null);
        this.refreshCurrentWeights();
        this.reloadPresetsAndHistory();
        this.cdr.markForCheck();
      },
      error: (err) => {
        this.rollingBack.set(false);
        this.snack.open(err?.error?.detail || 'Rollback failed', 'Dismiss', { duration: 4000 });
        this.cdr.markForCheck();
      },
    });
  }

  historySourceLabel(source: string): string {
    return {
      auto_tune: 'Auto-tune',
      manual: 'Manual',
      preset_applied: 'Preset applied',
      r_auto: 'Legacy R tune',
      cs_auto_tune: 'Auto-tuner (Python L-BFGS)',
    }[source] ?? source;
  }

  deltaKeys(delta: Record<string, unknown> | null | undefined): string[] {
    return delta ? Object.keys(delta) : [];
  }

  formatDeltaLine(key: string, entry: { previous: string | null; new: string | null }): string {
    return `${key}: ${entry.previous ?? '-'} -> ${entry.new ?? '-'}`;
  }

  // ── Challengers ───────────────────────────────────────────────────

  triggerWeightTune(): void {
    if (!confirm('Run the auto-tune now? This will analyse recent data and may propose new weights.')) return;
    this.triggeringWeightTune.set(true);
    this.siloSvc.triggerWeightTune().pipe(takeUntil(this.destroy$)).subscribe({
      next: () => {
        this.triggeringWeightTune.set(false);
        this.snack.open('Weight-tune task queued. Check back in a moment.', undefined, { duration: 3000 });
        setTimeout(() => this.loadChallengers(), 5000);
        this.cdr.markForCheck();
      },
      error: (err) => {
        this.triggeringWeightTune.set(false);
        this.snack.open(err?.error?.detail || 'Failed to queue the tune task.', 'Dismiss', { duration: 4000 });
        this.cdr.markForCheck();
      },
    });
  }

  promoteChallenger(challenger: RankingChallenger): void {
    if (!confirm('Promote this challenger? Its weights will become active immediately.')) return;
    this.evaluatingChallenger.set(true);
    this.siloSvc.evaluateChallenger(challenger.run_id).pipe(takeUntil(this.destroy$)).subscribe({
      next: () => {
        this.evaluatingChallenger.set(false);
        this.snack.open('Challenger evaluation queued. Reload the page to see the new weights.', undefined, { duration: 4000 });
        this.loadChallengers();
        this.cdr.markForCheck();
      },
      error: () => {
        this.evaluatingChallenger.set(false);
        this.snack.open('Failed to queue challenger evaluation.', 'Dismiss', { duration: 4000 });
        this.cdr.markForCheck();
      },
    });
  }

  rejectChallenger(challenger: RankingChallenger): void {
    if (!confirm('Reject this challenger? It will not be applied.')) return;
    this.siloSvc.rejectChallenger(challenger.id).pipe(takeUntil(this.destroy$)).subscribe({
      next: () => {
        this.snack.open('Challenger rejected.', undefined, { duration: 2500 });
        this.loadChallengers();
        this.cdr.markForCheck();
      },
      error: () => this.snack.open('Failed to reject challenger.', 'Dismiss', { duration: 4000 }),
    });
  }

  challengerImprovementPct(c: RankingChallenger): string {
    if (c.predicted_quality_score == null || c.champion_quality_score == null || c.champion_quality_score === 0) return '';
    const pct = ((c.predicted_quality_score - c.champion_quality_score) / c.champion_quality_score) * 100;
    return (pct >= 0 ? '+' : '') + pct.toFixed(1) + '%';
  }

  challengerDiffKeys(c: RankingChallenger): string[] {
    return Object.keys(c.candidate_weights ?? {});
  }

  // ── Preset matching helpers ───────────────────────────────────────

  private presetMatchesCurrent(preset: WeightPreset): boolean {
    const presetEntries = Object.entries(preset.weights ?? {});
    if (!presetEntries.length) return false;
    const current = this.currentWeights();
    return presetEntries.every(
      ([key, value]) => this.normalizeComparableValue(current[key]) === this.normalizeComparableValue(value),
    );
  }

  /**
   * Coerce values to a stable string representation for equality so
   * "0.10" and "0.1" don't appear different. Mirrors the helper that
   * still lives on the parent (used by `recommendedValueLabel` etc) —
   * exact byte-for-byte copy so cross-tab matching stays consistent.
   */
  private normalizeComparableValue(value: unknown): string {
    if (value == null) return '';
    const raw = String(value).trim();
    const normalized = raw.toLowerCase();
    if (normalized === 'true' || normalized === 'false') return normalized;
    const numeric = Number(raw);
    if (Number.isFinite(numeric)) return String(numeric);
    return normalized;
  }
}
