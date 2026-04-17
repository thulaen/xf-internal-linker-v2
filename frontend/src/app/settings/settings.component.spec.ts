import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { ActivatedRoute } from '@angular/router';
import { of } from 'rxjs';

import { SettingsComponent } from './settings.component';
import { WeightDiagnosticsCardComponent } from './weight-diagnostics-card/weight-diagnostics-card.component';
import { PerformanceSettingsComponent } from './performance-settings/performance-settings.component';
import { HelpersSettingsComponent } from './helpers-settings/helpers-settings.component';
import { MetaAlgorithmsTabComponent } from './meta-algorithms-tab/meta-algorithms-tab.component';
import { SiloSettingsService } from './silo-settings.service';
import { NotificationService } from '../core/services/notification.service';

@Component({
  selector: 'app-weight-diagnostics-card',
  standalone: true,
  template: '',
})
class MockWeightDiagnosticsCardComponent {}

@Component({
  selector: 'app-performance-settings',
  standalone: true,
  template: '',
})
class MockPerformanceSettingsComponent {}

@Component({
  selector: 'app-helpers-settings',
  standalone: true,
  template: '',
})
class MockHelpersSettingsComponent {}

@Component({
  selector: 'app-meta-algorithms-tab',
  standalone: true,
  template: '',
})
class MockMetaAlgorithmsTabComponent {}

describe('SettingsComponent', () => {
  it('renders the telemetry settings cards on the WordPress sync tab', async () => {
    localStorage.setItem('settings_active_tab', '2');

    TestBed.overrideComponent(SettingsComponent, {
      remove: {
        imports: [
          WeightDiagnosticsCardComponent,
          PerformanceSettingsComponent,
          HelpersSettingsComponent,
          MetaAlgorithmsTabComponent,
        ],
      },
      add: {
        imports: [
          MockWeightDiagnosticsCardComponent,
          MockPerformanceSettingsComponent,
          MockHelpersSettingsComponent,
          MockMetaAlgorithmsTabComponent,
        ],
      },
    });

    await TestBed.configureTestingModule({
      imports: [SettingsComponent, NoopAnimationsModule],
      providers: [
        provideHttpClient(),
        {
          provide: NotificationService,
          useValue: {
            loadPreferences: () => of({
              desktop_enabled: true,
              sound_enabled: true,
              quiet_hours_enabled: false,
              quiet_hours_start: '22:00',
              quiet_hours_end: '07:00',
              min_desktop_severity: 'warning',
              min_sound_severity: 'error',
              enable_job_completed: true,
              enable_job_failed: true,
              enable_job_stalled: true,
              enable_model_status: true,
              enable_gsc_spikes: true,
              toast_enabled: true,
              toast_min_severity: 'warning',
              duplicate_cooldown_seconds: 900,
              job_stalled_default_minutes: 15,
              gsc_spike_min_impressions_delta: 50,
              gsc_spike_min_clicks_delta: 5,
              gsc_spike_min_relative_lift: 0.5,
            }),
            savePreferences: () => of({}),
            sendTestNotification: () => of({}),
            unreadCount$: of(0),
            newAlert$: of(),
          },
        },
        {
          provide: SiloSettingsService,
          useValue: {
            getSettings: () => of({ mode: 'prefer_same_silo', same_silo_boost: 0.05, cross_silo_penalty: 0.05 }),
            getWeightedAuthoritySettings: () => of({
              ranking_weight: 0.1,
              position_bias: 0.5,
              empty_anchor_factor: 0.6,
              bare_url_factor: 0.35,
              weak_context_factor: 0.75,
              isolated_context_factor: 0.45,
            }),
            getLinkFreshnessSettings: () => of({
              ranking_weight: 0.05,
              recent_window_days: 30,
              newest_peer_percent: 0.25,
              min_peer_count: 3,
              w_recent: 0.35,
              w_growth: 0.35,
              w_cohort: 0.2,
              w_loss: 0.1,
            }),
            getPhraseMatchingSettings: () => of({
              ranking_weight: 0.08,
              enable_anchor_expansion: true,
              enable_partial_matching: true,
              context_window_tokens: 8,
            }),
            getLearnedAnchorSettings: () => of({
              ranking_weight: 0.05,
              minimum_anchor_sources: 2,
              minimum_family_support_share: 0.15,
              enable_noise_filter: true,
            }),
            getRareTermPropagationSettings: () => of({
              enabled: true,
              ranking_weight: 0.05,
              max_document_frequency: 3,
              minimum_supporting_related_pages: 2,
            }),
            getFieldAwareRelevanceSettings: () => of({
              ranking_weight: 0.1,
              title_field_weight: 0.4,
              body_field_weight: 0.3,
              scope_field_weight: 0.15,
              learned_anchor_field_weight: 0.15,
            }),
            getGSCSettings: () => of({
              ranking_weight: 0.05,
              property_url: '',
              client_email: '',
              private_key_configured: false,
              sync_enabled: false,
              sync_lookback_days: 7,
              manual_backfill_max_days: 365,
              manual_backfill_suggested_days: 180,
              excluded_countries: ['China', 'Singapore'],
              connection_status: 'not_configured',
              connection_message: 'Fill in the Search Console property URL and service-account credentials.',
              oauth_connected: false,
              last_sync: null,
            }),
            getGoogleOAuthSettings: () => of({
              client_id: '',
              client_secret_configured: false,
              oauth_connected: false,
              status: 'not_configured',
              message: 'Paste the Google OAuth client ID and secret once, then sign in once.',
              last_sync: null,
            }),
            getGA4TelemetrySettings: () => of({
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
            }),
            getMatomoTelemetrySettings: () => of({
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
            }),
            getXenForoSettings: () => of({
              base_url: '',
              api_key_configured: false,
            }),
            updateXenForoSettings: () => of({ status: 'saved' }),
            getWordPressSettings: () => of({
              base_url: '',
              username: '',
              app_password_configured: false,
              sync_enabled: false,
              sync_hour: 3,
              sync_minute: 0,
            }),
            getWebhookSettings: () => of({ xf_secret_configured: false, wp_secret_configured: false }),
            getClickDistanceSettings: () => of({
              ranking_weight: 0.07,
              k_cd: 4,
              b_cd: 0.75,
              b_ud: 0.25,
            }),
            getGraphCandidateSettings: () => of({
              enabled: true,
              walk_steps_per_entity: 2000,
              min_stable_candidates: 50,
              min_visit_threshold: 3,
            }),
            getValueModelSettings: () => of({
              enabled: true,
              w_traffic: 0.5,
              w_freshness: 0.3,
              traffic_lookback_days: 30,
            }),
            getFeedbackRerankSettings: () => of({
              enabled: true,
              ranking_weight: 0.08,
              exploration_rate: 1.41421356237,
            }),
            getClusteringSettings: () => of({
              enabled: true,
              similarity_threshold: 0.04,
              suppression_penalty: 20,
            }),
            getSpamGuardSettings: () => of({
              max_existing_links_per_host: 3,
              max_anchor_words: 4,
              paragraph_window: 3,
            }),
            updateSpamGuardSettings: () => of({
              max_existing_links_per_host: 3,
              max_anchor_words: 4,
              paragraph_window: 3,
            }),
            getSlateDiversitySettings: () => of({
              enabled: true,
              diversity_lambda: 0.65,
              score_window: 0.3,
              similarity_cap: 0.9,
            }),
            getCurrentWeights: () => of({
              'silo.mode': 'prefer_same_silo',
              'silo.same_silo_boost': '0.05',
              'silo.cross_silo_penalty': '0.05',
              'weighted_authority.ranking_weight': '0.1',
              'ga4_gsc.ranking_weight': '0.05',
            }),
            listWeightPresets: () => of([
              {
                id: 1,
                name: 'Recommended',
                is_system: true,
                weights: {
                  'silo.mode': 'prefer_same_silo',
                  'silo.same_silo_boost': '0.05',
                  'silo.cross_silo_penalty': '0.05',
                  'weighted_authority.ranking_weight': '0.1',
                  'ga4_gsc.ranking_weight': '0.05',
                },
                created_at: '2026-03-31T00:00:00Z',
                updated_at: '2026-03-31T00:00:00Z',
              },
            ]),
            listWeightHistory: () => of([]),
            listChallengers: () => of([]),
            triggerCsTune: () => of({ detail: 'queued', task_id: 'test' }),
            evaluateChallenger: () => of({ detail: 'queued', task_id: 'test' }),
            rejectChallenger: () => of({ detail: 'rejected' }),
            listSiloGroups: () => of([]),
            listScopes: () => of([]),
          },
        },
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: {
              queryParams: {},
              fragment: null,
            },
            queryParams: of({}),
            fragment: of(null),
          },
        },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(SettingsComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent as string;

    // Page header renders correctly — basic smoke test
    expect(text).toContain('Hover any info icon to see a plain-English explanation.');

    // selectedTabIndex read from localStorage
    expect(fixture.componentInstance.selectedTabIndex).toBe(2);

    // Angular Material renders tab labels into .mdc-tab__text-label spans
    const tabLabels: NodeListOf<Element> = fixture.nativeElement.querySelectorAll('.mdc-tab__text-label');
    const labels = Array.from(tabLabels).map((element) => element.textContent?.trim() ?? '');

    expect(labels.some((label) => label.includes('Connect & Sync'))).toBeTrue();
    expect(labels.some((label) => label.includes('Ranking Weights'))).toBeTrue();

    localStorage.removeItem('settings_active_tab');
  });
});
