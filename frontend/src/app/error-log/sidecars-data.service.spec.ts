import { provideHttpClient, withXhr } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { SidecarsDataService } from './sidecars-data.service';

describe('SidecarsDataService', () => {
  let service: SidecarsDataService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [SidecarsDataService, provideHttpClient(withXhr()), provideHttpClientTesting()],
    });
    service = TestBed.inject(SidecarsDataService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  describe('listSnapshots()', () => {
    it('appends the issue_id query when provided', () => {
      let captured: unknown;
      service.listSnapshots(42).subscribe((r) => (captured = r));
      const req = httpMock.expectOne('/api/sidecars/snapshots/?issue_id=42');
      req.flush({ status: 'ok', items: [] });
      expect(captured).toEqual({ status: 'ok', items: [] });
    });

    it('omits the query string when no issue_id is given', () => {
      let captured: unknown;
      service.listSnapshots().subscribe((r) => (captured = r));
      const req = httpMock.expectOne('/api/sidecars/snapshots/');
      req.flush({ status: 'ok', items: [] });
      expect(captured).toEqual({ status: 'ok', items: [] });
    });

    it('degrades to sidecars_unavailable on HTTP error', () => {
      let captured: unknown;
      service.listSnapshots(7).subscribe((r) => (captured = r));
      const req = httpMock.expectOne('/api/sidecars/snapshots/?issue_id=7');
      req.flush('boom', { status: 500, statusText: 'Server error' });
      expect(captured).toEqual({ status: 'sidecars_unavailable', items: [] });
    });
  });

  describe('listBulletins()', () => {
    it('builds the URL with no params when opts is empty', () => {
      let captured: unknown;
      service.listBulletins().subscribe((r) => (captured = r));
      const req = httpMock.expectOne((r) => r.urlWithParams === '/api/sidecars/bulletins/');
      req.flush({ status: 'ok', items: [] });
      expect(captured).toEqual({ status: 'ok', items: [] });
    });

    it('encodes eventType + minSeverity + limit into the query string', () => {
      let captured: unknown;
      service.listBulletins({ eventType: 'snapshot', minSeverity: 'high', limit: 25 }).subscribe((r) => (captured = r));
      const req = httpMock.expectOne('/api/sidecars/bulletins/?event_type=snapshot&min_severity=high&limit=25');
      req.flush({ status: 'ok', items: [] });
      expect(captured).toEqual({ status: 'ok', items: [] });
    });

    it('does not send omitted optional filters', () => {
      let captured: unknown;
      service.listBulletins({ eventType: 'snapshot' }).subscribe((r) => (captured = r));
      const req = httpMock.expectOne((r) => r.urlWithParams === '/api/sidecars/bulletins/?event_type=snapshot');
      req.flush({ status: 'ok', items: [] });
      expect(captured).toEqual({ status: 'ok', items: [] });
    });

    it('keeps a minSeverity-only filter in the query string', () => {
      let captured: unknown;
      service.listBulletins({ minSeverity: 'medium' }).subscribe((r) => (captured = r));
      const req = httpMock.expectOne('/api/sidecars/bulletins/?min_severity=medium');
      req.flush({ status: 'ok', items: [] });
      expect(captured).toEqual({ status: 'ok', items: [] });
    });

    it('keeps a positive limit-only filter in the query string', () => {
      let captured: unknown;
      service.listBulletins({ limit: 10 }).subscribe((r) => (captured = r));
      const req = httpMock.expectOne('/api/sidecars/bulletins/?limit=10');
      req.flush({ status: 'ok', items: [] });
      expect(captured).toEqual({ status: 'ok', items: [] });
    });

    it('keeps an explicit zero limit in the query string', () => {
      let captured: unknown;
      service.listBulletins({ limit: 0 }).subscribe((r) => (captured = r));
      const req = httpMock.expectOne((r) => r.urlWithParams === '/api/sidecars/bulletins/?limit=0');
      req.flush({ status: 'ok', items: [] });
      expect(captured).toEqual({ status: 'ok', items: [] });
    });

    it('degrades to sidecars_unavailable on HTTP error', () => {
      let captured: unknown;
      service.listBulletins().subscribe((r) => (captured = r));
      const req = httpMock.expectOne((r) => r.urlWithParams === '/api/sidecars/bulletins/');
      req.flush('boom', { status: 503, statusText: 'Service Unavailable' });
      expect(captured).toEqual({ status: 'sidecars_unavailable', items: [] });
    });
  });

  describe('static topic constants', () => {
    it('LIVE_BULLETIN_TOPIC matches the backend bridge', () => {
      expect(SidecarsDataService.LIVE_BULLETIN_TOPIC).toBe('bullboard');
    });

    it('LIVE_SNAPSHOT_TOPIC matches the snapshotd topic', () => {
      expect(SidecarsDataService.LIVE_SNAPSHOT_TOPIC).toBe('snapshotd');
    });
  });
});
