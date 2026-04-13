import { Component, Input, Output, EventEmitter, ChangeDetectionStrategy, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatChipsModule } from '@angular/material/chips';
import { catchError, EMPTY } from 'rxjs';

interface PerformanceOption {
  key: string;
  label: string;
  icon: string;
  description: string;
}

const MODES: PerformanceOption[] = [
  { key: 'safe', label: 'Safe While I Work', icon: 'shield', description: 'Low resource usage' },
  { key: 'balanced', label: 'Balanced', icon: 'balance', description: 'Normal throughput' },
  { key: 'high', label: 'High Performance Now', icon: 'speed', description: 'Maximum speed' },
];

@Component({
  selector: 'app-performance-mode',
  standalone: true,
  imports: [MatCardModule, MatIconModule, MatChipsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <mat-card id="performance-mode">
      <mat-card-header>
        <mat-icon mat-card-avatar>speed</mat-icon>
        <mat-card-title>Performance Mode</mat-card-title>
      </mat-card-header>
      <mat-card-content>
        <div class="mode-options">
          @for (opt of modes; track opt.key) {
            <button class="mode-button"
                    [class.active]="currentMode === opt.key"
                    (click)="selectMode(opt.key)">
              <mat-icon>{{ opt.icon }}</mat-icon>
              <span class="mode-label">{{ opt.label }}</span>
              <span class="mode-desc">{{ opt.description }}</span>
            </button>
          }
        </div>
      </mat-card-content>
    </mat-card>
  `,
  styles: [`
    mat-card { padding: var(--spacing-card); }
    mat-card-header { margin-bottom: var(--space-md); }
    .mode-options { display: flex; gap: var(--space-sm); flex-wrap: wrap; }
    .mode-button {
      flex: 1; min-width: 120px;
      display: flex; flex-direction: column; align-items: center;
      gap: var(--space-xs);
      padding: var(--space-md);
      border: 1px solid var(--color-border);
      border-radius: var(--radius-md);
      background: var(--color-bg-white);
      cursor: pointer;
      transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .mode-button:hover {
      border-color: var(--color-primary);
      box-shadow: var(--shadow-hover);
    }
    .mode-button.active {
      border-color: var(--color-primary);
      background: var(--color-blue-50);
    }
    .mode-button.active mat-icon { color: var(--color-primary); }
    .mode-button mat-icon { color: var(--color-text-muted); }
    .mode-label { font-size: 13px; font-weight: 500; color: var(--color-text-primary); }
    .mode-desc { font-size: 11px; color: var(--color-text-muted); text-align: center; }
  `],
})
export class PerformanceModeComponent {
  private http = inject(HttpClient);

  @Input() currentMode = 'balanced';
  @Output() modeChange = new EventEmitter<string>();

  readonly modes = MODES;

  selectMode(key: string): void {
    if (key === this.currentMode) return;
    this.http.patch<void>('/api/settings/runtime/switch/', { performance_mode: key })
      .pipe(catchError(() => EMPTY))
      .subscribe(() => {
        this.currentMode = key;
        this.modeChange.emit(key);
      });
  }
}
