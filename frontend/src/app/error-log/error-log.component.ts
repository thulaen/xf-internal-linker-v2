import { ChangeDetectionStrategy, ChangeDetectorRef, Component, DestroyRef, OnInit, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule, DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ScrollingModule } from '@angular/cdk/scrolling';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTooltipModule } from '@angular/material/tooltip';
import { timer } from 'rxjs';
import { switchMap } from 'rxjs/operators';
import { VisibilityGateService } from '../core/util/visibility-gate.service';
import { environment } from '../../environments/environment';
import { GlitchtipService } from '../core/services/glitchtip.service';
import {
  DiagnosticsService,
  ErrorLogEntry,
} from '../diagnostics/diagnostics.service';

const GLITCHTIP_TAB_INDEX = 1;
const ALL_TAB_INDEX = 2;
const GLITCHTIP_POLL_MS = 30_000;

/**
 * Phase E1 / Gap 27 — Virtual scroll applied to the error list.
 *
 * The error-log can grow to hundreds of entries in production. Rather than
 * rendering all DOM nodes at once (slow scrolling, high memory), we wrap the
 * list in `cdk-virtual-scroll-viewport` with `*cdkVirtualFor`.
 *
 * Row height approximation: each error card is ~200px when collapsed. Cards
 * with long stack traces expand beyond that, but CDK handles variable-height
 * cards reasonably with `minBufferPx` / `maxBufferPx`.
 *
 * Pattern reuse: See `core/util/virtual-scroll-datasource.ts` for the
 * VirtualScrollDataSource utility when a mat-table integration is needed.
 */
@Component({
  selector: 'app-error-log',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    DatePipe,
    FormsModule,
    ScrollingModule,
    MatButtonModule,
    MatCardModule,
    MatChipsModule,
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
  private diagnostics = inject(DiagnosticsService);
  private glitchtip = inject(GlitchtipService);
  private cdr = inject(ChangeDetectorRef);
  // Phase E2 / Gap 41 — cancel in-flight HTTP on route leave.
  private destroyRef = inject(DestroyRef);
  private visibilityGate = inject(VisibilityGateService);

  errors: ErrorLogEntry[] = [];
  glitchtipEvents: ErrorLogEntry[] = [];
  glitchtipLastSyncedAt: string | null = null;
  loading = true;
  selectedTabIndex = 0;

  filterJobType = '';
  filterAcknowledged = '';

  readonly glitchtipBaseUrl = environment.glitchtipBaseUrl;

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
      });
  }

  private startGlitchtipPoll(): void {
    // Gated by `VisibilityGateService` — hidden tabs / signed-out
    // sessions skip the poll. See docs/PERFORMANCE.md §13.
    this.visibilityGate
      .whileLoggedInAndVisible(() =>
        timer(GLITCHTIP_POLL_MS, GLITCHTIP_POLL_MS).pipe(
          switchMap(() => this.glitchtip.getRecentEvents()),
        ),
      )
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (events) => {
          this.glitchtipEvents = events;
          this.glitchtipLastSyncedAt = new Date().toISOString();
          this.cdr.markForCheck();
        },
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
    this.diagnostics.acknowledgeError(error.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          error.acknowledged = true;
        },
      });
  }

  /** Gap 27 — trackBy for *cdkVirtualFor; prevents full re-render on data refresh. */
  trackById(_index: number, error: ErrorLogEntry): number {
    return error.id;
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
}
