import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { CrawlerService } from './crawler.service';

describe('CrawlerService', () => {
  let service: CrawlerService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(CrawlerService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  it('resumes a crawl without sending a blank site_domain', () => {
    service.resumeCrawl('session-1').subscribe();

    const req = http.expectOne('/api/crawler/sessions/');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ resume_session_id: 'session-1' });
    req.flush({ session_id: 'session-1', status: 'pending' });
  });
});
