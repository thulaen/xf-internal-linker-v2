import { CommonModule } from '@angular/common';
import { Component, OnInit, inject } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { AnalyticsOverviewResponse, AnalyticsService } from './analytics.service';

@Component({
  selector: 'app-analytics',
  standalone: true,
  imports: [CommonModule, MatCardModule, MatIconModule],
  templateUrl: './analytics.component.html',
  styleUrls: ['./analytics.component.scss'],
})
export class AnalyticsComponent implements OnInit {
  private analyticsSvc = inject(AnalyticsService);

  loading = true;
  error = '';
  overview: AnalyticsOverviewResponse | null = null;

  ngOnInit(): void {
    this.analyticsSvc.getOverview().subscribe({
      next: (overview) => {
        this.overview = overview;
        this.loading = false;
      },
      error: () => {
        this.error = 'Could not load telemetry overview.';
        this.loading = false;
      },
    });
  }

  statusLabel(status: string): string {
    return {
      connected: 'Connected',
      saved: 'Saved',
      error: 'Error',
      not_configured: 'Not set up',
    }[status] ?? 'Unknown';
  }

  lastSyncLabel(sync: { completed_at: string | null; started_at: string | null; rows_written: number } | null): string {
    if (!sync) return 'Never synced';
    const stamp = sync.completed_at || sync.started_at;
    if (!stamp) return `${sync.rows_written} rows written`;
    return `${new Date(stamp).toLocaleString()} • ${sync.rows_written} rows written`;
  }
}
