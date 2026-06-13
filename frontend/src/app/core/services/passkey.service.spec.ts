import { provideHttpClient, withXhr } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { PasskeyService } from './passkey.service';

describe('PasskeyService', () => {
  let service: PasskeyService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [PasskeyService, provideHttpClient(withXhr()), provideHttpClientTesting()],
    });
    service = TestBed.inject(PasskeyService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('isBrowserSupported() returns boolean depending on WebAuthn presence', () => {
    // Headless Chrome ships PublicKeyCredential and navigator.credentials,
    // so the support check should be true here.
    expect(service.isBrowserSupported()).toBe(true);
  });

  it('register() returns {ok:false, reason:"unsupported"} when WebAuthn is unavailable', async () => {
    vi.spyOn(service, 'isBrowserSupported').mockReturnValue(false);
    const result = await service.register('My phone');
    expect(result).toEqual({ ok: false, reason: 'unsupported' });
  });

  it('login() returns {ok:false, reason:"unsupported"} when WebAuthn is unavailable', async () => {
    vi.spyOn(service, 'isBrowserSupported').mockReturnValue(false);
    const result = await service.login();
    expect(result).toEqual({ ok: false, reason: 'unsupported' });
  });

  it('listCredentials() GETs the credentials endpoint', () => {
    service.listCredentials().subscribe();
    const req = httpMock.expectOne('/api/auth/passkey/credentials/');
    expect(req.request.method).toBe('GET');
    req.flush([]);
  });

  it('relabelCredential() PATCHes the per-id endpoint with the new label', () => {
    service.relabelCredential(7, 'Work iPhone').subscribe();
    const req = httpMock.expectOne('/api/auth/passkey/credentials/7/');
    expect(req.request.method).toBe('PATCH');
    expect(req.request.body).toEqual({ label: 'Work iPhone' });
    req.flush({} as any);
  });

  it('deleteCredential() DELETEs the per-id endpoint', () => {
    service.deleteCredential(8).subscribe();
    const req = httpMock.expectOne('/api/auth/passkey/credentials/8/');
    expect(req.request.method).toBe('DELETE');
    req.flush(null);
  });

  it('isAvailable() returns false when the browser does not support WebAuthn', async () => {
    vi.spyOn(service, 'isBrowserSupported').mockReturnValue(false);
    expect(await service.isAvailable()).toBe(false);
  });

  it('isAvailable() returns true when the begin endpoint exists (status != 404)', async () => {
    vi.spyOn(window, 'fetch').mockResolvedValue({ status: 200 } as Response);
    expect(await service.isAvailable()).toBe(true);
  });

  it('isAvailable() returns false when the begin endpoint 404s', async () => {
    vi.spyOn(window, 'fetch').mockResolvedValue({ status: 404 } as Response);
    expect(await service.isAvailable()).toBe(false);
  });

  it('isAvailable() returns false when fetch rejects (network error)', async () => {
    vi.spyOn(window, 'fetch').mockRejectedValue(new Error('offline'));
    expect(await service.isAvailable()).toBe(false);
  });
});
