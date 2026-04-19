import { ChangeDetectionStrategy, Component, Input, inject, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { A11yPrefsService } from '../../../core/services/a11y-prefs.service';

/**
 * Phase GK1 / Gap 189 — Keyboard hotkey hint badge.
 *
 * Renders a small `<kbd>` chip next to a button indicating the
 * keyboard shortcut. Designed to sit inline inside a `mat-button` or
 * beside it:
 *
 *   <button mat-button (click)="save()">
 *     Save <app-kbd-hint keys="Ctrl+S" />
 *   </button>
 *
 * Respects Gap 99 font-size preference so the badge scales with the
 * user's text-size choice (90% / 100% / 115% / 130%).
 *
 * Auto-normalises modifier spelling — passing "Ctrl+S" on Mac renders
 * "⌘S" so the hint matches the user's actual shortcut.
 */
@Component({
  selector: 'app-kbd-hint',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule],
  template: `
    @for (chunk of parts(); track chunk) {
      <kbd class="kbd-hint">{{ chunk }}</kbd>
    }
  `,
  styles: [`
    :host {
      display: inline-flex;
      gap: 4px;
      margin-left: 8px;
      font-variant-numeric: tabular-nums;
      user-select: none;
      pointer-events: none;
    }
    .kbd-hint {
      font-family: var(--font-mono);
      font-size: 0.85em;
      padding: 1px 6px;
      background: var(--color-bg-faint, #f1f3f4);
      border: 0.8px solid var(--color-border, #dadce0);
      border-radius: 3px;
      color: var(--color-text-secondary, #5f6368);
    }
  `],
})
export class KbdHintComponent {
  /** e.g. "Ctrl+S", "Shift+?", "G" (comma-separate alternates). */
  @Input() keys = '';

  private a11y = inject(A11yPrefsService, { optional: true });

  protected readonly parts = computed(() => {
    const raw = (this.keys ?? '').trim();
    if (!raw) return [] as string[];
    // Comma-separated alternates → first alternate wins; UI stays small.
    const first = raw.split(',')[0].trim();
    return first.split('+').map((part) => this.normalize(part.trim()));
  });

  private normalize(part: string): string {
    const isMac =
      typeof navigator !== 'undefined' &&
      /Mac|iPhone|iPad/i.test(navigator.platform);
    const upper = part.toUpperCase();
    if (!isMac) return part;
    switch (upper) {
      case 'CTRL':
      case 'CMD':
      case 'META': return '⌘';
      case 'ALT':
      case 'OPT':
      case 'OPTION': return '⌥';
      case 'SHIFT': return '⇧';
      case 'ENTER':
      case 'RETURN': return '↵';
      default: return part;
    }
  }
}
