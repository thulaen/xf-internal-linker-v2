/**
 * ConnectSyncTabComponent — Settings tab 3 (Connect & Sync).
 *
 * Extracted from the legacy 4,415-line `SettingsComponent` (AutoIssue #31,
 * fourth tab in the prevention-cleanup tabs split). Mechanical move; no
 * behaviour change.
 *
 * Eight cards live here: XenForo connection, WordPress connection,
 * Crawler defaults, Webhook endpoints, Google OAuth, GA4 telemetry,
 * Matomo telemetry, and Google Search Console.
 *
 * The parent `SettingsComponent` keeps its own copies of every settings
 * object on this tab because:
 *   - `noSourceConnected` (rendered in the tab label) reads
 *     `xenforo.health` and `wordpress.health`.
 *   - `saveAllSettings()` builds a forkJoin payload that includes
 *     wordpress, ga4Gsc, googleOAuth, ga4Telemetry, matomoTelemetry.
 *   - `getFeatureSummary()` reads `ga4Gsc.ranking_weight`.
 *   - `reload()` re-hydrates every connection from the server-of-truth.
 *
 * This child duplicates those state objects internally for its own UI
 * and owns its own load + save flow — same pattern as Library & History
 * tab (`<app-library-history-tab>`).
 *
 * Tooltips that depend on the parent's `tip(key)` map are duplicated
 * here through a service-side identity helper (`SETTING_TIPS`) that
 * returns a no-op string for keys without an entry — every Connect &
 * Sync key already has a tooltip in the parent's `SETTING_TOOLTIPS`
 * map, so the rendered text is identical at runtime.
 *
 * One Output:
 *   - `(dirtyChanged)` — same convention as Notifications + Silo +
 *     Library & History tabs; keeps `HasUnsavedChanges` guard wired.
 */
import { ChangeDetectionStrategy, ChangeDetectorRef, Component, EventEmitter, OnDestroy, OnInit, Output, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterModule } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatChipsModule } from '@angular/material/chips';
import { MatDividerModule } from '@angular/material/divider';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Subject, forkJoin } from 'rxjs';
import { takeUntil } from 'rxjs/operators';

import {
  AnalyticsConnectionResult,
  GA4TelemetrySettings,
  GA4TelemetryUpdate,
  GoogleOAuthSettings,
  GSCSettings,
  GSCSettingsUpdate,
  MatomoTelemetrySettings,
  MatomoTelemetryUpdate,
  SiloSettingsService,
  WebhookSettings,
  WebhookSettingsUpdate,
  WordPressSettings,
  WordPressSettingsUpdate,
  XenForoSettings,
  XenForoSettingsUpdate,
} from '../silo-settings.service';
import { SETTING_TOOLTIPS } from '../setting-tooltips';

/**
 * Sentinel record for the "Pending check" health state on a freshly
 * mounted card (before the GET completes). Identical to the one on the
 * parent so the rendered status pill matches.
 */
const DEFAULT_HEALTH = {
  status: 'stale',
  label: 'Pending check',
  name: '',
  description: '',
  issue: '',
  fix: '',
  last_success: null,
  is_healthy: false,
};

@Component({
  selector: 'app-connect-sync-tab',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    FormsModule,
    RouterModule,
    MatButtonModule,
    MatCardModule,
    MatCheckboxModule,
    MatChipsModule,
    MatDividerModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatSnackBarModule,
    MatTooltipModule,
  ],
  templateUrl: './connect-sync-tab.component.html',
  styleUrls: ['./connect-sync-tab.component.scss'],
})
export class ConnectSyncTabComponent implements OnInit, OnDestroy {
  private siloSvc = inject(SiloSettingsService);
  private snack = inject(MatSnackBar);
  private cdr = inject(ChangeDetectorRef);
  private destroy$ = new Subject<void>();

  /** Parent toggles its `isDirty` flag on `true`; never flipped to false here. */
  @Output() dirtyChanged = new EventEmitter<boolean>();

  // ── XenForo ───────────────────────────────────────────────────────
  xenforo: XenForoSettings = {
    base_url: '',
    api_key_configured: false,
    health: DEFAULT_HEALTH,
  };
  xfApiKey = '';
  savingXenForo = false;
  testingXenForo = false;

  // ── WordPress ─────────────────────────────────────────────────────
  wordpress: WordPressSettings = {
    base_url: '',
    username: '',
    app_password_configured: false,
    sync_enabled: false,
    sync_hour: 3,
    sync_minute: 0,
    health: DEFAULT_HEALTH,
  };
  wordpressPassword = '';
  savingWordPress = false;
  testingWordPress = false;
  runningWordPressSync = false;

  // ── Crawler (local UI state — no API calls; saved via parent's Save All) ──
  crawlerExcludedPaths: string[] = [
    '/members/', '/login/', '/register/', '/account/',
    '/search/', '/admin.php', '/help/',
  ];
  newCrawlerExclusion = '';

  // ── Webhook ───────────────────────────────────────────────────────
  webhookSettings: WebhookSettings = { xf_secret_configured: false, wp_secret_configured: false };
  xfWebhookSecret = '';
  wpWebhookSecret = '';
  savingWebhooks = false;
  testingWebhooks = false;

  // ── Google OAuth ──────────────────────────────────────────────────
  googleOAuth: GoogleOAuthSettings = {
    client_id: '',
    client_secret_configured: false,
    oauth_connected: false,
    status: 'not_configured',
    message: 'Paste the Google OAuth client ID and secret once, then sign in once.',
    last_sync: null,
  };
  googleAuthClientId = '';
  googleAuthClientSecret = '';
  savingGoogleAuth = false;

  // ── GA4 telemetry ─────────────────────────────────────────────────
  ga4Telemetry: GA4TelemetrySettings = {
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
    connection_message: 'Fill in the GA4 fields and test the connection.',
    read_connection_status: 'not_configured',
    read_connection_message: 'Fill in the GA4 read-access fields and test read access.',
    last_sync: null,
    oauth_connected: false,
    google_oauth_client_id: '',
    google_oauth_client_secret_configured: false,
    ga4_health: DEFAULT_HEALTH,
    gsc_health: DEFAULT_HEALTH,
  };
  ga4TelemetrySecret = '';
  ga4TelemetryReadPrivateKey = '';
  savingGA4Telemetry = false;
  testingGA4Telemetry = false;
  testingGA4TelemetryRead = false;
  showGA4FallbackFields = false;

  // ── Matomo ────────────────────────────────────────────────────────
  matomoTelemetry: MatomoTelemetrySettings = {
    enabled: false,
    url: '',
    site_id_xenforo: '',
    site_id_wordpress: '',
    token_auth_configured: false,
    sync_enabled: false,
    sync_lookback_days: 7,
    connection_status: 'not_configured',
    connection_message: 'Fill in the Matomo fields and test the connection.',
    last_sync: null,
  };
  matomoTelemetryToken = '';
  savingMatomoTelemetry = false;
  testingMatomoTelemetry = false;

  // ── Google Search Console ─────────────────────────────────────────
  ga4Gsc: GSCSettings = {
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
    health: DEFAULT_HEALTH,
  };
  gscPrivateKey = '';
  gscManualBackfillDays = 180;
  savingGA4GSC = false;
  testingGSCConnection = false;
  runningGSCSync = false;
  showGSCFallbackFields = false;

  ngOnInit(): void {
    this.reload();
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  /**
   * Drains every GET endpoint the tab needs in one forkJoin. Keeps the
   * load symmetric with the parent's `reload()` for these eight cards.
   */
  reload(): void {
    forkJoin({
      ga4Gsc: this.siloSvc.getGSCSettings(),
      googleOAuth: this.siloSvc.getGoogleOAuthSettings(),
      ga4Telemetry: this.siloSvc.getGA4TelemetrySettings(),
      matomoTelemetry: this.siloSvc.getMatomoTelemetrySettings(),
      xenforo: this.siloSvc.getXenForoSettings(),
      wordpress: this.siloSvc.getWordPressSettings(),
      webhookSettings: this.siloSvc.getWebhookSettings(),
    }).pipe(takeUntil(this.destroy$)).subscribe({
      next: (data) => {
        this.ga4Gsc = { ...this.ga4Gsc, ...data.ga4Gsc };
        this.gscManualBackfillDays = Math.max(
          Number(this.ga4Gsc.sync_lookback_days || 1),
          Number(this.ga4Gsc.manual_backfill_suggested_days || 180),
        );
        this.googleOAuth = { ...this.googleOAuth, ...data.googleOAuth };
        this.googleAuthClientId = data.googleOAuth.client_id || '';
        this.googleAuthClientSecret = '';
        this.ga4Telemetry = { ...this.ga4Telemetry, ...data.ga4Telemetry };
        this.matomoTelemetry = { ...this.matomoTelemetry, ...data.matomoTelemetry };
        this.xenforo = { ...this.xenforo, ...data.xenforo };
        this.wordpress = { ...this.wordpress, ...data.wordpress };
        this.webhookSettings = { ...this.webhookSettings, ...data.webhookSettings };
        this.cdr.markForCheck();
      },
      error: () => {
        // Parent's giant reload covers errors via its own snack; the child
        // stays quiet so we don't double-toast on a single network blip.
        this.cdr.markForCheck();
      },
    });
  }

  /** Bound to every form-field `(ngModelChange)` so dirty signals propagate. */
  markDirty(): void {
    this.dirtyChanged.emit(true);
  }

  // ── Tip helpers (mirror parent `tip()` and helper methods) ────────

  /**
   * Tooltip lookup — the parent owns the canonical `SETTING_TOOLTIPS`
   * map plus dynamic severity warnings. Here we render the Material
   * tooltip via `[matTooltip]` only (no rich text), so passing the bare
   * key string is fine — the actual tooltip source still lives on the
   * parent. This matches how the silo-architecture tab handles
   * tooltips after extraction (returns the key for hover).
   */
  tip(key: string): string {
    const t = SETTING_TOOLTIPS[key];
    if (!t) return `No tooltip defined for "${key}" - add an entry to SETTING_TOOLTIPS in setting-tooltips.ts`;
    
    const lines: string[] = [];
    if (t.definition) lines.push(t.definition);
    if (t.impact) lines.push(`Impact: ${t.impact}`);
    if (t.default) lines.push(`Default: ${t.default}`);
    if (t.example) lines.push(`Example: ${t.example}`);
    if (t.range) lines.push(`Range: ${t.range}`);
    
    return lines.join('\n\n');
  }

  telemetryStatusLabel(status: string): string {
    switch (status) {
      case 'connected': return $localize`:@@settings.status.connected:Connected`;
      case 'saved': return $localize`:@@settings.status.saved:Saved`;
      case 'error': return $localize`:@@settings.status.error:Error`;
      case 'not_configured': return $localize`:@@settings.status.notConfigured:Not set up`;
      default: return $localize`:@@settings.status.unknown:Unknown`;
    }
  }

  get saveLabel(): string {
    return $localize`:@@settings.actions.save:Save`;
  }

  get savingLabel(): string {
    return $localize`:@@settings.actions.saving:Saving...`;
  }

  get saveXenForoLabel(): string {
    return this.savingXenForo ? this.savingLabel : this.saveLabel;
  }

  get testConnectionLabel(): string {
    return $localize`:@@settings.actions.testConnection:Test Connection`;
  }

  get testingLabel(): string {
    return $localize`:@@settings.actions.testing:Testing...`;
  }

  get saveWordPressLabel(): string {
    return this.savingWordPress ? this.savingLabel : this.saveLabel;
  }

  get saveGA4Label(): string {
    return this.savingGA4Telemetry ? this.savingLabel : this.saveLabel;
  }

  get testGA4Label(): string {
    return this.testingGA4Telemetry 
      ? $localize`:@@settings.actions.testing:Testing...` 
      : $localize`:@@settings.actions.testBrowserEvents:Test Browser Events`;
  }

  get testGA4ReadLabel(): string {
    return this.testingGA4TelemetryRead 
      ? $localize`:@@settings.actions.testingRead:Testing Read...` 
      : $localize`:@@settings.actions.testReadAccess:Test Read Access`;
  }

  get saveMatomoLabel(): string {
    return this.savingMatomoTelemetry ? this.savingLabel : this.saveLabel;
  }

  get testMatomoLabel(): string {
    return this.testingMatomoTelemetry ? this.testingLabel : this.testConnectionLabel;
  }

  get saveWebhooksLabel(): string {
    return this.savingWebhooks ? this.savingLabel : this.saveLabel;
  }

  get saveGSCLabel(): string {
    return this.savingGA4GSC
      ? $localize`:@@settings.actions.saving:Saving...`
      : $localize`:@@settings.actions.saveGSCSettings:Save GSC Settings`;
  }

  get testGSCLabel(): string {
    return this.testingGSCConnection ? this.testingLabel : this.testConnectionLabel;
  }

  get manualBackfillLabel(): string {
    return this.runningGSCSync
      ? $localize`:@@settings.actions.syncing:Syncing...`
      : $localize`:@@settings.actions.manualBackfill:Manual Backfill`;
  }

  telemetryStatusClass(status: string | undefined): string {
    return `status-pill--${status === 'connected' || status === 'healthy' ? 'success' : (status === 'error' || status === 'down') ? 'danger' : (status === 'warning' || status === 'stale') ? 'warning' : status === 'saved' ? 'status' : 'muted'}`;
  }

  getHealthIcon(status: string | undefined): string {
    switch (status) {
      case 'healthy': return 'check_circle';
      case 'warning': return 'warning';
      case 'error': return 'error';
      case 'down': return 'dangerous';
      case 'stale': return 'update';
      default: return 'help_outline';
    }
  }

  healthLabel(status: string | undefined): string {
    switch (status) {
      case 'healthy': return $localize`:@@settings.status.healthy:Healthy`;
      case 'warning': return $localize`:@@settings.status.warning:Warning`;
      case 'error': return $localize`:@@settings.status.error:Error`;
      case 'down': return $localize`:@@settings.status.down:Down`;
      case 'stale': return $localize`:@@settings.status.stale:Stale`;
      default: return status || $localize`:@@settings.status.unknown:Unknown`;
    }
  }

  lastSyncLabel(sync: { completed_at: string | null; started_at: string | null; rows_written: number } | null): string {
    if (!sync) return $localize`:@@settings.sync.neverSynced:Never synced`;
    const stamp = sync.completed_at || sync.started_at;
    const rows = sync.rows_written;
    const rowsWritten = $localize`:@@settings.sync.rowsWritten:{rows, plural, =1 {1 row written} other {${rows}:count: rows written}}`;
    
    if (!stamp) return rowsWritten;
    const dateStr = new Date(stamp).toLocaleString();
    return $localize`:@@settings.sync.lastSyncWithRows:${dateStr}:date: • ${rowsWritten}:summary:`;
  }

  hasGoogleAppCredentials(): boolean {
    return Boolean(this.googleAuthClientId.trim() || this.googleOAuth.client_secret_configured || this.googleAuthClientSecret.trim());
  }

  shouldShowReconnectGoogle(): boolean {
    return !this.googleOAuth.oauth_connected && this.hasGoogleAppCredentials();
  }

  shouldShowGA4FallbackFields(): boolean {
    return this.showGA4FallbackFields || !this.googleOAuth.oauth_connected;
  }

  shouldShowGSCFallbackFields(): boolean {
    return this.showGSCFallbackFields || !this.googleOAuth.oauth_connected;
  }

  // ── Webhook URLs (computed from current origin) ──────────────────

  get xfWebhookUrl(): string { return `${window.location.origin}/api/sync/webhooks/xenforo/`; }
  get wpWebhookUrl(): string { return `${window.location.origin}/api/sync/webhooks/wordpress/`; }

  // ── XenForo ───────────────────────────────────────────────────────

  saveXenForoSettings(): void {
    if (!this.xenforo.base_url.trim()) {
      this.snack.open('Forum URL is required.', 'Dismiss', { duration: 3000 });
      return;
    }
    this.savingXenForo = true;
    const payload: XenForoSettingsUpdate = { base_url: this.xenforo.base_url.trim() };
    if (this.xfApiKey.trim()) {
      payload.api_key = this.xfApiKey.trim();
    }
    this.siloSvc.updateXenForoSettings(payload).pipe(takeUntil(this.destroy$)).subscribe({
      next: () => {
        this.xfApiKey = '';
        this.savingXenForo = false;
        // Refresh from server so `health` and `api_key_configured` reflect
        // the new state — same two-step the parent did.
        this.siloSvc.getXenForoSettings().pipe(takeUntil(this.destroy$)).subscribe({
          next: (xf) => { this.xenforo = { ...this.xenforo, ...xf }; this.cdr.markForCheck(); },
          error: () => {},
        });
        this.snack.open('XenForo credentials saved.', 'Dismiss', { duration: 3000 });
        this.cdr.markForCheck();
      },
      error: (err) => {
        this.savingXenForo = false;
        this.snack.open(err?.error?.detail || 'Failed to save XenForo settings.', 'Dismiss', { duration: 4000 });
        this.cdr.markForCheck();
      },
    });
  }

  testXenForoConnection(): void {
    this.testingXenForo = true;
    this.siloSvc.testXenForoConnection({
      base_url: this.xenforo.base_url?.trim() || undefined,
      api_key: this.xfApiKey?.trim() || undefined,
    }).pipe(takeUntil(this.destroy$)).subscribe({
      next: (result: AnalyticsConnectionResult) => {
        this.testingXenForo = false;
        this.snack.open(result.message, undefined, { duration: 3500 });
        this.cdr.markForCheck();
      },
      error: (error) => {
        this.testingXenForo = false;
        const message = error?.error?.message || error?.error?.detail || 'XenForo connection failed';
        this.snack.open(message, 'Dismiss', { duration: 4500 });
        this.cdr.markForCheck();
      },
    });
  }

  // ── WordPress ─────────────────────────────────────────────────────

  saveWordPressSettings(): void {
    this.savingWordPress = true;
    const payload: WordPressSettingsUpdate = {
      base_url: this.wordpress.base_url.trim(),
      username: this.wordpress.username.trim(),
      sync_enabled: this.wordpress.sync_enabled,
      sync_hour: Number(this.wordpress.sync_hour),
      sync_minute: Number(this.wordpress.sync_minute),
    };
    if (this.wordpressPassword.trim()) {
      payload.app_password = this.wordpressPassword.trim();
    }
    this.siloSvc.updateWordPressSettings(payload).pipe(takeUntil(this.destroy$)).subscribe({
      next: (wordpress) => {
        // Spread-merge: PUT response strips `health` — preserve previously
        // loaded value. See the parent's saveAllSettings for full rationale.
        this.wordpress = { ...this.wordpress, ...(wordpress ?? {}) };
        this.wordpressPassword = '';
        this.savingWordPress = false;
        this.snack.open('WordPress settings saved', undefined, { duration: 2500 });
        this.cdr.markForCheck();
      },
      error: (error) => {
        this.savingWordPress = false;
        this.snack.open(error?.error?.detail || 'Failed to save WordPress settings', 'Dismiss', { duration: 4000 });
        this.cdr.markForCheck();
      },
    });
  }

  testWordPressConnection(): void {
    this.testingWordPress = true;
    this.siloSvc.testWordPressConnection({
      base_url: this.wordpress.base_url?.trim() || undefined,
      username: this.wordpress.username?.trim() || undefined,
      app_password: this.wordpressPassword?.trim() || undefined,
    }).pipe(takeUntil(this.destroy$)).subscribe({
      next: (result: AnalyticsConnectionResult) => {
        this.testingWordPress = false;
        this.snack.open(result.message, undefined, { duration: 3500 });
        this.cdr.markForCheck();
      },
      error: (error) => {
        this.testingWordPress = false;
        const message = error?.error?.message || error?.error?.detail || 'WordPress connection failed';
        this.snack.open(message, 'Dismiss', { duration: 4500 });
        this.cdr.markForCheck();
      },
    });
  }

  clearWordPressPassword(): void {
    this.savingWordPress = true;
    this.siloSvc.updateWordPressSettings({
      base_url: this.wordpress.base_url.trim(),
      username: this.wordpress.username.trim(),
      sync_enabled: this.wordpress.sync_enabled,
      sync_hour: Number(this.wordpress.sync_hour),
      sync_minute: Number(this.wordpress.sync_minute),
      app_password: '',
    }).pipe(takeUntil(this.destroy$)).subscribe({
      next: (wordpress) => {
        this.wordpress = { ...this.wordpress, ...(wordpress ?? {}) };
        this.wordpressPassword = '';
        this.savingWordPress = false;
        this.snack.open('WordPress Application Password cleared', undefined, { duration: 2500 });
        this.cdr.markForCheck();
      },
      error: (error) => {
        this.savingWordPress = false;
        this.snack.open(error?.error?.detail || 'Failed to clear WordPress password', 'Dismiss', { duration: 4000 });
        this.cdr.markForCheck();
      },
    });
  }

  runWordPressSync(): void {
    this.runningWordPressSync = true;
    this.siloSvc.runWordPressSync().pipe(takeUntil(this.destroy$)).subscribe({
      next: (response) => {
        this.runningWordPressSync = false;
        this.snack.open(`WordPress sync started (${response.job_id.slice(0, 8)})`, 'Dismiss', { duration: 5000 });
        this.cdr.markForCheck();
      },
      error: (error) => {
        this.runningWordPressSync = false;
        this.snack.open(error?.error?.detail || 'Failed to start WordPress sync', 'Dismiss', { duration: 4000 });
        this.cdr.markForCheck();
      },
    });
  }

  // ── Crawler exclusions (local UI only) ───────────────────────────

  addCrawlerExclusion(): void {
    const path = this.newCrawlerExclusion.trim();
    if (!path || this.crawlerExcludedPaths.includes(path)) return;
    this.crawlerExcludedPaths = [...this.crawlerExcludedPaths, path];
    this.newCrawlerExclusion = '';
    this.markDirty();
  }

  removeCrawlerExclusion(path: string): void {
    this.crawlerExcludedPaths = this.crawlerExcludedPaths.filter((p) => p !== path);
    this.markDirty();
  }

  // ── Webhooks ──────────────────────────────────────────────────────

  saveWebhookSettings(): void {
    const payload: WebhookSettingsUpdate = {};
    if (this.xfWebhookSecret.trim()) payload.xf_webhook_secret = this.xfWebhookSecret.trim();
    if (this.wpWebhookSecret.trim()) payload.wp_webhook_secret = this.wpWebhookSecret.trim();
    this.savingWebhooks = true;
    this.siloSvc.updateWebhookSettings(payload).pipe(takeUntil(this.destroy$)).subscribe({
      next: (result) => {
        this.webhookSettings = result;
        this.xfWebhookSecret = '';
        this.wpWebhookSecret = '';
        this.savingWebhooks = false;
        this.snack.open('Webhook secrets saved.', undefined, { duration: 2500 });
        this.cdr.markForCheck();
      },
      error: (err) => {
        this.savingWebhooks = false;
        this.snack.open(err?.error?.detail || 'Failed to save webhook secrets.', 'Dismiss', { duration: 4000 });
        this.cdr.markForCheck();
      },
    });
  }

  testWebhookEndpoints(): void {
    this.testingWebhooks = true;
    this.siloSvc.testWebhookEndpoints().pipe(takeUntil(this.destroy$)).subscribe({
      next: (result: AnalyticsConnectionResult) => {
        this.testingWebhooks = false;
        this.snack.open(result.message, undefined, { duration: 3500 });
        this.cdr.markForCheck();
      },
      error: (error) => {
        this.testingWebhooks = false;
        const message = error?.error?.message || error?.error?.detail || 'Webhook test failed';
        this.snack.open(message, 'Dismiss', { duration: 4500 });
        this.cdr.markForCheck();
      },
    });
  }

  // ── Google OAuth ──────────────────────────────────────────────────

  saveGoogleAuthSettings(): void {
    this.savingGoogleAuth = true;
    const payload: { client_id: string; client_secret?: string } = {
      client_id: this.googleAuthClientId.trim(),
    };
    if (this.googleAuthClientSecret.trim()) {
      payload.client_secret = this.googleAuthClientSecret.trim();
    }
    this.siloSvc.updateGoogleOAuthSettings(payload).pipe(takeUntil(this.destroy$)).subscribe({
      next: (googleOAuth) => {
        this.googleOAuth = { ...this.googleOAuth, ...(googleOAuth ?? {}) };
        this.googleAuthClientId = googleOAuth?.client_id ?? this.googleAuthClientId ?? '';
        this.googleAuthClientSecret = '';
        this.ga4Telemetry = {
          ...this.ga4Telemetry,
          google_oauth_client_id: googleOAuth?.client_id,
          google_oauth_client_secret_configured: googleOAuth?.client_secret_configured,
          oauth_connected: googleOAuth?.oauth_connected,
        };
        this.ga4Gsc = {
          ...this.ga4Gsc,
          oauth_connected: googleOAuth?.oauth_connected,
        };
        this.savingGoogleAuth = false;
        this.snack.open('Google app settings saved.', undefined, { duration: 3000 });
        this.cdr.markForCheck();
      },
      error: (error) => {
        this.savingGoogleAuth = false;
        this.snack.open(error?.error?.detail || 'Failed to save Google app settings.', 'Dismiss', { duration: 4000 });
        this.cdr.markForCheck();
      },
    });
  }

  authorizeGoogle(): void {
    this.siloSvc.getGoogleAuthUrl().pipe(takeUntil(this.destroy$)).subscribe({
      next: (res) => {
        if (res.authorization_url) {
          window.location.href = res.authorization_url;
        }
      },
      error: (err) => {
        this.snack.open('Failed to start Google authorization: ' + (err?.error?.detail || 'Unknown error'), 'Dismiss', { duration: 5000 });
      },
    });
  }

  unlinkGoogleAccount(): void {
    if (!confirm('Are you sure you want to unlink your Google account? Access to GA4 and GSC via OAuth will be revoked.')) return;
    this.siloSvc.unlinkGoogleAccount().pipe(takeUntil(this.destroy$)).subscribe({
      next: () => {
        this.snack.open('Google account unlinked.', undefined, { duration: 3000 });
        this.reload();
      },
      error: (err) => {
        this.snack.open('Failed to unlink Google account: ' + (err?.error?.detail || 'Unknown error'), 'Dismiss', { duration: 5000 });
      },
    });
  }

  // ── GA4 telemetry ─────────────────────────────────────────────────

  saveGA4TelemetrySettings(): void {
    this.savingGA4Telemetry = true;
    const payload: GA4TelemetryUpdate = {
      behavior_enabled: this.ga4Telemetry.behavior_enabled,
      property_id: this.ga4Telemetry.property_id.trim(),
      measurement_id: this.ga4Telemetry.measurement_id.trim(),
      read_project_id: this.ga4Telemetry.read_project_id.trim(),
      read_client_email: this.ga4Telemetry.read_client_email.trim(),
      sync_enabled: this.ga4Telemetry.sync_enabled,
      sync_lookback_days: Number(this.ga4Telemetry.sync_lookback_days),
      event_schema: this.ga4Telemetry.event_schema.trim(),
      geo_granularity: this.ga4Telemetry.geo_granularity,
      retention_days: Number(this.ga4Telemetry.retention_days),
      impression_visible_ratio: Number(this.ga4Telemetry.impression_visible_ratio),
      impression_min_ms: Number(this.ga4Telemetry.impression_min_ms),
      engaged_min_seconds: Number(this.ga4Telemetry.engaged_min_seconds),
    };
    if (this.ga4TelemetrySecret.trim()) {
      payload.api_secret = this.ga4TelemetrySecret.trim();
    }
    if (this.ga4TelemetryReadPrivateKey.trim()) {
      payload.read_private_key = this.ga4TelemetryReadPrivateKey.trim();
    }
    this.siloSvc.updateGA4TelemetrySettings(payload).pipe(takeUntil(this.destroy$)).subscribe({
      next: (ga4Telemetry) => {
        this.ga4Telemetry = { ...this.ga4Telemetry, ...(ga4Telemetry ?? {}) };
        this.ga4TelemetrySecret = '';
        this.ga4TelemetryReadPrivateKey = '';
        this.savingGA4Telemetry = false;
        this.snack.open('GA4 telemetry settings saved', undefined, { duration: 2500 });
        this.cdr.markForCheck();
      },
      error: (error) => {
        this.savingGA4Telemetry = false;
        this.snack.open(error?.error?.detail || 'Failed to save GA4 telemetry settings', 'Dismiss', { duration: 4000 });
        this.cdr.markForCheck();
      },
    });
  }

  testGA4TelemetryConnection(): void {
    this.testingGA4Telemetry = true;
    this.siloSvc.testGA4TelemetryConnection({
      measurement_id: this.ga4Telemetry.measurement_id.trim() || undefined,
      api_secret: this.ga4TelemetrySecret.trim() || undefined,
    }).pipe(takeUntil(this.destroy$)).subscribe({
      next: (result: AnalyticsConnectionResult) => {
        this.testingGA4Telemetry = false;
        this.ga4Telemetry = {
          ...this.ga4Telemetry,
          connection_status: result.status,
          connection_message: result.message,
        };
        this.snack.open(result.message, undefined, { duration: 3000 });
        this.cdr.markForCheck();
      },
      error: (error) => {
        this.testingGA4Telemetry = false;
        const message = error?.error?.message || error?.error?.detail || 'GA4 connection test failed';
        this.ga4Telemetry = {
          ...this.ga4Telemetry,
          connection_status: 'error',
          connection_message: message,
        };
        this.snack.open(message, 'Dismiss', { duration: 4000 });
        this.cdr.markForCheck();
      },
    });
  }

  testGA4TelemetryReadConnection(): void {
    this.testingGA4TelemetryRead = true;
    this.siloSvc.testGA4TelemetryReadConnection({
      property_id: this.ga4Telemetry.property_id.trim() || undefined,
      read_project_id: this.ga4Telemetry.read_project_id.trim() || undefined,
      read_client_email: this.ga4Telemetry.read_client_email.trim() || undefined,
      read_private_key: this.ga4TelemetryReadPrivateKey.trim() || undefined,
    }).pipe(takeUntil(this.destroy$)).subscribe({
      next: (result: AnalyticsConnectionResult) => {
        this.testingGA4TelemetryRead = false;
        this.ga4Telemetry = {
          ...this.ga4Telemetry,
          read_connection_status: result.status,
          read_connection_message: result.message,
        };
        this.snack.open(result.message, undefined, { duration: 3000 });
        this.cdr.markForCheck();
      },
      error: (error) => {
        this.testingGA4TelemetryRead = false;
        const message = error?.error?.message || error?.error?.detail || 'GA4 read-access test failed';
        this.ga4Telemetry = {
          ...this.ga4Telemetry,
          read_connection_status: 'error',
          read_connection_message: message,
        };
        this.snack.open(message, 'Dismiss', { duration: 4000 });
        this.cdr.markForCheck();
      },
    });
  }

  // ── Matomo ────────────────────────────────────────────────────────

  saveMatomoTelemetrySettings(): void {
    this.savingMatomoTelemetry = true;
    const payload: MatomoTelemetryUpdate = {
      enabled: this.matomoTelemetry.enabled,
      url: this.matomoTelemetry.url.trim(),
      site_id_xenforo: this.matomoTelemetry.site_id_xenforo.trim(),
      site_id_wordpress: this.matomoTelemetry.site_id_wordpress.trim(),
      sync_enabled: this.matomoTelemetry.sync_enabled,
      sync_lookback_days: Number(this.matomoTelemetry.sync_lookback_days),
    };
    if (this.matomoTelemetryToken.trim()) {
      payload.token_auth = this.matomoTelemetryToken.trim();
    }
    this.siloSvc.updateMatomoTelemetrySettings(payload).pipe(takeUntil(this.destroy$)).subscribe({
      next: (matomoTelemetry) => {
        this.matomoTelemetry = { ...this.matomoTelemetry, ...(matomoTelemetry ?? {}) };
        this.matomoTelemetryToken = '';
        this.savingMatomoTelemetry = false;
        this.snack.open('Matomo telemetry settings saved', undefined, { duration: 2500 });
        this.cdr.markForCheck();
      },
      error: (error) => {
        this.savingMatomoTelemetry = false;
        this.snack.open(error?.error?.detail || 'Failed to save Matomo telemetry settings', 'Dismiss', { duration: 4000 });
        this.cdr.markForCheck();
      },
    });
  }

  testMatomoTelemetryConnection(): void {
    this.testingMatomoTelemetry = true;
    this.siloSvc.testMatomoTelemetryConnection({
      url: this.matomoTelemetry.url.trim() || undefined,
      site_id_xenforo: this.matomoTelemetry.site_id_xenforo.trim() || undefined,
      token_auth: this.matomoTelemetryToken.trim() || undefined,
    }).pipe(takeUntil(this.destroy$)).subscribe({
      next: (result: AnalyticsConnectionResult) => {
        this.testingMatomoTelemetry = false;
        this.matomoTelemetry = {
          ...this.matomoTelemetry,
          connection_status: result.status,
          connection_message: result.message,
        };
        this.snack.open(result.message, undefined, { duration: 3000 });
        this.cdr.markForCheck();
      },
      error: (error) => {
        this.testingMatomoTelemetry = false;
        const message = error?.error?.message || error?.error?.detail || 'Matomo connection test failed';
        this.matomoTelemetry = {
          ...this.matomoTelemetry,
          connection_status: 'error',
          connection_message: message,
        };
        this.snack.open(message, 'Dismiss', { duration: 4000 });
        this.cdr.markForCheck();
      },
    });
  }

  // ── Google Search Console ─────────────────────────────────────────

  updateGSCSettings(): void {
    this.savingGA4GSC = true;
    const payload: GSCSettingsUpdate = {
      ranking_weight: this.ga4Gsc.ranking_weight,
      property_url: this.ga4Gsc.property_url,
      client_email: this.ga4Gsc.client_email,
      sync_enabled: this.ga4Gsc.sync_enabled,
      sync_lookback_days: this.ga4Gsc.sync_lookback_days,
    };
    if (this.gscPrivateKey) {
      payload.private_key = this.gscPrivateKey;
    }
    this.siloSvc.updateGSCSettings(payload).pipe(takeUntil(this.destroy$)).subscribe({
      next: (ga4Gsc: GSCSettings) => {
        this.ga4Gsc = { ...this.ga4Gsc, ...(ga4Gsc ?? {}) };
        this.gscManualBackfillDays = Math.max(
          Number(this.ga4Gsc.sync_lookback_days || 1),
          Number(this.ga4Gsc.manual_backfill_suggested_days || 180),
        );
        this.gscPrivateKey = '';
        this.savingGA4GSC = false;
        this.snack.open('Search Console settings saved.', undefined, { duration: 3000 });
        this.cdr.markForCheck();
      },
      error: (error: { error?: { detail?: string } } | unknown) => {
        this.savingGA4GSC = false;
        const detail = (error as { error?: { detail?: string } })?.error?.detail;
        this.snack.open(detail || 'Failed to save settings.', 'Dismiss', { duration: 4000 });
        this.cdr.markForCheck();
      },
    });
  }

  testGSCConnection(): void {
    this.testingGSCConnection = true;
    this.siloSvc.testGSCConnection({
      property_url: this.ga4Gsc.property_url.trim() || undefined,
      client_email: this.ga4Gsc.client_email.trim() || undefined,
      private_key: this.gscPrivateKey.trim() || undefined,
    }).pipe(takeUntil(this.destroy$)).subscribe({
      next: (result: AnalyticsConnectionResult) => {
        this.testingGSCConnection = false;
        this.ga4Gsc = {
          ...this.ga4Gsc,
          connection_status: result.status,
          connection_message: result.message,
        };
        this.snack.open(result.message, undefined, { duration: 3500 });
        this.cdr.markForCheck();
      },
      error: (error) => {
        this.testingGSCConnection = false;
        const message = error?.error?.message || error?.error?.detail || 'Search Console connection failed';
        this.ga4Gsc = {
          ...this.ga4Gsc,
          connection_status: 'error',
          connection_message: message,
        };
        this.snack.open(message, 'Dismiss', { duration: 4500 });
        this.cdr.markForCheck();
      },
    });
  }

  runGSCSync(): void {
    const lookbackDays = Math.max(1, Number(this.gscManualBackfillDays || this.ga4Gsc.sync_lookback_days));
    if (!confirm(`Run a GSC performance sync now? This will re-read the last ${lookbackDays} days and replace matching rows with the new country-filtered data.`)) return;
    this.runningGSCSync = true;
    this.siloSvc.runGSCSync({ lookback_days: lookbackDays }).pipe(takeUntil(this.destroy$)).subscribe({
      next: (res) => {
        this.runningGSCSync = false;
        this.snack.open(res?.message || 'GSC performance sync queued.', undefined, { duration: 3500 });
        this.cdr.markForCheck();
      },
      error: (err) => {
        this.runningGSCSync = false;
        this.snack.open(err?.error?.detail || 'Failed to queue GSC sync', 'Dismiss', { duration: 4000 });
        this.cdr.markForCheck();
      },
    });
  }
}
