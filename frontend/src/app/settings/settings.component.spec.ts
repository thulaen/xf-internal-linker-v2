import { TestBed } from '@angular/core/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { of } from 'rxjs';

import { SettingsComponent } from './settings.component';
import { SiloSettingsService } from './silo-settings.service';

describe('SettingsComponent', () => {
  it('renders the recommended preset guidance and the newer ranking cards', async () => {
    await TestBed.configureTestingModule({
      imports: [SettingsComponent, NoopAnimationsModule],
      providers: [
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
            getGA4GSCSettings: () => of({
              ranking_weight: 0.05,
            }),
            getWordPressSettings: () => of({
              base_url: '',
              username: '',
              app_password_configured: false,
              sync_enabled: false,
              sync_hour: 3,
              sync_minute: 0,
            }),
            getClickDistanceSettings: () => of({
              ranking_weight: 0.07,
              k_cd: 4,
              b_cd: 0.75,
              b_ud: 0.25,
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
            listSiloGroups: () => of([]),
            listScopes: () => of([]),
          },
        },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(SettingsComponent);
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent;
    expect(text).toContain('Hover any info icon to see a plain-English explanation.');
    expect(text).toContain('Load Recommended');
    expect(text).toContain('GA4 + Search Console');
    expect(text).toContain('WordPress site URL');
    expect(text).toContain('Rare-Term Propagation');
    expect(text).toContain('borrowed words stay separate');
    expect(text).toContain('A silo group is just a bucket of related pages.');
  });
});
