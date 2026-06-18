import {
  ChangeDetectionStrategy,
  ChangeDetectorRef,
  Component,
  OnInit,
  OnDestroy,
  HostListener,
  inject,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MonoTypeOperatorFunction, forkJoin, finalize, Subject, takeUntil } from 'rxjs';
import { RealtimeService } from '../core/services/realtime.service';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatChipsModule } from '@angular/material/chips';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TabFragmentRouterDirective } from '../core/directives/tab-fragment-router.directive';
import { MatDividerModule } from '@angular/material/divider';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ActivatedRoute } from '@angular/router';
import { HasUnsavedChanges } from '../core/guards/unsaved-changes.guard';
import {
  AnchorDiversitySettings,
  FieldAwareRelevanceSettings,
  ClickDistanceSettings,
  KeywordStuffingSettings,
  LearnedAnchorSettings,
  LinkFarmSettings,
  PhraseMatchingSettings,
  RareTermPropagationSettings,
  ScopeItem,
  SiloGroup,
  LinkFreshnessSettings,
  SiloMode,
  SiloSettings,
  SiloSettingsService,
  Stage1RetrieverSettings,
  Phase6PickSettings,
  WeightedAuthoritySettings,
  XenForoSettings,
  WordPressSettings,
  GSCSettings,
  FeedbackRerankSettings,
  ClusteringSettings,
  SlateDiversitySettings,
  WeightPreset,
  WeightAdjustmentHistory,
  GA4TelemetrySettings,
  GoogleOAuthSettings,
  MatomoTelemetrySettings,
  GraphCandidateSettings,
  ValueModelSettings,
  SpamGuardSettings,
  WebhookSettings,
} from './silo-settings.service';
import { PerformanceSettingsComponent } from './performance-settings/performance-settings.component';
import { HelpersSettingsComponent } from './helpers-settings/helpers-settings.component';
import { EmbeddingProviderScoreboardComponent } from './embedding-provider-scoreboard/embedding-provider-scoreboard.component';
// Phase MS — Meta Algorithm Settings tab (new at the end of the tab group).
import { MetaAlgorithmsTabComponent } from './meta-algorithms-tab/meta-algorithms-tab.component';
import { ConnectSyncTabComponent } from './connect-sync-tab/connect-sync-tab.component';
import { LibraryHistoryTabComponent } from './library-history-tab/library-history-tab.component';
import { NotificationsTabComponent } from './notifications-tab/notifications-tab.component';
import { RankingWeightsTabComponent } from './ranking-weights-tab/ranking-weights-tab.component';
import { SiloArchitectureTabComponent } from './silo-architecture-tab/silo-architecture-tab.component';
import { SettingsOverviewComponent } from './settings-overview/settings-overview.component';
import { WeightDiagnosticsCardComponent } from './weight-diagnostics-card/weight-diagnostics-card.component';
// MatDialog / meta-algo tooltips / SpecViewerDialogComponent — moved to
// `<app-ranking-weights-tab>` along with the FR-099–FR-105 card UI.

import { SETTING_TOOLTIPS } from './setting-tooltips';
import { ALERT_THRESHOLDS, UI_TO_PRESET_KEY } from './settings-constants';

type FieldSeverity = 'none' | 'warn' | 'danger';

@Component({
  selector: 'app-settings',
  standalone: true,
  templateUrl: './settings.component.html',
  styleUrls: ['./settings.component.scss'],
  imports: [
    FormsModule,
    MatButtonModule,
    MatCardModule,
    MatCheckboxModule,
    MatChipsModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatSelectModule,
    MatSlideToggleModule,
    MatSnackBarModule,
    MatTabsModule,
    MatTooltipModule,
    MatDividerModule,
    MatProgressSpinnerModule,
    MetaAlgorithmsTabComponent,
    ConnectSyncTabComponent,
    LibraryHistoryTabComponent,
    NotificationsTabComponent,
    RankingWeightsTabComponent,
    SiloArchitectureTabComponent,
    TabFragmentRouterDirective,
    SettingsOverviewComponent,
    PerformanceSettingsComponent,
    HelpersSettingsComponent,
    EmbeddingProviderScoreboardComponent,
    WeightDiagnosticsCardComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SettingsComponent implements OnInit, OnDestroy, HasUnsavedChanges {
  private siloSvc = inject(SiloSettingsService);
  private snack = inject(MatSnackBar);
  private route = inject(ActivatedRoute);
  private realtime = inject(RealtimeService);
  private cdr = inject(ChangeDetectorRef);

  /**
   * Phase R1.4 — tracks the last realtime refresh so we don't spam the user
   * with reload toasts if the backend fires several setting saves in a
   * tight burst (e.g. a preset that writes 20 keys). Debounced via the
   * stream below.
   */
  private destroy$ = new Subject<void>();

  /**
   * Epoch-ms cutoff. While `Date.now() < _suppressRuntimeUntil`, the
   * `settings.runtime` realtime handler ignores incoming events because
   * THIS browser tab is the one that triggered them (via a local save).
   * Without this, every save fires the "Settings changed in another tab"
   * toast against the user's own action — the realtime broadcast echoes
   * back into the same tab that initiated it.
   */
  private _suppressRuntimeUntil = 0;

  /** Mark that a local save just started so the next 8 seconds of
   *  `settings.runtime` events are treated as our own echo. */
  private _markLocalSave(): void {
    this._suppressRuntimeUntil = Date.now() + 8000;
  }

  loading = true;
  isDirty = false;

  graphCandidate: GraphCandidateSettings = {
    enabled: true,
    walk_steps_per_entity: 2000,
    min_stable_candidates: 50,
    min_visit_threshold: 4,
    top_k_candidates: 100,
    top_n_entities_per_article: 15,
  };

  valueModel: ValueModelSettings = {
    enabled: true,
    w_relevance: 0.35,
    w_traffic: 0.25,
    w_freshness: 0.1,
    w_authority: 0.1,
    w_penalty: 0.5,
    traffic_lookback_days: 90,
    traffic_fallback_value: 0.5,
    engagement_signal_enabled: true,
    w_engagement: 0.08,
    engagement_lookback_days: 30,
    engagement_words_per_minute: 200,
    engagement_cap_ratio: 1.5,
    engagement_fallback_value: 0.5,
    hot_decay_enabled: true,
    hot_gravity: 0.05,
    hot_clicks_weight: 1.0,
    hot_impressions_weight: 0.05,
    hot_lookback_days: 90,
    co_occurrence_signal_enabled: true,
    w_cooccurrence: 0.12,
    co_occurrence_fallback_value: 0.5,
    co_occurrence_min_co_sessions: 5,
  };

  // savingXenForo / savingWordPress / savingWebhooks / runningWordPressSync
  // / savingGA4Telemetry / savingMatomoTelemetry / testingGA4Telemetry /
  // testingGA4TelemetryRead / testingMatomoTelemetry / testingGSCConnection
  // / testingXenForo / testingWordPress / testingWebhooks / runningGSCSync
  // / savingGoogleAuth — moved with the per-card buttons to
  // <app-connect-sync-tab>. crawlerExcludedPaths / newCrawlerExclusion
  // moved with the Crawler card to the same child.

  // Tab persistence
  selectedTabIndex = Number(localStorage.getItem('settings_active_tab') || '0');

  // Maps the catalog tab keys (`ranking-weights`, `silo-architecture`, etc.)
  // to their numeric tab indexes inside this `<mat-tab-group>`. Consumed by
  // `appTabFragment` so `/settings#ranking-weights` and
  // `/settings?tab=ranking-weights` both activate the correct tab.
  readonly tabFragmentMap: Record<string, number> = {
    'ranking-weights': 0,
    'silo-architecture': 1,
    'connect-sync': 2,
    'history-presets': 3,
    'library-history': 3,
    notifications: 4,
    'diagnostics-weights': 5,
    diagnostics: 5,
    'performance-tunables': 6,
    performance: 6,
    helpers: 7,
    'meta-algorithms': 8,
    'embedding-provider-scoreboard': 9,
  };

  onTabChange(index: number): void {
    this.selectedTabIndex = index;
    localStorage.setItem('settings_active_tab', String(index));
    this.cdr.markForCheck();
  }

  private markForCheckOnComplete<T>(): MonoTypeOperatorFunction<T> {
    return finalize(() => this.cdr.markForCheck());
  }

  settings: SiloSettings = {
    mode: 'prefer_same_silo',
    same_silo_boost: 0.1, // Increased from 0.05 to match research
    cross_silo_penalty: 0.1, // Increased from 0.05 to match research
  };
  weightedAuthority: WeightedAuthoritySettings = {
    ranking_weight: 0.1,
    position_bias: 0.5,
    empty_anchor_factor: 0.6,
    bare_url_factor: 0.35,
    weak_context_factor: 0.75,
    isolated_context_factor: 0.45,
  };
  linkFreshness: LinkFreshnessSettings = {
    ranking_weight: 0.05,
    recent_window_days: 30,
    newest_peer_percent: 0.25,
    min_peer_count: 3,
    w_recent: 0.35,
    w_growth: 0.35,
    w_cohort: 0.2,
    w_loss: 0.1,
  };
  phraseMatching: PhraseMatchingSettings = {
    ranking_weight: 0.08,
    enable_anchor_expansion: true,
    enable_partial_matching: true,
    context_window_tokens: 8,
  };
  learnedAnchor: LearnedAnchorSettings = {
    ranking_weight: 0.05,
    minimum_anchor_sources: 2,
    minimum_family_support_share: 0.15,
    enable_noise_filter: true,
  };
  rareTermPropagation: RareTermPropagationSettings = {
    enabled: true,
    ranking_weight: 0.05,
    max_document_frequency: 3,
    minimum_supporting_related_pages: 2,
  };
  fieldAwareRelevance: FieldAwareRelevanceSettings = {
    ranking_weight: 0.1,
    title_field_weight: 0.3,
    heading_field_weight: 0.15,
    intro_field_weight: 0.2,
    body_field_weight: 0.15,
    scope_field_weight: 0.1,
    learned_anchor_field_weight: 0.1,
  };

  private readonly DEFAULT_HEALTH = {
    status: 'stale',
    label: 'Pending check',
    name: '',
    description: '',
    issue: '',
    fix: '',
    last_success: null,
    is_healthy: false,
  };
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
    health: this.DEFAULT_HEALTH,
  };
  googleOAuth: GoogleOAuthSettings = {
    client_id: '',
    client_secret_configured: false,
    oauth_connected: false,
    status: 'not_configured',
    message: 'Paste the Google OAuth client ID and secret once, then sign in once.',
    last_sync: null,
  };
  // showGA4FallbackFields / showGSCFallbackFields — moved with the
  // GA4 + GSC cards to <app-connect-sync-tab>.
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
    ga4_health: this.DEFAULT_HEALTH,
    gsc_health: this.DEFAULT_HEALTH,
  };
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
  clickDistance: ClickDistanceSettings = {
    ranking_weight: 0.07,
    k_cd: 4,
    b_cd: 0.75,
    b_ud: 0.25,
  };
  spamGuards: SpamGuardSettings = {
    max_existing_links_per_host: 3,
    max_anchor_words: 4,
    paragraph_window: 3,
  };
  anchorDiversity: AnchorDiversitySettings = {
    enabled: true,
    ranking_weight: 0.03,
    min_history_count: 3,
    max_exact_match_share: 0.4,
    max_exact_match_count: 3,
    hard_cap_enabled: false,
  };
  keywordStuffing: KeywordStuffingSettings = {
    enabled: true,
    ranking_weight: 0.04,
    alpha: 6.0,
    tau: 0.3,
    dirichlet_mu: 2000,
    top_k_stuff_terms: 5,
  };
  linkFarm: LinkFarmSettings = {
    enabled: true,
    ranking_weight: 0.03,
    min_scc_size: 3,
    density_threshold: 0.6,
    lambda: 0.8,
  };
  feedbackRerank: FeedbackRerankSettings = {
    enabled: true,
    ranking_weight: 0.08,
    exploration_rate: 1.41421356237,
  };
  clustering: ClusteringSettings = {
    enabled: true,
    similarity_threshold: 0.04,
    suppression_penalty: 20,
  };
  slateDiversity: SlateDiversitySettings = {
    enabled: true,
    diversity_lambda: 0.65,
    score_window: 0.3,
    similarity_cap: 0.9,
  };
  // Stage-1 candidate-retriever flags.
  // Lexical (FR-240) and XenForo BM25 default ON via migrations 0062+0066;
  // query expansion stays opt-in. RRF fusion (pick #31) automatically
  // merges any active retrievers' ranked lists per destination.
  // See backend/apps/pipeline/services/candidate_retrievers.py +
  // docs/specs/xf-bm25-retrieval.md.
  stage1Retrievers: Stage1RetrieverSettings = {
    lexical_retriever_enabled: false,
    query_expansion_retriever_enabled: false,
    xenforo_bm25_retriever_enabled: false,
    tantivy_bm25_retriever_enabled: false,
  };

  // Phase 6 optional-pick master switches. Defaults seeded ON via
  // migration 0043. Operator flips off any pick whose cost outweighs
  // the benefit on their corpus.
  phase6Picks: Phase6PickSettings = {
    vader_sentiment: { enabled: true },
    pysbd_segmenter: { enabled: true },
    yake_keywords: { enabled: true },
    trafilatura_extractor: { enabled: true },
    fasttext_langid: { enabled: true },
    lda: { enabled: true },
    kenlm: { enabled: true },
    node2vec: { enabled: true },
    bpr: { enabled: true },
    factorization_machines: { enabled: true },
  };

  // FR-099 through FR-105 — graph-topology ranking signals.
  // See docs/specs/fr099-*.md through docs/specs/fr105-*.md.
  // Defaults match backend/apps/suggestions/recommended_weights.py byte-for-byte.
  darb = {
    enabled: true,
    ranking_weight: 0.04,
    out_degree_saturation: 5,
    min_host_value: 0.5,
  };
  kmig = {
    enabled: true,
    ranking_weight: 0.05,
    attenuation: 0.5,
    max_hops: 2,
  };
  tapb = {
    enabled: true,
    ranking_weight: 0.03,
    apply_to_articulation_node_only: true,
  };
  kcib = {
    enabled: true,
    ranking_weight: 0.03,
    min_kcore_spread: 1,
  };
  berp = {
    enabled: true,
    ranking_weight: 0.04,
    min_component_size: 5,
  };
  hgte = {
    enabled: true,
    ranking_weight: 0.04,
    min_host_out_degree: 3,
  };
  rsqva = {
    enabled: true,
    ranking_weight: 0.05,
    min_queries_per_page: 5,
    min_query_clicks: 1,
    max_vocab_size: 10000,
  };
  xenforo: XenForoSettings = {
    base_url: '',
    api_key_configured: false,
    health: this.DEFAULT_HEALTH,
  };

  wordpress: WordPressSettings = {
    base_url: '',
    username: '',
    app_password_configured: false,
    sync_enabled: false,
    sync_hour: 3,
    sync_minute: 0,
    health: this.DEFAULT_HEALTH,
  };

  webhookSettings: WebhookSettings = { xf_secret_configured: false, wp_secret_configured: false };

  // Weight presets — kept here because cross-tab tooltips
  // (`recommendedValueLabel`, `getFeatureSummary`, `currentFeatureCount`,
  // `currentOffFeatures`) and the fresh-install auto-apply guard
  // (`checkAndAutoApplyRecommended`) all read these fields. The Library
  // & History tab UI moved to `<app-library-history-tab>` and owns its
  // own duplicate copies for its cards. The booleans / action methods
  // (applyingPreset, saveCurrentAsPreset, ...) and the challengers list
  // moved with the tab.
  weightPresets: WeightPreset[] = [];
  weightHistory: WeightAdjustmentHistory[] = [];
  currentWeights: Record<string, string> = {};

  siloGroups: SiloGroup[] = [];
  scopes: ScopeItem[] = [];

  // `modeOptions` retained even though the silo tab moved to
  // `<app-silo-architecture-tab>` — `recommendedValueLabel('silo.mode')`
  // (called by tooltip rendering across all tabs) still needs the
  // value→label map.
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

  get recommendedPreset(): WeightPreset | null {
    return (
      this.weightPresets.find((preset) => preset.is_system && preset.name.toLowerCase().includes('recommended')) ?? null
    );
  }

  get noSourceConnected(): boolean {
    // Optional chaining — `health` is present in GET responses but absent
    // in some PUT responses; defensive across in-flight saves.
    return !this.xenforo.health?.is_healthy && !this.wordpress.health?.is_healthy;
  }

  hasUnsavedChanges(): boolean {
    return this.isDirty;
  }

  markDirty(): void {
    this.isDirty = true;
  }

  /**
   * Listens to extracted-tab `(dirtyChanged)` outputs (Notifications,
   * Silo Architecture, Library & History) so the parent's isDirty signal
   * continues to drive the unsaved-changes guard after those tabs moved
   * out of this file. Child emits `true` on edit, `false` after a
   * successful save. Preserves the historical "set-only" semantic: the
   * parent's isDirty only flips on; it is cleared by the `reload()` /
   * preset-apply paths, never by a sibling tab's quiet save.
   */
  onChildDirty(dirty: boolean): void {
    if (dirty) {
      this.isDirty = true;
    }
  }

  /**
   * Listens to `<app-library-history-tab>` `(presetApplied)` output. Fires
   * after a successful preset apply or weight rollback inside the child.
   * The parent must re-run the giant 25+ endpoint forkJoin via `reload()`
   * so every weight card on every other tab re-hydrates from the
   * server-of-truth post-apply. Payload is the preset name (or `null` for
   * rollback) — informational only; the reload path is identical for
   * both. Mirrors the historical inline `applyPreset → this.reload()`
   * flow that the child replaced.
   */
  onPresetApplied(): void {
    this.reload();
  }

  @HostListener('window:beforeunload', ['$event'])
  onBeforeUnload(event: BeforeUnloadEvent): void {
    if (this.isDirty) {
      event.preventDefault();
    }
  }

  get matchedPreset(): WeightPreset | null {
    return this.weightPresets.find((preset) => this.presetMatchesCurrent(preset)) ?? null;
  }

  get activePresetLabel(): string {
    return this.matchedPreset?.name ?? 'Custom live mix';
  }

  get currentFeatureCount(): number {
    return this.getFeatureSummary().filter((feature) => feature.currentEnabled).length;
  }

  get currentOffFeatures(): string[] {
    const summary = this.getFeatureSummary();
    if (!summary) return [];
    return summary
      .filter((feature) => feature.recommendedEnabled && !feature.currentEnabled)
      .map((feature) => feature.label);
  }

  get assignedScopeCount(): number {
    return this.scopes.filter((scope) => scope.silo_group !== null).length;
  }

  recommendedValueLabel(key: string): string | null {
    const value = this.presetValueFor(key, this.recommendedPreset);
    if (value == null) return null;
    const normalized = value.trim().toLowerCase();
    if (normalized === 'true') return 'On';
    if (normalized === 'false') return 'Off';
    if (key === 'silo.mode') {
      return this.modeOptions.find((option) => option.value === normalized)?.label ?? value;
    }
    return value;
  }

  fieldHelper(key: string, value: number | boolean | string | null | undefined): string {
    const notes: string[] = [];
    const recommended = this.recommendedValueLabel(key);
    if (recommended) {
      notes.push(`Good starting point: ${recommended}.`);
    }
    if (typeof value === 'number') {
      const severity = this.fieldSeverity(value, key);
      if (severity === 'warn') {
        notes.push('Warning: this is stronger than the usual starting range.');
      }
      if (severity === 'danger') {
        notes.push('Risky: this is far outside the usual starting range.');
      }
    }
    return notes.join(' ');
  }

  tip(key: string): string {
    const t = SETTING_TOOLTIPS[key];
    if (!t) return `No tooltip defined for "${key}" - add an entry to SETTING_TOOLTIPS in setting-tooltips.ts`;

    const lines: string[] = [];

    // Add dynamic severity alerts
    const currentValue = this.valueFor(key);
    if (typeof currentValue === 'number') {
      const severity = this.fieldSeverity(currentValue, key);
      if (severity === 'warn') {
        lines.push('AMBER ALERT: This value is unusually strong. Monitor closely for over-optimized links.');
      }
      if (severity === 'danger') {
        lines.push('RED ALERT: This value is in the risky range! It may cause unnatural link patterns.');
      }
    }

    lines.push(`DEFINITION: ${t.definition}`);
    lines.push(`IMPACT: ${t.impact}`);
    lines.push(`RECOMMENDED: ${this.recommendedValueLabel(key) ?? t.default}`);
    lines.push(`EXAMPLE: ${t.example}`);
    lines.push(`VALID RANGE: ${t.range}`);

    return lines.join('\n\n');
  }

  valueFor(key: string): unknown {
    // Reflective dotted-key reader for the settings cards. Returns
    // `unknown` so call-sites narrow the value before using it; the
    // template-binding sites coerce to string with `| json` or stringify
    // by interpolation. Replaces a `: any` flagged by the 2026-05-09
    // audit (AutoIssue #21).
    const parts = key.split('.');
    if (parts.length !== 2) return null;
    const [section, field] = parts;
    const sectionValue = (this as unknown as Record<string, Record<string, unknown> | undefined>)[section];
    return sectionValue?.[field];
  }

  // metaAlgoTip / openMetaAlgoSpec / metaAlgoHasSpec — extracted to
  // `<app-ranking-weights-tab>` along with the FR-099–FR-105 card UI.

  fieldSeverity(value: number | undefined | null, key: string): FieldSeverity {
    if (value == null) return 'none';
    const threshold = ALERT_THRESHOLDS[key];
    if (!threshold) return 'none';
    if (threshold.dangerAbove !== undefined && value > threshold.dangerAbove) return 'danger';
    if (threshold.dangerBelow !== undefined && value < threshold.dangerBelow) return 'danger';
    if (threshold.warnAbove !== undefined && value > threshold.warnAbove) return 'warn';
    if (threshold.warnBelow !== undefined && value < threshold.warnBelow) return 'warn';
    return 'none';
  }

  isExtreme(value: number | undefined | null, key: string): boolean {
    return this.fieldSeverity(value, key) !== 'none';
  }

  isDanger(value: number | undefined | null, key: string): boolean {
    return this.fieldSeverity(value, key) === 'danger';
  }

  /**
   * Used as [compareWith] on every boolean mat-select.
   * Angular compares by reference by default, so if the API returns the
   * string "true" the option [value]="true" (boolean) won't match and the
   * dropdown shows blank. Normalising both sides to string fixes that.
   */
  compareBooleans(a: unknown, b: unknown): boolean {
    return String(a) === String(b);
  }

  // telemetryStatusLabel / telemetryStatusClass — extracted to
  // `<app-connect-sync-tab>` and `<app-ranking-weights-tab>`. The
  // parent template no longer calls them directly because every status
  // pill it used to render now lives inside one of those two child
  // components, each of which owns its own copy of the helper.

  // lastSyncLabel / getHealthIcon / hasGoogleAppCredentials /
  // shouldShowReconnectGoogle / shouldShowGA4FallbackFields /
  // shouldShowGSCFallbackFields / saveGoogleAuthSettings — moved with
  // the Connect & Sync tab to <app-connect-sync-tab>.

  private presetMatchesCurrent(preset: WeightPreset): boolean {
    const presetEntries = Object.entries(preset.weights ?? {});
    if (!presetEntries.length) return false;
    return presetEntries.every(
      ([key, value]) =>
        this.normalizeComparableValue(this.currentWeights[key]) === this.normalizeComparableValue(value),
    );
  }

  private presetValueFor(key: string, preset: WeightPreset | null): string | null {
    if (!preset) return null;
    const presetKey = UI_TO_PRESET_KEY[key];
    if (!presetKey) return null;
    const value = preset.weights?.[presetKey];
    return value == null ? null : String(value);
  }

  private getFeatureSummary(): Array<{ label: string; currentEnabled: boolean; recommendedEnabled: boolean }> {
    const recommended = this.recommendedPreset;
    return [
      {
        label: 'March 2026 PageRank',
        currentEnabled: this.weightedAuthority.ranking_weight > 0,
        recommendedEnabled: this.isFeatureEnabledInPreset(recommended, 'weighted_authority.ranking_weight'),
      },
      {
        label: 'Link Freshness',
        currentEnabled: this.linkFreshness.ranking_weight > 0,
        recommendedEnabled: this.isFeatureEnabledInPreset(recommended, 'link_freshness.ranking_weight'),
      },
      {
        label: 'Phrase Matching',
        currentEnabled: this.phraseMatching.ranking_weight > 0,
        recommendedEnabled: this.isFeatureEnabledInPreset(recommended, 'phrase_matching.ranking_weight'),
      },
      {
        label: 'Learned Anchors',
        currentEnabled: this.learnedAnchor.ranking_weight > 0,
        recommendedEnabled: this.isFeatureEnabledInPreset(recommended, 'learned_anchor.ranking_weight'),
      },
      {
        label: 'Rare-Term Propagation',
        currentEnabled: this.rareTermPropagation.enabled && this.rareTermPropagation.ranking_weight > 0,
        recommendedEnabled:
          this.isFeatureEnabledInPreset(recommended, 'rare_term_propagation.enabled') &&
          this.isFeatureEnabledInPreset(recommended, 'rare_term_propagation.ranking_weight'),
      },
      {
        label: 'Field-Aware Relevance',
        currentEnabled: this.fieldAwareRelevance.ranking_weight > 0,
        recommendedEnabled: this.isFeatureEnabledInPreset(recommended, 'field_aware_relevance.ranking_weight'),
      },
      {
        label: 'GA4 + Search Console',
        currentEnabled: this.ga4Gsc.ranking_weight > 0,
        recommendedEnabled: this.isFeatureEnabledInPreset(recommended, 'ga4_gsc.ranking_weight'),
      },
      {
        label: 'Click Distance',
        currentEnabled: this.clickDistance.ranking_weight > 0,
        recommendedEnabled: this.isFeatureEnabledInPreset(recommended, 'click_distance.ranking_weight'),
      },
      {
        label: 'Anchor Diversity',
        currentEnabled: this.anchorDiversity.enabled && this.anchorDiversity.ranking_weight > 0,
        recommendedEnabled:
          this.isFeatureEnabledInPreset(recommended, 'anchor_diversity.enabled') &&
          this.isFeatureEnabledInPreset(recommended, 'anchor_diversity.ranking_weight'),
      },
      {
        label: 'Keyword Stuffing',
        currentEnabled: this.keywordStuffing.enabled && this.keywordStuffing.ranking_weight > 0,
        recommendedEnabled:
          this.isFeatureEnabledInPreset(recommended, 'keyword_stuffing.enabled') &&
          this.isFeatureEnabledInPreset(recommended, 'keyword_stuffing.ranking_weight'),
      },
      {
        label: 'Link-Farm Detection',
        currentEnabled: this.linkFarm.enabled && this.linkFarm.ranking_weight > 0,
        recommendedEnabled:
          this.isFeatureEnabledInPreset(recommended, 'link_farm.enabled') &&
          this.isFeatureEnabledInPreset(recommended, 'link_farm.ranking_weight'),
      },
      {
        label: 'Silo Ranking',
        currentEnabled: this.settings.mode !== 'disabled',
        recommendedEnabled: this.isFeatureEnabledInPreset(recommended, 'silo.mode'),
      },
      {
        label: 'Feedback Reranking',
        currentEnabled: this.feedbackRerank.enabled && this.feedbackRerank.ranking_weight > 0,
        recommendedEnabled:
          this.isFeatureEnabledInPreset(recommended, 'explore_exploit.enabled') &&
          this.isFeatureEnabledInPreset(recommended, 'explore_exploit.ranking_weight'),
      },
      {
        label: 'Near-Duplicate Clustering',
        currentEnabled: this.clustering.enabled,
        recommendedEnabled: this.isFeatureEnabledInPreset(recommended, 'clustering.enabled'),
      },
      {
        label: 'Slate Diversity',
        currentEnabled: this.slateDiversity.enabled,
        recommendedEnabled: this.isFeatureEnabledInPreset(recommended, 'slate_diversity.enabled'),
      },
      {
        label: 'Graph Candidate Generation',
        currentEnabled: this.graphCandidate.enabled,
        recommendedEnabled: this.isFeatureEnabledInPreset(recommended, 'graph_candidate.enabled'),
      },
      {
        label: 'Value Model Scoring',
        currentEnabled: this.valueModel.enabled,
        recommendedEnabled: this.isFeatureEnabledInPreset(recommended, 'value_model.enabled'),
      },
    ];
  }

  private isFeatureEnabledInPreset(preset: WeightPreset | null, presetKey: string): boolean {
    const value = preset?.weights?.[presetKey];
    if (value == null) return false;
    const normalized = String(value).trim().toLowerCase();
    if (normalized === 'true') return true;
    if (normalized === 'false') return false;
    if (normalized === 'disabled') return false;
    const numeric = Number(normalized);
    if (Number.isFinite(numeric)) return numeric > 0;
    return normalized.length > 0;
  }

  private normalizeComparableValue(value: unknown): string {
    if (value == null) return '';
    const raw = String(value).trim();
    const normalized = raw.toLowerCase();
    if (normalized === 'true' || normalized === 'false') return normalized;
    const numeric = Number(raw);
    if (Number.isFinite(numeric)) return String(numeric);
    return normalized;
  }

  ngOnInit(): void {
    // 1. Check for OAuth status parameters
    const query = this.route.snapshot.queryParams;
    if (query['oauth_success']) {
      this.snack.open('Google account authorized successfully.', 'Dismiss', { duration: 5000 });
      window.history.replaceState({}, '', window.location.pathname);
    } else if (query['oauth_error']) {
      this.snack.open(`Google authorization failed: ${query['oauth_error']}`, 'Dismiss', { duration: 6000 });
      window.history.replaceState({}, '', window.location.pathname);
    }

    // 2. Listen for fragment changes to auto-switch tabs
    this.route.fragment.pipe(takeUntil(this.destroy$), this.markForCheckOnComplete()).subscribe((fragment) => {
      if (fragment) {
        this.syncTabWithFragment(fragment);
      }
    });

    this.reload();

    // ── settings.runtime realtime subscription removed ───────────────
    //
    // History: this used to subscribe to the staff-only `settings.runtime`
    // topic and toast on remote settings writes. Two problems made the
    // toast a net negative:
    //
    // 1. Suppression-context lifecycle: `_markLocalSave()` was a per-
    //    component instance field. When the user saved on (e.g.) the
    //    Dashboard's Performance Mode toggle and navigated to Settings,
    //    the suppression context was destroyed with the dashboard
    //    component, so the broadcast self-echo arrived on the freshly-
    //    mounted Settings component as if it were from a different tab.
    //    Toast fired on every navigation that followed a recent save.
    //
    // 2. Auto-reload race: the previous version called `this.reload()`
    //    on remote events, which raced the local save's `next:` handler
    //    and overwrote freshly-saved component state with stale GETs.
    //
    // The cross-tab use case is rare; manual refresh handles it. The
    // backend Celery filter at apps/core/signals.py keeps the broadcast
    // group quiet enough that future reintroductions of the toast (with
    // a session-shared suppression service) would be feasible — but
    // that's not needed for the user's reported workflow.
    //
    // `_markLocalSave()` and the suppression timer remain in case a
    // future feature re-attaches a notification, but they're inert now.
  }

  /**
   * Best-effort guard for the realtime reload path — if the component has a
   * dirty-form detector we use it; otherwise we assume clean. Avoids
   * overwriting in-flight user input during a collaborative edit.
   */
  private hasAnyDirtyForm(): boolean {
    const anyThis = this as unknown as { hasUnsavedChanges?: () => boolean };
    if (typeof anyThis.hasUnsavedChanges === 'function') {
      try {
        return !!anyThis.hasUnsavedChanges();
      } catch {
        return false;
      }
    }
    return false;
  }

  /**
   * Universal Smart Navigation: maps element IDs to their respective tab index.
   * This ensures that deep-linked content is rendered and visible before the
   * scroll-highlight system attempts to find it.
   */
  private syncTabWithFragment(id: string): void {
    const tabMap: Record<string, number> = {
      // Tab 0: Ranking Weights
      'ranking-weights': 0,
      'anchor-diversity': 0,
      'keyword-stuffing': 0,
      'link-farm': 0,

      // Tab 1: Silo Architecture
      'silo-architecture': 1,
      'silo-settings': 1,
      'silo-groups': 1,
      'scope-assignments': 1,

      // Tab 2: Connect & Sync
      'xenforo-settings': 2,
      'wordpress-settings': 2,
      'webhook-settings': 2,
      'google-settings': 2,
      'ga4-settings': 2,
      'matomo-settings': 2,
      'gsc-settings': 2,

      // Tab 3: History & Presets
      'weight-presets': 3,
      'adjustment-history': 3,
      'ranking-challengers': 3,

      // Tab 4: Notifications
      'notification-settings': 4,
      'alert-delivery': 4,
      'quiet-hours': 4,

      // Tab 5: Diagnostics
      'diagnostics-weights': 5,
      'algorithm-diagnostics': 5,

      // Tab 6: Performance
      'performance-tunables': 6,
      'model-runtime': 6,
      'runtime-recommendations': 6,

      // Tab 7: Helpers (plan item 22)
      helpers: 7,
    };

    const targetIndex = tabMap[id];
    if (targetIndex !== undefined && targetIndex !== this.selectedTabIndex) {
      this.selectedTabIndex = targetIndex;
      localStorage.setItem('settings_active_tab', String(targetIndex));
      this.cdr.markForCheck();
    }
  }

  reload(): void {
    this.loading = true;
    forkJoin({
      settings: this.siloSvc.getSettings(),
      weightedAuthority: this.siloSvc.getWeightedAuthoritySettings(),
      linkFreshness: this.siloSvc.getLinkFreshnessSettings(),
      phraseMatching: this.siloSvc.getPhraseMatchingSettings(),
      learnedAnchor: this.siloSvc.getLearnedAnchorSettings(),
      rareTermPropagation: this.siloSvc.getRareTermPropagationSettings(),
      fieldAwareRelevance: this.siloSvc.getFieldAwareRelevanceSettings(),
      ga4Gsc: this.siloSvc.getGSCSettings(),
      googleOAuth: this.siloSvc.getGoogleOAuthSettings(),
      ga4Telemetry: this.siloSvc.getGA4TelemetrySettings(),
      matomoTelemetry: this.siloSvc.getMatomoTelemetrySettings(),
      xenforo: this.siloSvc.getXenForoSettings(),
      wordpress: this.siloSvc.getWordPressSettings(),
      webhookSettings: this.siloSvc.getWebhookSettings(),
      clickDistance: this.siloSvc.getClickDistanceSettings(),
      spamGuards: this.siloSvc.getSpamGuardSettings(),
      anchorDiversity: this.siloSvc.getAnchorDiversitySettings(),
      keywordStuffing: this.siloSvc.getKeywordStuffingSettings(),
      linkFarm: this.siloSvc.getLinkFarmSettings(),
      feedbackRerank: this.siloSvc.getFeedbackRerankSettings(),
      clustering: this.siloSvc.getClusteringSettings(),
      slateDiversity: this.siloSvc.getSlateDiversitySettings(),
      graphCandidate: this.siloSvc.getGraphCandidateSettings(),
      valueModel: this.siloSvc.getValueModelSettings(),
      fr099Fr105: this.siloSvc.getFr099Fr105Settings(),
      stage1Retrievers: this.siloSvc.getStage1RetrieverSettings(),
      phase6Picks: this.siloSvc.getPhase6PickSettings(),
      currentWeights: this.siloSvc.getCurrentWeights(),
    })
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
        next: (data) => {
          // Merge API data with the class-level defaults so that boolean
          // fields the API omits (enable_anchor_expansion, enabled, etc.)
          // keep their safe default values instead of becoming undefined,
          // which would leave mat-select dropdowns blank.
          this.settings = { ...this.settings, ...data.settings };
          this.weightedAuthority = { ...this.weightedAuthority, ...data.weightedAuthority };
          this.linkFreshness = { ...this.linkFreshness, ...data.linkFreshness };
          this.phraseMatching = { ...this.phraseMatching, ...data.phraseMatching };
          this.learnedAnchor = { ...this.learnedAnchor, ...data.learnedAnchor };
          this.rareTermPropagation = { ...this.rareTermPropagation, ...data.rareTermPropagation };
          this.fieldAwareRelevance = { ...this.fieldAwareRelevance, ...data.fieldAwareRelevance };
          this.ga4Gsc = { ...this.ga4Gsc, ...data.ga4Gsc };
          this.googleOAuth = { ...this.googleOAuth, ...data.googleOAuth };
          this.ga4Telemetry = { ...this.ga4Telemetry, ...data.ga4Telemetry };
          this.matomoTelemetry = { ...this.matomoTelemetry, ...data.matomoTelemetry };
          this.xenforo = { ...this.xenforo, ...data.xenforo };
          this.wordpress = { ...this.wordpress, ...data.wordpress };
          this.webhookSettings = { ...this.webhookSettings, ...data.webhookSettings };
          this.clickDistance = { ...this.clickDistance, ...data.clickDistance };
          this.spamGuards = { ...this.spamGuards, ...data.spamGuards };
          this.anchorDiversity = { ...this.anchorDiversity, ...data.anchorDiversity };
          this.keywordStuffing = { ...this.keywordStuffing, ...data.keywordStuffing };
          this.linkFarm = { ...this.linkFarm, ...data.linkFarm };
          this.feedbackRerank = { ...this.feedbackRerank, ...data.feedbackRerank };
          this.clustering = { ...this.clustering, ...data.clustering };
          this.slateDiversity = { ...this.slateDiversity, ...data.slateDiversity };
          this.graphCandidate = { ...this.graphCandidate, ...data.graphCandidate };
          this.valueModel = { ...this.valueModel, ...data.valueModel };
          // FR-099 through FR-105 — 7 graph-topology signals loaded as a group.
          if (data.fr099Fr105) {
            this.darb = { ...this.darb, ...data.fr099Fr105.darb };
            this.kmig = { ...this.kmig, ...data.fr099Fr105.kmig };
            this.tapb = { ...this.tapb, ...data.fr099Fr105.tapb };
            this.kcib = { ...this.kcib, ...data.fr099Fr105.kcib };
            this.berp = { ...this.berp, ...data.fr099Fr105.berp };
            this.hgte = { ...this.hgte, ...data.fr099Fr105.hgte };
            this.rsqva = { ...this.rsqva, ...data.fr099Fr105.rsqva };
          }
          // Group C — Stage-1 retriever flags.
          if (data.stage1Retrievers) {
            this.stage1Retrievers = {
              ...this.stage1Retrievers,
              ...data.stage1Retrievers,
            };
          }
          // Phase 6 — 10 optional-pick toggles.
          if (data.phase6Picks) {
            this.phase6Picks = { ...this.phase6Picks, ...data.phase6Picks };
          }
          this.currentWeights = data.currentWeights;
          this.loadGroupsAndScopes();
          this.isDirty = false;
        },
        error: () => {
          this.loading = false;
          this.snack.open('Failed to load settings', 'Dismiss', { duration: 4000 });
        },
      });
    this.reloadPresetsAndHistory(true); // pass true to trigger auto-apply check
  }

  private refreshCurrentWeights(): void {
    this.siloSvc
      .getCurrentWeights()
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
        next: (weights) => {
          this.currentWeights = weights;
        },
        error: (err) => console.warn('refreshCurrentWeights failed', err),
      });
  }

  reloadPresetsAndHistory(shouldCheckAutoApply = false): void {
    // Two independent endpoints — but the auto-apply guard reads BOTH
    // (`weightHistory` and `weightPresets`). Previously these fired in
    // parallel via separate `.subscribe` calls and the auto-apply ran
    // as soon as `presets` resolved, racing the still-in-flight
    // `history` request. That made `weightHistory.length > 0` guard
    // unreliable — it almost always fired with `[]` even when history
    // rows existed in the DB. forkJoin waits for both before deciding.
    forkJoin({
      presets: this.siloSvc.listWeightPresets(),
      history: this.siloSvc.listWeightHistory(),
    })
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
        next: ({ presets, history }) => {
          this.weightPresets = presets;
          this.weightHistory = history;
          if (shouldCheckAutoApply) {
            this.checkAndAutoApplyRecommended();
          }
        },
        error: () => {},
      });
    // Challenger list moved to `<app-library-history-tab>`; the child
    // owns its own `loadChallengers()` and refresh cadence.
  }

  private checkAndAutoApplyRecommended(): void {
    // Only auto-apply on a TRULY fresh install:
    //   1. No history rows (no prior preset apply / autotuner promote /
    //      manual rollback).
    //   2. Current weights still match the Recommended baseline — i.e.
    //      no manual tweak via any settings card AND no autotuner
    //      output has landed yet. The autotuner's own writes are
    //      treated as "manual tweaks" per the user's protection rule
    //      (DEFAULT-ON-RULE.md): once it has written, current weights
    //      diverge from Recommended and we never auto-overwrite.
    if (this.weightHistory.length > 0) return;
    const recommended = this.recommendedPreset;
    if (!recommended) return;
    if (!this.presetMatchesCurrent(recommended)) return;
    // Defensive: even on a fresh install, if the user already started
    // editing a card before the auto-apply fires, don't trample their
    // input. The auto-apply window is only relevant when nothing on the
    // page has been touched yet — same trigger condition the toast was
    // designed for. AutoIssue #15.
    if (this.isDirty) return;
    // currentWeights == Recommended AND no history → genuinely fresh.
    // Apply once so a history row exists and we never fire again.
    this.siloSvc
      .applyWeightPreset(recommended.id)
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
        next: () => {
          this.snack.open('System Recommended settings applied by default.', undefined, { duration: 3000 });
          this.reload();
        },
        // Auto-apply is best-effort; if it fails, log and keep going.
        // The user can still pick a preset manually.
        error: (err) => console.warn('checkAndAutoApplyRecommended failed', err),
      });
  }

  // The Library & History tab UI moved to `<app-library-history-tab>`.
  // applyPreset / saveCurrentAsPreset / deletePreset / rollbackWeights /
  // triggerWeightTune / loadChallengers / promoteChallenger /
  // rejectChallenger / challengerImprovementPct / challengerDiffKeys /
  // deltaKeys / formatDeltaLine / historySourceLabel / startRenamePreset
  // / confirmRenamePreset all moved with it. The parent listens on the
  // child's `(presetApplied)` Output via `onPresetApplied()` above so the
  // giant 25+ endpoint reload still fires after a preset apply or
  // rollback, keeping every other weight card in sync with the server.

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  // Per-card save + recalculate handlers (savePhraseMatchingSettings,
  // saveLearnedAnchorSettings, saveRareTermPropagationSettings,
  // saveFieldAwareRelevanceSettings, saveGraphCandidateSettings,
  // saveValueModelSettings, triggerGraphRebuild, saveLinkFreshnessSettings,
  // saveSpamGuardSettings, saveAnchorDiversitySettings,
  // saveKeywordStuffingSettings, saveLinkFarmSettings, _saveFr099Fr105 +
  // its seven thin saveDarb/Kmig/Tapb/Kcib/Berp/Hgte/Rsqva wrappers,
  // saveStage1RetrieverSettings, savePhase6PickSettings,
  // saveClickDistanceSettings, saveFeedbackRerankSettings,
  // saveClusteringSettings, saveSlateDiversitySettings,
  // recalculateClickDistance, recalculateClustering) all extracted to
  // `<app-ranking-weights-tab>` along with their corresponding card UI.
  // The grouped `saveAllSettings()` forkJoin below still PUTs every
  // payload from the parent's local copies (kept in sync via `reload()`
  // after every save), so the global "Save all changes" button still
  // flushes every one of those 23 sections in a single network burst.

  private loadGroupsAndScopes(): void {
    this.siloSvc
      .listSiloGroups()
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
        next: (groups) => {
          this.siloGroups = groups;
          this.siloSvc
            .listScopes()
            .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
            .subscribe({
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

  // saveSettings() (silo) extracted to <app-silo-architecture-tab>.
  // saveWeightedAuthoritySettings / recalculateWeightedAuthority /
  // recalculateLinkFreshness extracted to <app-ranking-weights-tab>.
  // The parent's `saveAllSettings()` forkJoin below still PUTs the
  // weighted-authority + freshness payloads from the parent's local
  // copies (kept in sync via `reload()` after every save), so the
  // global "Save all changes" button still flushes both sections.

  // saveXenForoSettings / saveWordPressSettings / saveWebhookSettings /
  // xfWebhookUrl / wpWebhookUrl — extracted to <app-connect-sync-tab>.
  // The grouped `saveAllSettings()` below still PUTs WordPress + webhook
  // payloads as part of the global "Save All" forkJoin so the parent
  // owns the source-of-truth re-hydration after a Save All click.

  // saveXenForoSettings / saveWordPressSettings / saveWebhookSettings /
  // xfWebhookUrl / wpWebhookUrl — extracted to <app-connect-sync-tab>.
  // Global Save All functionality was retired in favor of per-card saving
  // to avoid stale data drift between the parent and child tabs.

  // clearWordPressPassword / runWordPressSync — extracted to
  // <app-connect-sync-tab>.

  // createGroup() / saveGroup() / deleteGroup() / updateScope() extracted
  // to <app-silo-architecture-tab>. The parent retains `siloGroups`,
  // `scopes`, and `assignedScopeCount` because the overview header card
  // (`<app-settings-overview>`) still consumes those counts.

  // ── Notification preferences ──────────────────────────────────────
  // Extracted to `<app-notifications-tab>` (see ./notifications-tab/).
  // The child component owns its own state, save flow, and load flow,
  // and emits `(dirtyChanged)` so the parent's isDirty signal still
  // fires when the user touches a notification toggle.

  // ── Crawler exclusion helpers — extracted to <app-connect-sync-tab>.

  // ── Connect & Sync per-card save / test helpers ───────────────
  // Extracted to `<app-connect-sync-tab>` (see ./connect-sync-tab/).
  // The child owns its own state, save flow, test flow, and load flow.
  // The parent retains its own `xenforo` / `wordpress` / `webhookSettings`
  // / `googleOAuth` / `ga4Telemetry` / `matomoTelemetry` / `ga4Gsc` copies
  // because:
  //   - `noSourceConnected` (rendered in the tab label) reads
  //     `xenforo.health` and `wordpress.health`.
  //   - `saveAllSettings()` builds a forkJoin payload that includes
  //     wordpress, ga4Gsc, googleOAuth, ga4Telemetry, matomoTelemetry.
  //   - `getFeatureSummary()` reads `ga4Gsc.ranking_weight`.
  //   - The Diagnostics-tab teaser card reads `ga4Gsc.connection_status`
  //     via `telemetryStatusClass` / `telemetryStatusLabel`.
}
