import { provideHttpClient, withXhr } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { ObservabilityService } from './observability.service';

describe('ObservabilityService', () => {
  let service: ObservabilityService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [ObservabilityService, provideHttpClient(withXhr()), provideHttpClientTesting()],
    });
    service = TestBed.inject(ObservabilityService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('requests the stack health endpoint through the configured API base', () => {
    service.stack().subscribe((response) => {
      expect(response.services).toEqual([]);
    });

    const req = httpMock.expectOne('/api/observability/stack/');
    expect(req.request.method).toBe('GET');
    req.flush({ services: [] });
  });

  it('passes HTTP errors through to be caught by the component', () =>
    new Promise<void>((done, reject) => {
      service.stack().subscribe({
        next: () => reject('Expected error'),
        error: (err) => {
          expect(err.status).toBe(500);
          done();
        },
      });

      const req = httpMock.expectOne('/api/observability/stack/');
      req.flush('Server Error', { status: 500, statusText: 'Internal Server Error' });
    }));

  // TODO(AutoIssue #21248): Given a malformed or partial response from the backend, When parsed, Then it passes the result without crashing (or lets Angular HTTP client throw).
  it('handles partial or missing data payloads gracefully', () => {
    service.stack().subscribe((response) => {
      expect(response.services).toBeUndefined();
    });

    const req = httpMock.expectOne('/api/observability/stack/');
    req.flush({}); // Missing the 'services' array
  });
});
