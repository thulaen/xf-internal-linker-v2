import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';

/**
 * Phase D1 / Gap 56 — One-question-per-day Quiz card.
 *
 * Teaches one vocabulary / concept item in ≤10 seconds, picks a new
 * question each calendar day (local time), and tracks a visit streak.
 *
 * Design:
 *   - Question bank is frontend-static (no network). Keeping it in the
 *     bundle means quiz works offline and adds zero backend load. New
 *     questions land in a future session by extending `QUESTION_BANK`.
 *   - The "day" key is `YYYY-MM-DD` in the user's local timezone so
 *     someone crossing a date boundary mid-session sees a fresh question.
 *   - Answering reveals the explanation. There's no score / punishment —
 *     this is a teaching card, not a gamified quiz.
 *   - Streak increments once per distinct day visited. Persists in
 *     localStorage under `xfil_quiz_streak`; last-visit day under
 *     `xfil_quiz_last_visit`.
 */

interface QuizQuestion {
  id: string;
  prompt: string;
  options: string[];
  correctIndex: number;
  explanation: string;
}

/**
 * Ordered deterministically by id. Day index = (days-since-epoch) %
 * length, so the same user sees the same rotation on the same day on
 * any device (within their timezone).
 */
const QUESTION_BANK: readonly QuizQuestion[] = [
  {
    id: 'q-anchor',
    prompt: "What is an \"anchor\" in internal linking?",
    options: [
      'The HTML metadata at the top of a page',
      'The visible text a user clicks to follow a link',
      'The URL fragment after the # symbol',
    ],
    correctIndex: 1,
    explanation:
      'Anchor text is the clickable text of a hyperlink. Good anchors describe what the user will find on the other side.',
  },
  {
    id: 'q-orphan',
    prompt: "What is an \"orphan page\"?",
    options: [
      'A page with no internal links pointing to it',
      'A page whose owner left the team',
      'A page older than 5 years',
    ],
    correctIndex: 0,
    explanation:
      "Orphan pages have no inbound links, so users and crawlers can't find them from anywhere on your site.",
  },
  {
    id: 'q-silo',
    prompt: 'In SEO, a "silo" is:',
    options: [
      'A backup copy of your database',
      'A topic cluster with internal cross-links',
      'A disabled plugin',
    ],
    correctIndex: 1,
    explanation:
      'A silo groups related pages into a topic cluster and cross-links them, building topical authority in that subject.',
  },
  {
    id: 'q-embedding',
    prompt: 'What does an "embedding" represent?',
    options: [
      'A password stored in a cookie',
      'A numeric vector capturing the meaning of text',
      'An iframe from a third-party site',
    ],
    correctIndex: 1,
    explanation:
      'An embedding is a list of numbers that encodes the meaning of a piece of text so similar texts land near each other mathematically.',
  },
  {
    id: 'q-pagerank',
    prompt: 'PageRank measures:',
    options: [
      'How many visitors a page gets per day',
      'Link-based authority flowing through the graph',
      'A page\'s loading speed',
    ],
    correctIndex: 1,
    explanation:
      'PageRank treats every link as a vote. Pages with many high-authority inbound links end up with higher PageRank themselves.',
  },
  {
    id: 'q-quarantine',
    prompt: 'When a job is "quarantined", it means:',
    options: [
      'It finished successfully and is archived',
      'It hit a repeated failure and is paused pending review',
      'It is waiting for another job to finish',
    ],
    correctIndex: 1,
    explanation:
      "Quarantined jobs failed too many times in a row. The system isolates them so you can inspect the root cause before retrying.",
  },
  {
    id: 'q-precision-recall',
    prompt:
      'If a suggestion engine has high precision but low recall, it:',
    options: [
      'Gives many accurate suggestions AND finds most of what exists',
      'Gives few accurate suggestions, missing a lot',
      "Rarely wrong about what it suggests, but misses a lot of opportunities",
    ],
    correctIndex: 2,
    explanation:
      'Precision = "when I guess, I\'m usually right." Recall = "I find most of what\'s there." High-precision/low-recall means accurate picks, but lots of missed chances.',
  },
  {
    id: 'q-stale',
    prompt: "A page is marked \"stale\" when:",
    options: [
      'It has a typo in the title',
      "Its analytics or sync data is older than the configured threshold",
      'It has more than 100 outbound links',
    ],
    correctIndex: 1,
    explanation:
      "Stale data means the cached copy is older than what we trust for decisions. The dashboard flags it so you don't act on old numbers.",
  },
  {
    id: 'q-cooccurrence',
    prompt: 'Session co-occurrence measures:',
    options: [
      'How often two pages are visited in the same session',
      'Whether two pages share a URL prefix',
      'The word count overlap between two pages',
    ],
    correctIndex: 0,
    explanation:
      'Co-occurrence is a behavioral signal — pages users actually visit together in one session are likely topically related to readers.',
  },
  {
    id: 'q-cardinality',
    prompt:
      'Why do we cap candidate pages per destination during ranking?',
    options: [
      'To save RAM during the ranking pass',
      "Because it doesn't matter which order the top pick comes out in",
      'To keep the Postgres disk usage down',
    ],
    correctIndex: 0,
    explanation:
      "Without a cap, every destination would score against every page — an N*M blowup. Capping each destination's candidate pool keeps it linear.",
  },
];

const STREAK_KEY = 'xfil_quiz_streak';
const LAST_VISIT_KEY = 'xfil_quiz_last_visit';
const ANSWERED_KEY_PREFIX = 'xfil_quiz_answered.';

@Component({
  selector: 'app-daily-quiz',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, MatCardModule, MatIconModule, MatButtonModule],
  template: `
    <mat-card class="quiz-card">
      <mat-card-header>
        <mat-icon mat-card-avatar class="quiz-avatar">quiz</mat-icon>
        <mat-card-title>Daily learning</mat-card-title>
        <mat-card-subtitle>
          Streak: {{ streak() }} day{{ streak() === 1 ? '' : 's' }}
        </mat-card-subtitle>
      </mat-card-header>
      <mat-card-content>
        <p class="quiz-prompt">{{ question().prompt }}</p>
        <div class="quiz-options" role="radiogroup" [attr.aria-label]="question().prompt">
          @for (opt of question().options; track opt; let i = $index) {
            <button
              type="button"
              class="quiz-option"
              [class.quiz-correct]="answered() && i === question().correctIndex"
              [class.quiz-wrong]="answered() && selectedIndex() === i && i !== question().correctIndex"
              [disabled]="answered()"
              [attr.aria-pressed]="selectedIndex() === i"
              [attr.aria-checked]="selectedIndex() === i"
              role="radio"
              (click)="answer(i)"
            >
              <span class="quiz-option-letter">{{ letter(i) }}</span>
              <span class="quiz-option-text">{{ opt }}</span>
            </button>
          }
        </div>
        @if (answered()) {
          <p class="quiz-explanation">
            <mat-icon class="quiz-exp-icon">lightbulb</mat-icon>
            <span>{{ question().explanation }}</span>
          </p>
        }
      </mat-card-content>
    </mat-card>
  `,
  styles: [`
    .quiz-card { height: 100%; }
    .quiz-avatar {
      background: var(--color-primary);
      color: var(--color-on-primary, #ffffff);
    }
    .quiz-prompt {
      font-weight: 500;
      font-size: 14px;
      margin: 0 0 12px;
      color: var(--color-text-primary);
      line-height: 1.5;
    }
    .quiz-options {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .quiz-option {
      display: flex;
      align-items: flex-start;
      gap: 8px;
      padding: 10px 12px;
      border: var(--card-border);
      border-radius: var(--card-border-radius, 8px);
      background: var(--color-bg-white);
      text-align: left;
      cursor: pointer;
      font: inherit;
      color: var(--color-text-primary);
      transition: all 0.15s ease;
    }
    .quiz-option:hover:not(:disabled) {
      background: var(--color-bg-faint);
      border-color: var(--color-primary);
    }
    .quiz-option:disabled { cursor: default; }
    .quiz-option.quiz-correct {
      border-color: var(--color-success, #1e8e3e);
      background: var(--color-success-light, rgba(30, 142, 62, 0.08));
    }
    .quiz-option.quiz-wrong {
      border-color: var(--color-error);
      background: var(--color-error-50, rgba(217, 48, 37, 0.06));
    }
    .quiz-option-letter {
      flex-shrink: 0;
      width: 20px;
      height: 20px;
      border-radius: 50%;
      background: var(--color-bg-faint);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 11px;
      font-weight: 600;
      color: var(--color-text-secondary);
    }
    .quiz-option-text {
      font-size: 13px;
      line-height: 1.4;
    }
    .quiz-explanation {
      display: flex;
      gap: 8px;
      align-items: flex-start;
      margin: 12px 0 0;
      padding: 10px 12px;
      background: var(--color-blue-50, rgba(26, 115, 232, 0.08));
      border-radius: var(--card-border-radius, 8px);
      font-size: 12px;
      line-height: 1.5;
      color: var(--color-text-primary);
    }
    .quiz-exp-icon {
      color: var(--color-primary);
      font-size: 18px;
      width: 18px;
      height: 18px;
      flex-shrink: 0;
    }
  `],
})
export class DailyQuizComponent implements OnInit {
  readonly streak = signal<number>(0);
  readonly question = signal<QuizQuestion>(QUESTION_BANK[0]);
  readonly answered = signal<boolean>(false);
  readonly selectedIndex = signal<number | null>(null);

  ngOnInit(): void {
    const today = this.localDayKey();
    this.question.set(this.pickForDay(today));

    // Restore per-question answered state so we don't reset when the
    // user navigates away and back on the same day.
    try {
      const answeredKey = ANSWERED_KEY_PREFIX + today;
      const raw = localStorage.getItem(answeredKey);
      if (raw !== null) {
        const parsed = Number.parseInt(raw, 10);
        if (Number.isFinite(parsed)) {
          this.selectedIndex.set(parsed);
          this.answered.set(true);
        }
      }
    } catch {
      // No-op.
    }

    // Streak bookkeeping: increment once per distinct day visited.
    this.streak.set(this.bumpStreak(today));
  }

  answer(idx: number): void {
    if (this.answered()) return;
    this.selectedIndex.set(idx);
    this.answered.set(true);
    try {
      localStorage.setItem(
        ANSWERED_KEY_PREFIX + this.localDayKey(),
        String(idx),
      );
    } catch {
      // In-memory only is fine.
    }
  }

  letter(idx: number): string {
    return String.fromCharCode(65 + idx); // A, B, C...
  }

  // ── internals ──────────────────────────────────────────────────────

  private localDayKey(): string {
    const d = new Date();
    const y = d.getFullYear();
    const m = (d.getMonth() + 1).toString().padStart(2, '0');
    const day = d.getDate().toString().padStart(2, '0');
    return `${y}-${m}-${day}`;
  }

  private pickForDay(dayKey: string): QuizQuestion {
    // Rotate deterministically by days-since-epoch.
    const msPerDay = 24 * 60 * 60 * 1000;
    const epochDays = Math.floor(Date.parse(dayKey + 'T00:00:00Z') / msPerDay);
    const idx = ((epochDays % QUESTION_BANK.length) + QUESTION_BANK.length) % QUESTION_BANK.length;
    return QUESTION_BANK[idx];
  }

  private bumpStreak(today: string): number {
    try {
      const last = localStorage.getItem(LAST_VISIT_KEY);
      const currentStreak = Number.parseInt(
        localStorage.getItem(STREAK_KEY) ?? '0',
        10,
      ) || 0;

      if (last === today) {
        // Same day — don't change.
        return currentStreak;
      }

      // Determine yesterday's local day key for streak continuity.
      const d = new Date();
      d.setDate(d.getDate() - 1);
      const y = d.getFullYear();
      const m = (d.getMonth() + 1).toString().padStart(2, '0');
      const day = d.getDate().toString().padStart(2, '0');
      const yesterday = `${y}-${m}-${day}`;

      const next = last === yesterday ? currentStreak + 1 : 1;
      localStorage.setItem(STREAK_KEY, String(next));
      localStorage.setItem(LAST_VISIT_KEY, today);
      return next;
    } catch {
      return 0;
    }
  }
}
