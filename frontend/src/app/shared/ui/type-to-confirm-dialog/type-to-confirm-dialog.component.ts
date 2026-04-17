import {
  ChangeDetectionStrategy,
  Component,
  inject,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';

/**
 * Phase GK1 / Gap 209 — "Type DELETE to confirm" dialog variant.
 *
 * For truly destructive actions where even a confirm-click is too
 * easy. User must type the exact verification phrase (default
 * "DELETE") before the confirm button enables.
 *
 * Wrapper around MatDialog — callers open it with:
 *   this.dialog.open(TypeToConfirmDialogComponent, {
 *     data: { title: 'Wipe cache?', phrase: 'DELETE',
 *             body: 'All cached embeddings will be rebuilt.' }
 *   }).afterClosed().subscribe(confirmed => ...);
 *
 * Distinct from Gap 30 ConfirmDialog (one-click OK) and Gap 205
 * double-confirm (two-step OK): this is the highest-friction tier.
 */

export interface TypeToConfirmData {
  title: string;
  body?: string;
  phrase?: string;
  confirmLabel?: string;
  cancelLabel?: string;
}

@Component({
  selector: 'app-type-to-confirm-dialog',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    FormsModule,
    MatDialogModule,
    MatButtonModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
  ],
  template: `
    <h2 mat-dialog-title>
      <mat-icon class="ttc-icon">warning</mat-icon>
      {{ data.title }}
    </h2>
    <mat-dialog-content>
      @if (data.body) {
        <p class="ttc-body">{{ data.body }}</p>
      }
      <p class="ttc-instruction">
        Type <strong>{{ phrase }}</strong> to confirm this cannot be undone.
      </p>
      <mat-form-field appearance="outline" class="ttc-input">
        <mat-label>Verification phrase</mat-label>
        <input
          matInput
          autocomplete="off"
          spellcheck="false"
          autocapitalize="off"
          [(ngModel)]="typed"
          (ngModelChange)="onTypedChange($event)"
          [placeholder]="phrase"
        />
      </mat-form-field>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button type="button" (click)="dialogRef.close(false)">
        {{ data.cancelLabel || 'Cancel' }}
      </button>
      <button
        mat-raised-button
        color="warn"
        type="button"
        [disabled]="!match()"
        (click)="dialogRef.close(true)"
      >
        {{ data.confirmLabel || 'Confirm' }}
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    :host { display: block; min-width: 420px; }
    .ttc-icon { color: var(--color-error, #d93025); }
    .ttc-body { margin: 0 0 12px; font-size: 13px; }
    .ttc-instruction { margin: 0 0 8px; font-size: 13px; }
    .ttc-input { width: 100%; }
  `],
})
export class TypeToConfirmDialogComponent {
  protected readonly data: TypeToConfirmData = inject(MAT_DIALOG_DATA);
  protected readonly dialogRef = inject<MatDialogRef<TypeToConfirmDialogComponent>>(MatDialogRef);

  protected typed = '';
  protected readonly phrase = (this.data.phrase ?? 'DELETE').toUpperCase();
  private readonly _match = signal(false);
  protected readonly match = this._match.asReadonly();

  onTypedChange(value: string): void {
    this.typed = value;
    this._match.set(value.trim() === this.phrase);
  }
}
