import {
  Component,
  ChangeDetectionStrategy,
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatDialogModule } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';

/**
 * Phase E1 / Gap 34 — Keyboard shortcut cheatsheet.
 *
 * Opens when the user presses `?` anywhere (excluding inputs / contenteditable).
 * Opened via ShortcutHelpService.open() which is called from app.component.
 *
 * Design:
 *  - MatDialog, 560px wide
 *  - Grouped table of shortcuts matching the actual app bindings
 *  - kbd badges styled like the command palette footer
 *  - Close via Esc (mat-dialog default) or the Close button
 */
interface Shortcut {
  keys: string[];
  label: string;
}

interface ShortcutGroup {
  title: string;
  shortcuts: Shortcut[];
}

const SHORTCUT_GROUPS: ShortcutGroup[] = [
  {
    title: 'Navigation',
    shortcuts: [
      { keys: ['Ctrl', 'K'], label: 'Open command palette' },
      { keys: ['?'], label: 'Show this keyboard shortcut guide' },
      { keys: ['Alt', 'G'], label: 'Open glossary drawer (Gap 69)' },
    ],
  },
  {
    title: 'Data tables',
    shortcuts: [
      { keys: ['↑', '↓'], label: 'Navigate rows' },
      { keys: ['Enter'], label: 'Open selected row' },
      { keys: ['G'], label: 'Go to row number' },
    ],
  },
  {
    title: 'Actions',
    shortcuts: [
      { keys: ['Ctrl', 'Z'], label: 'Undo last action (where available)' },
      { keys: ['Esc'], label: 'Close dialog / dismiss panel' },
      { keys: ['Shift', 'D'], label: 'Open debug overlay' },
    ],
  },
  {
    title: 'Accessibility',
    shortcuts: [
      { keys: ['Tab'], label: 'Move focus forward' },
      { keys: ['Shift', 'Tab'], label: 'Move focus backward' },
      { keys: ['Space', 'Enter'], label: 'Activate focused button or card' },
    ],
  },
];

@Component({
  selector: 'app-shortcut-help',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatDialogModule, MatButtonModule, MatIconModule],
  template: `
    <h2 mat-dialog-title class="sh-title">
      <mat-icon class="sh-title-icon" aria-hidden="true">keyboard</mat-icon>
      Keyboard shortcuts
    </h2>

    <mat-dialog-content class="sh-content">
      @for (group of groups; track group.title) {
        <div class="sh-group">
          <h3 class="sh-group-title">{{ group.title }}</h3>
          <dl class="sh-list">
            @for (shortcut of group.shortcuts; track shortcut.label) {
              <div class="sh-row">
                <dt class="sh-keys" [attr.aria-label]="shortcut.keys.join(' + ')">
                  @for (key of shortcut.keys; track key; let last = $last) {
                    <kbd class="sh-kbd">{{ key }}</kbd>
                    @if (!last) {
                      <span class="sh-plus" aria-hidden="true">+</span>
                    }
                  }
                </dt>
                <dd class="sh-desc">{{ shortcut.label }}</dd>
              </div>
            }
          </dl>
        </div>
      }
    </mat-dialog-content>

    <mat-dialog-actions align="end">
      <button mat-button mat-dialog-close type="button">Close</button>
    </mat-dialog-actions>
  `,
  styles: [`
    .sh-title {
      display: flex;
      align-items: center;
      gap: var(--space-sm);
    }
    .sh-title-icon {
      color: var(--color-text-secondary);
    }
    .sh-content {
      padding-top: var(--space-md) !important;
    }
    .sh-group {
      margin-bottom: var(--space-lg);
    }
    .sh-group:last-child {
      margin-bottom: 0;
    }
    .sh-group-title {
      margin: 0 0 var(--space-sm);
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: var(--color-text-muted);
    }
    .sh-list {
      margin: 0;
    }
    .sh-row {
      display: flex;
      align-items: center;
      gap: var(--space-md);
      padding: var(--space-xs) 0;
      border-bottom: var(--card-border);
    }
    .sh-row:last-child {
      border-bottom: none;
    }
    .sh-keys {
      display: flex;
      align-items: center;
      gap: var(--space-xs);
      min-width: 140px;
    }
    .sh-kbd {
      display: inline-block;
      min-width: 24px;
      padding: 2px 6px;
      border: var(--card-border);
      border-radius: var(--radius-sm, 4px);
      background: var(--color-bg-faint, #f8f9fa);
      font-family: inherit;
      font-size: 11px;
      text-align: center;
      color: var(--color-text-secondary);
    }
    .sh-plus {
      font-size: 11px;
      color: var(--color-text-muted);
    }
    .sh-desc {
      margin: 0;
      font-size: 13px;
      color: var(--color-text-primary);
    }
  `],
})
export class ShortcutHelpComponent {
  readonly groups = SHORTCUT_GROUPS;
}
