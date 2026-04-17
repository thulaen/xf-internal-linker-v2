import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';

import { GLOSSARY, GlossaryEntry } from './glossary.data';
import { GlossaryService } from './glossary.service';

/**
 * Phase D2 / Gap 69 — Slide-out Glossary drawer.
 *
 * Opens via the toolbar 📖 button or the global ALT+G shortcut. Lists
 * every term in the GLOSSARY bank, alphabetised, with an inline search
 * box that filters as the user types.
 *
 * Implementation is a fixed-position panel rather than mat-sidenav so
 * it can overlay any page (login, error, etc.) without restructuring
 * the global shell.
 */
@Component({
  selector: 'app-glossary-drawer',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    FormsModule,
    MatIconModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
  ],
  template: `
    @if (open()) {
      <div
        class="gd-backdrop"
        (click)="onClose()"
        aria-hidden="true"
      ></div>
      <aside
        class="gd-panel"
        role="dialog"
        aria-labelledby="gd-title"
        aria-modal="true"
      >
        <header class="gd-header">
          <h2 id="gd-title" class="gd-title">
            <mat-icon class="gd-title-icon">menu_book</mat-icon>
            Glossary
          </h2>
          <button
            mat-icon-button
            type="button"
            class="gd-close"
            aria-label="Close glossary"
            (click)="onClose()"
          >
            <mat-icon>close</mat-icon>
          </button>
        </header>

        <mat-form-field appearance="outline" class="gd-search">
          <mat-label>Search terms</mat-label>
          <mat-icon matPrefix>search</mat-icon>
          <input
            matInput
            autocomplete="off"
            type="search"
            [(ngModel)]="query"
            (ngModelChange)="onQueryChange($event)"
            placeholder="anchor, embedding, hub…"
          />
        </mat-form-field>

        <div class="gd-list" role="list">
          @if (filtered().length === 0) {
            <p class="gd-empty">
              No matches. Try a shorter query, or ask in chat — we may need to
              add this term.
            </p>
          } @else {
            @for (entry of filtered(); track entry.term) {
              <article class="gd-entry" role="listitem">
                <header class="gd-entry-head">
                  <span class="gd-term">{{ entry.term }}</span>
                  @if (entry.category) {
                    <span class="gd-cat">{{ entry.category }}</span>
                  }
                </header>
                <p class="gd-def">{{ entry.definition }}</p>
              </article>
            }
          }
        </div>

        <footer class="gd-footer">
          {{ filtered().length }} of {{ all.length }} terms
          <span class="gd-shortcut">
            Press <kbd>Alt</kbd> + <kbd>G</kbd> to toggle this drawer
          </span>
        </footer>
      </aside>
    }
  `,
  styles: [`
    .gd-backdrop {
      position: fixed;
      inset: 0;
      background: rgba(32, 33, 36, 0.32);
      z-index: 9990;
      animation: gd-fade-in 0.15s ease;
    }
    .gd-panel {
      position: fixed;
      top: 0;
      right: 0;
      bottom: 0;
      width: 380px;
      max-width: 90vw;
      background: var(--color-bg-white);
      border-left: var(--card-border);
      box-shadow: var(--shadow-lg, 0 8px 24px rgba(60, 64, 67, 0.2));
      z-index: 9991;
      display: flex;
      flex-direction: column;
      animation: gd-slide-in 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .gd-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 16px;
      border-bottom: var(--card-border);
      flex-shrink: 0;
    }
    .gd-title {
      display: flex;
      align-items: center;
      gap: 8px;
      margin: 0;
      font-size: 18px;
      font-weight: 500;
      color: var(--color-text-primary);
    }
    .gd-title-icon {
      color: var(--color-primary);
    }
    .gd-search {
      margin: 16px;
      flex-shrink: 0;
    }
    .gd-list {
      flex: 1;
      overflow-y: auto;
      padding: 0 16px 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .gd-entry {
      padding: 12px;
      border: var(--card-border);
      border-radius: var(--card-border-radius, 8px);
      background: var(--color-bg-faint);
    }
    .gd-entry-head {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 4px;
    }
    .gd-term {
      font-weight: 500;
      font-size: 14px;
      color: var(--color-text-primary);
    }
    .gd-cat {
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 0.4px;
      color: var(--color-text-secondary);
      background: var(--color-bg-white);
      padding: 2px 6px;
      border-radius: 10px;
      border: var(--card-border);
    }
    .gd-def {
      margin: 0;
      font-size: 13px;
      line-height: 1.5;
      color: var(--color-text-secondary);
    }
    .gd-empty {
      font-size: 13px;
      color: var(--color-text-secondary);
      font-style: italic;
      margin: 16px 0;
    }
    .gd-footer {
      padding: 12px 16px;
      border-top: var(--card-border);
      font-size: 11px;
      color: var(--color-text-secondary);
      display: flex;
      flex-direction: column;
      gap: 4px;
      flex-shrink: 0;
    }
    .gd-shortcut kbd {
      display: inline-block;
      padding: 1px 5px;
      border: 1px solid var(--color-border);
      border-bottom-width: 2px;
      border-radius: 3px;
      background: var(--color-bg-faint);
      font-size: 10px;
      font-family: var(--font-mono, monospace);
    }
    @keyframes gd-fade-in {
      from { opacity: 0; }
      to { opacity: 1; }
    }
    @keyframes gd-slide-in {
      from { transform: translateX(100%); }
      to { transform: translateX(0); }
    }
    @media (prefers-reduced-motion: reduce) {
      .gd-backdrop,
      .gd-panel {
        animation: none;
      }
    }
  `],
})
export class GlossaryDrawerComponent {
  private readonly glossary = inject(GlossaryService);

  readonly open = this.glossary.open;
  readonly all = GLOSSARY;
  readonly query = '';

  private readonly _query = signal('');

  readonly filtered = computed<readonly GlossaryEntry[]>(() => {
    const q = this._query().trim().toLowerCase();
    const sorted = [...this.all].sort((a, b) => a.term.localeCompare(b.term));
    if (q.length === 0) return sorted;
    return sorted.filter(
      (e) =>
        e.term.toLowerCase().includes(q) ||
        e.definition.toLowerCase().includes(q),
    );
  });

  onQueryChange(next: string): void {
    this._query.set(next ?? '');
  }

  onClose(): void {
    this.glossary.closeDrawer();
  }
}
