import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import {
  DashboardService,
  DashboardData,
  PipelineRunSummary,
} from './dashboard.service';
import { SuggestionService } from '../review/suggestion.service';
import { SyncService } from '../jobs/sync.service';
import { RunPipelineDialogComponent, RunPipelineDialogResult } from '../core/run-pipeline-dialog.component';
import { SystemSummaryComponent } from './components/system-summary/system-summary.component';
import { WebhookLogComponent } from './components/webhook-log/webhook-log.component';
import { ScrollHighlightDirective } from '../core/directives/scroll-highlight.directive';
import { SetupWizardDialogComponent } from './components/setup-wizard/setup-wizard-dialog.component';

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
    MatDialogModule,
    MatSnackBarModule,
    MatTableModule,
    MatTooltipModule,
    SystemSummaryComponent,
    WebhookLogComponent,
    ScrollHighlightDirective,
  ],
  templateUrl: './dashboard.component.html',
  styleUrls: ['./dashboard.component.scss'],
})
export class DashboardComponent implements OnInit {
  private dashSvc = inject(DashboardService);
  private suggSvc = inject(SuggestionService);
  private syncSvc = inject(SyncService);
  private dialog = inject(MatDialog);
  private snack = inject(MatSnackBar);

  data: DashboardData | null = null;
  loading = true;
  startingPipeline = false;
  syncing = false;
  daysSinceLastRun: number | null = null;

  showSetupChecklist = false;
  setupSteps = { connected: false, imported: false, pipelineRan: false, reviewed: false };

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
      next: (d) => {
        this.data = d;
        this.loading = false;
        this.daysSinceLastRun = this.computeDaysSinceLastRun(d.pipeline_runs);
        this.updateSetupChecklist(d);
        this.maybeShowSetupWizard(d);
      },
      error: () => {
        this.loading = false;
        this.snack.open('Failed to load dashboard', 'Dismiss', { duration: 4000 });
      },
    });
  }

  private computeDaysSinceLastRun(runs: PipelineRunSummary[]): number | null {
    const lastCompleted = runs.find(r => r.run_state === 'completed');
    if (!lastCompleted) return null;
    const diffMs = Date.now() - new Date(lastCompleted.created_at).getTime();
    return Math.floor(diffMs / (1000 * 60 * 60 * 24));
  }

  catchUpSync(): void {
    this.syncing = true;
    this.syncSvc.getSourceStatus().subscribe({
      next: (status) => {
        const calls: string[] = [];
        if (status.api) calls.push('api');
        if (status.wp) calls.push('wp');
        if (calls.length === 0) {
          this.syncing = false;
          this.snack.open('No sources configured', 'Dismiss', { duration: 4000 });
          return;
        }
        let completed = 0;
        for (const source of calls) {
          this.syncSvc.triggerApiSync(source as 'api' | 'wp', 'full').subscribe({
            next: () => {
              completed++;
              if (completed === calls.length) {
                this.syncing = false;
                this.snack.open(
                  'Sync started \u2014 check Jobs page for progress',
                  'Dismiss',
                  { duration: 5000 },
                );
              }
            },
            error: () => {
              completed++;
              if (completed === calls.length) this.syncing = false;
              this.snack.open(`Failed to sync ${source}`, 'Dismiss', { duration: 4000 });
            },
          });
        }
      },
      error: () => {
        this.syncing = false;
        this.snack.open('Failed to check source status', 'Dismiss', { duration: 4000 });
      },
    });
  }

  runPipeline(): void {
    const ref = this.dialog.open<
      RunPipelineDialogComponent,
      void,
      RunPipelineDialogResult | null
    >(RunPipelineDialogComponent, { width: '420px' });

    ref.afterClosed().subscribe((result) => {
      if (!result) return;
      this.startingPipeline = true;
      this.suggSvc.startPipeline(result.rerunMode).subscribe({
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

  private updateSetupChecklist(d: DashboardData): void {
    const dismissed = localStorage.getItem('setupChecklistDismissed') === 'true';
    this.setupSteps = {
      connected: d.content_count > 0 || d.recent_imports.some(j => j.status === 'completed'),
      imported: d.content_count > 0,
      pipelineRan: d.pipeline_runs.length > 0,
      reviewed: d.suggestion_counts.approved + d.suggestion_counts.applied > 0,
    };
    const allDone = this.setupSteps.connected && this.setupSteps.imported
      && this.setupSteps.pipelineRan && this.setupSteps.reviewed;
    this.showSetupChecklist = !dismissed && !allDone;
  }

  private maybeShowSetupWizard(d: DashboardData): void {
    const shown = localStorage.getItem('setupWizardCompleted') === 'true';
    if (!shown && d.content_count === 0) {
      localStorage.setItem('setupWizardCompleted', 'true');
      this.dialog.open(SetupWizardDialogComponent, { width: '520px', disableClose: false });
    }
  }

  dismissSetupChecklist(): void {
    this.showSetupChecklist = false;
    localStorage.setItem('setupChecklistDismissed', 'true');
  }

  getImportSettingsFragment(source: string): string {
    switch (source) {
      case 'api': return 'xenforo-settings';
      case 'wp':  return 'wordpress-settings';
      default:    return '';
    }
  }
}
