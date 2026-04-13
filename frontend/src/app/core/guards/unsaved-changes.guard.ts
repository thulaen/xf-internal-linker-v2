import { inject } from '@angular/core';
import { CanDeactivateFn } from '@angular/router';
import { MatDialog } from '@angular/material/dialog';
import { Observable, of } from 'rxjs';
import { map } from 'rxjs/operators';

export interface HasUnsavedChanges {
  hasUnsavedChanges(): boolean;
}

export const unsavedChangesGuard: CanDeactivateFn<HasUnsavedChanges> = (component): Observable<boolean> => {
  if (!component?.hasUnsavedChanges || !component.hasUnsavedChanges()) {
    return of(true);
  }

  // Use MatDialog instead of window.confirm for accessibility
  // (screen readers, keyboard navigation).
  const dialog = inject(MatDialog);
  const ref = dialog.open(UnsavedChangesDialogComponent, {
    width: '400px',
    disableClose: true,
  });
  return ref.afterClosed().pipe(map(result => result === true));
};

// Inline dialog component — small enough to live here.
import { Component } from '@angular/core';
import { MatDialogModule } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';

@Component({
  selector: 'app-unsaved-changes-dialog',
  standalone: true,
  imports: [MatDialogModule, MatButtonModule],
  template: `
    <h2 mat-dialog-title>Unsaved changes</h2>
    <mat-dialog-content>
      You have unsaved changes. Are you sure you want to leave this page?
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button [mat-dialog-close]="false">Stay</button>
      <button mat-raised-button color="primary" [mat-dialog-close]="true">Leave</button>
    </mat-dialog-actions>
  `,
})
export class UnsavedChangesDialogComponent {}
