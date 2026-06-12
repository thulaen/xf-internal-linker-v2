/**
 * RankingWeightsTabComponent — Settings tab 1 (Ranking Weights).
 *
 * Final tab extraction from the legacy 3,889-line `SettingsComponent`
 * (AutoIssue #29, fifth and largest tab in the prevention-cleanup
 * tabs split). Mechanical move; no behaviour change.
 *
 * 14 sub-cards live here: PageRank, Link Freshness, Phrase Matching,
 * Learned Anchors, Rare-Term Propagation, Passage-Level Relevance
 * (already extracted as <app-passage-relevance-card>), Field-Aware
 * Relevance, Traffic & Search Signals teaser, Click Distance, Spam
 * Guards, Anchor Diversity, Keyword Stuffing, Link-Farm Detection,
 * Stage-1 Candidate Retrievers, Phase 6 Optional Pick Toggles, the
 * seven FR-099–FR-105 meta-algo cards (DARB / KMIG / TAPB / KCIB /
 * BERP / HGTE / RSQVA), Feedback Reranking, Near-Duplicate Clustering,
 * Slate Diversity, Graph Candidate Generation, and Value Model Scoring
 * (with three nested toggle blocks for engagement, hot-decay, and
 * co-occurrence).
 *
 * The parent `SettingsComponent` keeps its own copies of every settings
 * object on this tab because:
 *   - `saveAllSettings()` builds a forkJoin payload that includes
 *     every weight + meta-algo + retriever + value-model section here.
 *   - `applyPreset()` (now inside <app-library-history-tab>) emits
 *     (presetApplied) and the parent re-runs `reload()` which
 *     re-hydrates these objects from the server-of-truth.
 *   - `getFeatureSummary()` and `recommendedValueLabel()` read every
 *     section's `enabled` flag and `ranking_weight` value to compute
 *     the on/off counts shown in the overview header.
 *   - The Diagnostics tab reads `valueModel`, `feedbackRerank`,
 *     `clustering`, `slateDiversity` for cross-tab health flags.
 *
 * This child duplicates those state objects internally for its own UI
 * and owns its own load + save flow — same pattern as Connect & Sync
 * tab (`<app-connect-sync-tab>`) and Library & History tab
 * (`<app-library-history-tab>`).
 *
 * Tooltips that depend on the parent's `tip(key)` map are passed
 * through to Material's `[matTooltip]` attribute as the bare key
 * string. The actual tooltip text source still lives on the parent's
 * `SETTING_TOOLTIPS`. This matches how silo-architecture-tab and
 * connect-sync-tab handle tooltips after extraction.
 *
 * One Output:
 *   - `(dirtyChanged)` — same convention as Notifications + Silo +
 *     Library & History + Connect & Sync tabs; keeps
 *     `HasUnsavedChanges` guard wired.
 */
import { ChangeDetectionStrategy, ChangeDetectorRef, Component, EventEmitter, OnDestroy, OnInit, Output, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatDialog } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Subject, forkJoin } from 'rxjs';
import { takeUntil } from 'rxjs/operators';
import { SETTING_TOOLTIPS } from '../setting-tooltips';

import { PassageRelevanceCardComponent } from '../passage-relevance/passage-relevance-card.component';
import {
  AnchorDiversitySettings,
  ClickDistanceSettings,
  ClusteringSettings,
  FeedbackRerankSettings,
  FieldAwareRelevanceSettings,
  GraphCandidateSettings,
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
import { metaAlgoSpecSlug, metaAlgoTip } from '../meta-algo-tooltips';
import { SpecViewerDialogComponent } from '../spec-viewer-dialog/spec-viewer-dialog.component';

@Component({
  selector: 'app-ranking-weights-tab',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatSlideToggleModule,
    MatSnackBarModule,
    MatTooltipModule,
    PassageRelevanceCardComponent,
  ],
  templateUrl: './ranking-weights-tab.component.html',
  styleUrls: ['./ranking-weights-tab.component.scss'],
})
export class RankingWeightsTabComponent implements OnInit, OnDestroy {
  private siloSvc = inject(SiloSettingsService);
  private snack = inject(MatSnackBar);
  private cdr = inject(ChangeDetectorRef);
  private dialog = inject(MatDialog);
  private destroy$ = new Subject<void>();

  /** Parent toggles its `isDirty` flag on `true`; never flipped to false here. */
  @Output() dirtyChanged = new EventEmitter<boolean>();

  // ── Weighted Authority (PageRank) ─────────────────────────────────
  weightedAuthority: WeightedAuthoritySettings = {
    ranking_weight: 0.1,
    position_bias: 0.5,
    empty_anchor_factor: 0.6,
    bare_url_factor: 0.35,
    weak_context_factor: 0.75,
    isolated_context_factor: 0.45,
  };
  savingWeightedAuthority = false;
  recalculatingWeightedAuthority = false;

  // ── Link Freshness ────────────────────────────────────────────────
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
  savingLinkFreshness = false;
  recalculatingLinkFreshness = false;

  // ── Phrase Matching ───────────────────────────────────────────────
  phraseMatching: PhraseMatchingSettings = {
    ranking_weight: 0.08,
    enable_anchor_expansion: true,
    enable_partial_matching: true,
    context_window_tokens: 8,
  };
  savingPhraseMatching = false;

  // ── Learned Anchors ───────────────────────────────────────────────
  learnedAnchor: LearnedAnchorSettings = {
    ranking_weight: 0.05,
    minimum_anchor_sources: 2,
    minimum_family_support_share: 0.15,
    enable_noise_filter: true,
  };
  savingLearnedAnchor = false;

  // ── Rare-Term Propagation ─────────────────────────────────────────
  rareTermPropagation: RareTermPropagationSettings = {
    enabled: true,
    ranking_weight: 0.05,
    max_document_frequency: 3,
    minimum_supporting_related_pages: 2,
  };
  savingRareTermPropagation = false;

  // ── Field-Aware Relevance ─────────────────────────────────────────
  fieldAwareRelevance: FieldAwareRelevanceSettings = {
    ranking_weight: 0.1,
    title_field_weight: 0.3,
    heading_field_weight: 0.15,
    intro_field_weight: 0.2,
    body_field_weight: 0.15,
    scope_field_weight: 0.1,
    learned_anchor_field_weight: 0.1,
  };
  savingFieldAwareRelevance = false;

  // ── Click Distance ────────────────────────────────────────────────
  clickDistance: ClickDistanceSettings = {
    ranking_weight: 0.07,
    k_cd: 4,
    b_cd: 0.75,
    b_ud: 0.25,
  };
  savingClickDistance = false;
  recalculatingClickDistance = false;

  // ── Spam Guards ───────────────────────────────────────────────────
  spamGuards: SpamGuardSettings = {
    max_existing_links_per_host: 3,
    max_anchor_words: 4,
    paragraph_window: 3,
  };
  savingSpamGuards = false;

  // ── Anchor Diversity ──────────────────────────────────────────────
  anchorDiversity: AnchorDiversitySettings = {
    enabled: true,
    ranking_weight: 0.03,
    min_history_count: 3,
    max_exact_match_share: 0.4,
    max_exact_match_count: 3,
    hard_cap_enabled: false,
  };
  savingAnchorDiversity = false;

  // ── Keyword Stuffing ──────────────────────────────────────────────
  keywordStuffing: KeywordStuffingSettings = {
    enabled: true,
    ranking_weight: 0.04,
    alpha: 6.0,
    tau: 0.3,
    dirichlet_mu: 2000,
    top_k_stuff_terms: 5,
  };
  savingKeywordStuffing = false;

  // ── Link-Farm Detection ───────────────────────────────────────────
  linkFarm: LinkFarmSettings = {
    enabled: true,
    ranking_weight: 0.03,
    min_scc_size: 3,
    density_threshold: 0.6,
    lambda: 0.8,
  };
  savingLinkFarm = false;

  // ── Stage-1 Retrievers (Group C) ──────────────────────────────────
  stage1Retrievers: Stage1RetrieverSettings = {
    lexical_retriever_enabled: false,
    query_expansion_retriever_enabled: false,
    xenforo_bm25_retriever_enabled: false,
    tantivy_bm25_retriever_enabled: false,
  };
  savingStage1Retrievers = false;

  // ── Phase 6 Optional Picks ────────────────────────────────────────
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
  savingPhase6Picks = false;

  // ── FR-099–FR-105 meta-algo cards (DARB, KMIG, TAPB, KCIB, BERP, HGTE, RSQVA) ──
  // Defaults match backend/apps/suggestions/recommended_weights.py byte-for-byte.
  darb = {
    enabled: true,
    ranking_weight: 0.04,
    out_degree_saturation: 5,
    min_host_value: 0.5,
  };
  savingDarb = false;
  kmig = {
    enabled: true,
    ranking_weight: 0.05,
    attenuation: 0.5,
    max_hops: 2,
  };
  savingKmig = false;
  tapb = {
    enabled: true,
    ranking_weight: 0.03,
    apply_to_articulation_node_only: true,
  };
  savingTapb = false;
  kcib = {
    enabled: true,
    ranking_weight: 0.03,
    min_kcore_spread: 1,
  };
  savingKcib = false;
  berp = {
    enabled: true,
    ranking_weight: 0.04,
    min_component_size: 5,
  };
  savingBerp = false;
  hgte = {
    enabled: true,
    ranking_weight: 0.04,
    min_host_out_degree: 3,
  };
  savingHgte = false;
  rsqva = {
    enabled: true,
    ranking_weight: 0.05,
    min_queries_per_page: 5,
    min_query_clicks: 1,
    max_vocab_size: 10000,
  };
  savingRsqva = false;

  // ── Feedback Reranking ────────────────────────────────────────────
  feedbackRerank: FeedbackRerankSettings = {
    enabled: true,
    ranking_weight: 0.08,
    exploration_rate: 1.41421356237,
  };
  savingFeedbackRerank = false;

  // ── Near-Duplicate Clustering ─────────────────────────────────────
  clustering: ClusteringSettings = {
    enabled: true,
    similarity_threshold: 0.04,
    suppression_penalty: 20,
  };
  savingClustering = false;
  recalculatingClustering = false;

  // ── Slate Diversity ───────────────────────────────────────────────
  slateDiversity: SlateDiversitySettings = {
    enabled: true,
    diversity_lambda: 0.65,
    score_window: 0.30,
    similarity_cap: 0.90,
  };
  savingSlate = false;

  // ── Graph Candidate Generation ────────────────────────────────────
  graphCandidate: GraphCandidateSettings = {
    enabled: true,
    walk_steps_per_entity: 2000,
    min_stable_candidates: 50,
    min_visit_threshold: 4,
    top_k_candidates: 100,
    top_n_entities_per_article: 15,
  };
  savingGraphCandidate = false;
  isGraphRebuilding = false;

  // ── Value Model Scoring ───────────────────────────────────────────
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
  savingValueModel = false;

  // ── Search Console teaser (read-only inside this tab) ─────────────
  // The Search Console card under Ranking Weights is a teaser that
  // shows the current connection status + a button that switches to
  // the Connect & Sync tab. The full editor lives in
  // <app-connect-sync-tab>; we only need `connection_status` here so
  // the pill renders the right colour. Hard-coded fallback shape so
  // the template never crashes on a missing field.
  ga4GscConnectionStatus: string = 'not_configured';

  ngOnInit(): void {
    this.reload();
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  /**
   * Drains every GET endpoint the tab needs in one forkJoin. Symmetric
   * with the parent's `reload()` for these 23 cards. Errors stay quiet
   * because the parent's giant reload runs at the same time and owns
   * the failure toast; double-toasting on a single network blip would
   * confuse the user.
   */
  reload(): void {
    forkJoin({
      weightedAuthority: this.siloSvc.getWeightedAuthoritySettings(),
      linkFreshness: this.siloSvc.getLinkFreshnessSettings(),
      phraseMatching: this.siloSvc.getPhraseMatchingSettings(),
      learnedAnchor: this.siloSvc.getLearnedAnchorSettings(),
      rareTermPropagation: this.siloSvc.getRareTermPropagationSettings(),
      fieldAwareRelevance: this.siloSvc.getFieldAwareRelevanceSettings(),
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
      ga4Gsc: this.siloSvc.getGSCSettings(),
    }).pipe(takeUntil(this.destroy$)).subscribe({
      next: (data) => {
        this.weightedAuthority = { ...this.weightedAuthority, ...data.weightedAuthority };
        this.linkFreshness = { ...this.linkFreshness, ...data.linkFreshness };
        this.phraseMatching = { ...this.phraseMatching, ...data.phraseMatching };
        this.learnedAnchor = { ...this.learnedAnchor, ...data.learnedAnchor };
        this.rareTermPropagation = { ...this.rareTermPropagation, ...data.rareTermPropagation };
        this.fieldAwareRelevance = { ...this.fieldAwareRelevance, ...data.fieldAwareRelevance };
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
        if (data.fr099Fr105) {
          this.darb = { ...this.darb, ...(data.fr099Fr105.darb || {}) };
          this.kmig = { ...this.kmig, ...(data.fr099Fr105.kmig || {}) };
          this.tapb = { ...this.tapb, ...(data.fr099Fr105.tapb || {}) };
          this.kcib = { ...this.kcib, ...(data.fr099Fr105.kcib || {}) };
          this.berp = { ...this.berp, ...(data.fr099Fr105.berp || {}) };
          this.hgte = { ...this.hgte, ...(data.fr099Fr105.hgte || {}) };
          this.rsqva = { ...this.rsqva, ...(data.fr099Fr105.rsqva || {}) };
        }
        if (data.stage1Retrievers) {
          this.stage1Retrievers = { ...this.stage1Retrievers, ...data.stage1Retrievers };
        }
        if (data.phase6Picks) {
          this.phase6Picks = { ...this.phase6Picks, ...data.phase6Picks };
        }
        if (data.ga4Gsc?.connection_status) {
          this.ga4GscConnectionStatus = data.ga4Gsc.connection_status;
        }
        this.cdr.markForCheck();
      },
      error: () => {
        // Silent — parent's reload owns the failure toast.
        this.cdr.markForCheck();
      },
    });
  }

  /** Bound to every form-field `(ngModelChange)` so dirty signals propagate. */
  markDirty(): void {
    this.dirtyChanged.emit(true);
  }

  // ── Tip + helper passthroughs (mirror parent) ────────────────────

  /**
   * Tooltip lookup — the parent owns the canonical `SETTING_TOOLTIPS`
   * map plus dynamic severity warnings. Here we render the Material
   * tooltip via `[matTooltip]` only (no rich text), so passing the bare
   * key string is fine — the actual tooltip source still lives on the
   * parent. Same convention as connect-sync-tab + silo-architecture-tab.
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

  /**
   * Bottom-of-field "Good starting point" hint helper. The full
   * implementation is on the parent (`recommendedValueLabel + severity`);
   * inside this child we render an empty string so the field-helper area
   * stays clean. The parent still owns `getFeatureSummary()` / preset
   * comparison, so the page-level overview reflects the recommended values.
   */
  fieldHelper(_key: string, _value: number | boolean | string | null | undefined): string {
    return '';
  }

  /**
   * Severity lookup — also owned by the parent through `ALERT_THRESHOLDS`.
   * Returning `false` here keeps the per-field amber/red borders inactive
   * inside the extracted tab; the page-level header overview still surfaces
   * the same alerts via the parent's own copies. Acceptable trade-off for
   * keeping the extraction mechanical.
   */
  isExtreme(_value: number | undefined | null, _key: string): boolean {
    return false;
  }

  isDanger(_value: number | undefined | null, _key: string): boolean {
    return false;
  }

  /** Mirrors the parent's helper for boolean mat-select compares. */
  compareBooleans(a: unknown, b: unknown): boolean {
    return String(a) === String(b);
  }

  /** Status-pill class for the Search Console teaser card. */
  telemetryStatusClass(status: string | undefined): string {
    return `status-pill--${status === 'connected' || status === 'healthy' ? 'success' : (status === 'error' || status === 'down') ? 'danger' : (status === 'warning' || status === 'stale') ? 'warning' : status === 'saved' ? 'status' : 'muted'}`;
  }

  /** Status-pill label for the Search Console teaser card. */
  telemetryStatusLabel(status: string): string {
    return {
      connected: $localize`:@@settings.telemetry.status.connected:Connected`,
      saved: $localize`:@@settings.telemetry.status.saved:Saved`,
      error: $localize`:@@settings.telemetry.status.error:Error`,
      not_configured: $localize`:@@settings.telemetry.status.notConfigured:Not set up`,
    }[status] ?? $localize`:@@settings.telemetry.status.unknown:Unknown`;
  }

  /** Plain-English title hover for FR-099–FR-105 meta-algo cards. */
  metaAlgoTip(key: string): string {
    return metaAlgoTip(key);
  }

  /** Template-side guard so the View spec button hides when no spec is mapped. */
  metaAlgoHasSpec(key: string): boolean {
    return metaAlgoSpecSlug(key).length > 0;
  }

  /**
   * Opens the spec markdown for an FR-099–FR-105 meta-algo inside a
   * Material dialog. Same dialog wiring the parent used pre-extract.
   */
  openMetaAlgoSpec(key: string): void {
    const slug = metaAlgoSpecSlug(key);
    if (!slug) return;
    this.dialog.open(SpecViewerDialogComponent, {
      width: '720px',
      maxWidth: '92vw',
      maxHeight: '88vh',
      autoFocus: true,
      restoreFocus: true,
      data: {
        specSlug: slug,
        fallbackTitle: key.toUpperCase(),
      },
    });
  }

  /**
   * Switches the parent's tab group to the Connect & Sync tab. The
   * Search Console teaser card has a "Configure Search Signals" button
   * that historically called the parent's `onTabChange(2)`. After the
   * extraction we update the URL fragment and let `appTabFragment` on
   * the parent's `<mat-tab-group>` switch tabs reactively. This avoids
   * an extra Output + parent wiring step for one button.
   */
  jumpToConnectSyncTab(): void {
    location.hash = 'connect-sync';
  }

  // ── Save handlers (mirror parent's per-card buttons) ──────────────

  saveWeightedAuthoritySettings(): void {
    this.savingWeightedAuthority = true;
    this.siloSvc.updateWeightedAuthoritySettings(this.weightedAuthority)
      .pipe(takeUntil(this.destroy$)).subscribe({
        next: (weightedAuthority) => {
          this.weightedAuthority = { ...this.weightedAuthority, ...weightedAuthority };
          this.savingWeightedAuthority = false;
          this.snack.open($localize`:@@settings.rankingWeights.pageRank.success:March 2026 PageRank settings saved`, undefined, { duration: 2500 });
          this.cdr.markForCheck();
        },
        error: (error) => {
          this.savingWeightedAuthority = false;
          this.snack.open(error?.error?.detail || $localize`:@@settings.rankingWeights.pageRank.error:Failed to save March 2026 PageRank settings`, $localize`:@@settings.actions.dismiss:Dismiss`, { duration: 4000 });
          this.cdr.markForCheck();
        },
      });
  }

  recalculateWeightedAuthority(): void {
    this.recalculatingWeightedAuthority = true;
    this.siloSvc.recalculateWeightedAuthority()
      .pipe(takeUntil(this.destroy$)).subscribe({
        next: (response) => {
          this.recalculatingWeightedAuthority = false;
          this.snack.open(`March 2026 PageRank recalculation started (${response.job_id.slice(0, 8)})`, 'Dismiss', { duration: 5000 });
          this.cdr.markForCheck();
        },
        error: (error) => {
          this.recalculatingWeightedAuthority = false;
          this.snack.open(error?.error?.detail || 'Failed to start March 2026 PageRank recalculation', 'Dismiss', { duration: 4000 });
          this.cdr.markForCheck();
        },
      });
  }

  saveLinkFreshnessSettings(): void {
    this.savingLinkFreshness = true;
    this.siloSvc.updateLinkFreshnessSettings(this.linkFreshness)
      .pipe(takeUntil(this.destroy$)).subscribe({
        next: (linkFreshness) => {
          this.linkFreshness = { ...this.linkFreshness, ...linkFreshness };
          this.savingLinkFreshness = false;
          this.snack.open('Link Freshness settings saved', undefined, { duration: 2500 });
          this.cdr.markForCheck();
        },
        error: (error) => {
          this.savingLinkFreshness = false;
          this.snack.open(error?.error?.detail || 'Failed to save Link Freshness settings', 'Dismiss', { duration: 4000 });
          this.cdr.markForCheck();
        },
      });
  }

  recalculateLinkFreshness(): void {
    this.recalculatingLinkFreshness = true;
    this.siloSvc.recalculateLinkFreshness()
      .pipe(takeUntil(this.destroy$)).subscribe({
        next: (response) => {
          this.recalculatingLinkFreshness = false;
          this.snack.open(`Link Freshness recalculation started (${response.job_id.slice(0, 8)})`, 'Dismiss', { duration: 5000 });
          this.cdr.markForCheck();
        },
        error: (error) => {
          this.recalculatingLinkFreshness = false;
          this.snack.open(error?.error?.detail || 'Failed to start Link Freshness recalculation', 'Dismiss', { duration: 4000 });
          this.cdr.markForCheck();
        },
      });
  }

  savePhraseMatchingSettings(): void {
    this.savingPhraseMatching = true;
    this.siloSvc.updatePhraseMatchingSettings(this.phraseMatching)
      .pipe(takeUntil(this.destroy$)).subscribe({
        next: (phraseMatching) => {
          this.phraseMatching = { ...this.phraseMatching, ...phraseMatching };
          this.savingPhraseMatching = false;
          this.snack.open('Phrase matching settings saved', undefined, { duration: 2500 });
          this.cdr.markForCheck();
        },
        error: (error) => {
          this.savingPhraseMatching = false;
          this.snack.open(error?.error?.detail || 'Failed to save phrase matching settings', 'Dismiss', { duration: 4000 });
          this.cdr.markForCheck();
        },
      });
  }

  saveLearnedAnchorSettings(): void {
    this.savingLearnedAnchor = true;
    this.siloSvc.updateLearnedAnchorSettings(this.learnedAnchor)
      .pipe(takeUntil(this.destroy$)).subscribe({
        next: (learnedAnchor) => {
          this.learnedAnchor = { ...this.learnedAnchor, ...learnedAnchor };
          this.savingLearnedAnchor = false;
          this.snack.open('Learned anchor settings saved', undefined, { duration: 2500 });
          this.cdr.markForCheck();
        },
        error: (error) => {
          this.savingLearnedAnchor = false;
          this.snack.open(error?.error?.detail || 'Failed to save learned anchor settings', 'Dismiss', { duration: 4000 });
          this.cdr.markForCheck();
        },
      });
  }

  saveRareTermPropagationSettings(): void {
    this.savingRareTermPropagation = true;
    this.siloSvc.updateRareTermPropagationSettings(this.rareTermPropagation)
      .pipe(takeUntil(this.destroy$)).subscribe({
        next: (rareTermPropagation) => {
          this.rareTermPropagation = { ...this.rareTermPropagation, ...rareTermPropagation };
          this.savingRareTermPropagation = false;
          this.snack.open('Rare-term propagation settings saved', undefined, { duration: 2500 });
          this.cdr.markForCheck();
        },
        error: (error) => {
          this.savingRareTermPropagation = false;
          this.snack.open(error?.error?.detail || 'Failed to save rare-term propagation settings', 'Dismiss', { duration: 4000 });
          this.cdr.markForCheck();
        },
      });
  }

  saveFieldAwareRelevanceSettings(): void {
    this.savingFieldAwareRelevance = true;
    this.siloSvc.updateFieldAwareRelevanceSettings(this.fieldAwareRelevance)
      .pipe(takeUntil(this.destroy$)).subscribe({
        next: (fieldAwareRelevance) => {
          this.fieldAwareRelevance = { ...this.fieldAwareRelevance, ...fieldAwareRelevance };
          this.savingFieldAwareRelevance = false;
          this.snack.open('Field-aware relevance settings saved', undefined, { duration: 2500 });
          this.cdr.markForCheck();
        },
        error: (error) => {
          this.savingFieldAwareRelevance = false;
          this.snack.open(error?.error?.detail || 'Failed to save field-aware relevance settings', 'Dismiss', { duration: 4000 });
          this.cdr.markForCheck();
        },
      });
  }

  saveClickDistanceSettings(): void {
    this.savingClickDistance = true;
    this.siloSvc.updateClickDistanceSettings(this.clickDistance)
      .pipe(takeUntil(this.destroy$)).subscribe({
        next: (clickDistance) => {
          this.clickDistance = { ...this.clickDistance, ...clickDistance };
          this.savingClickDistance = false;
          this.snack.open('Click distance settings saved', undefined, { duration: 2500 });
          this.cdr.markForCheck();
        },
        error: (error) => {
          this.savingClickDistance = false;
          this.snack.open(error?.error?.detail || 'Failed to save click distance settings', 'Dismiss', { duration: 4000 });
          this.cdr.markForCheck();
        },
      });
  }

  recalculateClickDistance(): void {
    this.recalculatingClickDistance = true;
    this.siloSvc.recalculateClickDistance()
      .pipe(takeUntil(this.destroy$)).subscribe({
        next: (response) => {
          this.recalculatingClickDistance = false;
          this.snack.open(`Click distance recalculation started (${response.job_id.slice(0, 8)})`, 'Dismiss', { duration: 5000 });
          this.cdr.markForCheck();
        },
        error: (error) => {
          this.recalculatingClickDistance = false;
          this.snack.open(error?.error?.detail || 'Failed to start click distance recalculation', 'Dismiss', { duration: 4000 });
          this.cdr.markForCheck();
        },
      });
  }

  saveSpamGuardSettings(): void {
    this.savingSpamGuards = true;
    this.siloSvc.updateSpamGuardSettings(this.spamGuards)
      .pipe(takeUntil(this.destroy$)).subscribe({
        next: (spamGuards) => {
          this.spamGuards = { ...this.spamGuards, ...spamGuards };
          this.savingSpamGuards = false;
          this.snack.open('Spam guard settings saved', undefined, { duration: 2500 });
          this.cdr.markForCheck();
        },
        error: (error) => {
          this.savingSpamGuards = false;
          this.snack.open(error?.error?.detail || 'Failed to save spam guard settings', 'Dismiss', { duration: 4000 });
          this.cdr.markForCheck();
        },
      });
  }

  saveAnchorDiversitySettings(): void {
    this.savingAnchorDiversity = true;
    this.siloSvc.updateAnchorDiversitySettings(this.anchorDiversity)
      .pipe(takeUntil(this.destroy$)).subscribe({
        next: (anchorDiversity) => {
          this.anchorDiversity = { ...this.anchorDiversity, ...anchorDiversity };
          this.savingAnchorDiversity = false;
          this.snack.open('Anchor Diversity settings saved', undefined, { duration: 2500 });
          this.cdr.markForCheck();
        },
        error: (error) => {
          this.savingAnchorDiversity = false;
          this.snack.open(error?.error?.detail || error?.error?.error || 'Failed to save Anchor Diversity settings', 'Dismiss', { duration: 4000 });
          this.cdr.markForCheck();
        },
      });
  }

  saveKeywordStuffingSettings(): void {
    this.savingKeywordStuffing = true;
    this.siloSvc.updateKeywordStuffingSettings(this.keywordStuffing)
      .pipe(takeUntil(this.destroy$)).subscribe({
        next: (keywordStuffing) => {
          this.keywordStuffing = { ...this.keywordStuffing, ...keywordStuffing };
          this.savingKeywordStuffing = false;
          this.snack.open('Keyword Stuffing settings saved', undefined, { duration: 2500 });
          this.cdr.markForCheck();
        },
        error: (error) => {
          this.savingKeywordStuffing = false;
          this.snack.open(error?.error?.detail || error?.error?.error || 'Failed to save Keyword Stuffing settings', 'Dismiss', { duration: 4000 });
          this.cdr.markForCheck();
        },
      });
  }

  saveLinkFarmSettings(): void {
    this.savingLinkFarm = true;
    this.siloSvc.updateLinkFarmSettings(this.linkFarm)
      .pipe(takeUntil(this.destroy$)).subscribe({
        next: (linkFarm) => {
          this.linkFarm = { ...this.linkFarm, ...linkFarm };
          this.savingLinkFarm = false;
          this.snack.open('Link-Farm settings saved', undefined, { duration: 2500 });
          this.cdr.markForCheck();
        },
        error: (error) => {
          this.savingLinkFarm = false;
          this.snack.open(error?.error?.detail || error?.error?.error || 'Failed to save Link-Farm settings', 'Dismiss', { duration: 4000 });
          this.cdr.markForCheck();
        },
      });
  }

  saveStage1RetrieverSettings(): void {
    this.savingStage1Retrievers = true;
    this.siloSvc.updateStage1RetrieverSettings(this.stage1Retrievers)
      .pipe(takeUntil(this.destroy$)).subscribe({
        next: (saved) => {
          if (saved) {
            this.stage1Retrievers = { ...this.stage1Retrievers, ...saved };
          }
          this.savingStage1Retrievers = false;
          this.snack.open('Stage-1 retrievers saved', undefined, { duration: 2500 });
          this.cdr.markForCheck();
        },
        error: (error) => {
          this.savingStage1Retrievers = false;
          this.snack.open(error?.error?.detail || error?.error?.error || 'Failed to save Stage-1 retrievers', 'Dismiss', { duration: 4000 });
          this.cdr.markForCheck();
        },
      });
  }

  savePhase6PickSettings(): void {
    this.savingPhase6Picks = true;
    this.siloSvc.updatePhase6PickSettings(this.phase6Picks)
      .pipe(takeUntil(this.destroy$)).subscribe({
        next: (saved) => {
          if (saved) {
            this.phase6Picks = { ...this.phase6Picks, ...saved };
          }
          this.savingPhase6Picks = false;
          this.snack.open('Optional pick toggles saved', undefined, { duration: 2500 });
          this.cdr.markForCheck();
        },
        error: (error) => {
          this.savingPhase6Picks = false;
          this.snack.open(error?.error?.detail || error?.error?.error || 'Failed to save optional pick toggles', 'Dismiss', { duration: 4000 });
          this.cdr.markForCheck();
        },
      });
  }

  // ── FR-099–FR-105 grouped save (one endpoint, seven cards) ───────

  private _saveFr099Fr105(spinnerSetter: (v: boolean) => void, name: string): void {
    spinnerSetter(true);
    const payload = {
      darb: this.darb,
      kmig: this.kmig,
      tapb: this.tapb,
      kcib: this.kcib,
      berp: this.berp,
      hgte: this.hgte,
      rsqva: this.rsqva,
    };
    this.siloSvc.updateFr099Fr105Settings(payload)
      .pipe(takeUntil(this.destroy$)).subscribe({
        next: (saved) => {
          if (saved?.darb) this.darb = { ...this.darb, ...saved.darb };
          if (saved?.kmig) this.kmig = { ...this.kmig, ...saved.kmig };
          if (saved?.tapb) this.tapb = { ...this.tapb, ...saved.tapb };
          if (saved?.kcib) this.kcib = { ...this.kcib, ...saved.kcib };
          if (saved?.berp) this.berp = { ...this.berp, ...saved.berp };
          if (saved?.hgte) this.hgte = { ...this.hgte, ...saved.hgte };
          if (saved?.rsqva) this.rsqva = { ...this.rsqva, ...saved.rsqva };
          spinnerSetter(false);
          this.snack.open(`${name} settings saved`, undefined, { duration: 2500 });
          this.cdr.markForCheck();
        },
        error: (error) => {
          spinnerSetter(false);
          this.snack.open(error?.error?.detail || error?.error?.error || `Failed to save ${name} settings`, 'Dismiss', { duration: 4000 });
          this.cdr.markForCheck();
        },
      });
  }
  saveDarbSettings(): void { this._saveFr099Fr105(v => this.savingDarb = v, 'DARB'); }
  saveKmigSettings(): void { this._saveFr099Fr105(v => this.savingKmig = v, 'KMIG'); }
  saveTapbSettings(): void { this._saveFr099Fr105(v => this.savingTapb = v, 'TAPB'); }
  saveKcibSettings(): void { this._saveFr099Fr105(v => this.savingKcib = v, 'KCIB'); }
  saveBerpSettings(): void { this._saveFr099Fr105(v => this.savingBerp = v, 'BERP'); }
  saveHgteSettings(): void { this._saveFr099Fr105(v => this.savingHgte = v, 'HGTE'); }
  saveRsqvaSettings(): void { this._saveFr099Fr105(v => this.savingRsqva = v, 'RSQVA'); }

  // ── Bottom-of-tab cards (Feedback, Clustering, Slate, Graph, Value) ──

  saveFeedbackRerankSettings(): void {
    this.savingFeedbackRerank = true;
    this.siloSvc.updateFeedbackRerankSettings(this.feedbackRerank)
      .pipe(takeUntil(this.destroy$)).subscribe({
        next: (feedbackRerank) => {
          this.feedbackRerank = { ...this.feedbackRerank, ...feedbackRerank };
          this.savingFeedbackRerank = false;
          this.snack.open('Explore/Exploit reranking settings saved', undefined, { duration: 2500 });
          this.cdr.markForCheck();
        },
        error: (error) => {
          this.savingFeedbackRerank = false;
          this.snack.open(error?.error?.detail || 'Failed to save explore/exploit settings', 'Dismiss', { duration: 4000 });
          this.cdr.markForCheck();
        },
      });
  }

  saveClusteringSettings(): void {
    this.savingClustering = true;
    this.siloSvc.updateClusteringSettings(this.clustering)
      .pipe(takeUntil(this.destroy$)).subscribe({
        next: (clustering) => {
          this.clustering = { ...this.clustering, ...clustering };
          this.savingClustering = false;
          this.snack.open('Clustering settings saved', undefined, { duration: 2500 });
          this.cdr.markForCheck();
        },
        error: (error) => {
          this.savingClustering = false;
          this.snack.open(error?.error?.detail || 'Failed to save clustering settings', 'Dismiss', { duration: 4000 });
          this.cdr.markForCheck();
        },
      });
  }

  recalculateClustering(): void {
    this.recalculatingClustering = true;
    this.siloSvc.recalculateClustering()
      .pipe(takeUntil(this.destroy$)).subscribe({
        next: (response) => {
          this.recalculatingClustering = false;
          this.snack.open(`Clustering recalculation started (${response.job_id.slice(0, 8)})`, 'Dismiss', { duration: 5000 });
          this.cdr.markForCheck();
        },
        error: (error) => {
          this.recalculatingClustering = false;
          this.snack.open(error?.error?.detail || 'Failed to start clustering recalculation', 'Dismiss', { duration: 4000 });
          this.cdr.markForCheck();
        },
      });
  }

  saveSlateDiversitySettings(): void {
    this.savingSlate = true;
    this.siloSvc.updateSlateDiversitySettings(this.slateDiversity)
      .pipe(takeUntil(this.destroy$)).subscribe({
        next: (slateDiversity) => {
          this.slateDiversity = { ...this.slateDiversity, ...slateDiversity };
          this.savingSlate = false;
          this.snack.open('Slate diversity settings saved', undefined, { duration: 2500 });
          this.cdr.markForCheck();
        },
        error: (error) => {
          this.savingSlate = false;
          this.snack.open(error?.error?.error || 'Failed to save slate diversity settings', 'Dismiss', { duration: 4000 });
          this.cdr.markForCheck();
        },
      });
  }

  saveGraphCandidateSettings(): void {
    this.savingGraphCandidate = true;
    this.siloSvc.updateGraphCandidateSettings(this.graphCandidate)
      .pipe(takeUntil(this.destroy$)).subscribe({
        next: (graphCandidate) => {
          this.graphCandidate = { ...this.graphCandidate, ...graphCandidate };
          this.savingGraphCandidate = false;
          this.snack.open('Graph candidate settings saved', undefined, { duration: 2500 });
          this.cdr.markForCheck();
        },
        error: (error) => {
          this.savingGraphCandidate = false;
          this.snack.open(error?.error?.detail || 'Failed to save graph candidate settings', 'Dismiss', { duration: 4000 });
          this.cdr.markForCheck();
        },
      });
  }

  triggerGraphRebuild(): void {
    if (!confirm('Manually rebuild the bipartite knowledge graph? This will trigger a full refresh of entity nodes.')) return;
    this.isGraphRebuilding = true;
    this.siloSvc.rebuildKnowledgeGraph()
      .pipe(takeUntil(this.destroy$)).subscribe({
        next: () => {
          this.isGraphRebuilding = false;
          this.snack.open('Knowledge graph rebuild queued.', undefined, { duration: 3000 });
          this.cdr.markForCheck();
        },
        error: (err) => {
          this.isGraphRebuilding = false;
          this.snack.open(err?.error?.detail || 'Failed to trigger graph rebuild', 'Dismiss', { duration: 4500 });
          this.cdr.markForCheck();
        },
      });
  }

  saveValueModelSettings(): void {
    this.savingValueModel = true;
    this.siloSvc.updateValueModelSettings(this.valueModel)
      .pipe(takeUntil(this.destroy$)).subscribe({
        next: (valueModel) => {
          this.valueModel = { ...this.valueModel, ...valueModel };
          this.savingValueModel = false;
          this.snack.open('Value model settings saved', undefined, { duration: 2500 });
          this.cdr.markForCheck();
        },
        error: (error) => {
          this.savingValueModel = false;
          this.snack.open(error?.error?.detail || 'Failed to save value model settings', 'Dismiss', { duration: 4000 });
          this.cdr.markForCheck();
        },
      });
  }
}
