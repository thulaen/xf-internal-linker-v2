import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatListModule } from '@angular/material/list';

export interface KernelDialogData {
  kernels: string[];
  tileState: string;
}

@Component({
  selector: 'app-kernel-list-dialog',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    MatDialogModule,
    MatButtonModule,
    MatIconModule,
    MatListModule,
  ],
  template: `
    <h2 mat-dialog-title>
      <mat-icon>memory</mat-icon>
      C++ Kernels ({{ data.kernels.length }})
    </h2>
    <mat-dialog-content>
      <p class="kl-subtitle">
        All ranking and utility kernels compiled into the native extension.
      </p>
      <mat-list>
        @for (name of data.kernels; track name) {
          <mat-list-item>
            <mat-icon matListItemIcon>circle</mat-icon>
            <span matListItemTitle>{{ name }}</span>
          </mat-list-item>
        }
      </mat-list>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button type="button" (click)="close()">Close</button>
    </mat-dialog-actions>
  `,
  styles: [`
    h2[mat-dialog-title] {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .kl-subtitle {
      margin: 0 0 8px;
      font-size: 13px;
      color: var(--color-text-secondary);
    }
    mat-list { max-height: 60vh; overflow-y: auto; }
    mat-icon[matListItemIcon] { font-size: 8px; width: 8px; height: 8px; color: var(--color-text-muted); }
  `],
})
export class KernelListDialogComponent {
  protected readonly data = inject<KernelDialogData>(MAT_DIALOG_DATA);
  private readonly dialogRef = inject(MatDialogRef<KernelListDialogComponent>);

  close(): void {
    this.dialogRef.close();
  }
}
