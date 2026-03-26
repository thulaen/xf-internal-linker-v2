import { TestBed } from '@angular/core/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { of } from 'rxjs';

import { SettingsComponent } from './settings.component';
import { SiloSettingsService } from './silo-settings.service';

describe('SettingsComponent', () => {
  it('renders the Rare-Term Propagation settings card', async () => {
    await TestBed.configureTestingModule({
      imports: [SettingsComponent, NoopAnimationsModule],
      providers: [
        {
          provide: SiloSettingsService,
          useValue: {
            getSettings: () => of({ mode: 'disabled', same_silo_boost: 0, cross_silo_penalty: 0 }),
            getWeightedAuthoritySettings: () => of({
              ranking_weight: 0.2,
              position_bias: 0.5,
              empty_anchor_factor: 0.6,
              bare_url_factor: 0.35,
              weak_context_factor: 0.75,
              isolated_context_factor: 0.45,
            }),
            getLinkFreshnessSettings: () => of({
              ranking_weight: 0,
              recent_window_days: 30,
              newest_peer_percent: 0.25,
              min_peer_count: 3,
              w_recent: 0.35,
              w_growth: 0.35,
              w_cohort: 0.2,
              w_loss: 0.1,
            }),
            getPhraseMatchingSettings: () => of({
              ranking_weight: 0,
              enable_anchor_expansion: true,
              enable_partial_matching: true,
              context_window_tokens: 8,
            }),
            getLearnedAnchorSettings: () => of({
              ranking_weight: 0,
              minimum_anchor_sources: 2,
              minimum_family_support_share: 0.15,
              enable_noise_filter: true,
            }),
            getRareTermPropagationSettings: () => of({
              enabled: true,
              ranking_weight: 0,
              max_document_frequency: 3,
              minimum_supporting_related_pages: 2,
            }),
            getFieldAwareRelevanceSettings: () => of({
              ranking_weight: 0,
              title_field_weight: 0.4,
              body_field_weight: 0.3,
              scope_field_weight: 0.15,
              learned_anchor_field_weight: 0.15,
            }),
            getWordPressSettings: () => of({
              base_url: '',
              username: '',
              app_password_configured: false,
              sync_enabled: false,
              sync_hour: 3,
              sync_minute: 0,
            }),
            listSiloGroups: () => of([]),
            listScopes: () => of([]),
          },
        },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(SettingsComponent);
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent;
    expect(text).toContain('Rare-Term Propagation');
    expect(text).toContain('Save rare-term propagation settings');
    expect(text).toContain('borrowed words stay separate from the destination\'s own text');
    expect(text).toContain('Field-Aware Relevance');
    expect(text).toContain('Save field-aware relevance settings');
  });
});
