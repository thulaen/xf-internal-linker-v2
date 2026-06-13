/**
 * Specs for the extracted Ranking Weights tab. Mirrors the contract the
 * parent settings page used to enforce inline:
 *   - Loads every weight + meta-algo + retriever + value-model section
 *     in one ngOnInit forkJoin (20 GETs).
 *   - `markDirty()` emits `dirtyChanged=true`.
 *   - `saveWeightedAuthoritySettings()` PUTs the March 2026 PageRank
 *     payload and re-hydrates the local copy from the server response.
 *   - `saveClickDistanceSettings()` PUTs the click-distance payload.
 *   - `recalculateLinkFreshness()` POSTs the recalculate trigger and
 *     surfaces the returned job_id in a snack toast.
 *   - Save handler error paths flip the spinner off and never crash.
 *
 * Render-tree is overridden to a stub `<div>` because the real template
 * inlines 14 sub-cards across 1,400 lines — way too heavy for unit
 * tests. We exercise the public TS API through `componentInstance`
 * instead. Same approach the parent settings spec uses for its own
 * heavy template tests.
 */
import { TestBed } from '@angular/core/testing';
import { provideHttpClient, withXhr } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { provideRouter } from '@angular/router';

import { RankingWeightsTabComponent } from './ranking-weights-tab.component';
import {
  AnchorDiversitySettings,
  ClickDistanceSettings,
  ClusteringSettings,
  FeedbackRerankSettings,
  FieldAwareRelevanceSettings,
  GraphCandidateSettings,
  GSCSettings,
  KeywordStuffingSettings,
  LearnedAnchorSettings,
  LinkFarmSettings,
  LinkFreshnessSettings,
  Phase6PickSettings,
  PhraseMatchingSettings,
  RareTermPropagationSettings,
  SiloSettingsService,
  SlateDiversitySettings,
  SpamGuardSettings,
  Stage1RetrieverSettings,
  ValueModelSettings,
  WeightedAuthoritySettings,
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

const WEIGHTED_AUTH_DEFAULTS: WeightedAuthoritySettings = {
  ranking_weight: 0.1,
  position_bias: 0.5,
  empty_anchor_factor: 0.6,
  bare_url_factor: 0.35,
  weak_context_factor: 0.75,
  isolated_context_factor: 0.45,
};

const LINK_FRESHNESS_DEFAULTS: LinkFreshnessSettings = {
  ranking_weight: 0.05,
  recent_window_days: 30,
  newest_peer_percent: 0.25,
  min_peer_count: 3,
  w_recent: 0.35,
  w_growth: 0.35,
  w_cohort: 0.2,
  w_loss: 0.1,
};

const PHRASE_MATCHING_DEFAULTS: PhraseMatchingSettings = {
  ranking_weight: 0.08,
  enable_anchor_expansion: true,
  enable_partial_matching: true,
  context_window_tokens: 8,
};

const LEARNED_ANCHOR_DEFAULTS: LearnedAnchorSettings = {
  ranking_weight: 0.05,
  minimum_anchor_sources: 2,
  minimum_family_support_share: 0.15,
  enable_noise_filter: true,
};

const RARE_TERM_DEFAULTS: RareTermPropagationSettings = {
  enabled: true,
  ranking_weight: 0.05,
  max_document_frequency: 3,
  minimum_supporting_related_pages: 2,
};

const FIELD_AWARE_DEFAULTS: FieldAwareRelevanceSettings = {
  ranking_weight: 0.1,
  title_field_weight: 0.3,
  heading_field_weight: 0.15,
  intro_field_weight: 0.2,
  body_field_weight: 0.15,
  scope_field_weight: 0.1,
  learned_anchor_field_weight: 0.1,
};

const CLICK_DISTANCE_DEFAULTS: ClickDistanceSettings = {
  ranking_weight: 0.07,
  k_cd: 4,
  b_cd: 0.75,
  b_ud: 0.25,
};

const SPAM_GUARD_DEFAULTS: SpamGuardSettings = {
  max_existing_links_per_host: 3,
  max_anchor_words: 4,
  paragraph_window: 3,
};

const ANCHOR_DIVERSITY_DEFAULTS: AnchorDiversitySettings = {
  enabled: true,
  ranking_weight: 0.03,
  min_history_count: 3,
  max_exact_match_share: 0.4,
  max_exact_match_count: 3,
  hard_cap_enabled: false,
};

const KEYWORD_STUFFING_DEFAULTS: KeywordStuffingSettings = {
  enabled: true,
  ranking_weight: 0.04,
  alpha: 6.0,
  tau: 0.3,
  dirichlet_mu: 2000,
  top_k_stuff_terms: 5,
};

const LINK_FARM_DEFAULTS: LinkFarmSettings = {
  enabled: true,
  ranking_weight: 0.03,
  min_scc_size: 3,
  density_threshold: 0.6,
  lambda: 0.8,
};

const FEEDBACK_RERANK_DEFAULTS: FeedbackRerankSettings = {
  enabled: true,
  ranking_weight: 0.08,
  exploration_rate: 1.41421356237,
};

const CLUSTERING_DEFAULTS: ClusteringSettings = {
  enabled: true,
  similarity_threshold: 0.04,
  suppression_penalty: 20,
};

const SLATE_DIVERSITY_DEFAULTS: SlateDiversitySettings = {
  enabled: true,
  diversity_lambda: 0.65,
  score_window: 0.3,
  similarity_cap: 0.9,
};

const GRAPH_CANDIDATE_DEFAULTS: GraphCandidateSettings = {
  enabled: true,
  walk_steps_per_entity: 2000,
  min_stable_candidates: 50,
  min_visit_threshold: 4,
  top_k_candidates: 100,
  top_n_entities_per_article: 15,
};

const VALUE_MODEL_DEFAULTS: ValueModelSettings = {
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

const FR099_FR105_DEFAULTS = {
  darb: { enabled: true, ranking_weight: 0.04, out_degree_saturation: 5, min_host_value: 0.5 },
  kmig: { enabled: true, ranking_weight: 0.05, attenuation: 0.5, max_hops: 2 },
  tapb: { enabled: true, ranking_weight: 0.03, apply_to_articulation_node_only: true },
  kcib: { enabled: true, ranking_weight: 0.03, min_kcore_spread: 1 },
  berp: { enabled: true, ranking_weight: 0.04, min_component_size: 5 },
  hgte: { enabled: true, ranking_weight: 0.04, min_host_out_degree: 3 },
  rsqva: { enabled: true, ranking_weight: 0.05, min_queries_per_page: 5, min_query_clicks: 1, max_vocab_size: 10000 },
};

const STAGE1_RETRIEVERS_DEFAULTS: Stage1RetrieverSettings = {
  lexical_retriever_enabled: false,
  query_expansion_retriever_enabled: false,
  xenforo_bm25_retriever_enabled: false,
  tantivy_bm25_retriever_enabled: false,
};

const PHASE6_PICKS_DEFAULTS: Phase6PickSettings = {
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
  connection_message: 'Not configured.',
  oauth_connected: false,
  last_sync: null,
  health: HEALTH,
};

describe('RankingWeightsTabComponent', () => {
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [RankingWeightsTabComponent, NoopAnimationsModule],
      providers: [
        provideHttpClient(withXhr()),
        provideHttpClientTesting(),
        provideRouter([]),
        // Use the real SiloSettingsService so the load + save HTTP calls
        // route through the actual endpoint paths the spec asserts on
        // via HttpTestingController. Same pattern as
        // connect-sync-tab.component.spec.ts.
        SiloSettingsService,
      ],
    })
      // Override the heavy 14-sub-card template — the real one inlines
      // 1,416 lines of mat-card markup that would balloon the test runtime
      // without exercising any TS logic the spec checks.
      .overrideComponent(RankingWeightsTabComponent, { set: { template: '<div></div>' } })
      .compileComponents();

    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  /**
   * Drains the 20 GETs ngOnInit fires inside one forkJoin. Order is not
   * guaranteed; match by URL via `expectOne(url)` instead of positional
   * `match`.
   */
  function flushInitialLoad(): void {
    httpMock.expectOne('/api/settings/weighted-authority/').flush(WEIGHTED_AUTH_DEFAULTS);
    httpMock.expectOne('/api/settings/link-freshness/').flush(LINK_FRESHNESS_DEFAULTS);
    httpMock.expectOne('/api/settings/phrase-matching/').flush(PHRASE_MATCHING_DEFAULTS);
    httpMock.expectOne('/api/settings/learned-anchor/').flush(LEARNED_ANCHOR_DEFAULTS);
    httpMock.expectOne('/api/settings/rare-term-propagation/').flush(RARE_TERM_DEFAULTS);
    httpMock.expectOne('/api/settings/field-aware-relevance/').flush(FIELD_AWARE_DEFAULTS);
    httpMock.expectOne('/api/settings/click-distance/').flush(CLICK_DISTANCE_DEFAULTS);
    httpMock.expectOne('/api/settings/spam-guards/').flush(SPAM_GUARD_DEFAULTS);
    httpMock.expectOne('/api/settings/anchor-diversity/').flush(ANCHOR_DIVERSITY_DEFAULTS);
    httpMock.expectOne('/api/settings/keyword-stuffing/').flush(KEYWORD_STUFFING_DEFAULTS);
    httpMock.expectOne('/api/settings/link-farm/').flush(LINK_FARM_DEFAULTS);
    httpMock.expectOne('/api/settings/explore-exploit/').flush(FEEDBACK_RERANK_DEFAULTS);
    httpMock.expectOne('/api/settings/clustering/').flush(CLUSTERING_DEFAULTS);
    httpMock.expectOne('/api/settings/slate-diversity/').flush(SLATE_DIVERSITY_DEFAULTS);
    httpMock.expectOne('/api/settings/graph-candidate/').flush(GRAPH_CANDIDATE_DEFAULTS);
    httpMock.expectOne('/api/settings/value-model/').flush(VALUE_MODEL_DEFAULTS);
    httpMock.expectOne('/api/settings/fr099-fr105/').flush(FR099_FR105_DEFAULTS);
    httpMock.expectOne('/api/settings/stage1-retrievers/').flush(STAGE1_RETRIEVERS_DEFAULTS);
    httpMock.expectOne('/api/settings/phase6-picks/').flush(PHASE6_PICKS_DEFAULTS);
    httpMock.expectOne('/api/analytics/settings/gsc/').flush(GSC_DEFAULTS);
  }

  it('renders the stub template and loads all 20 settings sections on init', () => {
    const fixture = TestBed.createComponent(RankingWeightsTabComponent);
    fixture.detectChanges();
    flushInitialLoad();
    fixture.detectChanges();

    const cmp = fixture.componentInstance;
    // Spot-check that the load actually populated the local copies.
    expect(cmp.weightedAuthority.ranking_weight).toBe(0.1);
    expect(cmp.linkFreshness.recent_window_days).toBe(30);
    expect(cmp.valueModel.w_relevance).toBe(0.35);
    expect(cmp.darb.ranking_weight).toBe(0.04);
    expect(cmp.ga4GscConnectionStatus).toBe('not_configured');
  });

  it('saves weighted-authority settings via PUT and re-hydrates the local copy', () => {
    const fixture = TestBed.createComponent(RankingWeightsTabComponent);
    fixture.detectChanges();
    flushInitialLoad();
    fixture.detectChanges();

    const cmp = fixture.componentInstance;
    cmp.weightedAuthority.ranking_weight = 0.18;
    cmp.saveWeightedAuthoritySettings();

    const req = httpMock.expectOne('/api/settings/weighted-authority/');
    expect(req.request.method).toBe('PUT');
    expect(req.request.body.ranking_weight).toBe(0.18);
    req.flush({ ...WEIGHTED_AUTH_DEFAULTS, ranking_weight: 0.18 });

    expect(cmp.weightedAuthority.ranking_weight).toBe(0.18);
    expect(cmp.savingWeightedAuthority).toBe(false);
  });

  it('saves click-distance settings via PUT', () => {
    const fixture = TestBed.createComponent(RankingWeightsTabComponent);
    fixture.detectChanges();
    flushInitialLoad();
    fixture.detectChanges();

    const cmp = fixture.componentInstance;
    cmp.clickDistance.k_cd = 6;
    cmp.saveClickDistanceSettings();

    const req = httpMock.expectOne('/api/settings/click-distance/');
    expect(req.request.method).toBe('PUT');
    expect(req.request.body.k_cd).toBe(6);
    req.flush({ ...CLICK_DISTANCE_DEFAULTS, k_cd: 6 });

    expect(cmp.clickDistance.k_cd).toBe(6);
    expect(cmp.savingClickDistance).toBe(false);
  });

  it('triggers Link Freshness recalculation via POST and clears the spinner', () => {
    const fixture = TestBed.createComponent(RankingWeightsTabComponent);
    fixture.detectChanges();
    flushInitialLoad();
    fixture.detectChanges();

    const cmp = fixture.componentInstance;
    cmp.recalculateLinkFreshness();

    const req = httpMock.expectOne('/api/settings/link-freshness/recalculate/');
    expect(req.request.method).toBe('POST');
    req.flush({ job_id: '12345678-abcd-efgh-ijkl-1234567890ab' });

    expect(cmp.recalculatingLinkFreshness).toBe(false);
  });

  it('emits dirtyChanged true when markDirty is called', () => {
    const fixture = TestBed.createComponent(RankingWeightsTabComponent);
    fixture.detectChanges();
    flushInitialLoad();
    fixture.detectChanges();

    const cmp = fixture.componentInstance;
    const emitted: boolean[] = [];
    cmp.dirtyChanged.subscribe((v) => emitted.push(v));

    cmp.markDirty();

    expect(emitted).toEqual([true]);
  });

  it('clears the saving spinner when a save handler errors', () => {
    const fixture = TestBed.createComponent(RankingWeightsTabComponent);
    fixture.detectChanges();
    flushInitialLoad();
    fixture.detectChanges();

    const cmp = fixture.componentInstance;
    cmp.saveValueModelSettings();

    const req = httpMock.expectOne('/api/settings/value-model/');
    expect(req.request.method).toBe('PUT');
    // Simulate a backend 500 — the handler must still flip the spinner
    // off so the user can retry without being stuck on "Saving...".
    req.flush({ detail: 'boom' }, { status: 500, statusText: 'Internal Server Error' });

    expect(cmp.savingValueModel).toBe(false);
  });
});
