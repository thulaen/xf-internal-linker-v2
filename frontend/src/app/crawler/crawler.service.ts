/**
 * CrawlerService — Angular service for the crawler REST API.
 */

import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

export interface CrawlSession {
  session_id: string;
  status: 'pending' | 'running' | 'paused' | 'completed' | 'failed';
  site_domain: string;
  config: Record<string, any>;
  pages_crawled: number;
  pages_changed: number;
  pages_skipped_304: number;
  new_pages_discovered: number;
  broken_links_found: number;
  bytes_downloaded: number;
  elapsed_seconds: number;
  progress: number;
  message: string;
  is_resumable: boolean;
  error_message: string;
  started_at: string | null;
  paused_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface CrawledPage {
  id: number;
  url: string;
  http_status: number;
  response_time_ms: number;
  title: string;
  word_count: number;
  internal_link_count: number;
  crawl_depth: number;
}

export interface CrawledLink {
  id: number;
  source_url: string;
  destination_url: string;
  anchor_text: string;
  context_class: string;
  is_nofollow: boolean;
}

export interface SitemapConfig {
  id: number;
  domain: string;
  sitemap_url: string;
  normalized_url: string;
  discovery_method: string;
  is_enabled: boolean;
  last_fetch_at: string | null;
  last_url_count: number;
  last_error: string;
  created_at: string;
}

export interface SEOAuditSummary {
  total_pages: number;
  missing_title: number;
  duplicate_titles: number;
  missing_meta_description: number;
  missing_h1: number;
  multiple_h1: number;
  missing_canonical: number;
  noindexed_pages: number;
  thin_content: number;
  slow_pages: number;
  non_mobile: number;
  missing_og: number;
  images_missing_alt: number;
  broken_links: number;
  orphan_pages: number;
}

export interface CrawlerContext {
  last_crawl_at: string | null;
  total_pages_crawled: number;
  storage_bytes: number;
  active_session: CrawlSession | null;
}

const BASE = `${environment.apiBaseUrl}/crawler`;

@Injectable({ providedIn: 'root' })
export class CrawlerService {
  private http = inject(HttpClient);

  // ── Sessions ────────────────────────────────────────────────────
  getSessions(): Observable<CrawlSession[]> {
    return this.http.get<CrawlSession[]>(`${BASE}/sessions/`);
  }

  getSession(id: string): Observable<CrawlSession> {
    return this.http.get<CrawlSession>(`${BASE}/sessions/${id}/`);
  }

  startCrawl(domain: string, rateLimit = 4, maxDepth = 5): Observable<CrawlSession> {
    return this.http.post<CrawlSession>(`${BASE}/sessions/`, {
      site_domain: domain,
      rate_limit: rateLimit,
      max_depth: maxDepth,
    });
  }

  resumeCrawl(sessionId: string): Observable<CrawlSession> {
    return this.http.post<CrawlSession>(`${BASE}/sessions/`, {
      site_domain: '',
      resume_session_id: sessionId,
    });
  }

  pauseCrawl(sessionId: string): Observable<CrawlSession> {
    return this.http.post<CrawlSession>(`${BASE}/sessions/${sessionId}/pause/`, {});
  }

  // ── Pages & Links ──────────────────────────────────────────────
  getPages(sessionId?: string, httpStatus?: number): Observable<CrawledPage[]> {
    let params = new HttpParams();
    if (sessionId) params = params.set('session', sessionId);
    if (httpStatus) params = params.set('http_status', httpStatus.toString());
    return this.http.get<CrawledPage[]>(`${BASE}/pages/`, { params });
  }

  getLinks(sessionId?: string, context?: string): Observable<CrawledLink[]> {
    let params = new HttpParams();
    if (sessionId) params = params.set('session', sessionId);
    if (context) params = params.set('context', context);
    return this.http.get<CrawledLink[]>(`${BASE}/links/`, { params });
  }

  // ── SEO Audit ──────────────────────────────────────────────────
  getSEOAudit(): Observable<SEOAuditSummary> {
    return this.http.get<SEOAuditSummary>(`${BASE}/seo-audit/`);
  }

  // ── Context header ─────────────────────────────────────────────
  getContext(): Observable<CrawlerContext> {
    return this.http.get<CrawlerContext>(`${BASE}/context/`);
  }

  // ── Sitemaps ───────────────────────────────────────────────────
  getSitemaps(): Observable<SitemapConfig[]> {
    return this.http.get<SitemapConfig[]>(`${BASE}/sitemaps/`);
  }

  addSitemap(domain: string, sitemapUrl: string): Observable<SitemapConfig> {
    return this.http.post<SitemapConfig>(`${BASE}/sitemaps/`, {
      domain,
      sitemap_url: sitemapUrl,
    });
  }

  deleteSitemap(id: number): Observable<void> {
    return this.http.delete<void>(`${BASE}/sitemaps/${id}/`);
  }

  testSitemap(id: number): Observable<any> {
    return this.http.post(`${BASE}/sitemaps/${id}/test/`, {});
  }

  autoDiscoverSitemaps(domain: string, baseUrl: string): Observable<any> {
    return this.http.post(`${BASE}/sitemaps/auto_discover/`, {
      domain,
      base_url: baseUrl,
    });
  }

  // ── Full orchestration ─────────────────────────────────────────
  triggerFullRun(): Observable<any> {
    return this.http.post(`${environment.apiBaseUrl}/sync-jobs/trigger_full_run/`, {});
  }
}
