import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatTableModule } from '@angular/material/table';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { DiagnosticsService, WeightDiagnosticsResponse } from '../../diagnostics/diagnostics.service';

@Component({
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
  styleUrls: ['./weight-diagnostics-card.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class WeightDiagnosticsCardComponent implements OnInit {
  private diagnosticsService = inject(DiagnosticsService);
  // Phase E2 / Gap 41 — cancel in-flight HTTP on destroy.
  private destroyRef = inject(DestroyRef);

  // Internal state lives in signals so OnPush change detection picks up
  // every mutation automatically. See AGENT-HANDOFF.md (signals migration
  // pattern, 2026-04-26) for the recipe.
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly data = signal<WeightDiagnosticsResponse | null>(null);

  readonly displayedColumns: string[] = ['name', 'weight', 'cpp', 'storage', 'health'];

  ngOnInit(): void {
    this.loadData();
  }

  loadData(): void {
    this.loading.set(true);
    this.error.set(null);
    this.diagnosticsService.getWeightDiagnostics()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
      next: (res) => {
        this.data.set(res);
        this.loading.set(false);
      },
      error: (err) => {
        console.error('Failed to load weight diagnostics:', err);
        this.error.set('Failed to load weight diagnostics. Please try again.');
        this.loading.set(false);
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
