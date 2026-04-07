import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatSelectModule } from '@angular/material/select';

export interface RunPipelineDialogResult {
  rerunMode: string;
}

interface RerunOption {
  value: string;
  label: string;
  description: string;
  icon: string;
}

@Component({
  changeDetection: ChangeDetectionStrategy.OnPush,
  selector: 'app-run-pipeline-dialog',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatDialogModule,
    MatFormFieldModule,
    MatIconModule,
    MatSelectModule,
  ],
  template: `
    <h2 mat-dialog-title>
      <mat-icon class="dialog-title-icon">play_arrow</mat-icon>
      Run Pipeline
    </h2>

    <mat-dialog-content>
      <p class="dialog-description">
        Choose how the pipeline handles existing suggestions.
      </p>

      <mat-form-field appearance="outline" class="mode-select">
        <mat-label>Pipeline mode</mat-label>
        <mat-select [(ngModel)]="selectedMode">
          @for (opt of options; track opt.value) {
            <mat-option [value]="opt.value">
              <span class="option-label">{{ opt.label }}</span>
            </mat-option>
          }
        </mat-select>
      </mat-form-field>

      <div class="mode-hint">
        <mat-icon class="hint-icon">info_outline</mat-icon>
        <span>{{ activeDescription }}</span>
      </div>
    </mat-dialog-content>

    <mat-dialog-actions align="end">
      <button mat-button (click)="dialogRef.close(null)">Cancel</button>
      <button mat-raised-button color="primary" (click)="confirm()">
        <mat-icon>play_arrow</mat-icon>
        Run
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    .dialog-title-icon {
      vertical-align: middle;
      margin-right: 4px;
    }

    .dialog-description {
      margin: 0 0 16px;
      color: var(--color-text-secondary);
      font-size: 13px;
    }

    .mode-select {
      width: 100%;
    }

    .option-label {
      font-weight: 500;
    }

    .mode-hint {
      display: flex;
      align-items: flex-start;
      gap: 8px;
      padding: 12px;
      background: var(--color-blue-50, #e8f0fe);
      border-radius: var(--card-border-radius, 8px);
      font-size: 12px;
      color: var(--color-text-secondary);
      line-height: 1.5;
    }

    .hint-icon {
      font-size: 16px;
      width: 16px;
      height: 16px;
      flex-shrink: 0;
      margin-top: 1px;
      color: var(--color-primary);
    }
  `],
})
export class RunPipelineDialogComponent {
  readonly dialogRef = inject(MatDialogRef) as MatDialogRef<RunPipelineDialogComponent, RunPipelineDialogResult | null>;

  selectedMode = 'skip_pending';

  readonly options: RerunOption[] = [
    {
      value: 'skip_pending',
      label: 'Quick update',
      description: 'Only process new content. Keeps your existing pending suggestions untouched.',
      icon: 'bolt',
    },
    {
      value: 'supersede_pending',
      label: 'Refresh suggestions',
      description: 'Replace all pending suggestions with fresh ones. Approved and applied suggestions stay.',
      icon: 'refresh',
    },
    {
      value: 'full_regenerate',
      label: 'Full rebuild',
      description: 'Delete everything and start over from scratch. Use this after big config or weight changes.',
      icon: 'restart_alt',
    },
  ];

  get activeDescription(): string {
    return this.options.find(o => o.value === this.selectedMode)?.description ?? '';
  }

  confirm(): void {
    this.dialogRef.close({ rerunMode: this.selectedMode });
  }
}
