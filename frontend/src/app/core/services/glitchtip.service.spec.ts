import { provideHttpClient, withXhr } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { GlitchtipService } from './glitchtip.service';

describe('GlitchtipService', () => {
  let service: GlitchtipService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [GlitchtipService, provideHttpClient(withXhr()), provideHttpClientTesting()],
    });
    service = TestBed.inject(GlitchtipService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('getRecentEvents() defaults to limit=50 and status=unresolved', () => {
    service.getRecentEvents().subscribe();
    const req = httpMock.expectOne(
      (r) =>
        r.url === '/api/glitchtip/events/' && r.params.get('limit') === '50' && r.params.get('status') === 'unresolved',
    );
    expect(req.request.method).toBe('GET');
    req.flush([]);
  });

  it('getRecentEvents(10) sends limit=10', () => {
    service.getRecentEvents(10).subscribe();
    const req = httpMock.expectOne((r) => r.url === '/api/glitchtip/events/' && r.params.get('limit') === '10');
    expect(req.request.method).toBe('GET');
    req.flush([]);
  });

  it('getRecentEvents(50, false) requests status=all', () => {
    service.getRecentEvents(50, false).subscribe();
    const req = httpMock.expectOne((r) => r.url === '/api/glitchtip/events/' && r.params.get('status') === 'all');
    expect(req.request.method).toBe('GET');
    req.flush([]);
  });

  it('getRecentEvents() rethrows HTTP errors via catchError → throwError', () =>
    new Promise<void>((done) => {
      service.getRecentEvents().subscribe({
        next: () => expect.fail('expected error path'),
        error: (err) => {
          expect(err).toBeTruthy();
          done();
        },
      });
      const req = httpMock.expectOne((r) => r.url === '/api/glitchtip/events/');
      req.flush('boom', { status: 500, statusText: 'Server Error' });
    }));
});
