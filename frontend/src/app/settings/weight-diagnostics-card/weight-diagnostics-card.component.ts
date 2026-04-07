import { ChangeDetectionStrategy, Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatTableModule } from '@angular/material/table';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { DiagnosticsService, WeightSignal, WeightDiagnosticsResponse } from '../../diagnostics/diagnostics.service';

@Component({
  changeDetection: ChangeDetectionStrategy.OnPush,
  selector: 'app-weight-diagnostics-card',
  standalone: true,
  imports: [
    CommonModule,
    MatCardModule,
    MatTableModule,
    MatIconModule,
    MatButtonModule,
    MatTooltipModule,
    MatProgressBarModule
  ],
  templateUrl: './weight-diagnostics-card.component.html',
  styleUrls: ['./weight-diagnostics-card.component.scss']
})
export class WeightDiagnosticsCardComponent implements OnInit {
  private diagnosticsService = inject(DiagnosticsService);

  loading = true;
  error: string | null = null;
  data: WeightDiagnosticsResponse | null = null;

  displayedColumns: string[] = ['name', 'weight', 'cpp', 'storage', 'health'];

  ngOnInit(): void {
    this.loadData();
  }

  loadData(): void {
    this.loading = true;
    this.error = null;
    this.diagnosticsService.getWeightDiagnostics().subscribe({
      next: (res) => {
        this.data = res;
        this.loading = false;
      },
      error: (err) => {
        console.error('Failed to load weight diagnostics:', err);
        this.error = 'Failed to load weight diagnostics. Please try again.';
        this.loading = false;
      }
    });
  }

  getTypeLabel(type: string): string {
    return type === 'ranking' ? 'Ranking Signal' : 'Value Model';
  }

  getHealthIcon(status: string): string {
    return status === 'healthy' ? 'check_circle' : 'warning';
  }

  getHealthColor(status: string): string {
    return status === 'healthy' ? '#228747' : '#a77a00';
  }
}
