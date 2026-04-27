/**
 * CrawlerComponent — Web Crawler GUI page.
 *
 * Top: Session controls (Start/Resume/Pause, domain selector, rate/depth sliders).
 * Middle: Real-time progress bar with live stats.
 * Bottom: 6 tabs (Overview, Storage, Internal Links, Broken Links, SEO Audit, History).
 */

import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { MatSliderModule } from '@angular/material/slider';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatDividerModule } from '@angular/material/divider';
import { EMPTY, switchMap, timer } from 'rxjs';
import { VisibilityGateService } from '../core/util/visibility-gate.service';
import {
  CrawlerService,
  CrawlSession,
  CrawledLink,
  SEOAuditSummary,
  SitemapConfig,
} from './crawler.service';
import { RealtimeService } from '../core/services/realtime.service';
import { TopicUpdate } from '../core/services/realtime.types';

const ACTIVE_STATUSES = new Set<string>(['running', 'pending']);

@Component({
  selector: 'app-crawler',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatCardModule,
    MatChipsModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressBarModule,
    MatSelectModule,
    MatSliderModule,
    MatSnackBarModule,
    MatTableModule,
    MatTabsModule,
    MatTooltipModule,
    MatProgressSpinnerModule,
    MatDividerModule,
  ],
  templateUrl: './crawler.component.html',
  styleUrls: ['./crawler.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CrawlerComponent implements OnInit {
  private crawlerSvc = inject(CrawlerService);
  private snack = inject(MatSnackBar);
  private destroyRef = inject(DestroyRef);
  private realtime = inject(RealtimeService);
  private visibilityGate = inject(VisibilityGateService);

  // ── Controls ──────────────────────────────────────────────────
  readonly sitemaps = signal<SitemapConfig[]>([]);
  // ngModel two-way bindings — need lvalues, stay plain. (ngModelChange)
  // events fire on the host so OnPush sees CD per keystroke.
  selectedDomain = '';
  rateLimit = 4;
  maxDepth = 5;

  // ── Session state ─────────────────────────────────────────────
  readonly activeSession = signal<CrawlSession | null>(null);
  readonly sessions = signal<CrawlSession[]>([]);
  readonly loading = signal(true);

  // ── Tab data ──────────────────────────────────────────────────
  readonly links = signal<CrawledLink[]>([]);
  readonly audit = signal<SEOAuditSummary | null>(null);
  readonly storageBytes = signal(0);

  // ── Sitemap management ─────────────────────────────────────────
  newSitemapDomain = '';
  newSitemapUrl = '';

  // ── Table columns ─────────────────────────────────────────────
  // Note: previous file had a `pageColumns` field and a `pages: CrawledPage[]`
  // field for a "Pages" tab that was never wired into the template — both
  // were dead code and have been removed (along with the now-unused
  // `CrawledPage` import). Tab indices: 0 Overview, 1 Storage, 2 Internal
  // Links, 3 Broken Links, 4 SEO Audit, 5 History.
  readonly linkColumns: readonly string[] = ['source_url', 'destination_url', 'anchor_text', 'context_class'];
  readonly historyColumns: readonly string[] = ['site_domain', 'status', 'pages_crawled', 'elapsed_seconds', 'created_at'];

  // ── Derived state ─────────────────────────────────────────────
  readonly domains = computed(() => [...new Set(this.sitemaps().map((s) => s.domain))]);
  readonly hasResumable = computed(() =>
    this.sessions().find((s) => s.is_resumable && s.status === 'paused'),
  );

  ngOnInit(): void {
    this.loadData();

    // Phase R1.2 — live updates from `crawler.sessions` topic. The backend
    // `CrawlSession` signals broadcast on every save/delete, so there's no
    // need to poll anymore. The 5-second `timer` below is kept as a
    // fallback for the case where the WebSocket is briefly disconnected
    // during an active crawl; `RealtimeService` handles reconnects but a
    // paused/broken socket shouldn't leave a running session stale.
    this.realtime
      .subscribeTopic('crawler.sessions')
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((update: TopicUpdate) => this.handleRealtimeUpdate(update));

    // Fallback poll — only fires when an active session is running and the
    // realtime stream may have missed a transition. switchMap flattens the
    // tick-of-fetches into one stream so each tick automatically cancels
    // any prior in-flight GET (no nested-subscribe smell, no leak if the
    // outer stream tears down mid-fetch). Gated by VisibilityGateService
    // — hidden tabs / signed-out sessions skip it. See docs/PERFORMANCE.md §13.
    this.visibilityGate
      .whileLoggedInAndVisible(() => timer(0, 5000))
      .pipe(
        switchMap(() => {
          const active = this.activeSession();
          if (!active || !ACTIVE_STATUSES.has(active.status)) {
            return EMPTY;
          }
          return this.crawlerSvc.getSession(active.session_id);
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (s) => this.activeSession.set(s),
        error: () => { /* transient — keep last known session, don't blank */ },
      });
  }

  private handleRealtimeUpdate(update: TopicUpdate): void {
    if (update.event === 'session.deleted') {
      const id = (update.payload as { session_id: string }).session_id;
      this.sessions.update(arr => arr.filter(s => s.session_id !== id));
      if (this.activeSession()?.session_id === id) {
        this.activeSession.set(null);
      }
      return;
    }

    if (update.event === 'session.created' || update.event === 'session.updated') {
      const next = update.payload as CrawlSession;
      // Single atomic update — read-modify-write inside the signal updater,
      // so two close-succession realtime emissions can't lose each other's
      // state. Mirrors the webhook-log / jobs realtime-handler fix.
      this.sessions.update(arr => {
        const idx = arr.findIndex(s => s.session_id === next.session_id);
        if (idx >= 0) {
          return arr.map(s => s.session_id === next.session_id ? next : s);
        }
        return [next, ...arr];
      });
      // Refresh the active-session binding so the live progress card updates
      // without waiting for the polling fallback.
      const current = this.activeSession();
      if (current?.session_id === next.session_id) {
        this.activeSession.set(next);
      } else if (!current && ACTIVE_STATUSES.has(next.status)) {
        this.activeSession.set(next);
      }
    }
  }

  loadData(): void {
    this.loading.set(true);
    this.crawlerSvc.getSitemaps()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (sitemaps) => {
          this.sitemaps.set(sitemaps);
          if (!this.selectedDomain) {
            const domains = [...new Set(sitemaps.map((s) => s.domain))];
            if (domains.length > 0) {
              this.selectedDomain = domains[0];
            }
          }
        },
        error: (err) => console.error('crawler sitemaps error', err),
      });
    this.crawlerSvc.getSessions()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (sessions) => {
          this.sessions.set(sessions);
          this.activeSession.set(
            sessions.find((s) => ACTIVE_STATUSES.has(s.status)) ?? null,
          );
          this.loading.set(false);
        },
        error: () => this.loading.set(false),
      });
    this.crawlerSvc.getContext()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (ctx) => this.storageBytes.set(ctx.storage_bytes),
        error: (err) => console.error('crawler context error', err),
      });
  }

  // ── Actions ───────────────────────────────────────────────────
  startCrawl(): void {
    if (!this.selectedDomain) return;
    this.crawlerSvc.startCrawl(this.selectedDomain, this.rateLimit, this.maxDepth)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (session) => {
          this.activeSession.set(session);
          this.snack.open('Crawl started!', 'OK', { duration: 3000 });
        },
        error: (err) =>
          this.snack.open(err.error?.error ?? 'Failed to start crawl', 'OK', { duration: 5000 }),
      });
  }

  resumeCrawl(): void {
    const resumable = this.hasResumable();
    if (!resumable) return;
    this.crawlerSvc.resumeCrawl(resumable.session_id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (session) => {
          this.activeSession.set(session);
          this.snack.open('Crawl resumed!', 'OK', { duration: 3000 });
        },
        error: (err) =>
          this.snack.open(err.error?.error ?? 'Failed to resume', 'OK', { duration: 5000 }),
      });
  }

  pauseCrawl(): void {
    const active = this.activeSession();
    if (!active) return;
    this.crawlerSvc.pauseCrawl(active.session_id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (session) => {
          this.activeSession.set(session);
          this.snack.open('Crawl paused.', 'OK', { duration: 3000 });
        },
        error: () =>
          this.snack.open('Failed to pause crawl', 'OK', { duration: 5000 }),
      });
  }

  // ── Sitemap management ────────────────────────────────────────
  addSitemap(): void {
    if (!this.newSitemapDomain || !this.newSitemapUrl) return;
    this.crawlerSvc.addSitemap(this.newSitemapDomain, this.newSitemapUrl)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (sm) => {
          this.sitemaps.update(arr => [...arr, sm]);
          if (!this.selectedDomain) {
            this.selectedDomain = sm.domain;
          }
          this.newSitemapDomain = '';
          this.newSitemapUrl = '';
          this.snack.open('Sitemap added!', 'OK', { duration: 3000 });
        },
        error: (err) =>
          this.snack.open(err.error?.error ?? 'Failed to add sitemap', 'OK', { duration: 5000 }),
      });
  }

  removeSitemap(id: number): void {
    this.crawlerSvc.deleteSitemap(id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.sitemaps.update(arr => arr.filter(s => s.id !== id));
          this.snack.open('Sitemap removed.', 'OK', { duration: 3000 });
        },
        error: () =>
          this.snack.open('Failed to remove sitemap', 'OK', { duration: 5000 }),
      });
  }

  // ── Tab loaders ───────────────────────────────────────────────
  onTabChange(index: number): void {
    const lastSession = this.sessions().find((s) => s.status === 'completed');
    const sid = lastSession?.session_id;

    switch (index) {
      case 2: // Internal Links
        this.crawlerSvc.getLinks(sid)
          .pipe(takeUntilDestroyed(this.destroyRef))
          .subscribe({
            next: (l) => this.links.set(l),
            error: (err) => console.error('crawler links error', err),
          });
        break;
      case 4: // SEO Audit
        this.crawlerSvc.getSEOAudit()
          .pipe(takeUntilDestroyed(this.destroyRef))
          .subscribe({
            // Don't blank the cached audit on a transient error — leave the
            // last known summary visible. Previously a single 5xx wiped the
            // whole audit panel even though the next refresh would refill it.
            next: (a) => this.audit.set(a),
            error: (err) => console.error('crawler SEO audit error', err),
          });
        break;
    }
  }

  formatBytes(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1048576).toFixed(1)} MB`;
  }

  formatDuration(seconds: number): string {
    if (seconds < 60) return `${seconds.toFixed(0)}s`;
    return `${(seconds / 60).toFixed(1)} min`;
  }
}
