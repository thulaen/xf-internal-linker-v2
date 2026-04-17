import { Injectable, inject } from '@angular/core';
import { MatDialog } from '@angular/material/dialog';
import { firstValueFrom } from 'rxjs';

import { ConfirmDialogComponent, ConfirmDialogData } from './confirm-dialog.component';

/**
 * Phase E1 / Gap 30 — Imperative confirm helper.
 *
 * Returns a Promise<boolean> so callers can await it inline.
 * No need to manage dialog refs or subscriptions in the caller.
 *
 * Example:
 *   const ok = await this.confirm.ask({ title: 'Delete?', danger: true });
 *   if (!ok) return;
 */
@Injectable({ providedIn: 'root' })
export class ConfirmService {
  private dialog = inject(MatDialog);

  async ask(data: ConfirmDialogData): Promise<boolean> {
    const ref = this.dialog.open(ConfirmDialogComponent, {
      width: '400px',
      data,
      disableClose: true,
      autoFocus: 'first-tabbable',
    });
    const result = await firstValueFrom(ref.afterClosed());
    return result === true;
  }
}
