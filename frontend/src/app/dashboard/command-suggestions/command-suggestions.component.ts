import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { MatAutocompleteModule } from '@angular/material/autocomplete';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';

/**
 * Phase D1 / Gap 57 — Command Suggestions dropdown.
 *
 * "I want to <type intent>" — the component fuzzy-matches the user's
 * typed intent against a curated list of verbs and suggests both a
 * route and a rough action description. Distinct from:
 *
 *   - The global Ctrl+K command palette (which lists every route/entity).
 *   - The `TaskToPageRouter` component which uses a <select> of preset
 *     intents, not free-text.
 *
 * Matching is a simple substring + prefix-weighted score, intentionally
 * naive — noobs type "sync" and expect "run a sync" to surface first.
 * No ML, no backend, no network.
 */

interface Intent {
  keywords: readonly string[];
  action: string;
  route: string;
  fragment?: string;
  icon: string;
}

const INTENT_LIBRARY: readonly Intent[] = [
  { keywords: ['sync', 'import', 'fetch', 'pull'], action: 'Run an import / sync', route: '/jobs', icon: 'sync' },
  { keywords: ['review', 'approve', 'pending', 'suggestions'], action: 'Review pending suggestions', route: '/review', icon: 'rate_review' },
  { keywords: ['broken', 'link', 'fix', 'scan'], action: 'Scan for broken links', route: '/link-health', icon: 'link_off' },
  { keywords: ['health', 'status', 'system', 'services'], action: 'Open the System Health page', route: '/health', icon: 'health_and_safety' },
  { keywords: ['alerts', 'warning', 'notifications'], action: 'Open the Alerts page', route: '/alerts', icon: 'notifications' },
  { keywords: ['graph', 'network', 'map', 'topology'], action: 'Explore the Link Graph', route: '/graph', icon: 'account_tree' },
  { keywords: ['analytics', 'traffic', 'impressions', 'clicks'], action: 'Open Analytics reports', route: '/analytics', icon: 'bar_chart' },
  { keywords: ['hubs', 'behavioral', 'cluster'], action: 'Explore Behavioral Hubs', route: '/behavioral-hubs', icon: 'hub' },
  { keywords: ['performance', 'benchmark', 'speed'], action: 'Open Performance benchmarks', route: '/performance', icon: 'speed' },
  { keywords: ['errors', 'bugs', 'exceptions', 'log'], action: 'Open the Error Log', route: '/error-log', icon: 'bug_report' },
  { keywords: ['crawl', 'sitemap', 'discover'], action: 'Start a web crawl', route: '/crawler', icon: 'travel_explore' },
  { keywords: ['settings', 'configure', 'weights', 'theme', 'appearance'], action: 'Open Settings', route: '/settings', icon: 'settings' },
  { keywords: ['pipeline', 'run', 'generate'], action: 'Run the pipeline', route: '/dashboard', fragment: 'today-focus', icon: 'play_arrow' },
  { keywords: ['pause', 'stop', 'halt'], action: 'Pause everything (master switch)', route: '/dashboard', fragment: 'today-focus', icon: 'pause_circle' },
];

@Component({
  selector: 'app-command-suggestions',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    FormsModule,
    RouterLink,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatAutocompleteModule,
    MatIconModule,
  ],
  template: `
    <mat-card class="cs-card">
      <mat-card-header>
        <mat-icon mat-card-avatar class="cs-avatar">psychology</mat-icon>
        <mat-card-title>I want to…</mat-card-title>
        <mat-card-subtitle>Type your intent, we'll suggest where to go</mat-card-subtitle>
      </mat-card-header>
      <mat-card-content>
        <mat-form-field appearance="outline" class="cs-field">
          <mat-label>What do you want to do?</mat-label>
          <input
            matInput
            autocomplete="off"
            [matAutocomplete]="intents"
            [(ngModel)]="query"
            (ngModelChange)="onQueryChange($event)"
            placeholder="e.g. sync content, find broken links…"
          />
          <mat-autocomplete #intents="matAutocomplete">
            @for (m of matches(); track m.action) {
              <mat-option
                [value]="m.action"
                [routerLink]="m.route"
                [fragment]="m.fragment ?? undefined"
                (click)="onPick(m)"
              >
                <mat-icon class="cs-option-icon">{{ m.icon }}</mat-icon>
                <span>{{ m.action }}</span>
              </mat-option>
            }
            @if (matches().length === 0 && query.length > 0) {
              <mat-option disabled>
                <span class="cs-no-match">No match — try a shorter word like "sync" or "broken".</span>
              </mat-option>
            }
          </mat-autocomplete>
        </mat-form-field>
      </mat-card-content>
    </mat-card>
  `,
  styles: [`
    .cs-card { height: 100%; }
    .cs-avatar {
      background: var(--color-primary);
      color: var(--color-on-primary, #ffffff);
    }
    .cs-field { width: 100%; }
    .cs-option-icon {
      margin-right: 8px;
      color: var(--color-text-secondary);
      font-size: 18px;
      width: 18px;
      height: 18px;
      vertical-align: middle;
    }
    .cs-no-match {
      color: var(--color-text-secondary);
      font-style: italic;
    }
  `],
})
export class CommandSuggestionsComponent {
  private readonly router = inject(Router);

  query = '';
  readonly matches = signal<readonly Intent[]>([]);

  onQueryChange(raw: string): void {
    const q = (raw ?? '').trim().toLowerCase();
    if (q.length === 0) {
      this.matches.set([]);
      return;
    }
    const scored = INTENT_LIBRARY.map((intent) => {
      let score = 0;
      for (const kw of intent.keywords) {
        if (kw.startsWith(q)) score += 3;
        else if (kw.includes(q)) score += 2;
      }
      // Also reward matches in the verbose action text.
      if (intent.action.toLowerCase().includes(q)) score += 1;
      return { intent, score };
    }).filter((s) => s.score > 0);
    scored.sort((a, b) => b.score - a.score);
    this.matches.set(scored.slice(0, 5).map((s) => s.intent));
  }

  onPick(intent: Intent): void {
    // The routerLink on the mat-option already navigates; we only have
    // to reset the input so the card is ready for the next intent.
    this.query = '';
    this.matches.set([]);
  }
}
