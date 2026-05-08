/**
 * Monthly Reports page.
 *
 * Lists every `monthly-suggestions-YYYY-MM.md` under `docs/reports/` and
 * renders the selected one inline. KISS v1 shows the markdown body in a
 * scrollable <pre> block — readable, copyable, no extra markdown-rendering
 * dependency. A future iteration can swap in `marked` or similar.
 */
import { ChangeDetectionStrategy, Component, OnInit, signal, inject } from '@angular/core';
import { CommonModule, DatePipe } from '@angular/common';

import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatListModule } from '@angular/material/list';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar } from '@angular/material/snack-bar';

import { McpService, MonthlyReportSummary, MonthlyReportBody } from '../core/services/mcp.service';

@Component({
  selector: 'app-monthly-reports',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    DatePipe,
    MatCardModule,
    MatIconModule,
    MatButtonModule,
    MatListModule,
    MatProgressSpinnerModule,
  ],
  templateUrl: './monthly-reports.component.html',
  styleUrls: ['./monthly-reports.component.scss'],
})
export class MonthlyReportsComponent implements OnInit {
  readonly reports = signal<MonthlyReportSummary[] | null>(null);
  readonly selectedMonth = signal<string | null>(null);
  readonly selectedBody = signal<MonthlyReportBody | null>(null);
  readonly loadingBody = signal(false);
  readonly runBusy = signal(false);

  private readonly mcp = inject(McpService);
  private readonly snack = inject(MatSnackBar);

  ngOnInit(): void {
    this.refresh();
  }

  refresh(): void {
    this.mcp.listMonthlyReports().subscribe({
      next: (res) => {
        this.reports.set(res.reports);
        if (res.reports.length > 0 && !this.selectedMonth()) {
          this.select(res.reports[0].month);
        }
      },
      error: (err) =>
        this.snack.open(`Could not load reports: ${err?.message ?? 'unknown error'}`, 'OK', {
          duration: 5000,
        }),
    });
  }

  select(month: string): void {
    this.selectedMonth.set(month);
    this.selectedBody.set(null);
    this.loadingBody.set(true);
    this.mcp.readMonthlyReport(month).subscribe({
      next: (res) => {
        this.selectedBody.set(res);
        this.loadingBody.set(false);
      },
      error: (err) => {
        this.loadingBody.set(false);
        this.snack.open(
          `Could not read ${month}: ${err?.message ?? 'unknown error'}`,
          'OK',
          { duration: 5000 },
        );
      },
    });
  }

  runNow(): void {
    if (this.runBusy()) return;
    this.runBusy.set(true);
    this.mcp.runMonthly().subscribe({
      next: (res) => {
        this.runBusy.set(false);
        this.snack.open(
          `Monthly Top-50 queued for ${res.month}. Refresh in a minute or two.`,
          'OK',
          { duration: 6000 },
        );
      },
      error: (err) => {
        this.runBusy.set(false);
        this.snack.open(
          `Could not queue: ${err?.message ?? 'unknown error'}`,
          'OK',
          { duration: 5000 },
        );
      },
    });
  }
}
