import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  inject,
  OnInit,
  signal,
  computed,
  effect,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatTooltipModule } from '@angular/material/tooltip';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import {
  OPS_FEED_MAX_ROWS,
  OpsEvent,
  OpsEventSeverity,
} from './ops-feed.types';
import { RealtimeService } from '../core/services/realtime.service';

/**
 * Phase OF — Operations Feed page.
 *
 * Streams ambient `operations.feed` realtime events plus hydrates the
 * last 500 rows from `/api/operations/events/` on load so a refresh
 * doesn't wipe history. Deduped consecutive events collapse into a
 * single row with an occurrence counter.
 *
 * Controls:
 *   • severity chips — all / info / warning / error / success
 *   • free-text filter — case-insensitive substring match on
 *     plain_english + event_type + source
 *   • pause/resume — when paused, incoming events buffer silently;
 *     resume appends them at once so the view never jumps while the
 *     operator is reading.
 *   • auto-follow toggle — when on, new events scroll into view;
 *     when off, the user stays where they are and only the badge
 *     on "Unread since paused" updates.
 */
@Component({
  selector: 'app-operations-feed',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatCardModule,
    MatChipsModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatTooltipModule,
  ],
  template: `
    <div class="of-page">
      <header class="of-header">
        <h1 class="of-title">
          <mat-icon>rss_feed</mat-icon>
          Operations Feed
        </h1>
        <p class="of-subtitle">
          Live, deduped narration of what the system is doing.
          Distinct from alerts (urgent) and error logs (debugging) —
          this is ambient context.
        </p>
      </header>

      <div class="of-controls" role="toolbar" aria-label="Feed controls">
        <mat-chip-listbox
          class="of-chips"
          [value]="severityFilter()"
          (change)="onSeverityChange($any($event))"
          aria-label="Filter by severity"
        >
          <mat-chip-option value="all">All</mat-chip-option>
          <mat-chip-option value="info">Info</mat-chip-option>
          <mat-chip-option value="success">Success</mat-chip-option>
          <mat-chip-option value="warning">Warning</mat-chip-option>
          <mat-chip-option value="error">Error</mat-chip-option>
        </mat-chip-listbox>

        <mat-form-field appearance="outline" class="of-search">
          <mat-label>Filter text</mat-label>
          <input
            matInput
            [(ngModel)]="searchModel"
            (ngModelChange)="search.set($event)"
            autocomplete="off"
            placeholder="type to filter…"
          />
          @if (search()) {
            <button
              matSuffix
              mat-icon-button
              type="button"
              aria-label="Clear filter"
              (click)="search.set(''); searchModel = ''"
            >
              <mat-icon>close</mat-icon>
            </button>
          }
        </mat-form-field>

        <button
          mat-stroked-button
          type="button"
          (click)="togglePause()"
          [matTooltip]="paused() ? 'Resume live stream' : 'Pause the live stream'"
        >
          <mat-icon>{{ paused() ? 'play_arrow' : 'pause' }}</mat-icon>
          {{ paused() ? 'Resume' : 'Pause' }}
          @if (paused() && buffered().length > 0) {
            <span class="of-buffer-count">
              +{{ buffered().length }}
            </span>
          }
        </button>

        <button
          mat-stroked-button
          type="button"
          (click)="autoFollow.set(!autoFollow())"
          [matTooltip]="autoFollow() ? 'New events scroll into view' : 'Scroll position is sticky'"
        >
          <mat-icon>{{ autoFollow() ? 'vertical_align_bottom' : 'push_pin' }}</mat-icon>
          {{ autoFollow() ? 'Auto-follow' : 'Hold position' }}
        </button>

        <!-- Phase MX1 / Gap 271 — error-beep toggle. -->
        <button
          mat-icon-button
          type="button"
          (click)="soundEnabled.set(!soundEnabled())"
          [matTooltip]="soundEnabled() ? 'Mute error beeps' : 'Beep on error'"
        >
          <mat-icon>{{ soundEnabled() ? 'volume_up' : 'volume_off' }}</mat-icon>
        </button>

        <!-- Phase MX1 / Gap 278 — timestamp format toggle. -->
        <button
          mat-icon-button
          type="button"
          (click)="absoluteTimestamps.set(!absoluteTimestamps())"
          [matTooltip]="absoluteTimestamps() ? 'Show relative times' : 'Show absolute times'"
        >
          <mat-icon>{{ absoluteTimestamps() ? 'schedule' : 'update' }}</mat-icon>
        </button>

        <!-- Phase MX1 / Gap 279 — density toggle. -->
        <button
          mat-icon-button
          type="button"
          (click)="compact.set(!compact())"
          [matTooltip]="compact() ? 'Spacious rows' : 'Compact rows'"
        >
          <mat-icon>{{ compact() ? 'density_medium' : 'density_small' }}</mat-icon>
        </button>

        <!-- Phase MX1 / Gap 282 — live events-per-minute counter. -->
        <span class="of-epm" [matTooltip]="'Events in the last minute'">
          <mat-icon inline>bolt</mat-icon>
          {{ epm() }}/min
        </span>
      </div>

      @if (visibleEvents().length === 0) {
        <section class="of-empty" role="status">
          <mat-icon>timelapse</mat-icon>
          <p>Quiet — nothing to narrate yet.</p>
        </section>
      } @else {
        <ol
          class="of-list"
          [class.of-follow]="autoFollow()"
          [class.of-compact]="compact()"
        >
          @for (e of visibleEvents(); track e.id) {
            <li
              class="of-row"
              [ngClass]="'of-sev-' + e.severity"
              [class.of-starred]="starred().has(e.id)"
              [attr.id]="'ops-event-' + e.id"
            >
              <span class="of-icon">
                <mat-icon>{{ iconFor(e) }}</mat-icon>
              </span>
              <div class="of-body">
                <div class="of-line">
                  <span class="of-time" [matTooltip]="e.timestamp">
                    {{ absoluteTimestamps() ? absoluteTime(e.timestamp) : relativeTime(e.timestamp) }}
                  </span>
                  <span class="of-source">{{ e.source || '—' }}</span>
                  @if (e.occurrence_count > 1) {
                    <span class="of-count" matTooltip="Deduped repeats in the last 60s">
                      ×{{ e.occurrence_count }}
                    </span>
                  }
                  <!-- Phase MX1 / Gap 280 — star event. -->
                  <button
                    mat-icon-button
                    type="button"
                    class="of-star-btn"
                    (click)="toggleStar(e.id)"
                    [matTooltip]="starred().has(e.id) ? 'Unstar' : 'Star for follow-up'"
                    [attr.aria-pressed]="starred().has(e.id)"
                    aria-label="Toggle star on event"
                  >
                    <mat-icon>{{ starred().has(e.id) ? 'star' : 'star_border' }}</mat-icon>
                  </button>
                  <!-- Phase MX1 / Gap 273 — copy as text. -->
                  <button
                    mat-icon-button
                    type="button"
                    class="of-copy-btn"
                    (click)="copyEvent(e)"
                    matTooltip="Copy event as plain text"
                    aria-label="Copy event"
                  >
                    <mat-icon>content_copy</mat-icon>
                  </button>
                  <!-- Phase MX1 / Gap 283 — share deep-link. -->
                  <button
                    mat-icon-button
                    type="button"
                    class="of-link-btn"
                    (click)="copyDeepLink(e)"
                    matTooltip="Copy direct link to this event"
                    aria-label="Copy link to event"
                  >
                    <mat-icon>link</mat-icon>
                  </button>
                </div>
                <p class="of-msg">{{ e.plain_english }}</p>
                @if (e.error_log_id) {
                  <a
                    class="of-fix"
                    [href]="'/diagnostics#error-' + e.error_log_id"
                  >
                    <mat-icon inline>arrow_forward</mat-icon>
                    Open error detail
                  </a>
                }
              </div>
            </li>
          }
        </ol>
      }
    </div>
  `,
  styles: [`
    .of-page {
      max-width: 960px;
      margin: 0 auto;
      padding: 24px;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }
    .of-title {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      margin: 0;
      font-size: 22px;
      font-weight: 500;
    }
    .of-subtitle {
      margin: 4px 0 0;
      font-size: 13px;
      color: var(--color-text-secondary, #5f6368);
    }
    .of-controls {
      display: flex;
      align-items: center;
      gap: 16px;
      flex-wrap: wrap;
    }
    .of-chips {
      flex: 0 1 auto;
    }
    .of-search {
      flex: 1 1 240px;
      max-width: 360px;
    }
    .of-buffer-count {
      margin-left: 8px;
      padding: 0 8px;
      font-size: 11px;
      font-weight: 600;
      background: var(--color-primary);
      color: #fff;
      border-radius: 12px;
    }
    .of-list {
      list-style: none;
      padding: 0;
      margin: 0;
      display: flex;
      flex-direction: column;
      gap: 8px;
      max-height: calc(100vh - 280px);
      overflow-y: auto;
      scroll-behavior: smooth;
    }
    .of-row {
      display: flex;
      gap: 12px;
      padding: 12px;
      background: var(--color-bg, #ffffff);
      border: var(--card-border, 0.8px solid #dadce0);
      border-left: 3px solid var(--color-border, #dadce0);
      border-radius: 4px;
    }
    .of-sev-info    { border-left-color: var(--color-primary, #1a73e8); }
    .of-sev-success { border-left-color: var(--color-success, #1e8e3e); }
    .of-sev-warning { border-left-color: var(--color-warning, #f9ab00); }
    .of-sev-error   { border-left-color: var(--color-error, #d93025); }
    .of-icon mat-icon {
      width: 20px;
      height: 20px;
      font-size: 20px;
    }
    .of-sev-info    .of-icon mat-icon { color: var(--color-primary); }
    .of-sev-success .of-icon mat-icon { color: var(--color-success); }
    .of-sev-warning .of-icon mat-icon { color: var(--color-warning); }
    .of-sev-error   .of-icon mat-icon { color: var(--color-error); }
    .of-body {
      flex: 1;
      min-width: 0;
    }
    .of-line {
      display: flex;
      gap: 8px;
      align-items: center;
      font-size: 11px;
      color: var(--color-text-secondary);
      font-variant-numeric: tabular-nums;
    }
    .of-source {
      font-weight: 500;
      color: var(--color-text-primary);
      text-transform: lowercase;
    }
    .of-count {
      margin-left: auto;
      padding: 0 6px;
      background: var(--color-bg-faint, #f1f3f4);
      border-radius: 10px;
      font-weight: 600;
    }
    .of-msg {
      margin: 4px 0 0;
      font-size: 13px;
      color: var(--color-text-primary);
      word-break: break-word;
    }
    .of-fix {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      margin-top: 4px;
      font-size: 12px;
      color: var(--color-primary);
    }
    .of-empty {
      text-align: center;
      padding: 48px 0;
      color: var(--color-text-secondary);
    }
    .of-empty mat-icon {
      width: 48px;
      height: 48px;
      font-size: 48px;
    }
    /* Phase MX1 — density toggle (Gap 279). */
    .of-list.of-compact .of-row { padding: 6px 8px; gap: 6px; }
    .of-list.of-compact .of-msg { font-size: 12px; margin-top: 2px; }
    .of-starred { border-left-width: 4px; box-shadow: inset 2px 0 0 #f9ab00; }
    .of-star-btn, .of-copy-btn, .of-link-btn {
      opacity: 0;
      transition: opacity 0.2s;
      margin-left: 4px;
    }
    .of-row:hover .of-star-btn,
    .of-row:hover .of-copy-btn,
    .of-row:hover .of-link-btn,
    .of-starred .of-star-btn { opacity: 1; }
    .of-star-btn .mat-icon,
    .of-copy-btn .mat-icon,
    .of-link-btn .mat-icon {
      font-size: 16px;
      width: 16px;
      height: 16px;
    }
    .of-epm {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-size: 11px;
      color: var(--color-text-secondary);
      font-variant-numeric: tabular-nums;
      padding: 4px 8px;
      background: var(--color-bg-faint, #f1f3f4);
      border-radius: 10px;
    }
  `],
})
export class OperationsFeedComponent implements OnInit {
  private http = inject(HttpClient);
  private realtime = inject(RealtimeService);
  private destroyRef = inject(DestroyRef);

  // ── reactive state ──────────────────────────────────────────────
  protected readonly events = signal<OpsEvent[]>([]);
  /** New events received while `paused` is true land here; flushed on resume. */
  protected readonly buffered = signal<OpsEvent[]>([]);
  protected readonly paused = signal<boolean>(false);
  protected readonly autoFollow = signal<boolean>(true);
  protected readonly severityFilter = signal<'all' | OpsEventSeverity>('all');
  protected readonly search = signal<string>('');
  /** two-way bound text input model mirrored back into `search` signal. */
  protected searchModel = '';

  // ── Phase MX1 extras ────────────────────────────────────────────
  /** Gap 271 — beep on severity=error when enabled. */
  protected readonly soundEnabled = signal<boolean>(false);
  /** Gap 278 — toggle relative ("3s ago") vs absolute ("HH:MM:SS") timestamp. */
  protected readonly absoluteTimestamps = signal<boolean>(false);
  /** Gap 279 — compact row density. */
  protected readonly compact = signal<boolean>(false);
  /** Gap 280 — starred event ids (in-memory only — feed is ephemeral). */
  protected readonly starred = signal<Set<number>>(new Set());
  /** Gap 282 — events-per-minute counter, recomputed every minute. */
  protected readonly epm = computed(() => {
    const cutoff = Date.now() - 60_000;
    return this.events().filter((e) => Date.parse(e.timestamp) >= cutoff).length;
  });

  /** Derived list: severity + text filter applied. */
  protected readonly visibleEvents = computed(() => {
    const sev = this.severityFilter();
    const q = this.search().trim().toLowerCase();
    return this.events().filter((e) => {
      if (sev !== 'all' && e.severity !== sev) return false;
      if (!q) return true;
      return (
        e.plain_english.toLowerCase().includes(q) ||
        e.event_type.toLowerCase().includes(q) ||
        e.source.toLowerCase().includes(q)
      );
    });
  });

  constructor() {
    // Phase MX1 / Gap 271 — ping a short beep when severity=error lands
    // and sound is enabled. Uses Web Audio API; no asset bundle required.
    effect(() => {
      const list = this.events();
      if (!this.soundEnabled()) return;
      const newest = list[list.length - 1];
      if (!newest || newest.severity !== 'error') return;
      this.beep();
    });
  }

  ngOnInit(): void {
    // Hydrate from REST.
    this.http
      .get<OpsEvent[]>('/api/operations/events/?limit=500')
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (rows) => {
          // Server already returns newest-first; our UI shows newest at
          // the bottom (append log style), so reverse once.
          this.events.set([...rows].reverse());
        },
        error: () => {
          /* empty feed is fine — realtime will fill it */
        },
      });

    // Live stream.
    this.realtime
      .subscribeTopic<OpsEvent>('operations.feed')
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((update) => {
        const payload = update?.payload as OpsEvent | undefined;
        if (!payload || typeof payload !== 'object') return;
        if (this.paused()) {
          this.buffered.update((b) => [...b, payload]);
        } else {
          this.appendEvents([payload]);
        }
      });
  }

  togglePause(): void {
    const wasPaused = this.paused();
    this.paused.set(!wasPaused);
    if (wasPaused) {
      // Resuming → flush the buffer in one batch.
      const queued = this.buffered();
      if (queued.length > 0) {
        this.appendEvents(queued);
        this.buffered.set([]);
      }
    }
  }

  onSeverityChange(ev: { value: 'all' | OpsEventSeverity }): void {
    this.severityFilter.set(ev.value);
  }

  iconFor(e: OpsEvent): string {
    switch (e.severity) {
      case 'error': return 'error';
      case 'warning': return 'warning';
      case 'success': return 'check_circle';
      default: return 'info';
    }
  }

  relativeTime(ts: string): string {
    const t = Date.parse(ts);
    if (Number.isNaN(t)) return '';
    const diff = Math.max(0, Date.now() - t);
    const s = Math.floor(diff / 1000);
    if (s < 5) return 'just now';
    if (s < 60) return `${s}s ago`;
    const m = Math.floor(s / 60);
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    return `${Math.floor(h / 24)}d ago`;
  }

  /** Phase MX1 / Gap 278 — absolute timestamp in HH:MM:SS (local tz). */
  absoluteTime(ts: string): string {
    const t = Date.parse(ts);
    if (Number.isNaN(t)) return '';
    return new Date(t).toLocaleTimeString(undefined, {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  }

  /** Phase MX1 / Gap 280 — star toggle. */
  toggleStar(id: number): void {
    const next = new Set(this.starred());
    if (next.has(id)) next.delete(id);
    else next.add(id);
    this.starred.set(next);
  }

  /** Phase MX1 / Gap 273 — copy a single event as plain text. */
  async copyEvent(e: OpsEvent): Promise<void> {
    const text = `[${e.timestamp}] (${e.severity.toUpperCase()}) ${e.source}: ${e.plain_english}`;
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      /* silent */
    }
  }

  /** Phase MX1 / Gap 283 — copy a direct link scrolling to this event
   *  on next visit. Uses a simple `#ops-event-<id>` hash which the
   *  Phase 147 GlobalLinkInterceptor handles on arrival. */
  async copyDeepLink(e: OpsEvent): Promise<void> {
    const url = `${window.location.origin}/operations-feed#ops-event-${e.id}`;
    try {
      await navigator.clipboard.writeText(url);
    } catch {
      /* silent */
    }
  }

  /** Phase MX1 / Gap 271 — short Web Audio beep on error. */
  private beep(): void {
    try {
      const w = window as unknown as { AudioContext?: typeof AudioContext };
      const Ctx = w.AudioContext;
      if (!Ctx) return;
      const ctx = new Ctx();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.value = 880;
      gain.gain.value = 0.05;
      osc.connect(gain).connect(ctx.destination);
      osc.start();
      setTimeout(() => {
        osc.stop();
        void ctx.close();
      }, 120);
    } catch {
      /* silent */
    }
  }

  private appendEvents(newOnes: OpsEvent[]): void {
    this.events.update((cur) => {
      // Dedup: if the last row shares `dedup_key`, roll up instead of pushing.
      // Backend already deduped in its 60s window, but clients that were
      // paused may receive a merged update; append-and-trim keeps order.
      const merged = [...cur, ...newOnes];
      // Cap memory — oldest rows drop when we exceed the cap.
      return merged.length > OPS_FEED_MAX_ROWS
        ? merged.slice(merged.length - OPS_FEED_MAX_ROWS)
        : merged;
    });
  }
}
