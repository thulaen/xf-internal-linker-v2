import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed, fakeAsync, tick } from '@angular/core/testing';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { errorInterceptor } from './error.interceptor';

/**
 * Verifies that the error interceptor surfaces server-supplied error
 * detail in the snackbar copy (Gap 9). Without this, the user always
 * saw "An unexpected error occurred" even when the backend told them
 * exactly what went wrong (e.g. "Quota exceeded for GA4 — wait 60s").
 */
describe('errorInterceptor', () => {
  let http: HttpClient;
  let httpMock: HttpTestingController;
  let snackOpen: Spy;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [MatSnackBarModule, NoopAnimationsModule],
      providers: [
        provideHttpClient(withInterceptors([errorInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpClient);
    httpMock = TestBed.inject(HttpTestingController);
    snackOpen = vi.spyOn(TestBed.inject(MatSnackBar), 'open');
  });

  afterEach(() => httpMock.verify());

  it('surfaces error.detail (string) in the snackbar copy', () => {
    http.post('/api/x', {}).subscribe({
      next: () => expect.fail('expected error'),
      error: () => undefined,
    });
    httpMock.expectOne('/api/x').flush(
      { detail: 'Quota exceeded for GA4 — wait 60 seconds' },
      { status: 400, statusText: 'Bad Request' }
    );
    expect(snackOpen).toHaveBeenCalled();
    expect(snackOpen.mock.calls.at(-1)![0]).toBe(
      'Quota exceeded for GA4 — wait 60 seconds'
    );
  });

  it('surfaces error.detail (array) in the snackbar copy', () => {
    http.post('/api/y', {}).subscribe({
      next: () => expect.fail('expected error'),
      error: () => undefined,
    });
    httpMock
      .expectOne('/api/y')
      .flush(
        { detail: ['Field is required.'] },
        { status: 400, statusText: 'Bad Request' }
      );
    expect(snackOpen.mock.calls.at(-1)![0]).toBe('Field is required.');
  });

  it('surfaces field-level errors when no top-level detail exists', () => {
    http.post('/api/z', {}).subscribe({
      next: () => expect.fail('expected error'),
      error: () => undefined,
    });
    httpMock.expectOne('/api/z').flush(
      { username: ['already taken'] },
      { status: 400, statusText: 'Bad Request' }
    );
    expect(snackOpen.mock.calls.at(-1)![0]).toBe('already taken');
  });

  it('falls back to the default message when no server detail is present', fakeAsync(() => {
    http.get('/api/foo').subscribe({
      next: () => expect.fail('expected error'),
      error: () => undefined,
    });
    httpMock
      .expectOne('/api/foo')
      .flush('', { status: 503, statusText: 'Service Unavailable' });
    // 503 GET is retried via `timer(1000)` in the interceptor — advance the
    // virtual clock past that delay so the retried request is actually issued.
    tick(1000);
    httpMock
      .expectOne('/api/foo')
      .flush('', { status: 503, statusText: 'Service Unavailable' });
    expect(snackOpen.mock.calls.at(-1)![0]).toBe(
      'Server error — please try again later'
    );
  }));

  it('does not show a snackbar for telemetry endpoints', () => {
    http.post('/api/telemetry/web-vitals/', {}).subscribe({
      next: () => expect.fail('expected error'),
      error: () => undefined,
    });
    httpMock
      .expectOne('/api/telemetry/web-vitals/')
      .flush('', { status: 500, statusText: 'Internal' });
    expect(snackOpen).not.toHaveBeenCalled();
  });
});
