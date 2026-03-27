import { CommonModule } from '@angular/common';
import { Component, OnInit, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import {
  FieldAwareRelevanceSettings,
  ClickDistanceSettings,
  LearnedAnchorSettings,
  PhraseMatchingSettings,
  RareTermPropagationSettings,
  ScopeItem,
  SiloGroup,
  LinkFreshnessSettings,
  SiloMode,
  SiloSettings,
  SiloSettingsService,
  WeightedAuthoritySettings,
  WordPressSettings,
  WordPressSettingsUpdate,
} from './silo-settings.service';

@Component({
  selector: 'app-settings',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatSelectModule,
    MatSnackBarModule,
  ],
  templateUrl: './settings.component.html',
  styleUrls: ['./settings.component.scss'],
})
export class SettingsComponent implements OnInit {
  private siloSvc = inject(SiloSettingsService);
  private snack = inject(MatSnackBar);

  loading = true;
  savingSettings = false;
  savingWeightedAuthority = false;
  savingLinkFreshness = false;
  savingPhraseMatching = false;
  savingLearnedAnchor = false;
  savingRareTermPropagation = false;
  savingFieldAwareRelevance = false;
  savingClickDistance = false;
  savingWordPress = false;
  recalculatingWeightedAuthority = false;
  recalculatingLinkFreshness = false;
  recalculatingClickDistance = false;
  runningWordPressSync = false;
  creatingGroup = false;

  settings: SiloSettings = {
    mode: 'disabled',
    same_silo_boost: 0,
    cross_silo_penalty: 0,
  };
  weightedAuthority: WeightedAuthoritySettings = {
    ranking_weight: 0.2,
    position_bias: 0.5,
    empty_anchor_factor: 0.6,
    bare_url_factor: 0.35,
    weak_context_factor: 0.75,
    isolated_context_factor: 0.45,
  };
  linkFreshness: LinkFreshnessSettings = {
    ranking_weight: 0,
    recent_window_days: 30,
    newest_peer_percent: 0.25,
    min_peer_count: 3,
    w_recent: 0.35,
    w_growth: 0.35,
    w_cohort: 0.2,
    w_loss: 0.1,
  };
  phraseMatching: PhraseMatchingSettings = {
    ranking_weight: 0,
    enable_anchor_expansion: true,
    enable_partial_matching: true,
    context_window_tokens: 8,
  };
  learnedAnchor: LearnedAnchorSettings = {
    ranking_weight: 0,
    minimum_anchor_sources: 2,
    minimum_family_support_share: 0.15,
    enable_noise_filter: true,
  };
  rareTermPropagation: RareTermPropagationSettings = {
    enabled: true,
    ranking_weight: 0,
    max_document_frequency: 3,
    minimum_supporting_related_pages: 2,
  };
  fieldAwareRelevance: FieldAwareRelevanceSettings = {
    ranking_weight: 0,
    title_field_weight: 0.4,
    body_field_weight: 0.3,
    scope_field_weight: 0.15,
    learned_anchor_field_weight: 0.15,
  };
  clickDistance: ClickDistanceSettings = {
    ranking_weight: 0,
    k_cd: 1.5,
    b_cd: 0.1,
    b_ud: 0.1,
  };
  wordpress: WordPressSettings = {
    base_url: '',
    username: '',
    app_password_configured: false,
    sync_enabled: false,
    sync_hour: 3,
    sync_minute: 0,
  };
  wordpressPassword = '';

  siloGroups: SiloGroup[] = [];
  scopes: ScopeItem[] = [];

  newGroup: Pick<SiloGroup, 'name' | 'slug' | 'description' | 'display_order'> = {
    name: '',
    slug: '',
    description: '',
    display_order: 0,
  };

  modeOptions: Array<{ value: SiloMode; label: string; description: string }> = [
    {
      value: 'disabled',
      label: 'Disabled',
      description: 'Preserve current ranking behaviour with no silo effect.',
    },
    {
      value: 'prefer_same_silo',
      label: 'Prefer same silo',
      description: 'Boost same-silo candidates and penalize cross-silo candidates.',
    },
    {
      value: 'strict_same_silo',
      label: 'Strict same silo',
      description: 'Block cross-silo matches only when both sides have silo assignments.',
    },
  ];

  get selectedModeDescription(): string {
    return this.modeOptions.find((option) => option.value === this.settings.mode)?.description ?? '';
  }

  ngOnInit(): void {
    this.reload();
  }

  reload(): void {
    this.loading = true;
    this.siloSvc.getSettings().subscribe({
      next: (settings) => {
        this.settings = settings;
        this.siloSvc.getWeightedAuthoritySettings().subscribe({
          next: (weightedAuthority) => {
            this.weightedAuthority = weightedAuthority;
            this.siloSvc.getLinkFreshnessSettings().subscribe({
              next: (linkFreshness) => {
                this.linkFreshness = linkFreshness;
                this.siloSvc.getPhraseMatchingSettings().subscribe({
                  next: (phraseMatching) => {
                    this.phraseMatching = phraseMatching;
                    this.siloSvc.getLearnedAnchorSettings().subscribe({
                      next: (learnedAnchor) => {
                        this.learnedAnchor = learnedAnchor;
                        this.siloSvc.getRareTermPropagationSettings().subscribe({
                          next: (rareTermPropagation) => {
                            this.rareTermPropagation = rareTermPropagation;
                            this.siloSvc.getFieldAwareRelevanceSettings().subscribe({
                              next: (fieldAwareRelevance) => {
                                this.fieldAwareRelevance = fieldAwareRelevance;
                                this.siloSvc.getWordPressSettings().subscribe({
                                  next: (wordpress) => {
                                    this.wordpress = wordpress;
                                    this.siloSvc.getClickDistanceSettings().subscribe({
                                      next: (clickDistance) => {
                                        this.clickDistance = clickDistance;
                                        this.loadGroupsAndScopes();
                                      },
                                      error: () => {
                                        this.loading = false;
                                        this.snack.open('Failed to load click distance settings', 'Dismiss', { duration: 4000 });
                                      },
                                    });
                                  },
                                  error: () => {
                                    this.loading = false;
                                    this.snack.open('Failed to load WordPress settings', 'Dismiss', { duration: 4000 });
                                  },
                                });
                              },
                              error: () => {
                                this.loading = false;
                                this.snack.open('Failed to load field-aware relevance settings', 'Dismiss', { duration: 4000 });
                              },
                            });
                          },
                          error: () => {
                            this.loading = false;
                            this.snack.open('Failed to load rare-term propagation settings', 'Dismiss', { duration: 4000 });
                          },
                        });
                      },
                      error: () => {
                        this.loading = false;
                        this.snack.open('Failed to load learned anchor settings', 'Dismiss', { duration: 4000 });
                      },
                    });
                  },
                  error: () => {
                    this.loading = false;
                    this.snack.open('Failed to load phrase matching settings', 'Dismiss', { duration: 4000 });
                  },
                });
              },
              error: () => {
                this.loading = false;
                this.snack.open('Failed to load Link Freshness settings', 'Dismiss', { duration: 4000 });
              },
            });
          },
          error: () => {
            this.loading = false;
            this.snack.open('Failed to load March 2026 PageRank settings', 'Dismiss', { duration: 4000 });
          },
        });
      },
      error: () => {
        this.loading = false;
        this.snack.open('Failed to load silo settings', 'Dismiss', { duration: 4000 });
      },
    });
  }

  savePhraseMatchingSettings(): void {
    this.savingPhraseMatching = true;
    this.siloSvc.updatePhraseMatchingSettings(this.phraseMatching).subscribe({
      next: (phraseMatching) => {
        this.phraseMatching = phraseMatching;
        this.savingPhraseMatching = false;
        this.snack.open('Phrase matching settings saved', undefined, { duration: 2500 });
      },
      error: (error) => {
        this.savingPhraseMatching = false;
        this.snack.open(error?.error?.detail || 'Failed to save phrase matching settings', 'Dismiss', { duration: 4000 });
      },
    });
  }

  saveLearnedAnchorSettings(): void {
    this.savingLearnedAnchor = true;
    this.siloSvc.updateLearnedAnchorSettings(this.learnedAnchor).subscribe({
      next: (learnedAnchor) => {
        this.learnedAnchor = learnedAnchor;
        this.savingLearnedAnchor = false;
        this.snack.open('Learned anchor settings saved', undefined, { duration: 2500 });
      },
      error: (error) => {
        this.savingLearnedAnchor = false;
        this.snack.open(error?.error?.detail || 'Failed to save learned anchor settings', 'Dismiss', { duration: 4000 });
      },
    });
  }

  saveRareTermPropagationSettings(): void {
    this.savingRareTermPropagation = true;
    this.siloSvc.updateRareTermPropagationSettings(this.rareTermPropagation).subscribe({
      next: (rareTermPropagation) => {
        this.rareTermPropagation = rareTermPropagation;
        this.savingRareTermPropagation = false;
        this.snack.open('Rare-term propagation settings saved', undefined, { duration: 2500 });
      },
      error: (error) => {
        this.savingRareTermPropagation = false;
        this.snack.open(error?.error?.detail || 'Failed to save rare-term propagation settings', 'Dismiss', { duration: 4000 });
      },
    });
  }

  saveFieldAwareRelevanceSettings(): void {
    this.savingFieldAwareRelevance = true;
    this.siloSvc.updateFieldAwareRelevanceSettings(this.fieldAwareRelevance).subscribe({
      next: (fieldAwareRelevance) => {
        this.fieldAwareRelevance = fieldAwareRelevance;
        this.savingFieldAwareRelevance = false;
        this.snack.open('Field-aware relevance settings saved', undefined, { duration: 2500 });
      },
      error: (error) => {
        this.savingFieldAwareRelevance = false;
        this.snack.open(error?.error?.detail || 'Failed to save field-aware relevance settings', 'Dismiss', { duration: 4000 });
      },
    });
  }

  saveLinkFreshnessSettings(): void {
    this.savingLinkFreshness = true;
    this.siloSvc.updateLinkFreshnessSettings(this.linkFreshness).subscribe({
      next: (linkFreshness) => {
        this.linkFreshness = linkFreshness;
        this.savingLinkFreshness = false;
        this.snack.open('Link Freshness settings saved', undefined, { duration: 2500 });
      },
      error: (error) => {
        this.savingLinkFreshness = false;
        this.snack.open(error?.error?.detail || 'Failed to save Link Freshness settings', 'Dismiss', { duration: 4000 });
      },
    });
  }

  saveClickDistanceSettings(): void {
    this.savingClickDistance = true;
    this.siloSvc.updateClickDistanceSettings(this.clickDistance).subscribe({
      next: (clickDistance) => {
        this.clickDistance = clickDistance;
        this.savingClickDistance = false;
        this.snack.open('Click distance settings saved', undefined, { duration: 2500 });
      },
      error: (error) => {
        this.savingClickDistance = false;
        this.snack.open(error?.error?.detail || 'Failed to save click distance settings', 'Dismiss', { duration: 4000 });
      },
    });
  }

  recalculateClickDistance(): void {
    this.recalculatingClickDistance = true;
    this.siloSvc.recalculateClickDistance().subscribe({
      next: (response) => {
        this.recalculatingClickDistance = false;
        this.snack.open(`Click distance recalculation started (${response.job_id.slice(0, 8)})`, 'Dismiss', { duration: 5000 });
      },
      error: (error) => {
        this.recalculatingClickDistance = false;
        this.snack.open(error?.error?.detail || 'Failed to start click distance recalculation', 'Dismiss', { duration: 4000 });
      },
    });
  }

  private loadGroupsAndScopes(): void {
    this.siloSvc.listSiloGroups().subscribe({
      next: (groups) => {
        this.siloGroups = groups;
        this.siloSvc.listScopes().subscribe({
          next: (scopes) => {
            this.scopes = scopes;
            this.loading = false;
          },
          error: () => {
            this.loading = false;
            this.snack.open('Failed to load scopes', 'Dismiss', { duration: 4000 });
          },
        });
      },
      error: () => {
        this.loading = false;
        this.snack.open('Failed to load silo groups', 'Dismiss', { duration: 4000 });
      },
    });
  }

  saveSettings(): void {
    this.savingSettings = true;
    this.siloSvc.updateSettings(this.settings).subscribe({
      next: (settings) => {
        this.settings = settings;
        this.savingSettings = false;
        this.snack.open('Silo settings saved', undefined, { duration: 2500 });
      },
      error: (error) => {
        this.savingSettings = false;
        this.snack.open(error?.error?.detail || 'Failed to save silo settings', 'Dismiss', { duration: 4000 });
      },
    });
  }

  saveWeightedAuthoritySettings(): void {
    this.savingWeightedAuthority = true;
    this.siloSvc.updateWeightedAuthoritySettings(this.weightedAuthority).subscribe({
      next: (weightedAuthority) => {
        this.weightedAuthority = weightedAuthority;
        this.savingWeightedAuthority = false;
        this.snack.open('March 2026 PageRank settings saved', undefined, { duration: 2500 });
      },
      error: (error) => {
        this.savingWeightedAuthority = false;
        this.snack.open(error?.error?.detail || 'Failed to save March 2026 PageRank settings', 'Dismiss', { duration: 4000 });
      },
    });
  }

  recalculateWeightedAuthority(): void {
    this.recalculatingWeightedAuthority = true;
    this.siloSvc.recalculateWeightedAuthority().subscribe({
      next: (response) => {
        this.recalculatingWeightedAuthority = false;
        this.snack.open(`March 2026 PageRank recalculation started (${response.job_id.slice(0, 8)})`, 'Dismiss', { duration: 5000 });
      },
      error: (error) => {
        this.recalculatingWeightedAuthority = false;
        this.snack.open(error?.error?.detail || 'Failed to start March 2026 PageRank recalculation', 'Dismiss', { duration: 4000 });
      },
    });
  }

  recalculateLinkFreshness(): void {
    this.recalculatingLinkFreshness = true;
    this.siloSvc.recalculateLinkFreshness().subscribe({
      next: (response) => {
        this.recalculatingLinkFreshness = false;
        this.snack.open(`Link Freshness recalculation started (${response.job_id.slice(0, 8)})`, 'Dismiss', { duration: 5000 });
      },
      error: (error) => {
        this.recalculatingLinkFreshness = false;
        this.snack.open(error?.error?.detail || 'Failed to start Link Freshness recalculation', 'Dismiss', { duration: 4000 });
      },
    });
  }

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

    this.siloSvc.updateWordPressSettings(payload).subscribe({
      next: (wordpress) => {
        this.wordpress = wordpress;
        this.wordpressPassword = '';
        this.savingWordPress = false;
        this.snack.open('WordPress settings saved', undefined, { duration: 2500 });
      },
      error: (error) => {
        this.savingWordPress = false;
        this.snack.open(error?.error?.detail || 'Failed to save WordPress settings', 'Dismiss', { duration: 4000 });
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
    }).subscribe({
      next: (wordpress) => {
        this.wordpress = wordpress;
        this.wordpressPassword = '';
        this.savingWordPress = false;
        this.snack.open('WordPress Application Password cleared', undefined, { duration: 2500 });
      },
      error: (error) => {
        this.savingWordPress = false;
        this.snack.open(error?.error?.detail || 'Failed to clear WordPress password', 'Dismiss', { duration: 4000 });
      },
    });
  }

  runWordPressSync(): void {
    this.runningWordPressSync = true;
    this.siloSvc.runWordPressSync().subscribe({
      next: (response) => {
        this.runningWordPressSync = false;
        this.snack.open(`WordPress sync started (${response.job_id.slice(0, 8)})`, 'Dismiss', { duration: 5000 });
      },
      error: (error) => {
        this.runningWordPressSync = false;
        this.snack.open(error?.error?.detail || 'Failed to start WordPress sync', 'Dismiss', { duration: 4000 });
      },
    });
  }

  createGroup(): void {
    if (!this.newGroup.name.trim()) {
      this.snack.open('Group name is required', 'Dismiss', { duration: 3000 });
      return;
    }
    this.creatingGroup = true;
    this.siloSvc.createSiloGroup(this.newGroup).subscribe({
      next: (group) => {
        this.siloGroups = [...this.siloGroups, group].sort((a, b) => a.display_order - b.display_order || a.name.localeCompare(b.name));
        this.newGroup = { name: '', slug: '', description: '', display_order: 0 };
        this.creatingGroup = false;
        this.snack.open('Silo group created', undefined, { duration: 2500 });
      },
      error: () => {
        this.creatingGroup = false;
        this.snack.open('Failed to create silo group', 'Dismiss', { duration: 4000 });
      },
    });
  }

  saveGroup(group: SiloGroup): void {
    this.siloSvc.updateSiloGroup(group.id, {
      name: group.name,
      slug: group.slug,
      description: group.description,
      display_order: group.display_order,
    }).subscribe({
      next: (updated) => {
        Object.assign(group, updated);
        this.snack.open('Silo group updated', undefined, { duration: 2500 });
      },
      error: () => {
        this.snack.open('Failed to update silo group', 'Dismiss', { duration: 4000 });
      },
    });
  }

  deleteGroup(group: SiloGroup): void {
    this.siloSvc.deleteSiloGroup(group.id).subscribe({
      next: () => {
        this.siloGroups = this.siloGroups.filter((item) => item.id !== group.id);
        this.scopes = this.scopes.map((scope) =>
          scope.silo_group === group.id
            ? { ...scope, silo_group: null, silo_group_name: '' }
            : scope
        );
        this.snack.open('Silo group deleted', undefined, { duration: 2500 });
      },
      error: () => {
        this.snack.open('Failed to delete silo group', 'Dismiss', { duration: 4000 });
      },
    });
  }

  updateScope(scope: ScopeItem, siloGroupId: number | null): void {
    this.siloSvc.updateScopeSilo(scope.id, siloGroupId).subscribe({
      next: (updated) => {
        Object.assign(scope, updated);
        this.snack.open('Scope assignment saved', undefined, { duration: 2000 });
      },
      error: () => {
        this.snack.open('Failed to save scope assignment', 'Dismiss', { duration: 4000 });
      },
    });
  }
}
