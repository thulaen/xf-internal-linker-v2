import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, OnChanges, Output, SimpleChanges, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatStepperModule } from '@angular/material/stepper';
import { MatTooltipModule } from '@angular/material/tooltip';
import { catchError, forkJoin, map, Observable, of, switchMap } from 'rxjs';

import {
  GA4TelemetrySettings,
  GA4TelemetryUpdate,
  GoogleOAuthSettings,
  GoogleSetupChoices,
  GSCSettings,
  MatomoReadiness,
  SiloSettingsService,
  WordPressSettings,
  XenForoSettings,
} from '../silo-settings.service';

type GoogleSetupResult = {
  label: string;
  ok: boolean;
};

@Component({
  selector: 'app-connection-setup-wizard',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatCardModule,
    MatChipsModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatStepperModule,
    MatTooltipModule,
  ],
  templateUrl: './connection-setup-wizard.component.html',
  styleUrls: ['./connection-setup-wizard.component.scss'],
})
export class ConnectionSetupWizardComponent implements OnChanges {
  private siloSvc = inject(SiloSettingsService);

  @Input({ required: true }) googleOAuth!: GoogleOAuthSettings;
  @Input({ required: true }) ga4Telemetry!: GA4TelemetrySettings;
  @Input({ required: true }) ga4Gsc!: GSCSettings;
  @Input({ required: true }) matomoReadiness!: MatomoReadiness;
  @Input({ required: true }) xenforo!: XenForoSettings;
  @Input({ required: true }) wordpress!: WordPressSettings;
  @Output() refreshRequested = new EventEmitter<void>();

  googleClientId = '';
  googleClientSecret = '';
  xfApiKey = '';
  wordpressPassword = '';
  googleChoices: GoogleSetupChoices | null = null;
  busy = '';
  setupMessage = '';
  private autoSetupStarted = false;
  private autoSetupFinished = false;

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['googleOAuth']) {
      this.googleClientId = this.googleOAuth?.client_id ?? '';
      this.maybeStartGoogleAutoSetup();
    }
  }

  get redirectUri(): string {
    return `${window.location.origin}/api/analytics/oauth/callback/`;
  }

  get canStartGoogleSignIn(): boolean {
    return Boolean(this.googleOAuth?.can_sign_in);
  }

  get googleConnectHint(): string {
    if (this.googleOAuth?.credential_source === 'app') {
      return 'No client ID or secret needed here.';
    }
    if (this.canStartGoogleSignIn) {
      return 'Google app details are saved.';
    }
    if (this.googleClientId.trim() || this.googleClientSecret.trim()) {
      return 'Save the Google app details before signing in.';
    }
    return 'Open Advanced setup and save Google app details before signing in.';
  }

  saveGoogleApp(): void {
    this.busy = 'google-save';
    const payload = {
      client_id: this.googleClientId.trim(),
      ...(this.googleClientSecret.trim() ? { client_secret: this.googleClientSecret.trim() } : {}),
    };
    this.siloSvc.updateGoogleOAuthSettings(payload).subscribe({
      next: () => this.finishAction(),
      error: () => this.finishAction(),
    });
  }

  startGoogleSignIn(): void {
    if (!this.canStartGoogleSignIn) {
      return;
    }
    this.busy = 'google-signin';
    this.siloSvc.getGoogleAuthUrl().subscribe({
      next: (res) => {
        this.busy = '';
        if (res.authorization_url) {
          window.location.href = res.authorization_url;
        }
      },
      error: () => {
        this.busy = '';
      },
    });
  }

  loadGoogleChoices(): void {
    this.busy = 'google-choices';
    this.siloSvc.getGoogleSetupChoices().subscribe({
      next: (choices) => {
        this.googleChoices = choices;
        this.busy = '';
      },
      error: () => {
        this.googleChoices = null;
        this.setupMessage = 'Google sign-in worked, but setup choices did not load.';
        this.busy = '';
      },
    });
  }

  setupGoogleFeedsForDstp(): void {
    if (!this.googleOAuth?.oauth_connected) {
      this.setupMessage = 'Connect Google first, then the app can prepare GA4 and Search Console.';
      return;
    }
    if (this.googleChoices) {
      this.autoConfigureGoogleChoices(this.googleChoices);
      return;
    }
    this.busy = 'google-auto-setup';
    this.siloSvc.getGoogleSetupChoices().subscribe({
      next: (choices) => {
        this.googleChoices = choices;
        this.autoConfigureGoogleChoices(choices);
      },
      error: () => {
        this.busy = '';
        this.setupMessage = 'Google sign-in worked, but GA4 and Search Console choices did not load.';
      },
    });
  }

  applyGa4Stream(propertyId: string, measurementId: string): void {
    const next = { ...this.ga4Telemetry, property_id: propertyId, measurement_id: measurementId };
    this.ga4Telemetry = next;
    this.siloSvc.updateGA4TelemetrySettings(this.ga4Payload(next, false)).subscribe({
      next: () => this.refreshRequested.emit(),
    });
  }

  testGa4ReadAndEnable(): void {
    this.busy = 'ga4-test';
    this.siloSvc.testGA4TelemetryReadConnection({ property_id: this.ga4Telemetry.property_id }).subscribe({
      next: () => {
        this.siloSvc.updateGA4TelemetrySettings(this.ga4Payload(this.ga4Telemetry, true)).subscribe({
          next: () => this.finishAction(),
          error: () => this.finishAction(),
        });
      },
      error: () => this.finishAction(),
    });
  }

  applyGscSite(siteUrl: string): void {
    this.ga4Gsc = { ...this.ga4Gsc, property_url: siteUrl };
    this.saveGsc(siteUrl, false);
  }

  testGscAndEnable(): void {
    this.busy = 'gsc-test';
    this.siloSvc.testGSCConnection({ property_url: this.ga4Gsc.property_url }).subscribe({
      next: () => this.saveGsc(this.ga4Gsc.property_url, true),
      error: () => this.finishAction(),
    });
  }

  saveXenForo(): void {
    this.busy = 'xf-save';
    this.siloSvc
      .updateXenForoSettings({
        base_url: this.xenforo.base_url,
        ...(this.xfApiKey.trim() ? { api_key: this.xfApiKey.trim() } : {}),
      })
      .subscribe({ next: () => this.finishAction(), error: () => this.finishAction() });
  }

  runXenForoSync(): void {
    this.busy = 'xf-sync';
    this.siloSvc.runXenForoSync().subscribe({ next: () => this.finishAction(), error: () => this.finishAction() });
  }

  saveWordPress(): void {
    this.busy = 'wp-save';
    this.siloSvc
      .updateWordPressSettings({
        base_url: this.wordpress.base_url,
        username: this.wordpress.username,
        sync_enabled: this.wordpress.sync_enabled,
        sync_hour: Number(this.wordpress.sync_hour),
        sync_minute: Number(this.wordpress.sync_minute),
        ...(this.wordpressPassword.trim() ? { app_password: this.wordpressPassword.trim() } : {}),
      })
      .subscribe({ next: () => this.finishAction(), error: () => this.finishAction() });
  }

  runWordPressSync(): void {
    this.busy = 'wp-sync';
    this.siloSvc.runWordPressSync().subscribe({ next: () => this.finishAction(), error: () => this.finishAction() });
  }

  private saveGsc(propertyUrl: string, syncEnabled: boolean): void {
    this.siloSvc
      .updateGSCSettings({
        ranking_weight: this.ga4Gsc.ranking_weight,
        property_url: propertyUrl,
        client_email: this.ga4Gsc.client_email,
        sync_enabled: syncEnabled,
        sync_lookback_days: this.ga4Gsc.sync_lookback_days,
      })
      .subscribe({ next: () => this.finishAction(), error: () => this.finishAction() });
  }

  private maybeStartGoogleAutoSetup(): void {
    if (!this.googleOAuth?.oauth_connected || this.autoSetupStarted || this.autoSetupFinished || this.busy) {
      return;
    }
    this.autoSetupStarted = true;
    this.setupGoogleFeedsForDstp();
  }

  private autoConfigureGoogleChoices(choices: GoogleSetupChoices): void {
    const requests = this.googleSetupRequests(choices);
    if (requests.length === 0) {
      this.busy = '';
      this.setupMessage = 'Google connected, but no GA4 web stream or Search Console site was found.';
      return;
    }
    this.busy = 'google-auto-setup';
    this.setupMessage = 'Setting up GA4 and Search Console for DSTP.';
    forkJoin(requests).subscribe({
      next: (results) => this.finishGoogleAutoSetup(results),
      error: () => {
        this.busy = '';
        this.setupMessage = 'Google setup stopped before all checks finished.';
      },
    });
  }

  private googleSetupRequests(choices: GoogleSetupChoices): Array<Observable<GoogleSetupResult>> {
    const requests: Array<Observable<GoogleSetupResult>> = [];
    const stream = choices.ga4_streams[0];
    const site = choices.gsc_sites[0];
    if (stream) {
      requests.push(this.testAndEnableGa4$(stream.property_id, stream.measurement_id));
    }
    if (site) {
      requests.push(this.testAndEnableGsc$(site.site_url));
    }
    return requests;
  }

  private testAndEnableGa4$(propertyId: string, measurementId: string): Observable<GoogleSetupResult> {
    const next = { ...this.ga4Telemetry, property_id: propertyId, measurement_id: measurementId };
    this.ga4Telemetry = next;
    return this.siloSvc.updateGA4TelemetrySettings(this.ga4Payload(next, false)).pipe(
      switchMap(() => this.siloSvc.testGA4TelemetryReadConnection({ property_id: propertyId })),
      switchMap(() => this.siloSvc.updateGA4TelemetrySettings(this.ga4Payload(next, true))),
      map(() => ({ label: 'GA4', ok: true })),
      catchError(() => of({ label: 'GA4', ok: false })),
    );
  }

  private testAndEnableGsc$(siteUrl: string): Observable<GoogleSetupResult> {
    this.ga4Gsc = { ...this.ga4Gsc, property_url: siteUrl };
    return this.siloSvc.testGSCConnection({ property_url: siteUrl }).pipe(
      switchMap(() => this.siloSvc.updateGSCSettings(this.gscPayload(siteUrl, true))),
      map(() => ({ label: 'Search Console', ok: true })),
      catchError(() => of({ label: 'Search Console', ok: false })),
    );
  }

  private gscPayload(
    propertyUrl: string,
    syncEnabled: boolean,
  ): {
    ranking_weight: number;
    property_url: string;
    client_email: string;
    sync_enabled: boolean;
    sync_lookback_days: number;
  } {
    return {
      ranking_weight: this.ga4Gsc.ranking_weight,
      property_url: propertyUrl,
      client_email: this.ga4Gsc.client_email,
      sync_enabled: syncEnabled,
      sync_lookback_days: this.ga4Gsc.sync_lookback_days,
    };
  }

  private finishGoogleAutoSetup(results: GoogleSetupResult[]): void {
    const failed = results.filter((result) => !result.ok).map((result) => result.label);
    this.busy = '';
    this.autoSetupFinished = failed.length === 0;
    this.setupMessage =
      failed.length === 0
        ? 'Google setup finished. GA4 and Search Console are ready for DSTP.'
        : `Google connected, but ${failed.join(' and ')} setup failed.`;
    this.refreshRequested.emit();
  }

  private ga4Payload(settings: GA4TelemetrySettings, syncEnabled: boolean): GA4TelemetryUpdate {
    return {
      behavior_enabled: settings.behavior_enabled,
      property_id: settings.property_id,
      measurement_id: settings.measurement_id,
      read_project_id: settings.read_project_id,
      read_client_email: settings.read_client_email,
      sync_enabled: syncEnabled,
      sync_lookback_days: settings.sync_lookback_days,
      event_schema: settings.event_schema,
      geo_granularity: settings.geo_granularity,
      retention_days: settings.retention_days,
      impression_visible_ratio: settings.impression_visible_ratio,
      impression_min_ms: settings.impression_min_ms,
      engaged_min_seconds: settings.engaged_min_seconds,
    };
  }

  private finishAction(): void {
    this.busy = '';
    this.googleClientSecret = '';
    this.wordpressPassword = '';
    this.xfApiKey = '';
    this.refreshRequested.emit();
  }
}
