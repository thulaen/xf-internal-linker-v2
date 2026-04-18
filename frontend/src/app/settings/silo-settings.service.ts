import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, of } from 'rxjs';
import { map, catchError } from 'rxjs/operators';

export type SiloMode = 'disabled' | 'prefer_same_silo' | 'strict_same_silo';

export interface SiloSettings {
  mode: SiloMode;
  same_silo_boost: number;
  cross_silo_penalty: number;
}

export interface SiloGroup {
  id: number;
  name: string;
  slug: string;
  description: string;
  display_order: number;
  scope_count: number;
  created_at: string;
  updated_at: string;
}

export interface ScopeItem {
  id: number;
  scope_id: number;
  scope_type: string;
  scope_type_label: string;
  source_label: string;
  title: string;
  parent: number | null;
  parent_title: string | null;
  silo_group: number | null;
  silo_group_name: string;
  is_enabled: boolean;
  content_count: number;
  display_order: number;
}

export interface ConnectionHealth {
  status: string;
  label: string;
  name: string;
  description: string;
  issue: string;
  fix: string;
  last_success: string | null;
  is_healthy: boolean;
}

export interface XenForoSettings {
  base_url: string;
  api_key_configured: boolean;
  health: ConnectionHealth;
}

export interface XenForoSettingsUpdate {
  base_url: string;
  api_key?: string;
}

export interface WordPressSettings {
  base_url: string;
  username: string;
  app_password_configured: boolean;
  sync_enabled: boolean;
  sync_hour: number;
  sync_minute: number;
  health: ConnectionHealth;
}

export interface WordPressSettingsUpdate {
  base_url: string;
  username: string;
  sync_enabled: boolean;
  sync_hour: number;
  sync_minute: number;
  app_password?: string;
}

export interface WebhookSettings {
  xf_secret_configured: boolean;
  wp_secret_configured: boolean;
}

export interface WebhookSettingsUpdate {
  xf_webhook_secret?: string;
  wp_webhook_secret?: string;
}

export interface WeightedAuthoritySettings {
  ranking_weight: number;
  position_bias: number;
  empty_anchor_factor: number;
  bare_url_factor: number;
  weak_context_factor: number;
  isolated_context_factor: number;
}

export interface LinkFreshnessSettings {
  ranking_weight: number;
  recent_window_days: number;
  newest_peer_percent: number;
  min_peer_count: number;
  w_recent: number;
  w_growth: number;
  w_cohort: number;
  w_loss: number;
}

export interface PhraseMatchingSettings {
  ranking_weight: number;
  enable_anchor_expansion: boolean;
  enable_partial_matching: boolean;
  context_window_tokens: number;
}

export interface LearnedAnchorSettings {
  ranking_weight: number;
  minimum_anchor_sources: number;
  minimum_family_support_share: number;
  enable_noise_filter: boolean;
}

export interface RareTermPropagationSettings {
  enabled: boolean;
  ranking_weight: number;
  max_document_frequency: number;
  minimum_supporting_related_pages: number;
}

export interface FieldAwareRelevanceSettings {
  ranking_weight: number;
  title_field_weight: number;
  body_field_weight: number;
  scope_field_weight: number;
  learned_anchor_field_weight: number;
}

export interface GSCSettings {
  ranking_weight: number;
  property_url: string;
  client_email: string;
  private_key_configured: boolean;
  sync_enabled: boolean;
  sync_lookback_days: number;
  manual_backfill_max_days: number;
  manual_backfill_suggested_days: number;
  excluded_countries: string[];
  connection_status: string;
  connection_message: string;
  oauth_connected: boolean;
  last_sync: AnalyticsSyncSummary | null;
  health: ConnectionHealth;
}

export interface GSCSettingsUpdate {
  ranking_weight: number;
  property_url: string;
  client_email: string;
  sync_enabled: boolean;
  sync_lookback_days: number;
  private_key?: string;
}

export interface GA4TelemetrySettings {
  behavior_enabled: boolean;
  property_id: string;
  measurement_id: string;
  api_secret_configured: boolean;
  read_project_id: string;
  read_client_email: string;
  read_private_key_configured: boolean;
  sync_enabled: boolean;
  sync_lookback_days: number;
  event_schema: string;
  geo_granularity: 'none' | 'country' | 'country_region';
  retention_days: number;
  impression_visible_ratio: number;
  impression_min_ms: number;
  engaged_min_seconds: number;
  connection_status: string;
  connection_message: string;
  read_connection_status: string;
  read_connection_message: string;
  last_sync: AnalyticsSyncSummary | null;
  oauth_connected: boolean;
  google_oauth_client_id: string;
  google_oauth_client_secret_configured: boolean;
  ga4_health: ConnectionHealth;
  gsc_health: ConnectionHealth;
}

export interface AnalyticsSyncSummary {
  status: string;
  started_at: string | null;
  completed_at: string | null;
  rows_read: number;
  rows_written: number;
  rows_updated: number;
  lookback_days: number;
  error_message: string;
}

export interface GoogleOAuthSettings {
  client_id: string;
  client_secret_configured: boolean;
  oauth_connected: boolean;
  status: string;
  message: string;
  last_sync: AnalyticsSyncSummary | null;
}

export interface GA4TelemetryUpdate {
  behavior_enabled: boolean;
  property_id: string;
  measurement_id: string;
  read_project_id: string;
  read_client_email: string;
  sync_enabled: boolean;
  sync_lookback_days: number;
  event_schema: string;
  geo_granularity: 'none' | 'country' | 'country_region';
  retention_days: number;
  impression_visible_ratio: number;
  impression_min_ms: number;
  engaged_min_seconds: number;
  api_secret?: string;
  read_private_key?: string;
}

export interface MatomoTelemetrySettings {
  enabled: boolean;
  url: string;
  site_id_xenforo: string;
  site_id_wordpress: string;
  token_auth_configured: boolean;
  sync_enabled: boolean;
  sync_lookback_days: number;
  connection_status: string;
  connection_message: string;
  last_sync: AnalyticsSyncSummary | null;
}

export interface MatomoTelemetryUpdate {
  enabled: boolean;
  url: string;
  site_id_xenforo: string;
  site_id_wordpress: string;
  sync_enabled: boolean;
  sync_lookback_days: number;
  token_auth?: string;
}

export interface AnalyticsConnectionResult {
  status: string;
  message: string;
}

export interface ClickDistanceSettings {
  ranking_weight: number;
  k_cd: number;
  b_cd: number;
  b_ud: number;
}

export interface FeedbackRerankSettings {
  enabled: boolean;
  ranking_weight: number;
  exploration_rate: number;
}

export interface ClusteringSettings {
  enabled: boolean;
  similarity_threshold: number;
  suppression_penalty: number;
}

export interface SlateDiversitySettings {
  enabled: boolean;
  diversity_lambda: number;
  score_window: number;
  similarity_cap: number;
  algorithm_version?: string;
}

export interface GraphCandidateSettings {
  enabled: boolean;
  walk_steps_per_entity: number;
  min_stable_candidates: number;
  min_visit_threshold: number;
  top_k_candidates: number;
  top_n_entities_per_article: number;
}

export interface ValueModelSettings {
  enabled: boolean;
  w_relevance: number;
  w_traffic: number;
  w_freshness: number;
  w_authority: number;
  w_penalty: number;
  traffic_lookback_days: number;
  traffic_fallback_value: number;
  // FR-024 engagement signal
  engagement_signal_enabled: boolean;
  w_engagement: number;
  engagement_lookback_days: number;
  engagement_words_per_minute: number;
  engagement_cap_ratio: number;
  engagement_fallback_value: number;
  // FR-023 hot decay signal
  hot_decay_enabled: boolean;
  hot_gravity: number;
  hot_clicks_weight: number;
  hot_impressions_weight: number;
  hot_lookback_days: number;
  // FR-025 co-occurrence signal
  co_occurrence_signal_enabled: boolean;
  w_cooccurrence: number;
  co_occurrence_fallback_value: number;
  co_occurrence_min_co_sessions: number;
}

export interface SpamGuardSettings {
  max_existing_links_per_host: number;
  max_anchor_words: number;
  paragraph_window: number;
}

export interface AnchorDiversitySettings {
  enabled: boolean;
  ranking_weight: number;
  min_history_count: number;
  max_exact_match_share: number;
  max_exact_match_count: number;
  hard_cap_enabled: boolean;
}

export interface KeywordStuffingSettings {
  enabled: boolean;
  ranking_weight: number;
  alpha: number;
  tau: number;
  dirichlet_mu: number;
  top_k_stuff_terms: number;
}

export interface LinkFarmSettings {
  enabled: boolean;
  ranking_weight: number;
  min_scc_size: number;
  density_threshold: number;
  lambda: number;
}

export interface RuntimeModelRegistryEntry {
  id: number;
  task_type: string;
  model_name: string;
  model_family: string;
  dimension: number | null;
  device_target: string;
  batch_size: number;
  memory_profile: Record<string, unknown>;
  role: string;
  status: string;
  health_result: Record<string, unknown>;
  algorithm_version: string;
  promoted_at: string | null;
  draining_since: string | null;
  last_warmup_result: Record<string, unknown>;
}

export interface RuntimeModelPlacement {
  id: number;
  registry_id: number;
  model_name: string;
  role: string;
  executor_type: string;
  helper_id: number | null;
  helper_name: string;
  artifact_path: string;
  disk_bytes: number;
  status: string;
  last_used_at: string | null;
  warmed_at: string | null;
  last_error: string;
  deletable: boolean;
}

export interface RuntimeBackfillPlan {
  id: number;
  from_model_id: number;
  to_model_id: number;
  status: string;
  compatibility_status: string;
  progress_pct: number;
  checkpoint: Record<string, unknown>;
  last_error: string;
}

export interface RuntimeAuditEntry {
  id: number;
  created_at: string;
  action: string;
  subject_type: string;
  subject_id: string;
  actor: string;
  message: string;
  metadata: Record<string, unknown>;
}

export interface RuntimeModelSummary {
  task_type: string;
  active_model: RuntimeModelRegistryEntry | null;
  candidate_model: RuntimeModelRegistryEntry | null;
  placements: RuntimeModelPlacement[];
  reclaimable_disk_bytes: number;
  backfill: RuntimeBackfillPlan | null;
  device: string;
  hot_swap_safe: boolean;
  recent_audit_log: RuntimeAuditEntry[];
  last_audit_at: string | null;
}

export interface HelperNodeSummary {
  online: number;
  busy: number;
  stale: number;
  offline: number;
}

export interface HelperNodesRuntimeSummary {
  counts: HelperNodeSummary;
  busiest: {
    name: string;
    effective_load: number;
  };
  aggregate_ram_pressure: number;
  helpers_enabled: boolean;
}

export interface HardwareCapabilitySummary {
  cpu_cores: number;
  ram_gb: number;
  gpu_name: string;
  gpu_vram_gb: number;
  disk_free_gb: number;
  native_kernels_healthy: boolean;
  detected_upgrade: boolean;
  captured_at: string;
}

export interface RuntimeProfileRecommendation {
  profile: string;
  reason: string;
  suggested_batch_size: number;
  suggested_concurrency: number;
}

export interface RuntimeSummaryPayload {
  model_runtime: RuntimeModelSummary;
  helper_nodes: HelperNodesRuntimeSummary;
  hardware: HardwareCapabilitySummary;
  recommended_profile: RuntimeProfileRecommendation;
}

export interface RuntimeModelRegistrationPayload {
  task_type?: string;
  model_name: string;
  model_family?: string;
  dimension?: number | null;
  device_target?: string;
  batch_size?: number;
  memory_profile?: Record<string, unknown>;
  role?: string;
  algorithm_version?: string;
  executor_type?: string;
  helper_id?: number | null;
  artifact_path?: string;
  artifact_checksum?: string;
  disk_bytes?: number;
}

export interface RuntimeModelActionPayload {
  action: 'download' | 'warm' | 'pause' | 'resume' | 'promote' | 'rollback' | 'drain';
  placement_id?: number;
}

export interface HelperNodeSettingsRecord {
  id: number;
  name: string;
  role: string;
  status: string;
  derived_state: string;
  capabilities: Record<string, unknown>;
  allowed_queues: string[];
  allowed_job_types: string[];
  time_policy: 'anytime' | 'nighttime' | 'maintenance';
  max_concurrency: number;
  cpu_cap_pct: number;
  ram_cap_pct: number;
  accepting_work: boolean;
  active_jobs: number;
  queued_jobs: number;
  cpu_pct: number;
  ram_pct: number;
  gpu_util_pct: number | null;
  gpu_vram_used_mb: number | null;
  gpu_vram_total_mb: number | null;
  network_rtt_ms: number | null;
  native_kernels_healthy: boolean;
  warmed_model_keys: string[];
  last_heartbeat: string | null;
  last_snapshot_at: string | null;
}

export interface HelperNodeCreatePayload {
  name: string;
  token: string;
  role?: string;
  capabilities?: Record<string, unknown>;
  allowed_queues?: string[];
  allowed_job_types?: string[];
  time_policy?: 'anytime' | 'nighttime' | 'maintenance';
  max_concurrency?: number;
  cpu_cap_pct?: number;
  ram_cap_pct?: number;
  accepting_work?: boolean;
}

export interface SyncRunResponse {
  job_id: string;
  source: string;
  mode: string;
}

export interface WeightPreset {
  id: number;
  name: string;
  is_system: boolean;
  weights: Record<string, string>;
  created_at: string;
  updated_at: string;
}

export interface WeightDeltaEntry {
  previous: string | null;
  new: string | null;
}

export interface WeightAdjustmentHistory {
  id: number;
  source: 'auto_tune' | 'manual' | 'preset_applied';
  preset: number | null;
  preset_name: string | null;
  previous_weights: Record<string, string>;
  new_weights: Record<string, string>;
  delta: Record<string, WeightDeltaEntry>;
  reason: string;
  r_run_id: string;
  created_at: string;
}

export interface RankingChallenger {
  id: number;
  run_id: string;
  status: 'pending' | 'promoted' | 'rolled_back' | 'rejected';
  candidate_weights: Record<string, number>;
  baseline_weights: Record<string, number>;
  predicted_quality_score: number | null;
  champion_quality_score: number | null;
  created_at: string;
  updated_at: string;
}

@Injectable({ providedIn: 'root' })
export class SiloSettingsService {
  private http = inject(HttpClient);
  private baseUrl = '/api';

  getSettings(): Observable<SiloSettings> {
    return this.http.get<SiloSettings>('/api/settings/silos/');
  }

  updateSettings(payload: SiloSettings): Observable<SiloSettings> {
    return this.http.put<SiloSettings>('/api/settings/silos/', payload);
  }

  listSiloGroups(): Observable<SiloGroup[]> {
    return this.http.get<SiloGroup[] | { results: SiloGroup[] }>('/api/silo-groups/')
      .pipe(
        map((r) => Array.isArray(r) ? r : r.results ?? []),
        catchError(() => of([]))
      );
  }

  createSiloGroup(payload: Partial<SiloGroup>): Observable<SiloGroup> {
    return this.http.post<SiloGroup>('/api/silo-groups/', payload);
  }

  updateSiloGroup(id: number, payload: Partial<SiloGroup>): Observable<SiloGroup> {
    return this.http.patch<SiloGroup>(`/api/silo-groups/${id}/`, payload);
  }

  deleteSiloGroup(id: number): Observable<void> {
    return this.http.delete<void>(`/api/silo-groups/${id}/`);
  }

  listScopes(): Observable<ScopeItem[]> {
    return this.http.get<ScopeItem[] | { results: ScopeItem[] }>('/api/scopes/')
      .pipe(
        map((r) => Array.isArray(r) ? r : r.results ?? []),
        catchError(() => of([]))
      );
  }

  updateScopeSilo(id: number, siloGroupId: number | null): Observable<ScopeItem> {
    return this.http.patch<ScopeItem>(`/api/scopes/${id}/`, { silo_group: siloGroupId });
  }

  getXenForoSettings(): Observable<XenForoSettings> {
    return this.http.get<XenForoSettings>('/api/settings/xenforo/');
  }

  updateXenForoSettings(payload: XenForoSettingsUpdate): Observable<{ status: string }> {
    return this.http.put<{ status: string }>('/api/settings/xenforo/', payload);
  }

  getWordPressSettings(): Observable<WordPressSettings> {
    return this.http.get<WordPressSettings>('/api/settings/wordpress/');
  }

  getWeightedAuthoritySettings(): Observable<WeightedAuthoritySettings> {
    return this.http.get<WeightedAuthoritySettings>('/api/settings/weighted-authority/');
  }

  getLinkFreshnessSettings(): Observable<LinkFreshnessSettings> {
    return this.http.get<LinkFreshnessSettings>('/api/settings/link-freshness/');
  }

  getPhraseMatchingSettings(): Observable<PhraseMatchingSettings> {
    return this.http.get<PhraseMatchingSettings>('/api/settings/phrase-matching/');
  }

  getLearnedAnchorSettings(): Observable<LearnedAnchorSettings> {
    return this.http.get<LearnedAnchorSettings>('/api/settings/learned-anchor/');
  }

  getRareTermPropagationSettings(): Observable<RareTermPropagationSettings> {
    return this.http.get<RareTermPropagationSettings>('/api/settings/rare-term-propagation/');
  }

  getFieldAwareRelevanceSettings(): Observable<FieldAwareRelevanceSettings> {
    return this.http.get<FieldAwareRelevanceSettings>('/api/settings/field-aware-relevance/');
  }

  getGSCSettings(): Observable<GSCSettings> {
    return this.http.get<GSCSettings>('/api/analytics/settings/gsc/');
  }

  getGA4TelemetrySettings(): Observable<GA4TelemetrySettings> {
    return this.http.get<GA4TelemetrySettings>('/api/analytics/settings/ga4/');
  }

  getGoogleOAuthSettings(): Observable<GoogleOAuthSettings> {
    return this.http.get<GoogleOAuthSettings>('/api/analytics/settings/google-oauth/');
  }

  getMatomoTelemetrySettings(): Observable<MatomoTelemetrySettings> {
    return this.http.get<MatomoTelemetrySettings>('/api/analytics/settings/matomo/');
  }

  getClickDistanceSettings(): Observable<ClickDistanceSettings> {
    return this.http.get<ClickDistanceSettings>('/api/settings/click-distance/');
  }

  getFeedbackRerankSettings(): Observable<FeedbackRerankSettings> {
    return this.http.get<FeedbackRerankSettings>('/api/settings/explore-exploit/');
  }

  getClusteringSettings(): Observable<ClusteringSettings> {
    return this.http.get<ClusteringSettings>('/api/settings/clustering/');
  }

  getSlateDiversitySettings(): Observable<SlateDiversitySettings> {
    return this.http.get<SlateDiversitySettings>('/api/settings/slate-diversity/');
  }

  getGraphCandidateSettings(): Observable<GraphCandidateSettings> {
    return this.http.get<GraphCandidateSettings>('/api/settings/graph-candidate/');
  }

  getValueModelSettings(): Observable<ValueModelSettings> {
    return this.http.get<ValueModelSettings>('/api/settings/value-model/');
  }

  updateWeightedAuthoritySettings(payload: WeightedAuthoritySettings): Observable<WeightedAuthoritySettings> {
    return this.http.put<WeightedAuthoritySettings>('/api/settings/weighted-authority/', payload);
  }

  recalculateWeightedAuthority(): Observable<{ job_id: string }> {
    return this.http.post<{ job_id: string }>('/api/settings/weighted-authority/recalculate/', {});
  }

  updateLinkFreshnessSettings(payload: LinkFreshnessSettings): Observable<LinkFreshnessSettings> {
    return this.http.put<LinkFreshnessSettings>('/api/settings/link-freshness/', payload);
  }

  updatePhraseMatchingSettings(payload: PhraseMatchingSettings): Observable<PhraseMatchingSettings> {
    return this.http.put<PhraseMatchingSettings>('/api/settings/phrase-matching/', payload);
  }

  updateLearnedAnchorSettings(payload: LearnedAnchorSettings): Observable<LearnedAnchorSettings> {
    return this.http.put<LearnedAnchorSettings>('/api/settings/learned-anchor/', payload);
  }

  updateRareTermPropagationSettings(payload: RareTermPropagationSettings): Observable<RareTermPropagationSettings> {
    return this.http.put<RareTermPropagationSettings>('/api/settings/rare-term-propagation/', payload);
  }

  updateFieldAwareRelevanceSettings(payload: FieldAwareRelevanceSettings): Observable<FieldAwareRelevanceSettings> {
    return this.http.put<FieldAwareRelevanceSettings>('/api/settings/field-aware-relevance/', payload);
  }

  updateGSCSettings(payload: GSCSettingsUpdate): Observable<GSCSettings> {
    return this.http.put<GSCSettings>('/api/analytics/settings/gsc/', payload);
  }

  testGSCConnection(payload: { property_url?: string; client_email?: string; private_key?: string }): Observable<AnalyticsConnectionResult> {
    return this.http.post<AnalyticsConnectionResult>('/api/analytics/settings/gsc/test-connection/', payload);
  }

  runGSCSync(payload?: { lookback_days?: number }): Observable<any> {
    return this.http.post(`${this.baseUrl}/analytics/telemetry/gsc-sync/`, payload ?? {});
  }

  getGoogleAuthUrl(): Observable<{ authorization_url: string }> {
    return this.http.get<{ authorization_url: string }>(`${this.baseUrl}/analytics/oauth/authorize/`);
  }

  updateGoogleOAuthSettings(payload: { client_id: string; client_secret?: string }): Observable<GoogleOAuthSettings> {
    return this.http.put<GoogleOAuthSettings>('/api/analytics/settings/google-oauth/', payload);
  }

  unlinkGoogleAccount(): Observable<any> {
    return this.http.post(`${this.baseUrl}/analytics/oauth/unlink/`, {});
  }

  updateGA4TelemetrySettings(payload: GA4TelemetryUpdate): Observable<GA4TelemetrySettings> {
    return this.http.put<GA4TelemetrySettings>('/api/analytics/settings/ga4/', payload);
  }

  testGA4TelemetryConnection(payload: { measurement_id?: string; api_secret?: string; google_oauth_client_id?: string; google_oauth_client_secret?: string }): Observable<AnalyticsConnectionResult> {
    return this.http.post<AnalyticsConnectionResult>('/api/analytics/settings/ga4/test-connection/', payload);
  }

  testGA4TelemetryReadConnection(payload: { property_id?: string; read_project_id?: string; read_client_email?: string; read_private_key?: string }): Observable<AnalyticsConnectionResult> {
    return this.http.post<AnalyticsConnectionResult>('/api/analytics/settings/ga4/test-read-connection/', payload);
  }

  updateMatomoTelemetrySettings(payload: MatomoTelemetryUpdate): Observable<MatomoTelemetrySettings> {
    return this.http.put<MatomoTelemetrySettings>('/api/analytics/settings/matomo/', payload);
  }

  testMatomoTelemetryConnection(payload: { url?: string; site_id_xenforo?: string; token_auth?: string }): Observable<AnalyticsConnectionResult> {
    return this.http.post<AnalyticsConnectionResult>('/api/analytics/settings/matomo/test-connection/', payload);
  }

  testXenForoConnection(payload: { base_url?: string; api_key?: string }): Observable<AnalyticsConnectionResult> {
    return this.http.post<AnalyticsConnectionResult>('/api/settings/xenforo/test-connection/', payload);
  }

  testWordPressConnection(payload: { base_url?: string; username?: string; app_password?: string }): Observable<AnalyticsConnectionResult> {
    return this.http.post<AnalyticsConnectionResult>('/api/settings/wordpress/test-connection/', payload);
  }

  testWebhookEndpoints(): Observable<AnalyticsConnectionResult> {
    return this.http.post<AnalyticsConnectionResult>('/api/settings/webhooks/test/', {});
  }

  getWebhookSettings(): Observable<WebhookSettings> {
    return this.http.get<WebhookSettings>('/api/settings/webhooks/');
  }

  updateWebhookSettings(payload: WebhookSettingsUpdate): Observable<WebhookSettings> {
    return this.http.put<WebhookSettings>('/api/settings/webhooks/', payload);
  }

  updateClickDistanceSettings(payload: ClickDistanceSettings): Observable<ClickDistanceSettings> {
    return this.http.put<ClickDistanceSettings>('/api/settings/click-distance/', payload);
  }

  updateFeedbackRerankSettings(payload: FeedbackRerankSettings): Observable<FeedbackRerankSettings> {
    return this.http.put<FeedbackRerankSettings>('/api/settings/explore-exploit/', payload);
  }

  updateClusteringSettings(payload: ClusteringSettings): Observable<ClusteringSettings> {
    return this.http.put<ClusteringSettings>('/api/settings/clustering/', payload);
  }

  updateSlateDiversitySettings(payload: SlateDiversitySettings): Observable<SlateDiversitySettings> {
    return this.http.put<SlateDiversitySettings>('/api/settings/slate-diversity/', payload);
  }

  updateGraphCandidateSettings(payload: GraphCandidateSettings): Observable<GraphCandidateSettings> {
    return this.http.put<GraphCandidateSettings>('/api/settings/graph-candidate/', payload);
  }

  updateValueModelSettings(payload: ValueModelSettings): Observable<ValueModelSettings> {
    return this.http.put<ValueModelSettings>('/api/settings/value-model/', payload);
  }

  getSpamGuardSettings(): Observable<SpamGuardSettings> {
    return this.http.get<SpamGuardSettings>('/api/settings/spam-guards/');
  }

  updateSpamGuardSettings(payload: SpamGuardSettings): Observable<SpamGuardSettings> {
    return this.http.put<SpamGuardSettings>('/api/settings/spam-guards/', payload);
  }

  getAnchorDiversitySettings(): Observable<AnchorDiversitySettings> {
    return this.http.get<AnchorDiversitySettings>('/api/settings/anchor-diversity/');
  }

  updateAnchorDiversitySettings(payload: AnchorDiversitySettings): Observable<AnchorDiversitySettings> {
    return this.http.put<AnchorDiversitySettings>('/api/settings/anchor-diversity/', payload);
  }

  getKeywordStuffingSettings(): Observable<KeywordStuffingSettings> {
    return this.http.get<KeywordStuffingSettings>('/api/settings/keyword-stuffing/');
  }

  updateKeywordStuffingSettings(payload: KeywordStuffingSettings): Observable<KeywordStuffingSettings> {
    return this.http.put<KeywordStuffingSettings>('/api/settings/keyword-stuffing/', payload);
  }

  getLinkFarmSettings(): Observable<LinkFarmSettings> {
    return this.http.get<LinkFarmSettings>('/api/settings/link-farm/');
  }

  updateLinkFarmSettings(payload: LinkFarmSettings): Observable<LinkFarmSettings> {
    return this.http.put<LinkFarmSettings>('/api/settings/link-farm/', payload);
  }

  getRuntimeSummary(): Observable<RuntimeSummaryPayload> {
    return this.http.get<RuntimeSummaryPayload>('/api/settings/runtime/summary/');
  }

  getRuntimeModels(): Observable<RuntimeModelSummary> {
    return this.http.get<RuntimeModelSummary>('/api/settings/runtime/models/');
  }

  registerRuntimeModel(payload: RuntimeModelRegistrationPayload): Observable<RuntimeModelSummary> {
    return this.http.post<RuntimeModelSummary>('/api/settings/runtime/models/', payload);
  }

  runRuntimeModelAction(id: number, payload: RuntimeModelActionPayload): Observable<Record<string, unknown>> {
    return this.http.post<Record<string, unknown>>(`/api/settings/runtime/models/${id}/action/`, payload);
  }

  deleteRuntimePlacement(id: number): Observable<{ deleted?: boolean; reclaimed_disk_bytes?: number }> {
    return this.http.delete<{ deleted?: boolean; reclaimed_disk_bytes?: number }>(`/api/settings/runtime/models/placements/${id}/`);
  }

  listHelpers(): Observable<HelperNodeSettingsRecord[]> {
    return this.http.get<HelperNodeSettingsRecord[] | { results: HelperNodeSettingsRecord[] }>('/api/settings/helpers/')
      .pipe(
        map((r) => Array.isArray(r) ? r : r.results ?? []),
        catchError(() => of([]))
      );
  }

  createHelper(payload: HelperNodeCreatePayload): Observable<{ id: number; name: string }> {
    return this.http.post<{ id: number; name: string }>('/api/settings/helpers/', payload);
  }

  updateHelper(id: number, payload: Partial<HelperNodeSettingsRecord>): Observable<HelperNodeSettingsRecord> {
    return this.http.patch<HelperNodeSettingsRecord>(`/api/settings/helpers/${id}/`, payload);
  }

  deleteHelper(id: number): Observable<void> {
    return this.http.delete<void>(`/api/settings/helpers/${id}/`);
  }

  recalculateClickDistance(): Observable<{ job_id: string }> {
    return this.http.post<{ job_id: string }>('/api/settings/click-distance/recalculate/', {});
  }

  recalculateLinkFreshness(): Observable<{ job_id: string }> {
    return this.http.post<{ job_id: string }>('/api/settings/link-freshness/recalculate/', {});
  }

  recalculateClustering(): Observable<{ job_id: string }> {
    return this.http.post<{ job_id: string }>('/api/settings/clustering/recalculate/', {});
  }

  rebuildKnowledgeGraph(): Observable<{ job_id: string }> {
    return this.http.post<{ job_id: string }>('/api/settings/graph/rebuild/', {});
  }

  updateWordPressSettings(payload: WordPressSettingsUpdate): Observable<WordPressSettings> {
    return this.http.put<WordPressSettings>('/api/settings/wordpress/', payload);
  }

  runWordPressSync(): Observable<SyncRunResponse> {
    return this.http.post<SyncRunResponse>('/api/sync/wordpress/run/', {});
  }

  // ── Weight presets ────────────────────────────────────────────────

  listWeightPresets(): Observable<WeightPreset[]> {
    return this.http.get<{ results: WeightPreset[] }>('/api/weight-presets/')
      .pipe(
        map((r) => r.results ?? []),
        catchError(() => of([]))
      );
  }

  createWeightPreset(payload: { name: string; weights: Record<string, string> }): Observable<WeightPreset> {
    return this.http.post<WeightPreset>('/api/weight-presets/', payload);
  }

  renameWeightPreset(id: number, name: string): Observable<WeightPreset> {
    return this.http.patch<WeightPreset>(`/api/weight-presets/${id}/`, { name });
  }

  deleteWeightPreset(id: number): Observable<void> {
    return this.http.delete<void>(`/api/weight-presets/${id}/`);
  }

  applyWeightPreset(id: number): Observable<{ detail: string }> {
    return this.http.post<{ detail: string }>(`/api/weight-presets/${id}/apply/`, {});
  }

  getCurrentWeights(): Observable<Record<string, string>> {
    return this.http.get<Record<string, string>>('/api/weight-presets/current/');
  }

  triggerWeightTune(): Observable<{ detail: string; task_id: string }> {
    return this.http.post<{ detail: string; task_id: string }>('/api/settings/weight-tune/trigger/', {});
  }

  listChallengers(): Observable<RankingChallenger[]> {
    return this.http.get<RankingChallenger[] | { results: RankingChallenger[] }>('/api/weight-challengers/')
      .pipe(
        map((r) => Array.isArray(r) ? r : r.results ?? []),
        catchError(() => of([]))
      );
  }

  evaluateChallenger(runId: string): Observable<{ detail: string; task_id: string }> {
    return this.http.post<{ detail: string; task_id: string }>(`/api/settings/weight-tune/evaluate/${runId}/`, {});
  }

  rejectChallenger(id: number): Observable<{ detail: string }> {
    return this.http.post<{ detail: string }>(`/api/weight-challengers/${id}/reject/`, {});
  }

  // ── Weight adjustment history ─────────────────────────────────────

  listWeightHistory(): Observable<WeightAdjustmentHistory[]> {
    return this.http.get<WeightAdjustmentHistory[] | { results: WeightAdjustmentHistory[] }>('/api/weight-history/')
      .pipe(
        map((r) => Array.isArray(r) ? r : r.results ?? []),
        catchError(() => of([]))
      );
  }

  rollbackWeights(id: number): Observable<{ detail: string }> {
    return this.http.post<{ detail: string }>(`/api/weight-history/${id}/rollback/`, {});
  }
}
