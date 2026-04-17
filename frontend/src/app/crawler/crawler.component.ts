/**
 * CrawlerComponent — Web Crawler GUI page.
 *
 * Top: Session controls (Start/Resume/Pause, domain selector, rate/depth sliders).
 * Middle: Real-time progress bar with live stats.
 * Bottom: 6 tabs (Overview, Storage, Internal Links, Broken Links, SEO Audit, History).
 */

import { Component, DestroyRef, OnInit, inject } from '@angular/core';
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
import { timer } from 'rxjs';
import {
  CrawlerService,
  CrawlSession,
  CrawledPage,
  CrawledLink,
  SEOAuditSummary,
  SitemapConfig,
} from './crawler.service';
import { RealtimeService } from '../core/services/realtime.service';
import { TopicUpdate } from '../core/services/realtime.types';

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
})
export class CrawlerComponent implements OnInit {
  private crawlerSvc = inject(CrawlerService);
  private snack = inject(MatSnackBar);
  private destroyRef = inject(DestroyRef);
  private realtime = inject(RealtimeService);

  // ── Controls ──────────────────────────────────────────────────
  sitemaps: SitemapConfig[] = [];
  selectedDomain = '';
  rateLimit = 4;
  maxDepth = 5;

  // ── Session state ─────────────────────────────────────────────
  activeSession: CrawlSession | null = null;
  sessions: CrawlSession[] = [];
  loading = true;

  // ── Tab data ──────────────────────────────────────────────────
  pages: CrawledPage[] = [];
  links: CrawledLink[] = [];
  audit: SEOAuditSummary | null = null;
  storageBytes = 0;

  // ── Sitemap management ─────────────────────────────────────────
  newSitemapDomain = '';
  newSitemapUrl = '';

  // ── Table columns ─────────────────────────────────────────────
  linkColumns = ['source_url', 'destination_url', 'anchor_text', 'context_class'];
  pageColumns = ['url', 'http_status', 'title', 'word_count', 'internal_link_count', 'crawl_depth'];
  historyColumns = ['site_domain', 'status', 'pages_crawled', 'elapsed_seconds', 'created_at'];

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
    // realtime stream may have missed a transition. Lightweight: single
    // GET of the one active session, not the list.
    timer(0, 5000)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        if (this.activeSession?.status === 'running' || this.activeSession?.status === 'pending') {
          this.crawlerSvc.getSession(this.activeSession.session_id).subscribe({
            next: (s) => (this.activeSession = s),
          });
        }
      });
  }

  private handleRealtimeUpdate(update: TopicUpdate): void {
    if (update.event === 'session.deleted') {
      const id = (update.payload as { session_id: string }).session_id;
      this.sessions = this.sessions.filter((s) => s.session_id !== id);
      if (this.activeSession?.session_id === id) {
        this.activeSession = null;
      }
      return;
    }

    if (update.event === 'session.created' || update.event === 'session.updated') {
      const next = update.payload as CrawlSession;
      const idx = this.sessions.findIndex((s) => s.session_id === next.session_id);
      if (idx >= 0) {
        this.sessions = this.sessions.map((s) => (s.session_id === next.session_id ? next : s));
      } else {
        this.sessions = [next, ...this.sessions];
      }
      // Refresh the active-session binding so the live progress card updates
      // without waiting for the polling fallback.
      if (this.activeSession?.session_id === next.session_id) {
        this.activeSession = next;
      } else if (!this.activeSession && (next.status === 'running' || next.status === 'pending')) {
        this.activeSession = next;
      }
    }
  }

  loadData(): void {
    this.loading = true;
    this.crawlerSvc.getSitemaps()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
      next: (sitemaps) => {
        this.sitemaps = sitemaps;
        const domains = [...new Set(sitemaps.map((s) => s.domain))];
        if (domains.length > 0 && !this.selectedDomain) {
          this.selectedDomain = domains[0];
        }
      },
    });
    this.crawlerSvc.getSessions()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
      next: (sessions) => {
        this.sessions = sessions;
        this.activeSession =
          sessions.find((s) => s.status === 'running' || s.status === 'pending') ?? null;
        this.loading = false;
      },
      error: () => (this.loading = false),
    });
    this.crawlerSvc.getContext()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
      next: (ctx) => (this.storageBytes = ctx.storage_bytes),
    });
  }

  get domains(): string[] {
    return [...new Set(this.sitemaps.map((s) => s.domain))];
  }

  get hasResumable(): CrawlSession | undefined {
    return this.sessions.find((s) => s.is_resumable && s.status === 'paused');
  }

  // ── Actions ───────────────────────────────────────────────────
  startCrawl(): void {
    if (!this.selectedDomain) return;
    this.crawlerSvc.startCrawl(this.selectedDomain, this.rateLimit, this.maxDepth)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
      next: (session) => {
        this.activeSession = session;
        this.snack.open('Crawl started!', 'OK', { duration: 3000 });
      },
      error: (err) =>
        this.snack.open(err.error?.error ?? 'Failed to start crawl', 'OK', { duration: 5000 }),
    });
  }

  resumeCrawl(): void {
    const resumable = this.hasResumable;
    if (!resumable) return;
    this.crawlerSvc.resumeCrawl(resumable.session_id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
      next: (session) => {
        this.activeSession = session;
        this.snack.open('Crawl resumed!', 'OK', { duration: 3000 });
      },
      error: (err) =>
        this.snack.open(err.error?.error ?? 'Failed to resume', 'OK', { duration: 5000 }),
    });
  }

  pauseCrawl(): void {
    if (!this.activeSession) return;
    this.crawlerSvc.pauseCrawl(this.activeSession.session_id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
      next: (session) => {
        this.activeSession = session;
        this.snack.open('Crawl paused.', 'OK', { duration: 3000 });
      },
    });
  }

  // ── Sitemap management ────────────────────────────────────────
  addSitemap(): void {
    if (!this.newSitemapDomain || !this.newSitemapUrl) return;
    this.crawlerSvc.addSitemap(this.newSitemapDomain, this.newSitemapUrl)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
      next: (sm) => {
        this.sitemaps = [...this.sitemaps, sm];
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
        this.sitemaps = this.sitemaps.filter((s) => s.id !== id);
        this.snack.open('Sitemap removed.', 'OK', { duration: 3000 });
      },
      error: () =>
        this.snack.open('Failed to remove sitemap', 'OK', { duration: 5000 }),
    });
  }

  // ── Tab loaders ───────────────────────────────────────────────
  onTabChange(index: number): void {
    const lastSession = this.sessions.find((s) => s.status === 'completed');
    const sid = lastSession?.session_id;

    switch (index) {
      case 2: // Internal Links
        this.crawlerSvc.getLinks(sid)
          .pipe(takeUntilDestroyed(this.destroyRef))
          .subscribe({ next: (l) => (this.links = l) });
        break;
      case 4: // SEO Audit
        this.crawlerSvc.getSEOAudit()
          .pipe(takeUntilDestroyed(this.destroyRef))
          .subscribe({
          next: (a) => (this.audit = a),
          error: () => (this.audit = null),
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
