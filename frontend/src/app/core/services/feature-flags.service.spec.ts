import { provideHttpClient, withXhr } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { BehaviorSubject } from 'rxjs';
import { AuthService } from './auth.service';
import { FeatureFlagsService } from './feature-flags.service';

describe('FeatureFlagsService', () => {
  let service: FeatureFlagsService;
  let httpMock: HttpTestingController;
  let isLoggedIn$: BehaviorSubject<boolean>;

  beforeEach(() => {
    localStorage.clear();
    isLoggedIn$ = new BehaviorSubject<boolean>(false);
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withXhr()),
        provideHttpClientTesting(),
        { provide: AuthService, useValue: { isLoggedIn$ } },
      ],
    });
    service = TestBed.inject(FeatureFlagsService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
    localStorage.clear();
  });

  it('isEnabled() returns false for an unknown key', () => {
    expect(service.isEnabled('nope')).toBe(false);
  });

  it('variantOf() returns "control" when the flag is unknown', () => {
    expect(service.variantOf('nope')).toBe('control');
  });

  it('all() snapshot is empty when no flags are loaded', () => {
    expect(service.all()).toEqual([]);
  });

  it('refresh() is a no-op while logged out', () => {
    service.refresh();
    httpMock.expectNone('/api/feature-flags/');
    expect(service.all()).toEqual([]);
  });

  it('refresh() fires the flags GET once the user logs in', () => {
    isLoggedIn$.next(true);
    const req = httpMock.expectOne('/api/feature-flags/');
    expect(req.request.method).toBe('GET');
    req.flush([
      { key: 'beta-card', enabled: true },
      { key: 'cta-copy', enabled: true, variant: 'b' },
      { key: 'killed', enabled: false },
    ]);

    expect(service.isEnabled('beta-card')).toBe(true);
    expect(service.isEnabled('killed')).toBe(false);
    expect(service.variantOf('cta-copy')).toBe('b');
    expect(service.variantOf('killed')).toBe('control');
    expect(service.all().length).toBe(3);
  });

  it('refresh() catches HTTP errors and leaves the cache intact', () => {
    isLoggedIn$.next(true);
    const req = httpMock.expectOne('/api/feature-flags/');
    req.flush('boom', { status: 500, statusText: 'Server' });
    expect(service.all()).toEqual([]); // empty cache after error
  });

  it('refresh() ignores a non-array response body (defensive)', () => {
    isLoggedIn$.next(true);
    const req = httpMock.expectOne('/api/feature-flags/');
    req.flush({ unexpected: 'shape' } as any);
    expect(service.all()).toEqual([]);
  });

  it('persists fetched flags to localStorage so the next page-load is warm', () => {
    isLoggedIn$.next(true);
    httpMock.expectOne('/api/feature-flags/').flush([{ key: 'one', enabled: true }]);
    expect(localStorage.getItem('xfil_feature_flags_cache')).toContain('"one"');
  });

  it('recordExposure() POSTs once per key per session', () => {
    isLoggedIn$.next(true);
    httpMock.expectOne('/api/feature-flags/').flush([{ key: 'cta', enabled: true, variant: 'b' }]);

    service.recordExposure('cta');
    const post1 = httpMock.expectOne('/api/feature-flags/exposures/');
    expect(post1.request.body).toEqual({ key: 'cta', variant: 'b' });
    post1.flush({});

    // Second call within the same session is suppressed.
    service.recordExposure('cta');
    httpMock.expectNone('/api/feature-flags/exposures/');
  });

  it('recordExposure() reports "control" for disabled flags', () => {
    isLoggedIn$.next(true);
    httpMock.expectOne('/api/feature-flags/').flush([{ key: 'cta', enabled: false, variant: 'b' }]);

    service.recordExposure('cta');
    const post = httpMock.expectOne('/api/feature-flags/exposures/');
    expect(post.request.body).toEqual({ key: 'cta', variant: 'control' });
    post.flush({});
  });

  it('recordExposure() swallows POST errors silently (best-effort)', () =>
    new Promise<void>((done) => {
      isLoggedIn$.next(true);
      httpMock.expectOne('/api/feature-flags/').flush([{ key: 'cta', enabled: true }]);

      service.recordExposure('cta');
      const post = httpMock.expectOne('/api/feature-flags/exposures/');
      expect(post.request.method).toBe('POST');
      post.flush('nope', { status: 500, statusText: 'Server' });
      // The catchError branch returned of(null), so no error propagates.
      setTimeout(() => done(), 0);
    }));

  it('start() triggers a refresh', () => {
    isLoggedIn$.next(true);
    httpMock.expectOne('/api/feature-flags/').flush([]);
    // start() should fire ANOTHER refresh.
    service.start();
    httpMock.expectOne('/api/feature-flags/').flush([{ key: 'x', enabled: true }]);
    expect(service.isEnabled('x')).toBe(true);
  });
});
