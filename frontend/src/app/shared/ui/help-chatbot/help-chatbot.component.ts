import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnInit,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { NavigationEnd, Router } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatTooltipModule } from '@angular/material/tooltip';
import { filter } from 'rxjs';

import { GLOSSARY, GlossaryEntry } from '../glossary/glossary.data';

/**
 * Phase D2 / Gap 78 — Persistent Help Chatbot FAB.
 *
 * A bottom-right floating button that opens a small chat-style panel.
 * Answers questions "grounded in repo docs" — the v1 grounding is the
 * shared GLOSSARY bank, which covers every term we've documented
 * in-app. A future session can swap the frontend-only lookup for a
 * real backend RAG endpoint without changing the UI contract.
 *
 * Design notes:
 *   - Not on the dashboard (the dashboard already has Command
 *     Suggestions and Task-to-Page Router for intent routing).
 *   - On every OTHER page, shown as a bottom-right FAB. Click opens
 *     an inline panel, not a dialog, so the user can keep reading the
 *     page they're on while chatting.
 *   - Purely client-side matching for now: substring/startsWith over
 *     glossary terms + definitions, returning the best 1-3 hits.
 *   - "No match" yields a polite "Try rephrasing" plus a link to the
 *     full glossary drawer.
 */

interface ChatExchange {
  /** 'user' = typed query; 'bot' = response. */
  role: 'user' | 'bot';
  text: string;
  /** Bot responses may include reference term(s). */
  refs?: readonly GlossaryEntry[];
}

@Component({
  selector: 'app-help-chatbot',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatIconModule,
    MatTooltipModule,
  ],
  template: `
    @if (showFab()) {
      <button
        mat-fab
        class="hc-fab"
        color="primary"
        [matTooltip]="'Ask for help on any term'"
        aria-label="Open help chatbot"
        (click)="toggleOpen()"
      >
        <mat-icon>{{ open() ? 'close' : 'question_answer' }}</mat-icon>
      </button>
      @if (open()) {
        <aside
          class="hc-panel"
          role="dialog"
          aria-labelledby="hc-title"
        >
          <header class="hc-head">
            <h3 id="hc-title" class="hc-title">
              <mat-icon aria-hidden="true">smart_toy</mat-icon>
              Help
            </h3>
            <button
              mat-icon-button
              type="button"
              aria-label="Close help"
              (click)="close()"
            >
              <mat-icon>close</mat-icon>
            </button>
          </header>
          <div class="hc-log" role="log" aria-live="polite">
            @if (history().length === 0) {
              <p class="hc-empty">
                Ask me what a term means or how something works. Try
                "what is an orphan page" or "embedding".
              </p>
            }
            @for (msg of history(); track $index) {
              <div
                class="hc-msg"
                [class.hc-msg-user]="msg.role === 'user'"
                [class.hc-msg-bot]="msg.role === 'bot'"
              >
                <p class="hc-msg-text">{{ msg.text }}</p>
                @if (msg.refs && msg.refs.length > 0) {
                  <dl class="hc-refs">
                    @for (ref of msg.refs; track ref.term) {
                      <div class="hc-ref">
                        <dt>{{ ref.term }}</dt>
                        <dd>{{ ref.definition }}</dd>
                      </div>
                    }
                  </dl>
                }
              </div>
            }
          </div>
          <form class="hc-form" (submit)="onSubmit($event)">
            <mat-form-field appearance="outline" class="hc-field">
              <mat-label>Ask a question</mat-label>
              <input
                matInput
                autocomplete="off"
                type="text"
                [(ngModel)]="query"
                name="hc-query"
                placeholder="e.g. what is a silo?"
              />
            </mat-form-field>
            <button
              mat-flat-button
              color="primary"
              type="submit"
              [disabled]="query.trim().length === 0"
            >
              Send
              <mat-icon iconPositionEnd>send</mat-icon>
            </button>
          </form>
        </aside>
      }
    }
  `,
  styles: [`
    .hc-fab {
      position: fixed;
      bottom: 24px;
      right: 24px;
      z-index: 980;
      box-shadow: var(--shadow-md);
    }
    .hc-panel {
      position: fixed;
      bottom: 96px;
      right: 24px;
      width: 340px;
      max-width: calc(100vw - 48px);
      height: 420px;
      max-height: calc(100vh - 140px);
      background: var(--color-bg-white);
      border: var(--card-border);
      border-radius: var(--card-border-radius, 8px);
      box-shadow: var(--shadow-lg, 0 8px 24px rgba(60, 64, 67, 0.2));
      z-index: 980;
      display: flex;
      flex-direction: column;
      animation: hc-rise 0.15s ease;
    }
    .hc-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 10px 12px;
      border-bottom: var(--card-border);
      background: var(--color-bg-faint);
    }
    .hc-title {
      display: flex;
      align-items: center;
      gap: 6px;
      margin: 0;
      font-size: 14px;
      font-weight: 500;
      color: var(--color-text-primary);
    }
    .hc-title mat-icon {
      color: var(--color-primary);
      font-size: 18px;
      width: 18px;
      height: 18px;
    }
    .hc-log {
      flex: 1;
      overflow-y: auto;
      padding: 12px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .hc-empty {
      font-size: 12px;
      color: var(--color-text-secondary);
      font-style: italic;
      margin: 0;
    }
    .hc-msg {
      padding: 8px 10px;
      border-radius: 8px;
      font-size: 12px;
      line-height: 1.5;
    }
    .hc-msg-user {
      background: var(--color-primary);
      color: var(--color-on-primary, #ffffff);
      align-self: flex-end;
      max-width: 85%;
    }
    .hc-msg-bot {
      background: var(--color-bg-faint);
      color: var(--color-text-primary);
      align-self: flex-start;
      max-width: 95%;
    }
    .hc-msg-text { margin: 0; }
    .hc-refs {
      margin: 6px 0 0;
      padding: 0;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .hc-ref {
      padding: 6px;
      background: var(--color-bg-white);
      border-radius: 4px;
      border: var(--card-border);
    }
    .hc-ref dt {
      margin: 0;
      font-weight: 500;
      font-size: 11px;
      color: var(--color-text-primary);
    }
    .hc-ref dd {
      margin: 2px 0 0;
      font-size: 11px;
      color: var(--color-text-secondary);
      line-height: 1.4;
    }
    .hc-form {
      display: flex;
      align-items: flex-start;
      gap: 6px;
      padding: 8px 12px;
      border-top: var(--card-border);
    }
    .hc-field { flex: 1; }
    @keyframes hc-rise {
      from { transform: translateY(8px); opacity: 0; }
      to   { transform: translateY(0);   opacity: 1; }
    }
    @media (prefers-reduced-motion: reduce) {
      .hc-panel { animation: none; }
    }
  `],
})
export class HelpChatbotComponent implements OnInit {
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  readonly open = signal(false);
  readonly history = signal<readonly ChatExchange[]>([]);
  readonly showFab = signal(true);
  query = '';

  ngOnInit(): void {
    this.showFab.set(this.shouldShow(this.router.url));
    this.router.events
      .pipe(
        filter((e) => e instanceof NavigationEnd),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((e) => {
        this.showFab.set(this.shouldShow((e as NavigationEnd).urlAfterRedirects));
      });
  }

  toggleOpen(): void {
    this.open.set(!this.open());
  }

  close(): void {
    this.open.set(false);
  }

  onSubmit(event: Event): void {
    event.preventDefault();
    const q = this.query.trim();
    if (!q) return;
    this.query = '';
    const reply = this.answer(q);
    this.history.set([
      ...this.history(),
      { role: 'user', text: q },
      reply,
    ]);
  }

  /** Matches the query against the GLOSSARY bank — substring in term
   *  or definition, term start gets a higher score. Returns the top
   *  three matches or a polite "try rephrasing" message. */
  private answer(query: string): ChatExchange {
    const q = query.toLowerCase();
    const scored = GLOSSARY.map((e) => {
      const term = e.term.toLowerCase();
      const def = e.definition.toLowerCase();
      let score = 0;
      if (term.startsWith(q)) score += 5;
      else if (term.includes(q)) score += 3;
      if (def.includes(q)) score += 1;
      return { entry: e, score };
    })
      .filter((s) => s.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, 3)
      .map((s) => s.entry);

    if (scored.length === 0) {
      return {
        role: 'bot',
        text:
          "I don't have that term in my glossary yet. Try rephrasing with a shorter word, or open the full glossary (Alt + G).",
      };
    }

    return {
      role: 'bot',
      text:
        scored.length === 1
          ? 'Here\'s what I found:'
          : `Here are the ${scored.length} best matches:`,
      refs: scored,
    };
  }

  /** Hidden on the dashboard (dashboard has its own intent tools)
   *  and the login page. */
  private shouldShow(url: string): boolean {
    const noQs = (url ?? '').split('?')[0].split('#')[0];
    if (noQs === '/' || noQs.startsWith('/dashboard')) return false;
    if (noQs.startsWith('/login')) return false;
    return true;
  }
}
