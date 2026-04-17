import { Injectable, inject } from '@angular/core';
import { MatDialog, MatDialogRef } from '@angular/material/dialog';
import { ShortcutHelpComponent } from './shortcut-help.component';

/**
 * Phase E1 / Gap 34 — Shortcut help service.
 *
 * Toggle-open the keyboard shortcut cheatsheet. The `?` listener in
 * app.component.ts calls `toggle()` whenever `?` is pressed outside
 * an input / textarea / contenteditable.
 */
@Injectable({ providedIn: 'root' })
export class ShortcutHelpService {
  private dialog = inject(MatDialog);
  private ref: MatDialogRef<ShortcutHelpComponent> | null = null;

  toggle(): void {
    if (this.ref) {
      this.ref.close();
      return;
    }
    this.ref = this.dialog.open(ShortcutHelpComponent, {
      width: '560px',
      maxWidth: '95vw',
      autoFocus: 'first-tabbable',
      restoreFocus: true,
    });
    this.ref.afterClosed().subscribe(() => {
      this.ref = null;
    });
  }
}
