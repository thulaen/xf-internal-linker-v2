import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { AutoIssuesService } from './auto-issues.service';

describe('AutoIssuesService', () => {
  let service: AutoIssuesService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        AutoIssuesService,
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });
    service = TestBed.inject(AutoIssuesService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('list() with no options issues a bare GET to /api/auto-issues/', () => {
    service.list().subscribe();
    const req = httpMock.expectOne((r) => r.url === '/api/auto-issues/');
    expect(req.request.method).toBe('GET');
    expect(req.request.params.keys().length).toBe(0);
    req.flush({ count: 0, next: null, previous: null, results: [] });
  });

  it('list({ status }) sets the status query parameter', () => {
    service.list({ status: 'open' }).subscribe();
    const req = httpMock.expectOne(
      (r) => r.url === '/api/auto-issues/' && r.params.get('status') === 'open',
    );
    expect(req.request.method).toBe('GET');
    expect(req.request.params.get('source')).toBeNull();
    req.flush({ count: 0, next: null, previous: null, results: [] });
  });

  it('list({ source }) sets the source query parameter', () => {
    service.list({ source: 'glitchtip' }).subscribe();
    const req = httpMock.expectOne(
      (r) => r.url === '/api/auto-issues/' && r.params.get('source') === 'glitchtip',
    );
    expect(req.request.params.get('status')).toBeNull();
    req.flush({ count: 0, next: null, previous: null, results: [] });
  });

  it('list({ status, source }) sets both parameters', () => {
    service.list({ status: 'resolved', source: 'agent' }).subscribe();
    const req = httpMock.expectOne(
      (r) =>
        r.url === '/api/auto-issues/' &&
        r.params.get('status') === 'resolved' &&
        r.params.get('source') === 'agent',
    );
    req.flush({ count: 0, next: null, previous: null, results: [] });
  });

  it('resync() POSTs an empty body to /api/auto-issues/resync/', () => {
    service.resync().subscribe();
    const req = httpMock.expectOne('/api/auto-issues/resync/');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({});
    req.flush({
      status: 'queued',
      glitchtip_sync: {},
      glitchtip_picker: {},
      internal_picker: {},
      pyroscope_picker: {},
      open_count: 0,
    });
  });

  it('flushCache() POSTs an empty body to /api/auto-issues/flush-cache/', () => {
    service.flushCache().subscribe();
    const req = httpMock.expectOne('/api/auto-issues/flush-cache/');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({});
    req.flush({ status: 'flushed', flushed_rows: 5, glitchtip_sync: {} });
  });
});
