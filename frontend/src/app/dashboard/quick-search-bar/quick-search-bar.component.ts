import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

import { CommandPaletteService } from '../../shared/services/command-palette.service';

/**
 * Phase D3 / Gap 157 — Visible quick-search affordance.
 *
 * The existing CommandPaletteService already gives the app a fuzzy
 * Ctrl+K command palette. Power users know about it; noobs don't.
 * This component is a top-pinned, always-visible search bar that
 * looks like an input but actually opens the same palette dialog —
 * the goal is to make the keyboard shortcut DISCOVERABLE without
 * forcing the dashboard to ship a second fuzzy-finder implementation.
 *
 * Click → opens the existing palette. Hovering reveals the keyboard
 * shortcut hint. The bar itself is read-only (the actual typing
 * happens inside the palette dialog).
 */
@Component({
  selector: 'app-quick-search-bar',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, MatIconModule, MatButtonModule, MatTooltipModule],
  template: `
    <button
      type="button"
      class="qsb"
      [matTooltip]="'Open the command palette (' + shortcutLabel + ')'"
      aria-label="Open command palette"
      (click)="onClick()"
    >
      <mat-icon class="qsb-icon" aria-hidden="true">search</mat-icon>
      <span class="qsb-placeholder">
        Search anything — pages, settings, entities…
      </span>
      <span class="qsb-shortcut" aria-hidden="true">
        <kbd>{{ shortcutLabel }}</kbd>
      </span>
    </button>
  `,
  styles: [`
    :host {
      display: block;
      /* Pinned to the top of the dashboard scroll area; 40px offset clears
         the freshness ribbon which is also sticky at top: 0 in the shell. */
      position: sticky;
      top: 40px;
      z-index: 5;
      background: var(--color-bg-page);
      padding: 8px 0;
      margin: -8px 0 0; /* reclaim the padding visually so layout doesn't shift */
    }
    .qsb {
      display: flex;
      align-items: center;
      gap: 8px;
      width: 100%;
      padding: 8px 12px;
      background: var(--color-bg-faint);
      border: var(--card-border);
      border-radius: var(--card-border-radius, 8px);
      font: inherit;
      cursor: pointer;
      color: var(--color-text-secondary);
      transition: border-color 0.15s ease, background-color 0.15s ease;
    }
    .qsb:hover {
      background: var(--color-bg-white);
      border-color: var(--color-primary);
    }
    .qsb:focus-visible {
      outline: 2px solid var(--color-primary);
      outline-offset: 2px;
    }
    .qsb-icon { color: var(--color-text-secondary); }
    .qsb-placeholder {
      flex: 1;
      text-align: left;
      font-size: 13px;
    }
    .qsb-shortcut kbd {
      display: inline-block;
      padding: 1px 6px;
      border: 1px solid var(--color-border);
      border-bottom-width: 2px;
      border-radius: 3px;
      background: var(--color-bg-white);
      font-size: 11px;
      font-family: var(--font-mono, monospace);
      color: var(--color-text-secondary);
    }
    @media (prefers-reduced-motion: reduce) {
      .qsb { transition: none; }
    }
  `],
})
export class QuickSearchBarComponent {
  private readonly palette = inject(CommandPaletteService);

  readonly shortcutLabel: string = this.detectShortcut();

  onClick(): void {
    this.palette.toggle();
  }

  private detectShortcut(): string {
    if (typeof navigator === 'undefined') return 'Ctrl+K';
    const ua = navigator.userAgent.toLowerCase();
    return ua.includes('mac') ? '⌘K' : 'Ctrl+K';
  }
}
