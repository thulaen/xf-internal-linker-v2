import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import {
  DashboardService,
  DashboardData,
  PipelineRunSummary,
} from './dashboard.service';
import { SuggestionService } from '../review/suggestion.service';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [
    CommonModule,
    RouterModule,
    MatButtonModule,
    MatCardModule,
    MatChipsModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    MatTableModule,
    MatTooltipModule,
  ],
  templateUrl: './dashboard.component.html',
  styleUrls: ['./dashboard.component.scss'],
})
export class DashboardComponent implements OnInit {
  private dashSvc = inject(DashboardService);
  private suggSvc = inject(SuggestionService);
  private snack = inject(MatSnackBar);

  data: DashboardData | null = null;
  loading = true;
  startingPipeline = false;

  readonly runColumns = [
    'run_id', 'run_state', 'suggestions_created',
    'destinations_processed', 'duration_display', 'created_at',
  ];

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading = true;
    this.dashSvc.refresh().subscribe({
      next: (d) => { this.data = d; this.loading = false; },
      error: () => {
        this.loading = false;
        this.snack.open('Failed to load dashboard', 'Dismiss', { duration: 4000 });
      },
    });
  }

  runPipeline(): void {
    this.startingPipeline = true;
    this.suggSvc.startPipeline().subscribe({
      next: (run) => {
        this.startingPipeline = false;
        this.snack.open(
          `Pipeline started (run ${run.run_id.slice(0, 8)})`,
          'Dismiss',
          { duration: 5000 },
        );
        this.load();
      },
      error: () => {
        this.startingPipeline = false;
        this.snack.open('Failed to start pipeline', 'Dismiss', { duration: 4000 });
      },
    });
  }

  stateColor(state: string): string {
    switch (state) {
      case 'completed': return 'success';
      case 'running':   return 'primary';
      case 'failed':    return 'warn';
      default:          return '';
    }
  }

  stateIcon(state: string): string {
    switch (state) {
      case 'completed': return 'check_circle';
      case 'running':   return 'sync';
      case 'failed':    return 'error';
      case 'queued':    return 'schedule';
      default:          return 'help_outline';
    }
  }

  trackByRunId(_: number, r: PipelineRunSummary): string {
    return r.run_id;
  }
}
