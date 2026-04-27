import { ChangeDetectionStrategy, ChangeDetectorRef, Component, DestroyRef, OnInit, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule, DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTooltipModule } from '@angular/material/tooltip';
import { EMPTY, timer } from 'rxjs';
import { catchError, switchMap } from 'rxjs/operators';
import { VisibilityGateService } from '../core/util/visibility-gate.service';
import { environment } from '../../environments/environment';
import { GlitchtipService } from '../core/services/glitchtip.service';
import {
  DiagnosticsService,
  ErrorLogEntry,
} from '../diagnostics/diagnostics.service';
import {
  ErrorGroup,
  groupErrors,
  trackGroupFingerprint,
} from '../diagnostics/diagnostics.error-log';

const GLITCHTIP_TAB_INDEX = 1;
const ALL_TAB_INDEX = 2;
const GLITCHTIP_POLL_MS = 30_000;

@Component({
  selector: 'app-error-log',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    DatePipe,
    FormsModule,
    MatButtonModule,
    MatExpansionModule,
    MatFormFieldModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatTabsModule,
    MatTooltipModule,
  ],
  templateUrl: './error-log.component.html',
  styleUrl: './error-log.component.scss',
})
export class ErrorLogComponent implements OnInit {
  private readonly diagnostics = inject(DiagnosticsService);
  private readonly glitchtip = inject(GlitchtipService);
  private readonly cdr = inject(ChangeDetectorRef);
  private readonly destroyRef = inject(DestroyRef);
  private readonly visibilityGate = inject(VisibilityGateService);

  errors: ErrorLogEntry[] = [];
  glitchtipEvents: ErrorLogEntry[] = [];
  glitchtipLastSyncedAt: string | null = null;
  loading = true;
  selectedTabIndex = 0;

  filterJobType = '';
  filterAcknowledged = '';

  readonly glitchtipBaseUrl = environment.glitchtipBaseUrl;
  readonly trackGroupFingerprint = trackGroupFingerprint;

  ngOnInit(): void {
    this.loadErrors();
    this.startGlitchtipPoll();
  }

  onTabChange(index: number): void {
    this.selectedTabIndex = index;
    if (index === GLITCHTIP_TAB_INDEX) {
      this.loadGlitchtipEvents();
    }
  }

  openGlitchtip(): void {
    if (!this.glitchtipBaseUrl) return;
    window.open(this.glitchtipBaseUrl, '_blank', 'noopener,noreferrer');
  }

  loadGlitchtipEvents(): void {
    this.glitchtip.getRecentEvents()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (events) => {
          this.glitchtipEvents = events;
          this.glitchtipLastSyncedAt = new Date().toISOString();
          this.cdr.markForCheck();
        },
        // Glitchtip is best-effort — surface failures in the console so
        // they're debuggable but never toast the user. Without this branch
        // an HTTP error would leave the tab silently empty forever.
        error: (err) => console.warn('glitchtip events failed', err),
      });
  }

  private startGlitchtipPoll(): void {
    // Gated by `VisibilityGateService` — hidden tabs / signed-out
    // sessions skip the poll. See docs/PERFORMANCE.md §13.
    //
    // The inner `catchError(() => EMPTY)` is critical: a single failed
    // fetch must NOT propagate up the switchMap, because that would tear
    // down the outer timer permanently. Swap the failed inner observable
    // for EMPTY so the next tick fires normally.
    this.visibilityGate
      .whileLoggedInAndVisible(() =>
        timer(GLITCHTIP_POLL_MS, GLITCHTIP_POLL_MS).pipe(
          switchMap(() =>
            this.glitchtip.getRecentEvents().pipe(
              catchError((err) => {
                console.warn('glitchtip poll fetch failed', err);
                return EMPTY;
              }),
            ),
          ),
        ),
      )
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (events) => {
          this.glitchtipEvents = events;
          this.glitchtipLastSyncedAt = new Date().toISOString();
          this.cdr.markForCheck();
        },
        error: (err) => console.warn('glitchtip poll stream errored', err),
      });
  }

  loadErrors(): void {
    this.loading = true;
    this.diagnostics.getErrors()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (data) => {
          this.errors = data;
          this.loading = false;
          this.cdr.markForCheck();
        },
        error: () => {
          this.loading = false;
          this.cdr.markForCheck();
        },
      });
  }

  get filteredErrors(): ErrorLogEntry[] {
    if (this.selectedTabIndex === GLITCHTIP_TAB_INDEX) {
      return this.glitchtipEvents;
    }
    const sourceFiltered = this.selectedTabIndex === ALL_TAB_INDEX
      ? this.errors
      : this.errors.filter((e) => e.source !== 'glitchtip');
    return sourceFiltered.filter((e) => {
      if (this.filterJobType && e.job_type !== this.filterJobType) return false;
      if (this.filterAcknowledged === 'reviewed' && !e.acknowledged) return false;
      if (this.filterAcknowledged === 'unreviewed' && e.acknowledged) return false;
      return true;
    });
  }

  get groupedErrors(): ErrorGroup[] {
    return groupErrors(this.filteredErrors, null);
  }

  get uniqueJobTypes(): string[] {
    return [...new Set(this.errors.map((e) => e.job_type))].sort();
  }

  get unreviewedCount(): number {
    return this.errors.filter((e) => !e.acknowledged).length;
  }

  get showJobTypeAndStatusFilters(): boolean {
    return this.selectedTabIndex !== GLITCHTIP_TAB_INDEX;
  }

  acknowledgeError(error: ErrorLogEntry): void {
    // Reload from the server after acknowledging rather than patching locally.
    // A grouped panel may contain multiple entries sharing a fingerprint — only
    // one id is sent to the server, so a local patch would leave the rest of
    // the group still unacknowledged and they would re-appear on the next poll.
    this.diagnostics.acknowledgeError(error.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.loadErrors();
          if (error.source === 'glitchtip') {
            this.loadGlitchtipEvents();
          }
        },
        // Without this branch, a failed acknowledge would silently leave
        // the error in the list and the user would think the click did
        // nothing. Reload anyway — the next poll will reconcile state.
        error: (err) => {
          console.warn('acknowledgeError failed', err);
          this.loadErrors();
        },
      });
  }

  jobTypeLabel(type: string): string {
    const labels: Record<string, string> = {
      import: 'Import',
      embed: 'Embed',
      pipeline: 'Pipeline',
      sync: 'Sync',
      auto_tune_weights: 'Auto-Tune',
    };
    return labels[type] || type;
  }

  previewMessage(error: ErrorLogEntry, maxLength = 140): string {
    const message = (error.error_message || '').trim();
    if (message.length <= maxLength) {
      return message;
    }
    return `${message.slice(0, maxLength - 3).trimEnd()}...`;
  }

  severityLabel(error: ErrorLogEntry): string {
    const severity = error.severity || 'medium';
    return severity.charAt(0).toUpperCase() + severity.slice(1);
  }

  sourceLabel(error: ErrorLogEntry): string {
    return error.source === 'glitchtip' ? 'GlitchTip' : 'Internal';
  }
}
