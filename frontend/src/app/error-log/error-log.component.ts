import { ChangeDetectionStrategy, Component, OnInit, inject } from '@angular/core';
import { CommonModule, DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';
import {
  DiagnosticsService,
  ErrorLogEntry,
} from '../diagnostics/diagnostics.service';

@Component({
  changeDetection: ChangeDetectionStrategy.OnPush,
  selector: 'app-error-log',
  standalone: true,
  imports: [
    CommonModule,
    DatePipe,
    FormsModule,
    MatButtonModule,
    MatCardModule,
    MatChipsModule,
    MatFormFieldModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatTooltipModule,
  ],
  templateUrl: './error-log.component.html',
  styleUrl: './error-log.component.scss',
})
export class ErrorLogComponent implements OnInit {
  private diagnostics = inject(DiagnosticsService);

  errors: ErrorLogEntry[] = [];
  loading = true;

  filterJobType = '';
  filterAcknowledged = '';

  ngOnInit(): void {
    this.loadErrors();
  }

  loadErrors(): void {
    this.loading = true;
    this.diagnostics.getErrors().subscribe({
      next: (data) => {
        this.errors = data;
        this.loading = false;
      },
      error: () => {
        this.loading = false;
      },
    });
  }

  get filteredErrors(): ErrorLogEntry[] {
    return this.errors.filter((e) => {
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

  acknowledgeError(error: ErrorLogEntry): void {
    this.diagnostics.acknowledgeError(error.id).subscribe({
      next: () => {
        error.acknowledged = true;
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
}
