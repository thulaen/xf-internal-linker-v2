/**
 * Specs for the extracted Connect & Sync tab. Mirrors the contract the
 * parent settings page used to enforce inline:
 *   - Loads all eight connection settings via the seven known endpoints
 *     on init (single forkJoin).
 *   - `markDirty()` emits `dirtyChanged=true`.
 *   - `saveXenForoSettings()` PUTs `/api/settings/xenforo/`, then GETs
 *     `/api/settings/xenforo/` to refresh the health snapshot.
 *   - `testWordPressConnection()` POSTs `/api/settings/wordpress/test-connection/`.
 *   - `updateGSCSettings()` PUTs `/api/analytics/settings/gsc/` and posts
 *     the embedded `private_key` only when the textarea is non-empty.
 *   - The eight cards (XenForo, WordPress, Crawler, Webhooks, Google,
 *     GA4, Matomo, GSC) render without throwing.
 */
import { TestBed } from '@angular/core/testing';
import { provideHttpClient, withXhr } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { provideRouter } from '@angular/router';

import { ConnectSyncTabComponent } from './connect-sync-tab.component';
import {
  GA4TelemetrySettings,
  GoogleOAuthSettings,
  GSCSettings,
  MatomoTelemetrySettings,
  SiloSettingsService,
  WebhookSettings,
  WordPressSettings,
  XenForoSettings,
} from '../silo-settings.service';

const HEALTH = {
  status: 'healthy',
  label: 'Connected',
  name: '',
  description: '',
  issue: '',
  fix: '',
  last_success: null,
  is_healthy: true,
};

const XENFORO_DEFAULTS: XenForoSettings = {
  base_url: 'https://forum.example.com',
  api_key_configured: true,
  health: HEALTH,
};

const WORDPRESS_DEFAULTS: WordPressSettings = {
  base_url: 'https://example.com',
  username: 'admin',
  app_password_configured: true,
  sync_enabled: false,
  sync_hour: 3,
  sync_minute: 0,
  health: HEALTH,
};

const WEBHOOK_DEFAULTS: WebhookSettings = { xf_secret_configured: false, wp_secret_configured: false };

const GOOGLE_OAUTH_DEFAULTS: GoogleOAuthSettings = {
  client_id: '',
  client_secret_configured: false,
  oauth_connected: false,
  status: 'not_configured',
  message: 'Not connected.',
  last_sync: null,
};

const GA4_DEFAULTS: GA4TelemetrySettings = {
  behavior_enabled: false,
  property_id: '',
  measurement_id: '',
  api_secret_configured: false,
  read_project_id: '',
  read_client_email: '',
  read_private_key_configured: false,
  sync_enabled: false,
  sync_lookback_days: 7,
  event_schema: 'fr016_v1',
  geo_granularity: 'country',
  retention_days: 400,
  impression_visible_ratio: 0.5,
  impression_min_ms: 1000,
  engaged_min_seconds: 10,
  connection_status: 'not_configured',
  connection_message: 'Fill in fields.',
  read_connection_status: 'not_configured',
  read_connection_message: 'Fill in fields.',
  last_sync: null,
  oauth_connected: false,
  google_oauth_client_id: '',
  google_oauth_client_secret_configured: false,
  ga4_health: HEALTH,
  gsc_health: HEALTH,
};

const MATOMO_DEFAULTS: MatomoTelemetrySettings = {
  enabled: false,
  url: '',
  site_id_xenforo: '',
  site_id_wordpress: '',
  token_auth_configured: false,
  sync_enabled: false,
  sync_lookback_days: 7,
  connection_status: 'not_configured',
  connection_message: 'Fill in fields.',
  last_sync: null,
};

const GSC_DEFAULTS: GSCSettings = {
  ranking_weight: 0.05,
  property_url: '',
  client_email: '',
  private_key_configured: false,
  sync_enabled: false,
  sync_lookback_days: 7,
  manual_backfill_max_days: 365,
  manual_backfill_suggested_days: 180,
  excluded_countries: [],
  connection_status: 'not_configured',
  connection_message: 'Connect via Google OAuth or fill in service-account credentials.',
  oauth_connected: false,
  last_sync: null,
  health: HEALTH,
};

describe('ConnectSyncTabComponent', () => {
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ConnectSyncTabComponent, NoopAnimationsModule],
      providers: [
        provideHttpClient(withXhr()),
        provideHttpClientTesting(),
        provideRouter([]),
        // Use the real SiloSettingsService so the load + save HTTP calls
        // go through the actual endpoint paths the spec asserts on via
        // HttpTestingController. Same pattern as
        // library-history-tab.component.spec.ts.
        SiloSettingsService,
      ],
    }).compileComponents();

    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  /**
   * Drains the seven GETs ngOnInit fires inside one forkJoin. Order is
   * not guaranteed; match by URL via `expectOne(url)` instead of
   * positional `match`.
   */
  function flushInitialLoad(): void {
    httpMock.expectOne('/api/analytics/settings/gsc/').flush(GSC_DEFAULTS);
    httpMock.expectOne('/api/analytics/settings/google-oauth/').flush(GOOGLE_OAUTH_DEFAULTS);
    httpMock.expectOne('/api/analytics/settings/ga4/').flush(GA4_DEFAULTS);
    httpMock.expectOne('/api/analytics/settings/matomo/').flush(MATOMO_DEFAULTS);
    httpMock.expectOne('/api/settings/xenforo/').flush(XENFORO_DEFAULTS);
    httpMock.expectOne('/api/settings/wordpress/').flush(WORDPRESS_DEFAULTS);
    httpMock.expectOne('/api/settings/webhooks/').flush(WEBHOOK_DEFAULTS);
  }

  it('renders the eight Connect & Sync cards once initial load completes', () => {
    const fixture = TestBed.createComponent(ConnectSyncTabComponent);
    fixture.detectChanges();
    flushInitialLoad();
    fixture.detectChanges();

    const root: HTMLElement = fixture.nativeElement;
    expect(root.querySelector('#xenforo-settings')).not.toBeNull();
    expect(root.querySelector('#wordpress-settings')).not.toBeNull();
    expect(root.querySelector('#crawler-settings')).not.toBeNull();
    expect(root.querySelector('#webhook-settings')).not.toBeNull();
    expect(root.querySelector('#google-settings')).not.toBeNull();
    expect(root.querySelector('#ga4-settings')).not.toBeNull();
    expect(root.querySelector('#matomo-settings')).not.toBeNull();
    expect(root.querySelector('#gsc-settings')).not.toBeNull();
  });

  it('loads xenforo settings into the local copy on init', () => {
    const fixture = TestBed.createComponent(ConnectSyncTabComponent);
    fixture.detectChanges();
    flushInitialLoad();
    fixture.detectChanges();

    const cmp = fixture.componentInstance;
    expect(cmp.xenforo.base_url).toBe('https://forum.example.com');
    expect(cmp.xenforo.api_key_configured).toBe(true);
    expect(cmp.wordpress.username).toBe('admin');
  });

  it('saves XenForo settings via PUT and refreshes via GET on success', () => {
    const fixture = TestBed.createComponent(ConnectSyncTabComponent);
    fixture.detectChanges();
    flushInitialLoad();
    fixture.detectChanges();

    const cmp = fixture.componentInstance;
    cmp.xenforo.base_url = 'https://newforum.example.com';
    cmp.xfApiKey = 'fresh-api-key';
    cmp.saveXenForoSettings();

    const putReq = httpMock.expectOne('/api/settings/xenforo/');
    expect(putReq.request.method).toBe('PUT');
    expect(putReq.request.body.base_url).toBe('https://newforum.example.com');
    expect(putReq.request.body.api_key).toBe('fresh-api-key');
    putReq.flush({ status: 'ok' });

    // Save handler immediately fires a refresh GET so the health pill
    // and api_key_configured badge re-hydrate from the server.
    const getReq = httpMock.expectOne('/api/settings/xenforo/');
    expect(getReq.request.method).toBe('GET');
    getReq.flush({ ...XENFORO_DEFAULTS, base_url: 'https://newforum.example.com' });

    expect(cmp.xfApiKey).toBe('');
    expect(cmp.savingXenForo).toBe(false);
  });

  it('tests the WordPress connection without persisting credentials', () => {
    const fixture = TestBed.createComponent(ConnectSyncTabComponent);
    fixture.detectChanges();
    flushInitialLoad();
    fixture.detectChanges();

    const cmp = fixture.componentInstance;
    cmp.wordpressPassword = 'temp-password';
    cmp.testWordPressConnection();

    const req = httpMock.expectOne('/api/settings/wordpress/test-connection/');
    expect(req.request.method).toBe('POST');
    expect(req.request.body.app_password).toBe('temp-password');
    expect(req.request.body.username).toBe('admin');
    req.flush({ status: 'connected', message: 'Connected to WordPress.' });

    expect(cmp.testingWordPress).toBe(false);
    // Test path never persists; password stays in the local field for
    // the user to keep refining or save.
    expect(cmp.wordpressPassword).toBe('temp-password');
  });

  it('updates GSC settings, including the optional private_key payload', () => {
    const fixture = TestBed.createComponent(ConnectSyncTabComponent);
    fixture.detectChanges();
    flushInitialLoad();
    fixture.detectChanges();

    const cmp = fixture.componentInstance;
    cmp.ga4Gsc.property_url = 'https://example.com/';
    cmp.ga4Gsc.client_email = 'gsc-bot@project.iam.gserviceaccount.com';
    cmp.gscPrivateKey = '-----BEGIN PRIVATE KEY-----';
    cmp.updateGSCSettings();

    const req = httpMock.expectOne('/api/analytics/settings/gsc/');
    expect(req.request.method).toBe('PUT');
    expect(req.request.body.property_url).toBe('https://example.com/');
    expect(req.request.body.private_key).toBe('-----BEGIN PRIVATE KEY-----');
    req.flush({ ...GSC_DEFAULTS, property_url: 'https://example.com/' });

    // Private key is one-shot — cleared after a successful PUT so the
    // textarea returns to its placeholder.
    expect(cmp.gscPrivateKey).toBe('');
    expect(cmp.savingGA4GSC).toBe(false);
  });

  it('emits dirtyChanged true when markDirty is called', () => {
    const fixture = TestBed.createComponent(ConnectSyncTabComponent);
    fixture.detectChanges();
    flushInitialLoad();
    fixture.detectChanges();

    const cmp = fixture.componentInstance;
    const emitted: boolean[] = [];
    cmp.dirtyChanged.subscribe((v) => emitted.push(v));

    cmp.markDirty();

    expect(emitted).toEqual([true]);
  });
});
