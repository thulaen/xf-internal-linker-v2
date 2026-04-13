import { Component, Input, Output, EventEmitter, ChangeDetectionStrategy } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { EmptyStateComponent } from '../../shared/empty-state/empty-state.component';

export interface RunningTask {
  name: string;
  progress: number;
  message: string;
  eta_seconds?: number;
  state: string;
}

@Component({
  selector: 'app-running-now',
  standalone: true,
  imports: [MatCardModule, MatIconModule, MatButtonModule, MatProgressBarModule, EmptyStateComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <mat-card id="running-now">
      <mat-card-header>
        <mat-icon mat-card-avatar>play_circle</mat-icon>
        <mat-card-title>Running Now</mat-card-title>
      </mat-card-header>
      <mat-card-content>
        @if (activeTasks.length === 0) {
          <app-empty-state
            icon="pause_circle"
            heading="No tasks running"
            body="Everything is idle."
            ctaLabel="Run Pipeline"
            ctaRoute="/dashboard" />
        } @else {
          @for (task of activeTasks; track task.name) {
            <div class="task-row">
              <div class="task-header">
                <span class="task-name">{{ task.name }}</span>
                @if (task.eta_seconds) {
                  <span class="task-eta">~{{ formatEta(task.eta_seconds) }} left</span>
                }
              </div>
              <mat-progress-bar mode="determinate" [value]="task.progress" />
              <span class="task-message">{{ task.message }}</span>
            </div>
          }
        }
      </mat-card-content>
      @if (activeTasks.length === 0) {
        <mat-card-actions align="end">
          <button mat-raised-button color="primary" (click)="runPipeline.emit()">
            <mat-icon>play_arrow</mat-icon> Run Pipeline
          </button>
        </mat-card-actions>
      }
    </mat-card>
  `,
  styles: [`
    mat-card { padding: var(--spacing-card); }
    mat-card-header { margin-bottom: var(--space-md); }
    .task-row {
      display: flex; flex-direction: column; gap: var(--space-xs);
      padding: var(--space-sm) 0;
      border-bottom: 1px solid var(--color-border-faint);
    }
    .task-row:last-child { border-bottom: none; }
    .task-header { display: flex; justify-content: space-between; align-items: center; }
    .task-name { font-weight: 500; font-size: 13px; color: var(--color-text-primary); }
    .task-eta { font-size: 12px; color: var(--color-text-muted); }
    .task-message { font-size: 12px; color: var(--color-text-secondary); }
    mat-card-actions { padding: var(--space-md); }
  `],
})
export class RunningNowComponent {
  @Input() activeTasks: RunningTask[] = [];
  @Output() runPipeline = new EventEmitter<void>();

  formatEta(seconds: number): string {
    if (seconds < 60) return `${seconds}s`;
    const mins = Math.floor(seconds / 60);
    return mins < 60 ? `${mins}m` : `${Math.floor(mins / 60)}h ${mins % 60}m`;
  }
}
