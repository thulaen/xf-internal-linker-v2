import { ComponentFixture, TestBed } from '@angular/core/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { of } from 'rxjs';
import { vi } from 'vitest';

import { ConnectionSetupWizardComponent } from './connection-setup-wizard.component';
import {
  GA4TelemetrySettings,
  GoogleOAuthSettings,
  GSCSettings,
  MatomoReadiness,
  SiloSettingsService,
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

const GOOGLE: GoogleOAuthSettings = {
  client_id: '123456789-app.apps.googleusercontent.com',
  client_secret_configured: true,
  oauth_connected: false,
  can_sign_in: true,
  credential_source: 'app',
  status: 'not_configured',
  message: 'Click Connect Google to finish setup.',
  last_sync: null,
};

const GA4: GA4TelemetrySettings = {
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

const GSC: GSCSettings = {
  ranking_weight: 0.05,
  property_url: '',
  client_email: '',
  private_key_configured: false,
  sync_enabled: false,
  sync_lookback_days: 14,
  manual_backfill_max_days: 365,
  manual_backfill_suggested_days: 180,
  excluded_countries: [],
  connection_status: 'not_configured',
  connection_message: 'Connect Google.',
  oauth_connected: false,
  last_sync: null,
  health: HEALTH,
};

const READINESS: MatomoReadiness = {
  status: 'not_ready',
  message: 'Matomo connection worked, but Matomo returned 0 visits.',
  visits_fetched: 0,
  known_content_url_paths: 0,
  matched_page_visits: 0,
  dstp_transition_rows: 0,
  last_sync: null,
};

describe('ConnectionSetupWizardComponent', () => {
  let fixture: ComponentFixture<ConnectionSetupWizardComponent>;
  let service: ReturnType<typeof buildServiceStub>;

  function buildServiceStub() {
    return {
      updateGoogleOAuthSettings: vi.fn(),
      getGoogleAuthUrl: vi.fn(),
      getGoogleSetupChoices: vi.fn(),
      updateGA4TelemetrySettings: vi.fn(),
      testGA4TelemetryReadConnection: vi.fn(),
      updateGSCSettings: vi.fn(),
      testGSCConnection: vi.fn(),
      updateXenForoSettings: vi.fn(),
      runXenForoSync: vi.fn(),
      updateWordPressSettings: vi.fn(),
      runWordPressSync: vi.fn(),
    };
  }

  beforeEach(async () => {
    service = buildServiceStub();
    service.updateGoogleOAuthSettings.mockReturnValue(of(GOOGLE));
    service.getGoogleAuthUrl.mockReturnValue(of({ authorization_url: '/google/start' }));
    service.getGoogleSetupChoices.mockReturnValue(
      of({
        status: 'connected',
        message: 'loaded',
        ga4_properties: [],
        ga4_streams: [
          { property_id: '335454538', stream_id: '4119085177', display_name: 'Web', measurement_id: 'G-LL8JM7BSR2' },
        ],
        gsc_sites: [{ site_url: 'https://www.goldmidi.com/', permission_level: 'siteOwner' }],
      }),
    );
    service.updateGA4TelemetrySettings.mockReturnValue(of(GA4));
    service.testGA4TelemetryReadConnection.mockReturnValue(of({ status: 'connected', message: 'ok' }));
    service.updateGSCSettings.mockReturnValue(of(GSC));
    service.testGSCConnection.mockReturnValue(of({ status: 'connected', message: 'ok' }));
    service.updateXenForoSettings.mockReturnValue(of({ status: 'saved' }));
    service.runXenForoSync.mockReturnValue(of({ job_id: 'xf-1', source: 'api', mode: 'full' }));
    service.updateWordPressSettings.mockReturnValue(of({} as WordPressSettings));
    service.runWordPressSync.mockReturnValue(of({ job_id: 'wp-1', source: 'wp', mode: 'full' }));

    await TestBed.configureTestingModule({
      imports: [ConnectionSetupWizardComponent, NoopAnimationsModule],
      providers: [{ provide: SiloSettingsService, useValue: service }],
    }).compileComponents();

    fixture = TestBed.createComponent(ConnectionSetupWizardComponent);
    fixture.componentRef.setInput('googleOAuth', GOOGLE);
    fixture.componentRef.setInput('ga4Telemetry', GA4);
    fixture.componentRef.setInput('ga4Gsc', GSC);
    fixture.componentRef.setInput('matomoReadiness', READINESS);
    fixture.componentRef.setInput('xenforo', {
      base_url: '',
      api_key_configured: false,
      health: HEALTH,
    } satisfies XenForoSettings);
    fixture.componentRef.setInput('wordpress', {
      base_url: '',
      username: '',
      app_password_configured: false,
      sync_enabled: false,
      sync_hour: 3,
      sync_minute: 0,
      health: HEALTH,
    } satisfies WordPressSettings);
    fixture.detectChanges();
  });

  it('shows the Matomo zero-row readiness message', () => {
    expect(fixture.nativeElement.textContent).toContain('Matomo connection worked');
  });

  it('shows one-click Google connect before advanced setup fields', () => {
    const text = fixture.nativeElement.textContent;

    expect(text).toContain('Connect Google');
    expect(text).toContain('No client ID or secret needed here.');
    expect(fixture.nativeElement.querySelector('.advanced-google-setup')?.open).toBe(false);
  });

  it('applies a selected GA4 stream without enabling sync before the read test', () => {
    fixture.componentInstance.loadGoogleChoices();
    fixture.componentInstance.applyGa4Stream('335454538', 'G-LL8JM7BSR2');

    expect(service.updateGA4TelemetrySettings).toHaveBeenCalledWith(
      expect.objectContaining({
        property_id: '335454538',
        measurement_id: 'G-LL8JM7BSR2',
        sync_enabled: false,
      }),
    );
  });

  it('starts Google sign-in from the guided setup path', () => {
    const originalLocation = window.location;
    const locationStub = { ...originalLocation, href: '' } as Location;
    Object.defineProperty(window, 'location', { configurable: true, value: locationStub });

    fixture.componentInstance.startGoogleSignIn();

    expect(service.getGoogleAuthUrl).toHaveBeenCalled();
    expect(window.location.href).toBe('/google/start');

    Object.defineProperty(window, 'location', { configurable: true, value: originalLocation });
  });

  it('does not start Google sign-in when the backend says credentials are incomplete', () => {
    fixture.componentRef.setInput('googleOAuth', {
      ...GOOGLE,
      client_id: '',
      client_secret_configured: false,
      can_sign_in: false,
      credential_source: 'none',
      status: 'not_configured',
      message: 'Built-in Google sign-in is not configured yet.',
    });
    fixture.detectChanges();

    fixture.componentInstance.startGoogleSignIn();

    expect(service.getGoogleAuthUrl).not.toHaveBeenCalled();
    expect(fixture.componentInstance.canStartGoogleSignIn).toBe(false);
    expect(fixture.nativeElement.textContent).toContain(
      'Open Advanced setup and save Google app details before signing in.',
    );
  });

  it('auto-loads Google choices and enables GA4 plus Search Console after sign-in', () => {
    fixture.componentRef.setInput('googleOAuth', {
      ...GOOGLE,
      oauth_connected: true,
      status: 'connected',
      message: 'Connected to Google.',
    });
    fixture.detectChanges();

    expect(service.getGoogleSetupChoices).toHaveBeenCalled();
    expect(service.testGA4TelemetryReadConnection).toHaveBeenCalledWith({ property_id: '335454538' });
    expect(service.testGSCConnection).toHaveBeenCalledWith({ property_url: 'https://www.goldmidi.com/' });
    expect(service.updateGA4TelemetrySettings).toHaveBeenCalledWith(
      expect.objectContaining({
        property_id: '335454538',
        measurement_id: 'G-LL8JM7BSR2',
        sync_enabled: true,
      }),
    );
    expect(service.updateGSCSettings).toHaveBeenCalledWith(
      expect.objectContaining({
        property_url: 'https://www.goldmidi.com/',
        sync_enabled: true,
      }),
    );
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain(
      'Google setup finished. GA4 and Search Console are ready for DSTP.',
    );
  });

  it('enables GSC sync only after the connection test passes', () => {
    fixture.componentInstance.applyGscSite('https://www.goldmidi.com/');
    fixture.componentInstance.testGscAndEnable();

    expect(service.testGSCConnection).toHaveBeenCalled();
    expect(service.updateGSCSettings).toHaveBeenCalledWith(
      expect.objectContaining({
        property_url: 'https://www.goldmidi.com/',
        sync_enabled: true,
      }),
    );
  });
});
