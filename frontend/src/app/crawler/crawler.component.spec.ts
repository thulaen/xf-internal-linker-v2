import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { EMPTY, of, throwError } from 'rxjs';

import { CrawlerComponent } from './crawler.component';
import { CrawlerService, CrawlSession, SitemapConfig } from './crawler.service';
import { RealtimeService } from '../core/services/realtime.service';
import { VisibilityGateService } from '../core/util/visibility-gate.service';

function makeSession(over: Partial<CrawlSession> = {}): CrawlSession {
  return {
    session_id: 's1',
    status: 'pending',
    site_domain: 'example.com',
    config: {},
    pages_crawled: 0,
    pages_changed: 0,
    pages_skipped_304: 0,
    new_pages_discovered: 0,
    broken_links_found: 0,
    bytes_downloaded: 0,
    elapsed_seconds: 0,
    progress: 0,
    message: '',
    is_resumable: false,
    error_message: '',
    started_at: null,
    paused_at: null,
    completed_at: null,
    created_at: '2026-05-10T00:00:00Z',
    ...over,
  };
}

function sitemap(): SitemapConfig {
  return {
    id: 1,
    domain: 'example.com',
    sitemap_url: 'https://example.com/sitemap.xml',
    normalized_url: 'https://example.com/sitemap.xml',
    discovery_method: 'manual',
    is_enabled: true,
    last_fetch_at: null,
    last_url_count: 0,
    last_error: '',
    created_at: '2026-05-10T00:00:00Z',
  };
}

describe('CrawlerComponent', () => {
  let fixture: ComponentFixture<CrawlerComponent>;
  let component: CrawlerComponent;
  let crawlerSvc: SpyObj<CrawlerService>;

  beforeEach(async () => {
    crawlerSvc = createSpyObj<CrawlerService>([
      'getSitemaps',
      'getSessions',
      'getContext',
      'getSession',
      'startCrawl',
      'pauseCrawl',
      'resumeCrawl',
      'addSitemap',
      'deleteSitemap',
      'getLinks',
      'getSEOAudit',
    ]);
    crawlerSvc.getSitemaps.mockReturnValue(of([sitemap()]));
    crawlerSvc.getSessions.mockReturnValue(of([]));
    crawlerSvc.getContext.mockReturnValue(of({
      last_crawl_at: null, total_pages_crawled: 0, storage_bytes: 1024, active_session: null,
    }));
    crawlerSvc.startCrawl.mockReturnValue(of(makeSession({ status: 'running' })));

    await TestBed.configureTestingModule({
      imports: [CrawlerComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        provideNoopAnimations(),
        { provide: CrawlerService, useValue: crawlerSvc },
        { provide: RealtimeService, useValue: { subscribeTopic: () => EMPTY } },
        { provide: VisibilityGateService, useValue: { whileLoggedInAndVisible: () => EMPTY } },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(CrawlerComponent);
    component = fixture.componentInstance;
  });

  it('renders, populates sitemaps, and seeds the selected domain', () => {
    fixture.detectChanges();
    expect(component).toBeTruthy();
    expect(component.sitemaps().length).toBe(1);
    expect(component.selectedDomain).toBe('example.com');
  });

  it('startCrawl posts to the service and stores the active session', () => {
    fixture.detectChanges();
    component.startCrawl();
    expect(crawlerSvc.startCrawl).toHaveBeenCalledWith('example.com', 4, 5);
    expect(component.activeSession()?.status).toBe('running');
  });

  it('formatBytes formats KB and MB correctly', () => {
    expect(component.formatBytes(512)).toBe('512 B');
    expect(component.formatBytes(2048)).toBe('2.0 KB');
    expect(component.formatBytes(2_097_152)).toBe('2.0 MB');
  });

  it('handles getSessions error path without crashing', () => {
    crawlerSvc.getSessions.mockReturnValue(throwError(() => new Error('boom')));
    fixture.detectChanges();
    expect(component.loading()).toBe(false);
  });
});
