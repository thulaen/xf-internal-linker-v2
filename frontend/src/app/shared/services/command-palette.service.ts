import { Injectable, inject } from '@angular/core';
import { MatDialog, MatDialogRef } from '@angular/material/dialog';
import { CommandPaletteComponent } from '../components/command-palette/command-palette.component';

/**
 * Opens and closes the global Command Palette.
 *
 * The palette is bound to Ctrl+K (or Cmd+K on Mac) from the app shell.
 * Re-pressing the shortcut while the palette is open closes it.
 */
@Injectable({ providedIn: 'root' })
export class CommandPaletteService {
  private dialog = inject(MatDialog);
  private ref: MatDialogRef<CommandPaletteComponent> | null = null;

  /**
   * Toggle the palette open/closed.
   * If already open, close it. If closed, open it.
   */
  toggle(): void {
    if (this.ref) {
      this.ref.close();
      return;
    }
    this.ref = this.dialog.open(CommandPaletteComponent, {
      width: '640px',
      maxWidth: '92vw',
      panelClass: 'command-palette-dialog',
      autoFocus: 'first-tabbable',
      restoreFocus: true,
      // Smaller backdrop feel: let the palette float without a heavy scrim.
      hasBackdrop: true,
    });
    this.ref.afterClosed().subscribe(() => {
      this.ref = null;
    });
  }

  /** Force the palette closed. Safe to call when not open. */
  close(): void {
    this.ref?.close();
  }
}
