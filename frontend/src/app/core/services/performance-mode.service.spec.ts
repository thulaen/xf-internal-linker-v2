import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideHttpClient } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';

import { PerformanceModeService, RuntimeSettingsResponse } from './performance-mode.service';

/**
 * Tests for PerformanceModeService focused on the 2026-05-09 hardware-
 * capability gate (AutoIssue #16). The pre-existing fields (mode /
 * expiry / expiresAt) are validated alongside the new fields
 * (highPerformanceCapable / hardwareTier / hardwareSummary) so the
 * single round-trip behaviour is documented end-to-end.
 */
describe('PerformanceModeService', () => {
  let svc: PerformanceModeService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        PerformanceModeService,
      ],
    });
    svc = TestBed.inject(PerformanceModeService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('boots with balanced/none defaults and capable=true', () => {
    expect(svc.mode()).toBe('balanced');
    expect(svc.expiry()).toBe('none');
    expect(svc.highPerformanceCapable()).toBe(true);
    expect(svc.hardwareTier()).toBe('high');
  });

  it('refresh() updates mode + expiry from server response', () => {
    const stub: RuntimeSettingsResponse = {
      runtime_mode: 'cpu',
      performance_mode: 'high',
      effective_runtime_mode: 'cpu',
      performance_mode_expiry: 'night',
      performance_mode_expires_at: '2026-05-10T06:00:00Z',
    };
    svc.refresh().subscribe();
    httpMock.expectOne('/api/settings/runtime/').flush(stub);
    expect(svc.mode()).toBe('high');
    expect(svc.expiry()).toBe('night');
    expect(svc.expiresAt()).toBe('2026-05-10T06:00:00Z');
  });

  it('refresh() picks up the new hardware-capability fields when present', () => {
    const stub: RuntimeSettingsResponse = {
      runtime_mode: 'cpu',
      performance_mode: 'balanced',
      hardware_tier: 'low',
      high_performance_capable: false,
      hardware_summary: 'tier=low ram=8.0GB cores=4',
    };
    svc.refresh().subscribe();
    httpMock.expectOne('/api/settings/runtime/').flush(stub);
    expect(svc.highPerformanceCapable()).toBe(false);
    expect(svc.hardwareTier()).toBe('low');
    expect(svc.hardwareSummary()).toBe('tier=low ram=8.0GB cores=4');
  });

  it('refresh() leaves capability fields at their defaults when the server omits them', () => {
    // Older backend (pre-2026-05-09) doesn't send the hardware fields —
    // the service must NOT clobber the cached defaults to undefined.
    const stub: RuntimeSettingsResponse = {
      runtime_mode: 'cpu',
      performance_mode: 'balanced',
    };
    svc.refresh().subscribe();
    httpMock.expectOne('/api/settings/runtime/').flush(stub);
    expect(svc.highPerformanceCapable()).toBe(true);
    expect(svc.hardwareTier()).toBe('high');
  });

  it('refresh() failure does not crash the page (catchError → safe fallback)', () => {
    let errored = false;
    svc.refresh().subscribe({
      error: () => (errored = true),
    });
    httpMock.expectOne('/api/settings/runtime/').flush(null, {
      status: 500,
      statusText: 'Server Error',
    });
    // catchError swallows the failure; subscriber sees the fallback value, not an error.
    expect(errored).toBe(false);
    expect(svc.mode()).toBe('balanced');
  });

  it('switchMode() POSTs and updates the cached signal', () => {
    svc.switchMode('safe').subscribe();
    const req = httpMock.expectOne('/api/settings/runtime/switch/');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ mode: 'safe' });
    req.flush({ runtime_mode: 'cpu', performance_mode: 'safe' });
    expect(svc.mode()).toBe('safe');
  });

  it('switchMode() with high + expiry sends both', () => {
    svc.switchMode('high', 'activity').subscribe();
    const req = httpMock.expectOne('/api/settings/runtime/switch/');
    expect(req.request.body).toEqual({ mode: 'high', expiry: 'activity' });
    req.flush({
      runtime_mode: 'cpu',
      performance_mode: 'high',
      performance_mode_expiry: 'activity',
    });
    expect(svc.mode()).toBe('high');
    expect(svc.expiry()).toBe('activity');
  });
});
