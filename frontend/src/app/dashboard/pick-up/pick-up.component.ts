import { Component, Input, Output, EventEmitter, ChangeDetectionStrategy } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { EmptyStateComponent } from '../../shared/empty-state/empty-state.component';

export interface ResumeState {
  interrupted_runs: { run_id: string; name: string; progress: number }[];
  resumable_syncs: { job_id: string; source: string }[];
  missed_tasks: { task_name: string; scheduled_for: string }[];
}

@Component({
  selector: 'app-pick-up',
  standalone: true,
  imports: [MatCardModule, MatIconModule, MatButtonModule, EmptyStateComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <mat-card id="pick-up">
      <mat-card-header>
        <mat-icon mat-card-avatar>replay</mat-icon>
        <mat-card-title>Pick Up Where You Left Off</mat-card-title>
      </mat-card-header>
      <mat-card-content>
        @if (isEmpty) {
          <app-empty-state
            icon="done_all"
            heading="All caught up"
            body="Nothing to resume." />
        } @else {
          @for (run of resumeState.interrupted_runs; track run.run_id) {
            <div class="resume-row">
              <mat-icon class="row-icon">pause_circle</mat-icon>
              <span class="row-label">{{ run.name }} -- {{ run.progress }}% done</span>
              <button mat-stroked-button (click)="resumeRun.emit(run.run_id)">Resume</button>
            </div>
          }
          @for (task of resumeState.missed_tasks; track task.task_name) {
            <div class="resume-row">
              <mat-icon class="row-icon">event_busy</mat-icon>
              <span class="row-label">Missed: {{ task.task_name }}</span>
              <button mat-stroked-button (click)="runNow.emit(task.task_name)">Run Now</button>
              <button mat-button (click)="defer.emit(task.task_name)">Defer to Tonight</button>
            </div>
          }
          @for (sync of resumeState.resumable_syncs; track sync.job_id) {
            <div class="resume-row">
              <mat-icon class="row-icon">sync_problem</mat-icon>
              <span class="row-label">Sync interrupted: {{ sync.source }}</span>
              <button mat-stroked-button (click)="resumeRun.emit(sync.job_id)">Resume</button>
            </div>
          }
        }
      </mat-card-content>
    </mat-card>
  `,
  styles: [`
    mat-card { padding: var(--spacing-card); }
    mat-card-header { margin-bottom: var(--space-md); }
    .resume-row {
      display: flex; align-items: center; gap: var(--space-sm);
      padding: var(--space-sm) 0;
      border-bottom: 1px solid var(--color-border-faint);
    }
    .resume-row:last-child { border-bottom: none; }
    .row-icon { color: var(--color-warning); flex-shrink: 0; }
    .row-label { flex: 1; font-size: 13px; color: var(--color-text-primary); }
  `],
})
export class PickUpComponent {
  @Input() resumeState: ResumeState = { interrupted_runs: [], resumable_syncs: [], missed_tasks: [] };
  @Output() resumeRun = new EventEmitter<string>();
  @Output() runNow = new EventEmitter<string>();
  @Output() defer = new EventEmitter<string>();

  get isEmpty(): boolean {
    return this.resumeState.interrupted_runs.length === 0
      && this.resumeState.resumable_syncs.length === 0
      && this.resumeState.missed_tasks.length === 0;
  }
}
