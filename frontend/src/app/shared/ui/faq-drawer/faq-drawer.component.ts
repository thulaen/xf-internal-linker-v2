import {
  ChangeDetectionStrategy,
  Component,
  inject,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';

import { FAQ, FaqEntry } from './faq.data';
import { FaqService } from './faq.service';

/**
 * Phase D3 / Gap 177 — Slide-in FAQ drawer.
 *
 * One-click panel listing the most-asked operator questions with
 * expandable answers. Triggered by the toolbar 💬 button. Distinct
 * from the Help Chatbot (Gap 78, free-text) and Glossary (Gap 69,
 * single-term definitions) — this is the curated answer list.
 */
@Component({
  selector: 'app-faq-drawer',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    FormsModule,
    MatIconModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatExpansionModule,
  ],
  template: `
    @if (open()) {
      <div class="fd-backdrop" (click)="onClose()" aria-hidden="true"></div>
      <aside
        class="fd-panel"
        role="dialog"
        aria-labelledby="fd-title"
        aria-modal="true"
      >
        <header class="fd-head">
          <h2 id="fd-title" class="fd-title">
            <mat-icon class="fd-title-icon">contact_support</mat-icon>
            FAQ
          </h2>
          <button
            mat-icon-button
            type="button"
            aria-label="Close FAQ"
            (click)="onClose()"
          >
            <mat-icon>close</mat-icon>
          </button>
        </header>
        <mat-form-field appearance="outline" class="fd-search">
          <mat-label>Search FAQ</mat-label>
          <mat-icon matPrefix>search</mat-icon>
          <input
            matInput
            autocomplete="off"
            type="search"
            [(ngModel)]="query"
            (ngModelChange)="onQueryChange($event)"
            placeholder="pause, ranking, broken…"
          />
        </mat-form-field>
        <div class="fd-list">
          @if (filtered().length === 0) {
            <p class="fd-empty">
              Nothing matched. Try the help chatbot (bottom-right) or open the
              glossary (Alt + G).
            </p>
          } @else {
            <mat-accordion>
              @for (entry of filtered(); track entry.id) {
                <mat-expansion-panel>
                  <mat-expansion-panel-header>
                    <mat-panel-title>{{ entry.question }}</mat-panel-title>
                  </mat-expansion-panel-header>
                  <p class="fd-answer">{{ entry.answer }}</p>
                </mat-expansion-panel>
              }
            </mat-accordion>
          }
        </div>
      </aside>
    }
  `,
  styles: [`
    .fd-backdrop {
      position: fixed; inset: 0;
      background: rgba(32, 33, 36, 0.32);
      z-index: 9990;
    }
    .fd-panel {
      position: fixed;
      top: 0; right: 0; bottom: 0;
      width: 420px;
      max-width: 92vw;
      background: var(--color-bg-white);
      border-left: var(--card-border);
      box-shadow: var(--shadow-lg, 0 8px 24px rgba(60, 64, 67, 0.2));
      z-index: 9991;
      display: flex;
      flex-direction: column;
    }
    .fd-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 16px;
      border-bottom: var(--card-border);
    }
    .fd-title {
      display: flex; align-items: center; gap: 8px;
      margin: 0;
      font-size: 18px;
      font-weight: 500;
    }
    .fd-title-icon { color: var(--color-primary); }
    .fd-search { margin: 16px; }
    .fd-list { flex: 1; overflow-y: auto; padding: 0 16px 16px; }
    .fd-answer {
      margin: 0;
      font-size: 13px;
      line-height: 1.6;
      color: var(--color-text-secondary);
    }
    .fd-empty {
      font-size: 13px;
      font-style: italic;
      color: var(--color-text-secondary);
    }
  `],
})
export class FaqDrawerComponent {
  private readonly faqSvc = inject(FaqService);

  readonly open = this.faqSvc.open;
  readonly all = FAQ;
  query = '';
  private readonly _query = signal('');

  readonly filtered = signal<readonly FaqEntry[]>(FAQ);

  toggle(): void {
    this.faqSvc.toggle();
  }

  onClose(): void {
    this.faqSvc.closeDrawer();
  }

  onQueryChange(next: string): void {
    this._query.set(next ?? '');
    const q = (next ?? '').trim().toLowerCase();
    if (q.length === 0) {
      this.filtered.set(FAQ);
      return;
    }
    this.filtered.set(
      FAQ.filter(
        (e) =>
          e.question.toLowerCase().includes(q) ||
          e.answer.toLowerCase().includes(q),
      ),
    );
  }
}
