import {
  ChangeDetectionStrategy,
  Component,
  computed,
  DestroyRef,
  inject,
  OnInit,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatDialogModule } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import { FormsModule } from '@angular/forms';
import { ConfirmService } from '../../shared/confirm-dialog/confirm.service';

/**
 * Phase 4.1 — Undo History Timeline page.
 *
 * Lists restorable AuditEvent rows from GET /api/audit/timeline/.
 * Per-row Restore button POSTs to /api/audit/timeline/<id>/restore/.
 * Filters: subject_type, actor, lookback_days. The plain-English diff
 * (old vs new) is rendered side-by-side so the operator sees what they
 * changed before clicking Restore.
 *
 * Storage discipline: NO new tables. Reads existing AuditEvent
 * (Codex Slice 5) via the backend Phase 4.1 service shipped in commit
 * fffed67. Restoring records a NEW AuditEvent so the timeline stays
 * honest (operator can roll back a rollback).
 */

interface TimelineEntry {
  id: number;
  action: string;
  subject_type: string;
  subject_id: string;
  actor: string;
  message: string;
  created_at: string;
  old_value: unknown;
  new_value: unknown;
  is_restorable: boolean;
  not_restorable_reason: string;
  metadata: Record<string, unknown>;
}

interface TimelineResponse {
  lookback_days: number;
  count: number;
  entries: TimelineEntry[];
}

interface RestoreResponse {
  ok: boolean;
  message: string;
  new_event_id: number | null;
}

@Component({
  selector: 'app-undo-timeline',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatCardModule,
    MatChipsModule,
    MatDialogModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatSnackBarModule,
    MatTableModule,
    MatTooltipModule,
  ],
  templateUrl: './undo-timeline.component.html',
  styleUrls: ['./undo-timeline.component.scss'],
})
export class UndoTimelineComponent implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly snack = inject(MatSnackBar);
  private readonly confirm = inject(ConfirmService);
  private readonly destroyRef = inject(DestroyRef);

  // Filter state.
  readonly lookbackDays = signal<number>(30);
  readonly subjectFilter = signal<string>('');
  readonly actorFilter = signal<string>('');

  // Server data.
  readonly entries = signal<TimelineEntry[]>([]);
  readonly loading = signal<boolean>(false);
  readonly error = signal<string>('');
  readonly busyRowId = signal<number | null>(null);

  readonly restorableCount = computed<number>(
    () => this.entries().filter((e) => e.is_restorable).length,
  );

  readonly availableSubjectTypes = computed<string[]>(() => {
    const set = new Set<string>();
    for (const e of this.entries()) set.add(e.subject_type);
    return Array.from(set).sort();
  });

  readonly displayedColumns = ['created_at', 'subject', 'diff', 'actor', 'actions'];

  ngOnInit(): void {
    this.refresh();
  }

  refresh(): void {
    this.loading.set(true);
    this.error.set('');
    const params: Record<string, string> = {
      lookback_days: String(this.lookbackDays()),
      limit: '100',
    };
    if (this.subjectFilter()) params['subject_type'] = this.subjectFilter();
    if (this.actorFilter()) params['actor'] = this.actorFilter();

    this.http
      .get<TimelineResponse>('/api/audit/timeline/', { params })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (resp) => {
          this.entries.set(resp.entries);
          this.loading.set(false);
        },
        error: (err) => {
          this.error.set(
            err?.error?.detail ?? 'Could not load the audit timeline. Try again in a moment.',
          );
          this.loading.set(false);
        },
      });
  }

  async onRestore(entry: TimelineEntry): Promise<void> {
    if (!entry.is_restorable) return;
    const ok = await this.confirm.ask({
      title: `Restore ${entry.subject_type} '${entry.subject_id}'?`,
      message:
        `This will roll back the change from ${this.formatDate(entry.created_at)}. ` +
        `A new audit event will record the rollback so you can roll IT back too.`,
      confirmLabel: 'Restore',
      icon: 'restore',
    });
    if (!ok) return;

    this.busyRowId.set(entry.id);
    this.http
      .post<RestoreResponse>(`/api/audit/timeline/${entry.id}/restore/`, {})
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (resp) => {
          this.busyRowId.set(null);
          this.snack.open(resp.message, 'Dismiss', { duration: 5000 });
          if (resp.ok) {
            // Refresh the list so the new restore-event appears.
            this.refresh();
          }
        },
        error: (err) => {
          this.busyRowId.set(null);
          this.snack.open(
            err?.error?.detail ?? 'Restore failed. Original change is unchanged.',
            'Dismiss',
            { duration: 6000 },
          );
        },
      });
  }

  formatDate(iso: string): string {
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  }

  formatValue(v: unknown): string {
    if (v === null || v === undefined) return '∅ (none)';
    if (typeof v === 'string') return v;
    return JSON.stringify(v, null, 2);
  }

  trackById(_index: number, entry: TimelineEntry): number {
    return entry.id;
  }
}
