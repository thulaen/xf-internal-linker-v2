import { CommonModule, DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, ChangeDetectorRef, Component, OnInit, OnDestroy, HostListener, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MonoTypeOperatorFunction, forkJoin, finalize, Subject, takeUntil } from 'rxjs';
import { debounceTime } from 'rxjs/operators';
import { RealtimeService } from '../core/services/realtime.service';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatChipsModule } from '@angular/material/chips';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatDividerModule } from '@angular/material/divider';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ActivatedRoute } from '@angular/router';
import { HasUnsavedChanges } from '../core/guards/unsaved-changes.guard';
import { DesktopNotificationService } from '../core/services/desktop-notification.service';
import {
  NotificationPreferences,
  NotificationService,
} from '../core/services/notification.service';
import { AudioCueService } from '../core/services/audio-cue.service';
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
  XenForoSettingsUpdate,
  WordPressSettings,
  WordPressSettingsUpdate,
  GSCSettings,
  GSCSettingsUpdate,
  FeedbackRerankSettings,
  ClusteringSettings,
  SlateDiversitySettings,
  WeightPreset,
  WeightAdjustmentHistory,
  RankingChallenger,
  AnalyticsConnectionResult,
  GA4TelemetrySettings,
  GA4TelemetryUpdate,
  GoogleOAuthSettings,
  MatomoTelemetrySettings,
  MatomoTelemetryUpdate,
  GraphCandidateSettings,
  ValueModelSettings,
  SpamGuardSettings,
  WebhookSettings,
  WebhookSettingsUpdate,
} from './silo-settings.service';
import { WeightDiagnosticsCardComponent } from './weight-diagnostics-card/weight-diagnostics-card.component';
import { PerformanceSettingsComponent } from './performance-settings/performance-settings.component';
import { HelpersSettingsComponent } from './helpers-settings/helpers-settings.component';
// Phase MS — Meta Algorithm Settings tab (new at the end of the tab group).
import { MetaAlgorithmsTabComponent } from './meta-algorithms-tab/meta-algorithms-tab.component';

interface SettingTooltip {
  definition: string;
  impact: string;
  default: string;
  example: string;
  range: string;
}

type FieldSeverity = 'none' | 'warn' | 'danger';

const SETTING_TOOLTIPS: Record<string, SettingTooltip> = {
  // March 2026 PageRank
  'weightedAuthority.ranking_weight': {
    definition: 'How much the PageRank authority score contributes to the final link ranking.',
    impact: 'Higher values make authority the dominant factor. Links will strongly prefer high-authority destinations.',
    default: '0.10',
    example: 'Raising to 0.18 makes authority much stronger. Setting to 0 turns this off entirely.',
    range: '0 to 0.25',
  },
  'weightedAuthority.position_bias': {
    definition: 'Favours link placements that appear earlier on a page.',
    impact: 'Higher values prefer destinations already linked near the top of content. Lower values treat all positions equally.',
    default: '0.5',
    example: 'Raising to 0.9 makes early-position links dominant. Lowering to 0.1 almost ignores position.',
    range: '0 to 1',
  },
  'weightedAuthority.empty_anchor_factor': {
    definition: 'A penalty multiplier for links that have no anchor text at all.',
    impact: 'Lower values penalise empty anchors more. Higher values treat them almost like normal links.',
    default: '0.6',
    example: 'Raising to 0.9 nearly ignores missing anchors. Lowering to 0.1 strongly demotes them.',
    range: '0.1 to 1',
  },
  'weightedAuthority.bare_url_factor': {
    definition: 'A penalty multiplier for links that are raw URLs with no surrounding text.',
    impact: 'Lower values demote bare URLs more heavily in the ranking.',
    default: '0.35',
    example: 'Raising to 0.8 treats bare URLs close to normal links. Lowering to 0.1 nearly hides them.',
    range: '0.1 to 1',
  },
  'weightedAuthority.weak_context_factor': {
    definition: 'A penalty multiplier for links found in low-quality zones such as sidebars or footers.',
    impact: 'Lower values discount weak-context links more. Higher values give them nearly full credit.',
    default: '0.75',
    example: 'Raising to 0.95 treats sidebar links equally. Lowering to 0.2 strongly discounts them.',
    range: '0.1 to 1',
  },
  'weightedAuthority.isolated_context_factor': {
    definition: 'A penalty multiplier for links on pages with very few other links, which may indicate thin content.',
    impact: 'Lower values discount links from isolated, thin pages. Higher values give them full credit.',
    default: '0.45',
    example: 'Raising to 0.9 gives isolated pages full credit. Lowering to 0.1 nearly ignores them.',
    range: '0.1 to 1',
  },
  'tabs.diagnostics': {
    definition: 'Diagnostic view of all 23 algorithm signals and scoring components.',
    impact: 'Provides transparency into why certain links are suggested and allows monitoring of C++ acceleration and storage health.',
    default: 'N/A',
    example: 'Check this tab if you suspect a specific signal (e.g. Semantic Similarity) is misconfigured or underperforming.',
    range: 'N/A',
  },
  // Link Freshness
  'linkFreshness.ranking_weight': {
    definition: 'How much the freshness score influences the final ranking.',
    impact: 'Higher values reward destinations that are actively gaining new inbound links.',
    default: '0.05',
    example: '0.05 gives a gentle freshness boost. Raising to 0.15 makes freshness a strong signal.',
    range: '0 to 0.15',
  },
  'linkFreshness.recent_window_days': {
    definition: 'The number of days that counts as "recent" when measuring inbound link growth.',
    impact: 'A wider window smooths out short-term spikes. A narrower window reacts faster to recent changes.',
    default: '30',
    example: 'Raising to 60 gives a calmer, longer view of trends. Lowering to 7 focuses on very recent activity only.',
    range: '7 to 90',
  },
  'linkFreshness.newest_peer_percent': {
    definition: 'The top fraction of newest links used to define the "fresh" peer group for comparison.',
    impact: 'A higher value compares against a larger group. A lower value focuses on only the very newest peers.',
    default: '0.25',
    example: 'Raising to 0.5 broadens the comparison group. Lowering to 0.1 uses only the freshest links.',
    range: '0.1 to 0.5',
  },
  'linkFreshness.min_peer_count': {
    definition: 'Minimum number of inbound links a destination needs before its freshness score is calculated.',
    impact: 'Pages below this threshold receive a neutral score. Higher values keep uncertain pages neutral for longer.',
    default: '3',
    example: 'Raising to 10 requires more data before scoring. Lowering to 1 scores nearly everything.',
    range: '1 to 20',
  },
  'linkFreshness.w_recent': {
    definition: 'Weight given to whether the destination recently gained new inbound links.',
    impact: 'Higher values make recent link acquisition the biggest freshness driver.',
    default: '0.35',
    example: 'Raising to 0.7 makes recent gains dominate. Lowering to 0.1 reduces their influence.',
    range: '0 to 1',
  },
  'linkFreshness.w_growth': {
    definition: 'Weight given to the rate at which inbound links are growing over time.',
    impact: 'Higher values favour destinations with accelerating link acquisition.',
    default: '0.35',
    example: 'Raising to 0.6 rewards fast-growing destinations more. Lowering to 0.1 de-emphasises growth rate.',
    range: '0 to 1',
  },
  'linkFreshness.w_cohort': {
    definition: 'Weight given to how a destination compares against similar pages that gained links at the same time.',
    impact: 'Higher values reward destinations outperforming their cohort peers.',
    default: '0.2',
    example: 'Raising to 0.5 makes cohort comparison a major factor. Lowering reduces its influence.',
    range: '0 to 1',
  },
  'linkFreshness.w_loss': {
    definition: 'Weight given to whether the destination is losing inbound links.',
    impact: 'Higher values penalise destinations that are shedding links.',
    default: '0.1',
    example: 'Raising to 0.4 strongly penalises link loss. Lowering to 0 ignores link loss entirely.',
    range: '0 to 1',
  },
  // Phrase Matching
  'phraseMatching.ranking_weight': {
    definition: 'How much the phrase match score influences the final ranking.',
    impact: 'Higher values reward destinations whose title or text closely matches the linking phrase.',
    default: '0.08',
    example: '0.08 gives phrase matching a clear voice. Raising to 0.1 makes it even stronger.',
    range: '0 to 0.1',
  },
  'phraseMatching.enable_anchor_expansion': {
    definition: 'Generates candidate anchor phrases from the destination title and distilled text.',
    impact: 'Enabled broadens what can trigger a match. Disabled limits matching to the original anchor only.',
    default: 'Enabled',
    example: 'Disabling is useful if expansion is producing too many false-positive link suggestions.',
    range: 'Enabled / Disabled',
  },
  'phraseMatching.enable_partial_matching': {
    definition: 'Allows a link to match even if only part of the phrase is found in the destination.',
    impact: 'Enabled finds more links but may include weaker matches. Disabled requires exact phrase alignment.',
    default: 'Enabled',
    example: 'Disabling tightens phrase matching, reducing suggestions but improving precision.',
    range: 'Enabled / Disabled',
  },
  'phraseMatching.context_window_tokens': {
    definition: 'The number of words around a potential link considered when scoring a phrase match.',
    impact: 'Larger windows capture more surrounding context. Smaller windows focus on immediate words only.',
    default: '8',
    example: 'Raising to 12 captures more context. Lowering to 4 focuses only on the nearby words.',
    range: '4 to 12',
  },
  // Learned Anchors
  'learnedAnchor.ranking_weight': {
    definition: 'How much the learned anchor score influences the final ranking.',
    impact: 'Higher values reward destinations that already have real-world anchor text pointing to them.',
    default: '0.05',
    example: '0.05 gives a gentle boost. Raising above 0.08 may over-fit to past link patterns.',
    range: '0 to 0.1',
  },
  'learnedAnchor.minimum_anchor_sources': {
    definition: 'The minimum number of different source pages that must use the same anchor before it is trusted.',
    impact: 'Higher values require more evidence before a pattern is learned, reducing noise.',
    default: '2',
    example: 'Raising to 5 demands strong multi-page consensus. Lowering to 1 learns from a single page.',
    range: '1 to 10',
  },
  'learnedAnchor.minimum_family_support_share': {
    definition: 'The fraction of a destination\'s related pages that must also use the anchor before it counts.',
    impact: 'Higher values require broader support across the content family, improving pattern quality.',
    default: '0.15',
    example: 'Raising to 0.3 requires wider agreement. Lowering to 0.05 accepts very narrow support.',
    range: '0.05 to 0.5',
  },
  'learnedAnchor.enable_noise_filter': {
    definition: 'Removes anchors that appear too frequently across the site and carry little meaning (e.g. "click here").',
    impact: 'Enabled keeps learned patterns meaningful. Disabled may introduce noisy, low-quality anchors.',
    default: 'Enabled',
    example: 'Disabling is rarely useful - only consider it if you need to debug which anchors are being filtered.',
    range: 'Enabled / Disabled',
  },
  // Rare-Term Propagation
  'rareTermPropagation.enabled': {
    definition: 'Turns on the ability to borrow rare keywords from nearby related pages to help thin-content destinations.',
    impact: 'Enabled helps pages with little text become discoverable via shared rare terms. Disabled turns this off entirely.',
    default: 'Enabled',
    example: 'Disabling is useful if propagated terms are causing unrelated pages to surface for the same query.',
    range: 'Enabled / Disabled',
  },
  'rareTermPropagation.ranking_weight': {
    definition: 'How much the rare-term propagation signal influences the final ranking.',
    impact: 'Higher values give more credit to thin pages that borrowed rare terms from neighbours.',
    default: '0.05',
    example: '0.05 gently helps thin pages. Raising above 0.08 may over-reward borrowed terms.',
    range: '0 to 0.1',
  },
  'rareTermPropagation.max_document_frequency': {
    definition: 'A word must appear in no more than this many documents to be considered rare and worth propagating.',
    impact: 'Higher values allow more common words to be shared. Lower values restrict sharing to very rare terms only.',
    default: '3',
    example: 'Raising to 8 lets moderately common words propagate. Lowering to 1 shares only extremely rare terms.',
    range: '1 to 10',
  },
  'rareTermPropagation.minimum_supporting_related_pages': {
    definition: 'At least this many related pages must all contain the rare term before it is borrowed.',
    impact: 'Higher values require stronger consensus, reducing the chance of borrowing irrelevant terms.',
    default: '2',
    example: 'Raising to 4 demands broader agreement. Lowering to 1 borrows from any single related page.',
    range: '1 to 5',
  },
  // Field-Aware Relevance
  'fieldAwareRelevance.ranking_weight': {
    definition: 'How much the field-aware relevance score influences the final ranking.',
    impact: 'Higher values reward destinations whose title, body, or anchor text aligns with the source sentence.',
    default: '0.10',
    example: '0.10 gives a meaningful relevance boost. Raising above 0.12 may dominate other signals.',
    range: '0 to 0.15',
  },
  'fieldAwareRelevance.title_field_weight': {
    definition: 'How much the destination title contributes to the relevance score relative to other fields.',
    impact: 'Higher values make title matches the most important relevance signal.',
    default: '0.4',
    example: 'Raising to 0.7 prioritises title matching heavily. Lowering to 0.1 makes titles nearly irrelevant.',
    range: '0 to 1',
  },
  'fieldAwareRelevance.body_field_weight': {
    definition: 'How much the destination body text contributes to the relevance score.',
    impact: 'Higher values reward destinations whose body text closely matches the source sentence.',
    default: '0.3',
    example: 'Raising to 0.6 makes body text the primary signal. Lowering to 0.1 reduces its importance.',
    range: '0 to 1',
  },
  'fieldAwareRelevance.scope_field_weight': {
    definition: 'How much the destination scope or category label contributes to the relevance score.',
    impact: 'Higher values reward destinations in the same topical scope as the source.',
    default: '0.15',
    example: 'Raising to 0.4 makes scope alignment a strong signal. Lowering to 0 ignores scope entirely.',
    range: '0 to 1',
  },
  'fieldAwareRelevance.learned_anchor_field_weight': {
    definition: 'How much learned anchor text contributes to the relevance score.',
    impact: 'Higher values reward destinations that have anchor patterns matching the source sentence.',
    default: '0.15',
    example: 'Raising to 0.4 gives strong weight to existing anchor patterns. Lowering reduces this influence.',
    range: '0 to 1',
  },
  // FR-021 — Graph Candidate Generation (Pixie Walk)
  'graphCandidate.enabled': {
    definition: 'Turns on graph-based candidate generation using bipartite random walks (Pixie).',
    impact: 'Enabled finds structural link candidates that semantic embedding searches might miss. Disabled relies purely on vector and keyword search.',
    default: 'Enabled',
    example: 'Keep enabled if you want to discover "people also linked" and structural relationship candidates.',
    range: 'Enabled / Disabled',
  },
  'graphCandidate.walk_steps_per_entity': {
    definition: 'Number of random walk steps to perform for each entity extracted from the source page.',
    impact: 'Higher values explore the graph more deeply but take longer. Lower values are faster but may miss distant relatives.',
    default: '2000',
    example: '2000 steps provides a good balance of depth and speed. Raise to 5000 for extremely thorough discovery.',
    range: '500 to 10000',
  },
  'graphCandidate.min_stable_candidates': {
    definition: 'Minimum number of candidates that must reach the visit threshold before stopping the walk early.',
    impact: 'Higher values ensure a more diverse set of candidates. Lower values stop faster once a few strong ones are found.',
    default: '50',
    example: '50 ensures we find enough high-confidence candidates before giving up.',
    range: '10 to 500',
  },
  'graphCandidate.min_visit_threshold': {
    definition: 'Number of visits required for a node to be considered stable during the walk.',
    impact: 'Higher values improve precision but may miss candidates in sparse graph areas. Lower values are more inclusive.',
    default: '4',
    example: 'Keep at 4 for a good mix. Raise to 8 if you find the candidates are too noisy.',
    range: '1 to 20',
  },
  'graphCandidate.top_k_candidates': {
    definition: 'Max number of top-visited candidates to return for full ranking.',
    impact: 'Higher values give the ranker more options but increase pipeline latency.',
    default: '100',
    example: '100 is usually plenty. Lower to 50 if the pipeline feels slow.',
    range: '10 to 1000',
  },
  'graphCandidate.top_n_entities_per_article': {
    definition: 'Max number of entities to extract from an article to use as seeds for the graph walk.',
    impact: 'Higher values capture more topics but increase walk time per page.',
    default: '15',
    example: '15 extracts the most salient entities. Raise to 30 for long-form content.',
    range: '5 to 100',
  },
  // FR-021 — Value Model (Instagram-style pre-scoring)
  'valueModel.enabled': {
    definition: 'Turns on the value model, which predicts the long-term engagement value of a potential link before full ranking.',
    impact: 'Enabled uses traffic, freshness, and authority signals to prune weak candidates early. Disabled skips pre-scoring.',
    default: 'Enabled',
    example: 'Keep enabled to ensure high-value destination content is prioritised in the final suggestions.',
    range: 'Enabled / Disabled',
  },
  'valueModel.w_relevance': {
    definition: 'Weight given to semantic relevance in the value prediction.',
    impact: 'Higher values prioritise candidates that look topically correct even if they have low traffic.',
    default: '0.35',
    example: '0.35 keeps relevance as the strongest single value signal.',
    range: '0 to 1.0',
  },
  'valueModel.w_traffic': {
    definition: 'Weight given to historical traffic in the value prediction.',
    impact: 'Higher values prioritise destinations that are already proven to be popular with users.',
    default: '0.25',
    example: '0.25 makes traffic the second strongest value driver.',
    range: '0 to 1.0',
  },
  'valueModel.w_freshness': {
    definition: 'Weight given to content freshness in the value prediction.',
    impact: 'Higher values prioritise newly updated content.',
    default: '0.1',
    example: '0.1 gives a light boost to fresh content in the early prune stage.',
    range: '0 to 1.0',
  },
  'valueModel.w_authority': {
    definition: 'Weight given to PageRank authority in the value prediction.',
    impact: 'Higher values prioritise established, high-authority pages.',
    default: '0.1',
    example: '0.1 ensures authority contributes without dominating the value filter.',
    range: '0 to 1.0',
  },
  'valueModel.w_penalty': {
    definition: 'Weight given to blocklist/penalty signals in the value prediction.',
    impact: 'Higher values more aggressively suppress penalised content early.',
    default: '0.5',
    example: 'Internal blocklists use this weight to sink undesirable suggestions.',
    range: '0 to 1.0',
  },
  'valueModel.traffic_lookback_days': {
    definition: 'Number of days of traffic history to consider for the value model.',
    impact: 'Longer windows are more stable. Shorter windows react faster to viral content.',
    default: '90',
    example: '90 days provides a solid statistical baseline.',
    range: '7 to 365',
  },
  'valueModel.traffic_fallback_value': {
    definition: 'Default traffic score for pages with no historical traffic data.',
    impact: 'Higher values give new content a "benefit of the doubt" during pruning.',
    default: '0.5',
    example: '0.5 is neutral — neither boosts nor penalises untracked pages.',
    range: '0 to 1',
  },
  // FR-024 engagement signal
  'valueModel.engagement_signal_enabled': {
    definition: 'Whether read-through rate is used to score link destinations.',
    impact: 'Pages that hold reader attention rank higher as link destinations.',
    default: 'true',
    example: 'Disable if you have no GA4 engagement data yet.',
    range: 'on / off',
  },
  'valueModel.w_engagement': {
    definition: 'How much read-through rate contributes to the value model score.',
    impact: 'Higher values favour pages with long average session times.',
    default: '0.08',
    example: 'Raise to 0.15 after you have 90 days of GA4 data.',
    range: '0 to 0.5',
  },
  'valueModel.engagement_lookback_days': {
    definition: 'How many days of GA4 data to average for engagement metrics.',
    impact: 'Longer windows are more stable; shorter windows react faster to changes.',
    default: '30',
    example: '7 for fast-moving content, 90 for evergreen articles.',
    range: '1 to 365',
  },
  'valueModel.engagement_words_per_minute': {
    definition: 'Reading speed used to estimate how long each article takes to read.',
    impact: 'Affects estimated read time, which divides into GA4 average engagement time.',
    default: '200',
    example: 'Lower for dense technical content, keep 200 for general posts.',
    range: '50 to 600',
  },
  'valueModel.engagement_cap_ratio': {
    definition: 'Raw read-through rates above this are capped before normalization.',
    impact: 'Prevents a handful of extreme outliers from collapsing all other scores to near-zero.',
    default: '1.5',
    example: 'Pages with very long dwell times (tabbed, re-reading) are capped here.',
    range: '1.0 to 5.0',
  },
  'valueModel.engagement_fallback_value': {
    definition: 'Score assigned to pages with no GA4 engagement data.',
    impact: 'New pages without analytics history receive this neutral value.',
    default: '0.5',
    example: '0.5 is neutral — it neither boosts nor penalises untracked pages.',
    range: '0 to 1',
  },
  // FR-023 hot decay signal
  'valueModel.hot_decay_enabled': {
    definition: 'Whether Reddit Hot decay replaces flat traffic averaging in the value model.',
    impact: 'When enabled, recent traffic momentum counts for more and old traffic fades over time.',
    default: 'true',
    example: 'Disable to fall back to original flat 90-day average.',
    range: 'on / off',
  },
  'valueModel.hot_gravity': {
    definition: 'Time-decay gravity factor in the Reddit Hot formula. Higher values penalise older traffic more.',
    impact: 'At 0.05, a page loses about one log-unit of hot score every 20 days.',
    default: '0.05',
    example: 'Raise to 0.08 for fast-moving sites where yesterday matters far more than last month.',
    range: '0.001 to 0.5',
  },
  'valueModel.hot_clicks_weight': {
    definition: 'Multiplier applied to click volume before feeding into the hot score formula.',
    impact: 'Higher values make clicks count more than impressions in the momentum calculation.',
    default: '1.0',
    example: 'Keep at 1.0 unless you want to deliberately downweight clicks vs impressions.',
    range: '0 to 5.0',
  },
  'valueModel.hot_impressions_weight': {
    definition: 'Multiplier applied to impression volume before feeding into the hot score formula.',
    impact: 'Impressions are much noisier than clicks, so the default is deliberately low.',
    default: '0.05',
    example: 'Raise to 0.2 if your pages have low CTR but high visibility matters.',
    range: '0 to 5.0',
  },
  'valueModel.hot_lookback_days': {
    definition: 'Number of days of daily SearchMetric rows to feed into the hot score calculation.',
    impact: 'Longer windows capture slow-burn trends; shorter windows react faster to momentum shifts.',
    default: '90',
    example: '30 for a news-heavy site, 90 for evergreen content.',
    range: '7 to 365',
  },
  // FR-025 co-occurrence signal
  'valueModel.co_occurrence_signal_enabled': {
    definition: 'Whether session co-occurrence data is used to boost link candidates.',
    impact: 'Pages frequently read together in the same GA4 session are ranked higher as link pairs.',
    default: 'true',
    example: 'Disable if you have no GA4 session data yet.',
    range: 'on / off',
  },
  'valueModel.w_cooccurrence': {
    definition: 'How much session co-occurrence contributes to the value model score.',
    impact: 'Higher values give more weight to reader-navigation patterns over text similarity.',
    default: '0.12',
    example: 'Raise to 0.20 once you have 90+ days of session data.',
    range: '0 to 1.0',
  },
  'valueModel.co_occurrence_fallback_value': {
    definition: 'Score assigned to pairs with no co-occurrence data.',
    impact: 'New or unpopular article pairs with no session history receive this neutral value.',
    default: '0.5',
    example: '0.5 is neutral — use lower to actively penalise unknown pairs.',
    range: '0 to 1',
  },
  'valueModel.co_occurrence_min_co_sessions': {
    definition: 'Minimum number of shared sessions for a co-occurrence pair to count.',
    impact: 'Lower values include noisier pairs; higher values require stronger evidence.',
    default: '5',
    example: 'Raise to 10 on high-traffic sites to filter coincidental co-reads.',
    range: '1 to 100',
  },
  // Click Distance
  'ga4Gsc.ranking_weight': {
    definition: 'How much first-party search and behavior data influences the final ranking.',
    impact: 'Higher values reward destinations that already earn stronger search clicks and better on-site engagement.',
    default: '0.05',
    example: 'Start at 0.05 so analytics acts like a light tie-breaker instead of overruling relevance.',
    range: '0 to 0.3',
  },
  'ga4Gsc.property_url': {
    definition: 'The Google Search Console property URL for your site.',
    impact: 'Required to fetch search performance data for your pages.',
    default: 'https://example.com/ or sc-domain:example.com',
    example: 'Use the exact property URL from the GSC dashboard.',
    range: 'Full URL or sc-domain: prefix',
  },
  'ga4Gsc.client_email': {
    definition: 'The client email from your Google Cloud service account JSON.',
    impact: 'Used to authenticate the app with the Google Search Console API.',
    default: 'service-account@project.iam.gserviceaccount.com',
    example: 'Copy from the "client_email" field of your JSON key.',
    range: 'A valid email address',
  },
  'ga4Gsc.private_key': {
    definition: 'The private key from your Google Cloud service account JSON.',
    impact: 'Used to securely sign API requests to Google.',
    default: '-----BEGIN PRIVATE KEY----- ...',
    example: 'Paste the entire key including the BEGIN and END markers.',
    range: 'A valid RSA private key string',
  },
  'ga4Gsc.sync_enabled': {
    definition: 'Turns the automatic GSC search performance sync on or off.',
    impact: 'When on, the app pulls daily clicks and impressions for your content.',
    default: 'Off',
    example: 'Recommended to keep this on for accurate search attribution.',
    range: 'Enabled / Disabled',
  },
  'ga4Gsc.sync_lookback_days': {
    definition: 'How many days of history to reread during each GSC sync.',
    impact: 'Helps pick up late-arriving data. Search Console data usually lags by 48 hours.',
    default: '14',
    example: 'Set to 14 or 28 to ensure all data is eventually captured.',
    range: '1 to 90 days',
  },
  'ga4Gsc.manual_backfill_days': {
    definition: 'A one-time window for rewriting older Search Console rows with the current filters and setup.',
    impact: 'Useful after changing country exclusions, reconnecting the property, or cleaning up older imported data.',
    default: 'Use the suggested value once',
    example: 'If you changed the blocked-country list, run a 180-day backfill once so historical rows match the new rules.',
    range: '1 to the max shown in the field',
  },
  'clickDistance.ranking_weight': {
    definition: 'How much the click-distance score influences the final ranking.',
    impact: 'Higher values prefer destinations structurally closer to the homepage or entry points.',
    default: '0.07',
    example: '0.07 gently favours shallower pages. Raising above 0.15 may over-penalise deep content.',
    range: '0 to 0.2',
  },
  'clickDistance.k_cd': {
    definition: 'Depth sensitivity - controls how steeply the score drops off as click-distance from the homepage increases.',
    impact: 'Higher values aggressively penalise pages many clicks from the homepage. Lower values are more lenient.',
    default: '4.0',
    example: 'Raising to 4.0 strongly penalises deep pages. Lowering to 0.5 makes depth almost irrelevant.',
    range: '0.5 to 5.0',
  },
  'clickDistance.b_cd': {
    definition: 'Click-distance bias - blends raw click-distance with a smoothed version to avoid extreme scores.',
    impact: 'Higher values smooth out very deep or very shallow pages. Lower values use the raw depth score.',
    default: '0.75',
    example: '0.75 keeps depth useful without letting one very deep URL dominate the score.',
    range: '0 to 1',
  },
  'clickDistance.b_ud': {
    definition: 'URL-depth bias - blends the URL depth (number of slashes in the path) into the score.',
    impact: 'Higher values prefer pages with shorter URL paths. Lower values ignore URL depth.',
    default: '0.25',
    example: '0.25 uses URL depth as light supporting evidence. Lowering to 0 ignores URL path depth.',
    range: '0 to 1',
  },
  // Spam Guards
  'spamGuards.max_existing_links_per_host': {
    definition: 'The maximum number of existing outgoing internal links a host page may already have before the pipeline skips it entirely.',
    impact: 'Lower values keep pages cleaner — the tool will not add any suggestions to heavily-linked pages. Higher values allow more suggestions on already-linked pages.',
    default: '3',
    example: 'At 3, a page with 3 existing body links receives no new suggestions. Raise to 5 for larger, content-rich pages.',
    range: '1 to 20',
  },
  'spamGuards.max_anchor_words': {
    definition: 'The maximum number of words the tool will use in a suggested anchor phrase.',
    impact: 'Lower values force shorter, more natural-looking anchors. Higher values allow longer, more descriptive (but potentially spammy) phrases.',
    default: '4',
    example: 'At 4 words, "carbon fibre bicycle frame" is accepted but "best carbon fibre bicycle frame" is rejected. Google recommends 2–5 words.',
    range: '1 to 10',
  },
  'spamGuards.paragraph_window': {
    definition: 'How many sentences apart two suggestions must be on the same page before they are allowed to coexist. Suggestions closer than this are treated as being in the same paragraph — only the better one is kept.',
    impact: 'Lower values are stricter — links must be further apart. Higher values are more lenient and allow links to appear closer together.',
    default: '3',
    example: 'At 3, if suggestion A is at sentence 2 and suggestion B is at sentence 4, only one survives. Set to 1 to allow links in consecutive sentences.',
    range: '1 to 10',
  },
  'keywordStuffing.enabled': {
    definition: 'Turns on FR-198, which penalises destination pages whose term distribution diverges sharply from the site baseline.',
    impact: 'Enabled demotes stuffed pages. Disabled removes this content-level anti-spam signal.',
    default: 'Enabled',
    example: 'Keep enabled so stuffing risk complements anchor and graph anti-spam signals.',
    range: 'Enabled / Disabled',
  },
  'keywordStuffing.ranking_weight': {
    definition: 'How strongly FR-198 penalises keyword stuffing anomalies.',
    impact: 'Higher values demote stuffed pages more. Lower values keep the penalty gentle.',
    default: '0.04',
    example: '0.04 is the strongest anti-spam default because stuffing is a direct content-quality issue.',
    range: '0 to 0.25',
  },
  'keywordStuffing.alpha': {
    definition: 'Steepness of the sigmoid that converts KL divergence into the final stuffing penalty.',
    impact: 'Higher values make the penalty rise faster once the threshold is crossed.',
    default: '6.0',
    example: 'Raise this if you want suspicious pages to move from neutral to penalised more abruptly.',
    range: '0.1 to 20',
  },
  'keywordStuffing.tau': {
    definition: 'KL-divergence threshold where FR-198 starts shifting from neutral toward penalised.',
    impact: 'Lower values make the detector more sensitive. Higher values make it more tolerant.',
    default: '0.30',
    example: 'Lowering to 0.2 catches more anomalies, but can increase false positives.',
    range: '0 to 2',
  },
  'keywordStuffing.dirichlet_mu': {
    definition: 'Dirichlet smoothing mass for the site-wide baseline language model.',
    impact: 'Higher values smooth harder toward the corpus baseline. Lower values trust each page distribution more.',
    default: '2000',
    example: 'Keep this reasonably high so small pages do not look stuffed too easily.',
    range: '100 to 20000',
  },
  'keywordStuffing.top_k_stuff_terms': {
    definition: 'How many suspicious repeated terms FR-198 should surface in diagnostics.',
    impact: 'Higher values show more evidence. Lower values keep diagnostics shorter.',
    default: '5',
    example: 'Five terms is usually enough to explain why a page looked stuffed.',
    range: '1 to 20',
  },
  'linkFarm.enabled': {
    definition: 'Turns on FR-197, which penalises destinations inside dense reciprocal link rings.',
    impact: 'Enabled adds graph-topology anti-spam protection. Disabled removes ring penalties.',
    default: 'Enabled',
    example: 'Keep enabled so the graph layer complements anchor and content anti-spam signals.',
    range: 'Enabled / Disabled',
  },
  'linkFarm.ranking_weight': {
    definition: 'How strongly FR-197 penalises reciprocal link-ring structures.',
    impact: 'Higher values demote suspicious rings more. Lower values make the graph penalty gentler.',
    default: '0.03',
    example: '0.03 is conservative because topology can be noisier on smaller sites.',
    range: '0 to 0.25',
  },
  'linkFarm.min_scc_size': {
    definition: 'Minimum strongly connected component size before FR-197 treats a reciprocal ring as suspicious.',
    impact: 'Higher values ignore smaller clusters. Lower values let the detector react earlier.',
    default: '3',
    example: 'Three avoids overreacting to simple two-page reciprocity.',
    range: '2 to 100',
  },
  'linkFarm.density_threshold': {
    definition: 'Density floor required before FR-197 treats a reciprocal ring as suspicious.',
    impact: 'Higher values focus on tighter rings. Lower values catch looser reciprocal structures.',
    default: '0.6',
    example: 'Raise this if you only want the tightest rings to be penalised.',
    range: '0.1 to 1.0',
  },
  'linkFarm.lambda': {
    definition: 'Penalty-curve slope used when FR-197 converts ring score into the final penalty.',
    impact: 'Higher values make the penalty rise faster as the ring score increases.',
    default: '0.8',
    example: '0.8 gives a moderate curve that complements the other anti-spam signals without dominating them.',
    range: '0.01 to 5.0',
  },
  // Silo Ranking
  'silo.mode': {
    definition: 'Sets how strictly the system enforces topic silo boundaries when ranking links.',
    impact: '"Disabled" ignores silos entirely. "Prefer same silo" boosts same-silo matches. "Strict same silo" blocks cross-silo links when both pages have silo assignments.',
    default: 'Prefer same silo',
    example: 'Start with "Prefer same silo" to keep link suggestions on-topic without hard blocking.',
    range: 'Disabled / Prefer same silo / Strict same silo',
  },
  'silo.same_silo_boost': {
    definition: 'A score bonus added to destinations that belong to the same topic silo as the source page.',
    impact: 'Higher values make the system strongly prefer linking within the same silo group.',
    default: '0.05',
    example: 'Raising to 0.2 noticeably prioritises same-silo links. Raising to 0.5 may nearly eliminate cross-silo suggestions.',
    range: '0 and above (no hard maximum)',
  },
  'silo.cross_silo_penalty': {
    definition: 'A score deduction applied to destinations that belong to a different silo from the source page.',
    impact: 'Higher values suppress cross-silo suggestions more aggressively.',
    default: '0.05',
    example: 'Raising to 0.2 significantly reduces cross-silo suggestions. Raising to 0.5 makes them rare.',
    range: '0 and above (no hard maximum)',
  },
  // Feedback Rerank
  'feedbackRerank.enabled': {
    definition: 'Turns on the explore/exploit reranking system, which uses historical reviewer feedback to improve suggestions over time.',
    impact: 'Enabled gradually learns from accept/reject decisions. Disabled keeps ranking purely algorithmic.',
    default: 'On',
    example: 'Keep this on at a light weight so feedback acts like a helper, not the boss.',
    range: 'On / Off',
  },
  'feedbackRerank.ranking_weight': {
    definition: 'How strongly historical reviewer feedback adjusts the final link ranking.',
    impact: 'Higher values make the feedback signal dominant. Lower values keep it as a subtle nudge.',
    default: '0.08',
    example: '0.08 keeps feedback as a light nudge. Raising too far can let old reviewer habits overpower relevance.',
    range: '0 to 1',
  },
  'feedbackRerank.exploration_rate': {
    definition: 'Controls how much the system explores links with little historical data versus exploiting known-good ones.',
    impact: 'Higher values aggressively test uncertain link pairs. Lower values rely more on established patterns.',
    default: '1.41421356237',
    example: 'About 1.41 is a balanced starting point. Raising too high pushes many untested links to the top for review.',
    range: '0 to 10',
  },
  // Clustering
  'clustering.enabled': {
    definition: 'Turns on near-duplicate destination clustering based on semantic embedding similarity.',
    impact: 'Enabled prevents suggesting multiple redundant links to effectively the same content. Disabled treats every URL as unique.',
    default: 'On',
    example: 'Enable to clean up the Review dashboard if you see many similar thread/resource pairs.',
    range: 'On / Off',
  },
  'clustering.similarity_threshold': {
    definition: 'How similar two pages must be (cosine distance) to be grouped into the same cluster.',
    impact: 'Lower values are stricter (only clones are grouped). Higher values are more inclusive (related topics might be grouped).',
    default: '0.04',
    example: 'Lower to 0.02 to only group exact duplicates. Raise to 0.08 to group broadly related content.',
    range: '0 to 0.15',
  },
  'clustering.suppression_penalty': {
    definition: 'The score penalty applied to non-canonical (redundant) versions of a content cluster.',
    impact: 'Higher values aggressively hide duplicates. Lower values let them surface if they are strong matches.',
    default: '20.0',
    example: 'Set to 20 to push duplicates far down the list. Lowering toward 5 makes suppression softer.',
    range: '0 to 50',
  },
  // Slate Diversity
  'slateDiversity.enabled': {
    definition: 'Turns on FR-015 MMR (Maximal Marginal Relevance) diversity reranking for the final per-host link slate.',
    impact: 'When enabled, the 3 suggestions for each host thread are chosen to cover different topics. When disabled, the top 3 by score are used regardless of similarity.',
    default: 'On',
    example: 'Enable to prevent three nearly-identical destination links appearing on the same thread.',
    range: 'On / Off',
  },
  'slateDiversity.diversity_lambda': {
    definition: 'MMR lambda - controls the balance between relevance and diversity in the final slate.',
    impact: 'Higher values (closer to 1.0) keep the most relevant suggestions. Lower values force more variety even if the alternatives score lower.',
    default: '0.65',
    example: 'Lower to 0.5 for stronger diversity. Raise to 0.9 to preserve near-original ranking with a light diversity nudge.',
    range: '0.0 to 1.0',
  },
  'slateDiversity.score_window': {
    definition: 'How far below the top candidate score a destination can be and still be considered for diversity reranking.',
    impact: 'Prevents low-quality items from jumping to the top purely for variety. Only candidates within this gap of the best score are eligible.',
    default: '0.30',
    example: 'Lower to 0.10 to only consider very close competitors. Raise to 0.50 to allow more distant alternatives.',
    range: '0.05 to 1.0',
  },
  'slateDiversity.similarity_cap': {
    definition: 'Cosine similarity threshold above which two selected destinations are flagged as near-redundant in diagnostics.',
    impact: 'Purely diagnostic - does not block selection. Helps you understand when the diversity reranker is doing meaningful work.',
    default: '0.90',
    example: 'Lower to 0.80 to flag moderately similar pairs. Keep at 0.90 to only flag near-clones.',
    range: '0.70 to 0.99',
  },
  'wordpress.base_url': {
    definition: 'The main front-door address of your WordPress site.',
    impact: 'The app uses this address when it talks to WordPress. If it is wrong, sync will fail or pull from the wrong place.',
    default: 'Your live site home page',
    example: 'Use https://example.com, not https://example.com/wp-admin.',
    range: 'A full site URL starting with http:// or https://',
  },
  'wordpress.username': {
    definition: 'The WordPress username tied to the application password.',
    impact: 'Needed when the site requires login for the API. Leave blank if you only sync public content.',
    default: 'Blank unless your site needs login',
    example: 'Use the real WordPress account name, not your display nickname.',
    range: 'Any valid WordPress username',
  },
  'wordpress.app_password': {
    definition: 'A special WordPress app password, not your normal login password.',
    impact: 'Lets this app sync content safely without storing your main site password.',
    default: 'Blank unless private content needs access',
    example: 'Create it in WordPress, then paste it here once. Leave this box empty later to keep the saved one.',
    range: 'A valid WordPress application password',
  },
  'wordpress.sync_enabled': {
    definition: 'Turns the automatic WordPress sync schedule on or off.',
    impact: 'When on, the app runs a background sync at the hour and minute below.',
    default: 'Off',
    example: 'Turn it on if you want fresh posts pulled in every day without clicking Run sync now.',
    range: 'Enabled / Disabled',
  },
  'wordpress.sync_hour': {
    definition: 'The UTC hour for the automatic WordPress sync.',
    impact: 'Sets the hour part of the schedule. Use UTC, not your local clock.',
    default: '3',
    example: '3 means the sync starts at 03:00 UTC every day.',
    range: '0 to 23',
  },
  'wordpress.sync_minute': {
    definition: 'The UTC minute for the automatic WordPress sync.',
    impact: 'Sets the minute part of the schedule.',
    default: '0',
    example: '30 means the sync starts at half past the chosen UTC hour.',
    range: '0 to 59',
  },
  'googleOAuth.client_id': {
    definition: 'The OAuth client ID from Google Cloud for your web application.',
    impact: 'This lets the app open Google sign-in so one login can authorize both GA4 and Search Console.',
    default: 'Blank until you create a Google OAuth app',
    example: 'Create a Web application credential in Google Cloud, then paste the client ID exactly as shown.',
    range: 'A valid Google OAuth client ID',
  },
  'googleOAuth.client_secret': {
    definition: 'The matching OAuth client secret for the Google app above.',
    impact: 'Required alongside the client ID to complete Google sign-in and token exchange.',
    default: 'Blank until you create the Google OAuth app',
    example: 'Copy the secret from Google Cloud Console > APIs & Services > Credentials for the same web app as the client ID.',
    range: 'A valid Google OAuth client secret',
  },
  'ga4Telemetry.behavior_enabled': {
    definition: 'Turns GA4 browser event sending on or off.',
    impact: 'When enabled, the frontend can send impression, click, and engagement events to your GA4 property.',
    default: 'Off',
    example: 'Turn this on only after the Measurement ID and API secret are saved and tested.',
    range: 'Enabled / Disabled',
  },
  'ga4Telemetry.property_id': {
    definition: 'The numeric GA4 property ID used for read access and reporting sync.',
    impact: 'Needed to pull daily traffic totals back from the GA4 Data API.',
    default: 'Blank until your GA4 property is ready',
    example: 'Use the numeric Property ID from GA4 Admin, not the Measurement ID that starts with G-.',
    range: 'A numeric GA4 property ID',
  },
  'ga4Telemetry.measurement_id': {
    definition: 'The GA4 Measurement ID used by browser events.',
    impact: 'This tells event pings which GA4 web data stream should receive the telemetry.',
    default: 'Blank until a GA4 web stream exists',
    example: 'Copy the Measurement ID from the GA4 web stream. It usually looks like G-ABC123XYZ.',
    range: 'A GA4 Measurement ID starting with G-',
  },
  'ga4Telemetry.api_secret': {
    definition: 'The Measurement Protocol API secret for the same GA4 web stream.',
    impact: 'Required for securely sending browser events to GA4 from this app.',
    default: 'Blank until you create one in GA4',
    example: 'In GA4 Admin, open your web stream, create an API secret under Measurement Protocol, then paste it here once.',
    range: 'A valid GA4 API secret',
  },
  'ga4Telemetry.sync_enabled': {
    definition: 'Turns GA4 read-sync on or off.',
    impact: 'When enabled, the backend pulls daily GA4 totals back into the app as a first-party behavior signal.',
    default: 'Off',
    example: 'Leave this on if you want GA4 page metrics imported regularly, even when browser events are already being sent.',
    range: 'Enabled / Disabled',
  },
  'ga4Telemetry.read_project_id': {
    definition: 'The Google Cloud project ID for the fallback GA4 service account.',
    impact: 'Used only when you choose service-account read access instead of relying on Google OAuth.',
    default: 'Blank unless you use the fallback setup',
    example: 'Copy the project_id value from the service-account JSON key file.',
    range: 'A valid Google Cloud project ID',
  },
  'ga4Telemetry.read_client_email': {
    definition: 'The client email from the fallback GA4 service-account JSON key.',
    impact: 'The app uses this identity to call the GA4 Data API when OAuth is not being used.',
    default: 'Blank unless you use the fallback setup',
    example: 'Share GA4 property access with this service-account email before testing read access.',
    range: 'A valid service-account email address',
  },
  'ga4Telemetry.read_private_key': {
    definition: 'The private key from the fallback GA4 service-account JSON key.',
    impact: 'Allows the backend to authenticate as the fallback service account for GA4 read access.',
    default: 'Blank unless you use the fallback setup',
    example: 'Paste the full private_key value including the BEGIN and END markers.',
    range: 'A valid PEM private key',
  },
  'ga4Telemetry.sync_lookback_days': {
    definition: 'How many recent days of GA4 data are reread on each sync.',
    impact: 'A small overlap helps catch late processing and keeps imported totals stable.',
    default: '7',
    example: 'Use 7 to keep imports fresh without rereading too much data every day.',
    range: '1 to 30 days',
  },
  'ga4Telemetry.geo_granularity': {
    definition: 'Controls how much geographic detail is stored from GA4 imports.',
    impact: 'More detail gives richer analysis, while less detail reduces stored location information.',
    default: 'Country only',
    example: 'Choose Country only for a balanced default. Use Do not store geography if location data is unnecessary.',
    range: 'None / Country / Country and region',
  },
  'ga4Telemetry.event_schema': {
    definition: 'The internal event schema version expected by this app.',
    impact: 'Helps keep browser event names and imported analytics logic aligned across releases.',
    default: 'fr016_v1',
    example: 'Leave the shipped value unless the app release notes tell you to move to a newer schema.',
    range: 'A supported schema identifier',
  },
  'ga4Telemetry.retention_days': {
    definition: 'How long imported GA4 telemetry should be kept in this app.',
    impact: 'Higher values preserve more history for trend analysis but store more data locally.',
    default: '400',
    example: 'Keep the default unless you need shorter retention for storage or policy reasons.',
    range: '1 to 800 days',
  },
  'ga4Telemetry.impression_visible_ratio': {
    definition: 'The portion of a suggestion card that must be visible before it counts as an impression.',
    impact: 'Higher values avoid counting glancing views, while lower values count impressions earlier.',
    default: '0.5',
    example: '0.5 means roughly half the card should be on screen before the event is sent.',
    range: '0.25 to 1.0',
  },
  'ga4Telemetry.impression_min_ms': {
    definition: 'The minimum on-screen time before an impression event is recorded.',
    impact: 'Prevents very brief scroll-pasts from being treated as meaningful impressions.',
    default: '1000',
    example: '1000 means a card must stay visible for at least one second before it counts.',
    range: '250 to 5000 milliseconds',
  },
  'ga4Telemetry.engaged_min_seconds': {
    definition: 'The minimum active time before a session is treated as engaged for this feature.',
    impact: 'Higher values make engagement stricter. Lower values count shorter visits as meaningful.',
    default: '10',
    example: '10 seconds is a sensible starting point for settings and review workflows.',
    range: '5 to 60 seconds',
  },
  'matomoTelemetry.url': {
    definition: 'The base URL of your Matomo installation.',
    impact: 'The app uses this endpoint to validate access and sync traffic data.',
    default: 'Blank until Matomo is available',
    example: 'Use the root Matomo URL like https://analytics.example.com, not a reporting page URL.',
    range: 'A full URL starting with http:// or https://',
  },
  'matomoTelemetry.site_id_xenforo': {
    definition: 'The Matomo site ID that tracks your XenForo pages.',
    impact: 'Lets the app import forum traffic into the correct telemetry bucket.',
    default: 'Blank until known',
    example: 'Find the numeric site ID in Matomo Admin for the XenForo tracked website.',
    range: 'A Matomo site ID',
  },
  'matomoTelemetry.site_id_wordpress': {
    definition: 'The Matomo site ID that tracks your WordPress site, if it is tracked separately.',
    impact: 'Lets the app import WordPress traffic without mixing it into the XenForo site ID.',
    default: 'Optional',
    example: 'Leave this blank if WordPress traffic is already included under the XenForo site ID or you do not track WordPress in Matomo.',
    range: 'Blank or a Matomo site ID',
  },
  'matomoTelemetry.token_auth': {
    definition: 'The Matomo API token used for authenticated requests.',
    impact: 'Required for connection tests and telemetry imports from Matomo.',
    default: 'Blank until you create one in Matomo',
    example: 'Create or copy a token_auth value from your Matomo user settings, then paste it here once.',
    range: 'A valid Matomo API token',
  },
  'matomoTelemetry.enabled': {
    definition: 'Turns Matomo telemetry collection on or off for this integration.',
    impact: 'When enabled, Matomo becomes an active first-party analytics source for the app.',
    default: 'Off',
    example: 'Enable this after the URL, site IDs, and token have all been saved and tested.',
    range: 'Enabled / Disabled',
  },
  'matomoTelemetry.sync_enabled': {
    definition: 'Turns scheduled Matomo imports on or off.',
    impact: 'When enabled, the app regularly rereads recent Matomo data instead of relying only on manual tests.',
    default: 'Off',
    example: 'Keep this on if Matomo is one of your main traffic sources for ranking and diagnostics.',
    range: 'Enabled / Disabled',
  },
  'matomoTelemetry.sync_lookback_days': {
    definition: 'How many recent days of Matomo data are reread on each sync.',
    impact: 'A short overlap helps refresh delayed updates without creating a very large import window each run.',
    default: '7',
    example: 'Use 7 for a safe default. Increase it if your Matomo data tends to settle slowly.',
    range: '1 to 30 days',
  },
  'siloGroup.name': {
    definition: 'The human-friendly name for this silo group.',
    impact: 'This is the label people see when assigning scopes and reading silo settings.',
    default: 'A short clear label',
    example: 'Good examples: Guides, Troubleshooting, Plugins.',
    range: 'Plain text',
  },
  'siloGroup.slug': {
    definition: 'The short machine name for this silo group.',
    impact: 'Used behind the scenes in saved data and API calls.',
    default: 'A lowercase short code',
    example: 'guides or troubleshooting are good slugs.',
    range: 'Short lowercase text, usually words joined with dashes',
  },
  'siloGroup.description': {
    definition: 'A simple note about what belongs in this group.',
    impact: 'Helps you and future users remember the purpose of the group.',
    default: 'Blank',
    example: 'Use this for pages that teach people how to fix common setup problems.',
    range: 'Short plain-English text',
  },
  'siloGroup.display_order': {
    definition: 'Controls the order the group appears in the settings page.',
    impact: 'Lower numbers show first. This does not change ranking by itself.',
    default: '0',
    example: '0 shows above 10.',
    range: 'Any whole number',
  },
  'scopeAssignment.silo_group': {
    definition: 'Picks which silo bucket a scope belongs to.',
    impact: 'Silo ranking only works when scopes are assigned to groups. Unassigned scopes are ignored by silo rules.',
    default: 'Unassigned',
    example: 'Put all WordPress guides into Guides, and all product docs into Products.',
    range: 'Any existing silo group or Unassigned',
  },
  // Tabs
  'tabs.ranking_weights': {
    definition: 'Fine-tune the mathematical weights used to rank link suggestions.',
    impact: 'Changes here directly affect which links the ranker picks as the best matches.',
    default: 'Research-backed defaults',
    example: 'Increase the PageRank weight to favor high-authority pages.',
    range: 'Numerical weights',
  },
  'tabs.silo_architecture': {
    definition: 'Manage topical content silos and scope mapping.',
    impact: 'Controls how content is grouped to prevent irrelevant cross-topic link suggestions.',
    default: 'Silo mapping logic',
    example: 'Assign "Post Type: Guide" to the "Guides" silo.',
    range: 'Group assignments',
  },
  'tabs.wordpress_sync': {
    definition: 'Configure and test the app integrations for WordPress, Google OAuth, GA4, Matomo, and Google Search Console.',
    impact: 'This tab controls how content sync and first-party analytics flow into the platform, so mistakes here affect imports, telemetry, and attribution.',
    default: 'Connection and sync setup',
    example: 'Connect Google once for GA4 and GSC, save WordPress credentials for content sync, and add Matomo only if you use it.',
    range: 'URLs, credentials, toggles, and sync windows',
  },
  'tabs.library_history': {
    definition: 'Save weight presets and view your adjustment history.',
    impact: 'Allows you to experiment with different weights and quickly rollback if needed.',
    default: 'Snapshot library',
    example: 'Save your "Black Friday" weights as a preset.',
    range: 'Presets and logs',
  },
  // FR-038 — Information Gain Scoring
  'informationGain.enabled': {
    definition: 'Turns on information gain scoring, which rewards destinations that add new content the source page does not already cover.',
    impact: 'Enabled computes gain silently alongside other signals. Disabled skips all gain computation and stores a neutral score.',
    default: 'Enabled',
    example: 'Keep enabled so diagnostics run even at weight 0. You can inspect sample novel tokens before raising the weight.',
    range: 'Enabled / Disabled',
  },
  'informationGain.ranking_weight': {
    definition: 'How much the information gain score influences the final ranking.',
    impact: 'Higher values reward destinations that add genuinely new vocabulary the source page does not already contain. This is the complementary signal to semantic similarity — one rewards topic match, this rewards topic novelty.',
    default: '0.03',
    example: '0.03 acts as a light tie-breaker. Raise to 0.05 once diagnostics confirm the signal looks sensible on your content.',
    range: '0 to 0.10',
  },
  'informationGain.min_source_chars': {
    definition: 'The minimum character count the source page body must have before a gain score is computed.',
    impact: 'Pages shorter than this threshold receive a neutral score. Prevents misleading gain scores from very thin source pages with only a few tokens.',
    default: '200',
    example: 'Keep at 200. Lowering below 100 risks gain scores on source pages that are too short to compare meaningfully.',
    range: '50 to 1000',
  },
  // FR-039 — Entity Salience Match
  'entitySalience.enabled': {
    definition: 'Turns on entity salience matching, which rewards destinations that are built around the same core topics that define the source page.',
    impact: 'Enabled computes salience silently alongside other signals. Disabled skips all salience computation and stores a neutral score.',
    default: 'Enabled',
    example: 'Keep enabled so diagnostics run even at weight 0. Inspect top_salient_terms before raising the weight.',
    range: 'Enabled / Disabled',
  },
  'entitySalience.ranking_weight': {
    definition: 'How much the entity salience match score influences the final ranking.',
    impact: 'Higher values reward destinations that prominently feature the source page\'s most important and distinctive terms — not just topic-adjacent pages that mention the terms in passing.',
    default: '0.04',
    example: '0.04 gives a gentle boost to on-topic destinations. Raise to 0.06 once diagnostics confirm salient terms look meaningful.',
    range: '0 to 0.10',
  },
  'entitySalience.max_salient_terms': {
    definition: 'The maximum number of salient source-page terms extracted for comparison against the destination.',
    impact: 'More terms give a broader signal but may dilute precision. Fewer terms focus only on the most distinctive source topics.',
    default: '10',
    example: 'Lowering to 5 focuses on only the strongest salient terms. Raising to 20 broadens the comparison but includes weaker signals.',
    range: '3 to 25',
  },
  'entitySalience.max_site_document_frequency': {
    definition: 'A term must appear in no more than this many pages site-wide to qualify as salient for the source page.',
    impact: 'Lower values restrict salience to very distinctive terms. Higher values allow moderately common terms to qualify.',
    default: '20',
    example: 'Lowering to 5 extracts only very rare, highly distinctive terms. Raising to 50 includes terms that appear on many pages and may be too generic.',
    range: '5 to 100',
  },
  'entitySalience.min_source_term_frequency': {
    definition: 'A term must appear at least this many times within the source page itself to be considered salient.',
    impact: 'Higher values require terms to be repeatedly emphasised in the source. Lower values pick up terms mentioned only once or twice.',
    default: '2',
    example: 'Raising to 3 requires terms to be mentioned at least three times. Lowering to 1 picks up any term that survives the site-frequency filter.',
    range: '1 to 5',
  },
  // FR-040 - Multimedia Boost
  'multimediaSignal.enabled': {
    definition: 'Turns on multimedia richness scoring, which rewards destinations with better video, image, and alt-text coverage.',
    impact: 'Enabled computes the multimedia signal from stored HTML-extraction metadata. Disabled skips that signal and falls back to the neutral value.',
    default: 'Enabled',
    example: 'Keep enabled so visually rich destinations can benefit once FR-040 is implemented. Disable only if multimedia extraction is unavailable or too noisy.',
    range: 'Enabled / Disabled',
  },
  'multimediaSignal.ranking_weight': {
    definition: 'How much the multimedia richness signal influences the value-model score.',
    impact: 'Higher values make pages with helpful videos, descriptive images, and strong alt-text coverage more attractive as destinations.',
    default: '0.10',
    example: '0.10 gives multimedia a meaningful supporting role. Raising far above this can over-reward pretty pages that are not the best semantic match.',
    range: '0 to 0.20',
  },
  'multimediaSignal.fallback_value': {
    definition: 'The neutral score used when multimedia metadata is missing for a destination.',
    impact: 'Higher values make missing metadata almost harmless. Lower values effectively punish pages that have not been re-synced yet.',
    default: '0.5',
    example: 'Keep at 0.5 so pages without extracted metadata remain neutral until the next sync.',
    range: '0 to 1',
  },
  // FR-041 - Originality Provenance Scoring
  'originalityProvenance.enabled': {
    definition: 'Turns on originality provenance scoring, which prefers the earliest and most source-like page inside a family of near-duplicate pages.',
    impact: 'Enabled computes provenance diagnostics and origin preference. Disabled skips provenance analysis and stores a neutral score.',
    default: 'Enabled',
    example: 'Keep enabled so provenance diagnostics are available even while the ranking weight remains conservative.',
    range: 'Enabled / Disabled',
  },
  'originalityProvenance.ranking_weight': {
    definition: 'How much originality provenance influences the final ranking.',
    impact: 'Higher values make historically primary pages win more often against reposts, mirrors, or lightly rewritten copies.',
    default: '0.03',
    example: '0.03 is a gentle tie-breaker. Raise carefully only after verifying that provenance families and timestamps look trustworthy.',
    range: '0 to 0.10',
  },
  'originalityProvenance.resemblance_threshold': {
    definition: 'The minimum shingle-overlap resemblance required before two pages are treated as belonging to the same provenance family.',
    impact: 'Lower values group more pages together. Higher values require pages to be much closer lexical matches before provenance logic activates.',
    default: '0.55',
    example: 'Keep near 0.55 for broad near-copy detection. Raising toward 0.75 makes the signal much stricter and more clone-focused.',
    range: '0.30 to 0.90',
  },
  'originalityProvenance.containment_threshold': {
    definition: 'The minimum containment score required before one page is treated as substantially contained within another provenance family member.',
    impact: 'Higher values make partial-copy detection stricter. Lower values catch more derivative pages but risk over-grouping.',
    default: '0.80',
    example: 'Keep near 0.80 so derivative pages must substantially include another page before provenance support activates.',
    range: '0.50 to 0.95',
  },
  // FR-042 - Fact Density Scoring
  'factDensity.enabled': {
    definition: 'Turns on fact density scoring, which rewards destinations that contain more concrete facts relative to their length.',
    impact: 'Enabled computes a text-density quality signal. Disabled skips density analysis and stores a neutral score.',
    default: 'Enabled',
    example: 'Keep enabled so the signal can run in shadow mode while you inspect whether it behaves well on forum and article content.',
    range: 'Enabled / Disabled',
  },
  'factDensity.ranking_weight': {
    definition: 'How much fact density influences the final ranking.',
    impact: 'Higher values reward pages that pack more concrete, verifiable information into fewer words and reduce the impact of fluffy pages.',
    default: '0.04',
    example: '0.04 gives density a useful quality voice without letting it overpower topical relevance.',
    range: '0 to 0.10',
  },
  'factDensity.min_word_count': {
    definition: 'The minimum destination word count required before a fact-density score is computed.',
    impact: 'Pages shorter than this stay neutral. Higher values reduce noisy scores on thin pages; lower values score more of the corpus.',
    default: '120',
    example: 'Keep around 120 so tiny blurbs and stub pages do not get misleading density scores.',
    range: '50 to 400',
  },
  'factDensity.density_cap_per_100_words': {
    definition: 'The maximum effective fact count per 100 words before the score saturates.',
    impact: 'Lower values make dense pages hit the top score faster. Higher values spread out the score across a wider range of factual writing styles.',
    default: '8.0',
    example: '8.0 treats very information-dense how-to or product pages as strong performers without making normal prose impossible to score well.',
    range: '2 to 20',
  },
  'factDensity.filler_penalty_weight': {
    definition: 'How strongly filler-heavy sentences reduce the final fact-density score.',
    impact: 'Higher values punish vague or padded writing more aggressively. Lower values let density dominate even when some filler is present.',
    default: '0.35',
    example: '0.35 trims obvious filler without turning a few soft sentences into a major penalty.',
    range: '0 to 1',
  },
  // FR-043 - Semantic Drift Penalty
  'semanticDrift.enabled': {
    definition: 'Turns on semantic drift analysis, which penalizes destinations that start on-topic but drift into unrelated material later.',
    impact: 'Enabled computes drift diagnostics and a bounded penalty score. Disabled skips drift analysis and stores a neutral value.',
    default: 'Enabled',
    example: 'Keep enabled so you can inspect drift diagnostics before letting the penalty affect ranking.',
    range: 'Enabled / Disabled',
  },
  'semanticDrift.ranking_weight': {
    definition: 'How strongly semantic drift subtracts from the final ranking.',
    impact: 'Higher values punish pages that lose topical focus as they progress. Lower values keep drift as a light quality guardrail.',
    default: '0.03',
    example: '0.03 keeps drift lighter than the fact-density boost, which is safer because penalties are felt as regressions faster than boosts.',
    range: '0 to 0.10',
  },
  'semanticDrift.tokens_per_sequence': {
    definition: 'The token count used for each low-level sequence before larger drift-analysis blocks are formed.',
    impact: 'Smaller values make the signal more sensitive to local topic shifts. Larger values smooth out noise but may miss short drift events.',
    default: '20',
    example: '20 is a balanced starting point. Lowering too far makes chatter and quoted fragments look like drift.',
    range: '10 to 60',
  },
  'semanticDrift.block_size_in_sequences': {
    definition: 'How many token sequences are combined into each comparison block for drift analysis.',
    impact: 'Higher values create smoother, more stable topic blocks. Lower values make the signal react faster but increase noise.',
    default: '6',
    example: '6 provides enough context for stable segmentation on long forum and article pages without making blocks too large.',
    range: '3 to 12',
  },
  'semanticDrift.anchor_similarity_threshold': {
    definition: 'The minimum similarity a later segment must retain to the opening anchor segment before it is marked as drifted.',
    impact: 'Higher values make the penalty stricter. Lower values tolerate broader topic expansion before drift is recorded.',
    default: '0.18',
    example: '0.18 is lenient enough for related subsections but still catches pages that wander into a different subject entirely.',
    range: '0.05 to 0.40',
  },
  'semanticDrift.min_word_count': {
    definition: 'The minimum destination word count required before semantic drift is analyzed.',
    impact: 'Short pages stay neutral. Higher values reduce false positives on brief content; lower values attempt drift scoring on more pages.',
    default: '180',
    example: 'Keep around 180 so short threads, notices, and stubs do not get forced through topic-segmentation logic.',
    range: '80 to 500',
  },
  // FR-044 - Internal Search Intensity Signal
  'internalSearch.enabled': {
    definition: 'Turns on internal-search intensity scoring, which rewards destinations matching topics users are actively searching for inside the site.',
    impact: 'Enabled computes a burst-aware demand signal from aggregate internal-search queries. Disabled skips that analysis and stores a neutral score.',
    default: 'Enabled',
    example: 'Keep enabled so the signal can run in shadow mode while you validate the quality of query matching.',
    range: 'Enabled / Disabled',
  },
  'internalSearch.ranking_weight': {
    definition: 'How much internal-search intensity influences the final ranking.',
    impact: 'Higher values favor destinations tied to currently high-demand internal search topics. Lower values keep search demand as a subtle freshness signal.',
    default: '0.02',
    example: '0.02 is intentionally light because search-demand spikes can be noisy until query matching is proven on real content.',
    range: '0 to 0.08',
  },
  'internalSearch.recent_days': {
    definition: 'The number of most-recent days used to measure current internal-search demand.',
    impact: 'Smaller windows react faster to short-lived spikes. Larger windows smooth demand and make the signal slower but steadier.',
    default: '3',
    example: '3 days catches short bursts of user interest without making the signal too jumpy hour-to-hour.',
    range: '1 to 14',
  },
  'internalSearch.baseline_days': {
    definition: 'The longer baseline window used to judge whether recent internal-search demand is unusually high.',
    impact: 'Larger baselines make burst detection stricter and more stable. Smaller baselines react faster but can misread normal fluctuations as spikes.',
    default: '28',
    example: '28 days is a good monthly baseline for detecting genuine lifts above normal search demand.',
    range: '7 to 90',
  },
  'internalSearch.max_active_queries': {
    definition: 'The maximum number of high-intensity internal-search queries kept in the active scoring set.',
    impact: 'Higher values broaden coverage but increase matching noise and compute cost. Lower values focus only on the strongest current topics.',
    default: '200',
    example: '200 keeps the active set broad enough for medium-size sites without letting long-tail noise dominate.',
    range: '20 to 1000',
  },
  'internalSearch.min_recent_count': {
    definition: 'The minimum recent search count a query must have before it is considered active for scoring.',
    impact: 'Higher values filter out one-off queries. Lower values make the signal more sensitive but noisier.',
    default: '3',
    example: '3 is a practical floor that filters accidental one-offs while still allowing emerging topics to appear.',
    range: '1 to 20',
  },
  // FR-045 — Anchor Diversity & Exact-Match Reuse Guard
  'anchorDiversity.enabled': {
    definition: 'Turns on FR-045, which demotes repeated exact-match anchors pointing at the same destination.',
    impact: 'Enabled reduces over-optimized anchor repetition. Disabled leaves that risk to the older spam guards only.',
    default: 'Enabled',
    example: 'Keep enabled for normal production use so anchor reuse stays natural.',
    range: 'Enabled / Disabled',
  },
  'anchorDiversity.ranking_weight': {
    definition: 'How strongly FR-045 penalises repeated exact-match anchor reuse.',
    impact: 'Higher values demote repetitive exact-match anchors more aggressively. Lower values keep the penalty gentle.',
    default: '0.03',
    example: '0.03 is conservative. Raising to 0.06 makes the system much less tolerant of exact-match reuse.',
    range: '0 to 0.25',
  },
  'anchorDiversity.min_history_count': {
    definition: 'Minimum active suggestion history required before FR-045 starts scoring anchor reuse.',
    impact: 'Higher values keep low-data destinations neutral for longer. Lower values start judging reuse sooner.',
    default: '3',
    example: 'Set to 5 if you want sparse destinations to stay neutral until more history exists.',
    range: '1 to 50',
  },
  'anchorDiversity.max_exact_match_share': {
    definition: 'Maximum safe share of active suggestions using the same exact anchor for one destination.',
    impact: 'Lower values trigger penalties earlier. Higher values tolerate more exact-match reuse.',
    default: '0.40',
    example: 'Lowering to 0.25 makes the ranker diversify anchors sooner.',
    range: '0.05 to 1.0',
  },
  'anchorDiversity.max_exact_match_count': {
    definition: 'Maximum safe count of active exact-match suggestions before FR-045 penalises the candidate.',
    impact: 'Lower values curb repeated anchors earlier. Higher values allow more reuse before penalties apply.',
    default: '3',
    example: 'Three is a balanced starting point for manual-review workflows.',
    range: '1 to 50',
  },
  'anchorDiversity.hard_cap_enabled': {
    definition: 'Allows FR-045 to hard-block extreme exact-match reuse instead of only demoting it.',
    impact: 'Enabled is stricter and may suppress some relevant candidates. Disabled stays soft-penalty-first.',
    default: 'Disabled',
    example: 'Leave off unless you want the system to reject extreme anchor repetition outright.',
    range: 'Enabled / Disabled',
  },
  // FR-046 — Multi-Query Fan-Out for Stage 1 Retrieval
  'fanOut.enabled': {
    definition: 'Whether multi-query fan-out is used for Stage 1 candidate retrieval.',
    impact: 'Decomposes multi-topic destinations into segments and runs separate searches, finding candidates single-vector search would miss.',
    default: 'true',
    example: 'Disable if your content is short and single-topic.',
    range: 'on / off',
  },
  'fanOut.max_sub_queries': {
    definition: 'Maximum number of segments per destination to decompose into separate queries.',
    impact: 'Higher values capture more sub-topics but increase retrieval cost.',
    default: '3',
    example: '3 covers title + intro + body. Raise to 5 for very long, multi-section articles.',
    range: '1 to 5',
  },
  'fanOut.min_segment_words': {
    definition: 'Minimum words for a body segment to qualify as a sub-query.',
    impact: 'Prevents tiny fragments from generating noisy retrieval results.',
    default: '50',
    example: 'Lower to 30 if your pages have many short but distinct sections.',
    range: '20 to 200',
  },
  'fanOut.rrf_k': {
    definition: 'RRF smoothing constant (Cormack et al. 2009 standard) for merging sub-query results.',
    impact: 'Higher values give more weight to lower-ranked results when merging.',
    default: '60',
    example: '60 is the standard default. Lower to 30 to favour top-ranked results more.',
    range: '10 to 120',
  },
  // FR-047 — Navigation Path Prediction
  'navigationPath.enabled': {
    definition: 'Whether Markov transition data from GA4 page-view sequences is used for scoring.',
    impact: 'Pages users already navigate toward get a ranking boost.',
    default: 'true',
    example: 'Disable if you have no GA4 session data.',
    range: 'on / off',
  },
  'navigationPath.ranking_weight': {
    definition: 'How much navigation-path prediction contributes to the final score.',
    impact: 'Higher values favour destinations users are already trying to reach.',
    default: '0.04',
    example: 'Raise to 0.06 after confirming transition counts are stable across pipeline runs.',
    range: '0 to 0.15',
  },
  'navigationPath.lookback_days': {
    definition: 'Historical window of GA4 sessions used to build transition matrices.',
    impact: 'Longer windows are more stable but slower to adapt to changed navigation patterns.',
    default: '90',
    example: '30 for a fast-changing site, 90 for stable content.',
    range: '7 to 365',
  },
  'navigationPath.min_sessions': {
    definition: 'Minimum sessions before computing transition probabilities for a page.',
    impact: 'Higher values require stronger evidence but may exclude low-traffic pages.',
    default: '50',
    example: 'Lower to 20 on smaller sites with fewer sessions.',
    range: '5 to 500',
  },
  'navigationPath.min_transition_count': {
    definition: 'Minimum observed page-to-page transitions before scoring a link.',
    impact: 'Filters noise from rare or accidental navigation paths.',
    default: '5',
    example: 'Raise to 10 on high-traffic sites for stronger signal quality.',
    range: '1 to 50',
  },
  'navigationPath.w_direct': {
    definition: 'Weight for direct (one-hop) page-to-page transitions.',
    impact: 'Higher values prefer links that match immediate next-page navigation.',
    default: '0.6',
    example: 'Keep higher than w_shortcut since direct transitions are more reliable.',
    range: '0 to 1',
  },
  'navigationPath.w_shortcut': {
    definition: 'Weight for multi-hop shortcut navigation patterns.',
    impact: 'Higher values reward links that skip intermediate pages users commonly traverse.',
    default: '0.4',
    example: 'Raise if your site has deep navigation hierarchies.',
    range: '0 to 1',
  },
  // FR-048 — Topical Authority Cluster Density
  'topicalCluster.enabled': {
    definition: 'Whether HDBSCAN topic clustering is used to boost destinations in dense topic areas.',
    impact: 'Destinations in large, well-covered topic clusters score higher.',
    default: 'true',
    example: 'Disable on very small sites where clustering is not meaningful.',
    range: 'on / off',
  },
  'topicalCluster.ranking_weight': {
    definition: 'How much topical cluster density contributes to the final score.',
    impact: 'Higher values favour destinations where the site has demonstrated topical depth.',
    default: '0.04',
    example: 'Raise to 0.06 after verifying HDBSCAN produces stable, meaningful clusters.',
    range: '0 to 0.15',
  },
  'topicalCluster.min_cluster_size': {
    definition: 'Minimum pages required to form a recognized topic cluster.',
    impact: 'Prevents tiny noise clusters from inflating authority scores.',
    default: '5',
    example: 'Raise to 10 on large sites with 1000+ pages.',
    range: '2 to 50',
  },
  'topicalCluster.min_site_pages': {
    definition: 'Minimum total site pages needed for clustering to activate.',
    impact: 'Prevents clustering on sites too small for meaningful topic grouping.',
    default: '20',
    example: 'The signal stays neutral until your site crosses this threshold.',
    range: '5 to 200',
  },
  'topicalCluster.max_staleness_days': {
    definition: 'Days before cluster assignments are considered stale and need recomputation.',
    impact: 'Shorter values keep clusters fresh but increase compute cost.',
    default: '14',
    example: '7 for fast-growing sites, 30 for stable content libraries.',
    range: '1 to 90',
  },
  'topicalCluster.fallback_value': {
    definition: 'Score assigned when clustering data is unavailable for a destination.',
    impact: 'New or unclustered pages receive this neutral value.',
    default: '0.5',
    example: '0.5 is neutral — neither boosts nor penalises.',
    range: '0 to 1',
  },
  // FR-049 — Query Intent Funnel Alignment
  'intentFunnel.enabled': {
    definition: 'Whether GSC query-intent classification is used to boost funnel-aligned links.',
    impact: 'Links that move users one stage forward through the buyer journey score higher.',
    default: 'true',
    example: 'Disable if your site is purely informational with no commercial funnel.',
    range: 'on / off',
  },
  'intentFunnel.ranking_weight': {
    definition: 'How much funnel alignment contributes to the final score.',
    impact: 'Higher values strongly prefer links that guide users toward conversion.',
    default: '0.03',
    example: 'Raise to 0.05 after validating that intent classification is stable.',
    range: '0 to 0.15',
  },
  'intentFunnel.optimal_offset': {
    definition: 'Ideal stage distance between source and destination (1 = one stage forward).',
    impact: 'Links matching this offset get the maximum funnel alignment bonus.',
    default: '1',
    example: 'Keep at 1 for standard one-step-forward funnel progression.',
    range: '1 to 3',
  },
  'intentFunnel.sigma': {
    definition: 'Gaussian width controlling penalty for non-optimal funnel distances.',
    impact: 'Smaller values penalise distant stage jumps more harshly.',
    default: '1.2',
    example: 'Lower to 0.8 if you want strict one-stage-forward enforcement.',
    range: '0.3 to 3.0',
  },
  'intentFunnel.min_confidence': {
    definition: 'Minimum classification confidence for intent scoring to apply.',
    impact: 'Pages with low-confidence classification fall back to neutral scoring.',
    default: '0.25',
    example: 'Raise to 0.5 if you see too many misclassified pages affecting ranking.',
    range: '0 to 1',
  },
  'intentFunnel.navigational_confidence_threshold': {
    definition: 'Confidence threshold for opting navigational pages out of funnel scoring.',
    impact: 'Navigational queries (brand searches, homepage) are excluded above this confidence.',
    default: '0.6',
    example: 'Lower to 0.4 if navigational queries are rare on your site.',
    range: '0 to 1',
  },
  // FR-050 — Seasonality & Temporal Demand Matching
  'seasonality.enabled': {
    definition: 'Whether seasonal traffic patterns are used to boost time-relevant destinations.',
    impact: 'Destinations whose annual peak is approaching or active score higher.',
    default: 'true',
    example: 'Disable on sites with no seasonal content patterns.',
    range: 'on / off',
  },
  'seasonality.ranking_weight': {
    definition: 'How much seasonal demand matching contributes to the final score.',
    impact: 'Higher values strongly prefer destinations aligned with current seasonal demand.',
    default: '0.03',
    example: 'Raise to 0.05 after confirming seasonal_strength separates seasonal from perennial pages.',
    range: '0 to 0.15',
  },
  'seasonality.min_history_months': {
    definition: 'Minimum months of GA4/GSC history needed to fit a seasonal model.',
    impact: 'Ensures enough data points for reliable annual pattern detection.',
    default: '12',
    example: '12 months gives a full annual cycle. 18 is safer for noisy data.',
    range: '6 to 36',
  },
  'seasonality.min_seasonal_strength': {
    definition: 'Minimum seasonal variance ratio to classify a page as seasonal.',
    impact: 'Pages below this threshold are treated as perennial (no seasonal boost).',
    default: '0.3',
    example: 'Lower to 0.2 if you want more pages to qualify for seasonal scoring.',
    range: '0.1 to 0.8',
  },
  'seasonality.anticipation_window_months': {
    definition: 'Months before a page\'s seasonal peak to start applying an anticipation bonus.',
    impact: 'Lets you link to seasonal content before demand peaks, not just during.',
    default: '3',
    example: '3 months means holiday content starts getting boosted in September.',
    range: '1 to 6',
  },
  'seasonality.w_current': {
    definition: 'Weight for the current month\'s seasonal index value.',
    impact: 'Higher values make the score track the current seasonal cycle closely.',
    default: '0.7',
    example: 'Keep higher than w_anticipation to anchor scoring in observed demand.',
    range: '0 to 1',
  },
  'seasonality.w_anticipation': {
    definition: 'Weight for the approaching-peak anticipation bonus.',
    impact: 'Higher values boost pages earlier before their seasonal peak.',
    default: '0.3',
    example: 'Raise to 0.5 if you want aggressive early linking to seasonal content.',
    range: '0 to 1',
  },
  'seasonality.index_cap': {
    definition: 'Cap on the seasonal index to prevent extreme spikes from dominating.',
    impact: 'Clamps the seasonal multiplier so no single month can overwhelm other signals.',
    default: '3.0',
    example: 'Lower to 2.0 if your site has very spiky seasonal patterns.',
    range: '1.5 to 10.0',
  },
  // FR-099 Dangling Authority Redistribution Bonus (DARB)
  'darb.enabled': {
    definition: 'FR-099 DARB: turns on the "dangling hoarder" boost for high-value hosts that have few outbound links.',
    impact: 'Enabled adds a small boost to candidates from hosts that are strong pages but barely link out. Disabled turns the feature off.',
    default: 'On',
    example: 'Leave on — the boost is tiny but fixes the classic "dead-end street" SEO problem in the Reddit post.',
    range: 'On / Off',
  },
  'darb.ranking_weight': {
    definition: 'How strongly the DARB bonus contributes to the final score.',
    impact: 'Higher values push harder to route juice out of hoarder hosts. Zero disables the boost without turning off the signal.',
    default: '0.04',
    example: '0.04 is a gentle nudge. Raise to 0.08 if your site has many high-traffic posts with no outbound links.',
    range: '0 to 0.15',
  },
  'darb.out_degree_saturation': {
    definition: 'Minimum outbound links above which a host is no longer considered "dangling".',
    impact: 'Lower values mean only very sparse hosts qualify; higher values widen the boost to hosts with a few existing links.',
    default: '5',
    example: 'Raising to 8 makes the boost fire on more hosts. Broder et al. 2000 median out-degree is 8.',
    range: '1 to 20',
  },
  'darb.min_host_value': {
    definition: 'Minimum host content_value_score (GSC+GA4+PageRank composite) required to trigger the boost.',
    impact: 'Higher values restrict the boost to high-quality hosts only. 0.5 is neutral.',
    default: '0.5',
    example: 'Raise to 0.7 if you want only your very best pages to benefit from the boost.',
    range: '0 to 1',
  },
  // FR-100 Katz Marginal Information Gain (KMIG)
  'kmig.enabled': {
    definition: 'FR-100 KMIG: penalises candidates already reachable within 1-2 hops via existing links.',
    impact: 'Enabled discourages duplicate-line edges. Disabled ignores graph reachability redundancy.',
    default: 'On',
    example: 'Keep on — prevents the ranker from suggesting redundant edges that add no new information.',
    range: 'On / Off',
  },
  'kmig.ranking_weight': {
    definition: 'How strongly the Katz marginal-information-gain signal contributes.',
    impact: 'Higher values punish "we already have a path there" more aggressively.',
    default: '0.05',
    example: '0.05 is the Salton-Buckley magnitude band. Raise to 0.10 on densely-linked sites.',
    range: '0 to 0.15',
  },
  'kmig.attenuation': {
    definition: 'Katz attenuation β for the 2-hop reachability sum.',
    impact: 'Lower β emphasises direct edges; higher β weights 2-hop paths more.',
    default: '0.5',
    example: 'Pigueiral 2017 validates 0.5 for truncated Katz. Only tune if you fully understand Katz centrality.',
    range: '0.1 to 0.9',
  },
  'kmig.max_hops': {
    definition: 'Max path length used in the truncated Katz sum. Higher values blow RAM; we truncate at 2.',
    impact: 'Raising above 2 makes the signal much slower with minimal score impact.',
    default: '2',
    example: 'Leave at 2. Raising to 3 roughly 15x the per-pipeline RAM cost for a 50k-node graph.',
    range: '1 to 3',
  },
  // FR-101 Tarjan Articulation Point Boost (TAPB)
  'tapb.enabled': {
    definition: 'FR-101 TAPB: boosts candidates whose host is a structural cut vertex (articulation point).',
    impact: 'Enabled rewards hosts that bridge otherwise-disconnected graph regions. Disabled ignores cut-vertex topology.',
    default: 'On',
    example: 'Leave on — articulation-point hosts are rare (~5-8%) so the boost rarely fires but is valuable when it does.',
    range: 'On / Off',
  },
  'tapb.ranking_weight': {
    definition: 'How much the cut-vertex host boost contributes.',
    impact: 'Higher values strongly reward bridge-style hosts.',
    default: '0.03',
    example: '0.03 matches link_farm magnitude band for rare-event structural signals.',
    range: '0 to 0.10',
  },
  'tapb.apply_to_articulation_node_only': {
    definition: 'When on, only exact articulation points trigger the boost; off enables a graded boost on near-articulation nodes.',
    impact: 'On keeps the signal conservative. Off (future option) would widen the boost.',
    default: 'On',
    example: 'Keep on for v1. The graded variant is a future extension.',
    range: 'On / Off',
  },
  // FR-102 K-Core Integration Boost (KCIB)
  'kcib.enabled': {
    definition: 'FR-102 KCIB: rewards links from high-kcore hosts to low-kcore destinations, pulling peripheral pages into the core.',
    impact: 'Enabled actively integrates peripheral content. Disabled leaves the graph topology alone.',
    default: 'On',
    example: 'Keep on — especially useful for sites with deep long-tail content that rarely gets linked.',
    range: 'On / Off',
  },
  'kcib.ranking_weight': {
    definition: 'How strongly the k-core integration boost contributes.',
    impact: 'Higher values more aggressively pull peripheral pages into the core.',
    default: '0.03',
    example: '0.03 matches the link_farm rarity magnitude band.',
    range: '0 to 0.10',
  },
  'kcib.min_kcore_spread': {
    definition: 'Minimum host.kcore - dest.kcore gap needed to fire the boost.',
    impact: 'Lower values let smaller core-gaps trigger; higher values restrict the boost to clearly hub-to-periphery links.',
    default: '1',
    example: '1 is the smallest meaningful step. Raise to 3 to only reward big integration jumps.',
    range: '1 to 10',
  },
  // FR-103 Bridge-Edge Redundancy Penalty (BERP)
  'berp.enabled': {
    definition: 'FR-103 BERP: penalises candidates where host->dest would become a new bridge edge (fragile single-path connector).',
    impact: 'Enabled discourages creating structural single points of failure. Disabled ignores bridge-edge topology.',
    default: 'On',
    example: 'Leave on — multi-path resilience is generally healthier than narrow bridges.',
    range: 'On / Off',
  },
  'berp.ranking_weight': {
    definition: 'How strongly the would-be-bridge penalty subtracts from the score.',
    impact: 'Higher values punish would-be bridges harder.',
    default: '0.04',
    example: '0.04 matches the keyword_stuffing penalty magnitude.',
    range: '0 to 0.15',
  },
  'berp.min_component_size': {
    definition: 'Minimum biconnected-component size before the penalty fires. Smaller components are treated as noise.',
    impact: 'Higher values keep the penalty restricted to meaningfully-large components.',
    default: '5',
    example: 'Seidman 1983 small-component discussion. Raise to 10 on very small sites.',
    range: '2 to 20',
  },
  // FR-104 Host-Graph Topic Entropy Boost (HGTE)
  'hgte.enabled': {
    definition: 'FR-104 HGTE: rewards candidates that increase the Shannon entropy of the host\'s outbound silo distribution.',
    impact: 'Enabled diversifies host portfolios. Disabled ignores portfolio topic-distribution health.',
    default: 'On',
    example: 'Keep on to prevent hosts from becoming topically monotone over time.',
    range: 'On / Off',
  },
  'hgte.ranking_weight': {
    definition: 'How strongly the entropy-delta boost contributes.',
    impact: 'Higher values strongly reward diversifying links.',
    default: '0.04',
    example: '0.04 matches the rare_term_propagation magnitude band.',
    range: '0 to 0.10',
  },
  'hgte.min_host_out_degree': {
    definition: 'Minimum number of outbound links the host must have before entropy is computed at all (too few links = noisy entropy).',
    impact: 'Higher values mean only well-linked hosts trigger the signal.',
    default: '3',
    example: 'Shannon 1948 asymptotic reliability discussion. 3 is the minimum meaningful.',
    range: '2 to 10',
  },
  // FR-105 Reverse Search-Query Vocabulary Alignment (RSQVA)
  'rsqva.enabled': {
    definition: 'FR-105 RSQVA: TF-IDF cosine between host\'s and destination\'s GSC query vocabularies. High overlap = same search intent.',
    impact: 'Enabled rewards user-intent-aligned pairs even when body text differs. Disabled ignores GSC query vocabularies.',
    default: 'On',
    example: 'Keep on — this catches topically-related pairs that embeddings miss.',
    range: 'On / Off',
  },
  'rsqva.ranking_weight': {
    definition: 'How strongly GSC query-vocabulary alignment contributes.',
    impact: 'Higher values treat GSC query overlap as a stronger relevance signal.',
    default: '0.05',
    example: '0.05 matches the ga4_gsc magnitude band.',
    range: '0 to 0.15',
  },
  'rsqva.min_queries_per_page': {
    definition: 'Minimum GSC queries a page must have to participate in the alignment signal.',
    impact: 'Higher values exclude more low-traffic pages; lower values let noisy vocabularies participate.',
    default: '5',
    example: 'Salton-Buckley 1988 §3.2 reliability floor. Below 5 the TF-IDF vector is noise.',
    range: '3 to 20',
  },
  'rsqva.min_query_clicks': {
    definition: 'Minimum clicks a query must have to count in the TF-IDF aggregation.',
    impact: 'Higher values exclude impression-only queries; 1 keeps all converting queries.',
    default: '1',
    example: 'Keep at 1. Järvelin-Kekäläinen 2002 click-weighted CG framework motivates click-gating.',
    range: '1 to 10',
  },
  'rsqva.max_vocab_size': {
    definition: 'Hard cap on the number of distinct query terms tracked per page.',
    impact: 'Larger caps handle broader vocabularies; hashing collisions remain bounded.',
    default: '10000',
    example: 'Leave at 10000. Smaller sites won\'t hit the cap; very large sites benefit from the upper bound.',
    range: '1000 to 50000',
  },
};

const UI_TO_PRESET_KEY: Record<string, string> = {
  'weightedAuthority.ranking_weight': 'weighted_authority.ranking_weight',
  'weightedAuthority.position_bias': 'weighted_authority.position_bias',
  'weightedAuthority.empty_anchor_factor': 'weighted_authority.empty_anchor_factor',
  'weightedAuthority.bare_url_factor': 'weighted_authority.bare_url_factor',
  'weightedAuthority.weak_context_factor': 'weighted_authority.weak_context_factor',
  'weightedAuthority.isolated_context_factor': 'weighted_authority.isolated_context_factor',
  'linkFreshness.ranking_weight': 'link_freshness.ranking_weight',
  'linkFreshness.recent_window_days': 'link_freshness.recent_window_days',
  'linkFreshness.newest_peer_percent': 'link_freshness.newest_peer_percent',
  'linkFreshness.min_peer_count': 'link_freshness.min_peer_count',
  'linkFreshness.w_recent': 'link_freshness.w_recent',
  'linkFreshness.w_growth': 'link_freshness.w_growth',
  'linkFreshness.w_cohort': 'link_freshness.w_cohort',
  'linkFreshness.w_loss': 'link_freshness.w_loss',
  'phraseMatching.ranking_weight': 'phrase_matching.ranking_weight',
  'phraseMatching.enable_anchor_expansion': 'phrase_matching.enable_anchor_expansion',
  'phraseMatching.enable_partial_matching': 'phrase_matching.enable_partial_matching',
  'phraseMatching.context_window_tokens': 'phrase_matching.context_window_tokens',
  'learnedAnchor.ranking_weight': 'learned_anchor.ranking_weight',
  'learnedAnchor.minimum_anchor_sources': 'learned_anchor.minimum_anchor_sources',
  'learnedAnchor.minimum_family_support_share': 'learned_anchor.minimum_family_support_share',
  'learnedAnchor.enable_noise_filter': 'learned_anchor.enable_noise_filter',
  'rareTermPropagation.enabled': 'rare_term_propagation.enabled',
  'rareTermPropagation.ranking_weight': 'rare_term_propagation.ranking_weight',
  'rareTermPropagation.max_document_frequency': 'rare_term_propagation.max_document_frequency',
  'rareTermPropagation.minimum_supporting_related_pages': 'rare_term_propagation.minimum_supporting_related_pages',
  'fieldAwareRelevance.ranking_weight': 'field_aware_relevance.ranking_weight',
  'fieldAwareRelevance.title_field_weight': 'field_aware_relevance.title_field_weight',
  'fieldAwareRelevance.body_field_weight': 'field_aware_relevance.body_field_weight',
  'fieldAwareRelevance.scope_field_weight': 'field_aware_relevance.scope_field_weight',
  'fieldAwareRelevance.learned_anchor_field_weight': 'field_aware_relevance.learned_anchor_field_weight',
  'ga4Gsc.ranking_weight': 'ga4_gsc.ranking_weight',
  'clickDistance.ranking_weight': 'click_distance.ranking_weight',
  'clickDistance.k_cd': 'click_distance.k_cd',
  'clickDistance.b_cd': 'click_distance.b_cd',
  'clickDistance.b_ud': 'click_distance.b_ud',
  'silo.mode': 'silo.mode',
  'silo.same_silo_boost': 'silo.same_silo_boost',
  'silo.cross_silo_penalty': 'silo.cross_silo_penalty',
  'feedbackRerank.enabled': 'explore_exploit.enabled',
  'feedbackRerank.ranking_weight': 'explore_exploit.ranking_weight',
  'feedbackRerank.exploration_rate': 'explore_exploit.exploration_rate',
  'clustering.enabled': 'clustering.enabled',
  'clustering.similarity_threshold': 'clustering.similarity_threshold',
  'clustering.suppression_penalty': 'clustering.suppression_penalty',
  'slateDiversity.enabled': 'slate_diversity.enabled',
  'slateDiversity.diversity_lambda': 'slate_diversity.diversity_lambda',
  'slateDiversity.score_window': 'slate_diversity.score_window',
  'slateDiversity.similarity_cap': 'slate_diversity.similarity_cap',
  // FR-038 — Information Gain Scoring
  'informationGain.enabled': 'information_gain.enabled',
  'informationGain.ranking_weight': 'information_gain.ranking_weight',
  'informationGain.min_source_chars': 'information_gain.min_source_chars',
  // FR-039 — Entity Salience Match
  'entitySalience.enabled': 'entity_salience.enabled',
  'entitySalience.ranking_weight': 'entity_salience.ranking_weight',
  'entitySalience.max_salient_terms': 'entity_salience.max_salient_terms',
  'entitySalience.max_site_document_frequency': 'entity_salience.max_site_document_frequency',
  'entitySalience.min_source_term_frequency': 'entity_salience.min_source_term_frequency',
  // FR-040 - Multimedia Boost
  'multimediaSignal.enabled': 'multimedia_signal_enabled',
  'multimediaSignal.ranking_weight': 'w_multimedia',
  'multimediaSignal.fallback_value': 'multimedia_fallback_value',
  // FR-041 - Originality Provenance Scoring
  'originalityProvenance.enabled': 'originality_provenance.enabled',
  'originalityProvenance.ranking_weight': 'originality_provenance.ranking_weight',
  'originalityProvenance.resemblance_threshold': 'originality_provenance.resemblance_threshold',
  'originalityProvenance.containment_threshold': 'originality_provenance.containment_threshold',
  // FR-042 - Fact Density Scoring
  'factDensity.enabled': 'fact_density.enabled',
  'factDensity.ranking_weight': 'fact_density.ranking_weight',
  'factDensity.min_word_count': 'fact_density.min_word_count',
  'factDensity.density_cap_per_100_words': 'fact_density.density_cap_per_100_words',
  'factDensity.filler_penalty_weight': 'fact_density.filler_penalty_weight',
  // FR-043 - Semantic Drift Penalty
  'semanticDrift.enabled': 'semantic_drift.enabled',
  'semanticDrift.ranking_weight': 'semantic_drift.ranking_weight',
  'semanticDrift.tokens_per_sequence': 'semantic_drift.tokens_per_sequence',
  'semanticDrift.block_size_in_sequences': 'semantic_drift.block_size_in_sequences',
  'semanticDrift.anchor_similarity_threshold': 'semantic_drift.anchor_similarity_threshold',
  'semanticDrift.min_word_count': 'semantic_drift.min_word_count',
  // FR-044 - Internal Search Intensity Signal
  'internalSearch.enabled': 'internal_search.enabled',
  'internalSearch.ranking_weight': 'internal_search.ranking_weight',
  'internalSearch.recent_days': 'internal_search.recent_days',
  'internalSearch.baseline_days': 'internal_search.baseline_days',
  'internalSearch.max_active_queries': 'internal_search.max_active_queries',
  'internalSearch.min_recent_count': 'internal_search.min_recent_count',
  // FR-045 — Anchor Diversity & Exact-Match Reuse Guard
  'anchorDiversity.enabled': 'anchor_diversity.enabled',
  'anchorDiversity.ranking_weight': 'anchor_diversity.ranking_weight',
  'anchorDiversity.min_history_count': 'anchor_diversity.min_history_count',
  'anchorDiversity.max_exact_match_share': 'anchor_diversity.max_exact_match_share',
  'anchorDiversity.max_exact_match_count': 'anchor_diversity.max_exact_match_count',
  'anchorDiversity.hard_cap_enabled': 'anchor_diversity.hard_cap_enabled',
  // FR-046 — Multi-Query Fan-Out for Stage 1 Retrieval
  'keywordStuffing.enabled': 'keyword_stuffing.enabled',
  'keywordStuffing.ranking_weight': 'keyword_stuffing.ranking_weight',
  'keywordStuffing.alpha': 'keyword_stuffing.alpha',
  'keywordStuffing.tau': 'keyword_stuffing.tau',
  'keywordStuffing.dirichlet_mu': 'keyword_stuffing.dirichlet_mu',
  'keywordStuffing.top_k_stuff_terms': 'keyword_stuffing.top_k_stuff_terms',
  'linkFarm.enabled': 'link_farm.enabled',
  'linkFarm.ranking_weight': 'link_farm.ranking_weight',
  'linkFarm.min_scc_size': 'link_farm.min_scc_size',
  'linkFarm.density_threshold': 'link_farm.density_threshold',
  'linkFarm.lambda': 'link_farm.lambda',
  'fanOut.enabled': 'fan_out.enabled',
  'fanOut.max_sub_queries': 'fan_out.max_sub_queries',
  'fanOut.min_segment_words': 'fan_out.min_segment_words',
  'fanOut.rrf_k': 'fan_out.rrf_k',
  // FR-047 — Navigation Path Prediction
  'navigationPath.enabled': 'navigation_path.enabled',
  'navigationPath.ranking_weight': 'navigation_path.ranking_weight',
  'navigationPath.lookback_days': 'navigation_path.lookback_days',
  'navigationPath.min_sessions': 'navigation_path.min_sessions',
  'navigationPath.min_transition_count': 'navigation_path.min_transition_count',
  'navigationPath.w_direct': 'navigation_path.w_direct',
  'navigationPath.w_shortcut': 'navigation_path.w_shortcut',
  // FR-048 — Topical Authority Cluster Density
  'topicalCluster.enabled': 'topical_cluster.enabled',
  'topicalCluster.ranking_weight': 'topical_cluster.ranking_weight',
  'topicalCluster.min_cluster_size': 'topical_cluster.min_cluster_size',
  'topicalCluster.min_site_pages': 'topical_cluster.min_site_pages',
  'topicalCluster.max_staleness_days': 'topical_cluster.max_staleness_days',
  'topicalCluster.fallback_value': 'topical_cluster.fallback_value',
  // FR-049 — Query Intent Funnel Alignment
  'intentFunnel.enabled': 'intent_funnel.enabled',
  'intentFunnel.ranking_weight': 'intent_funnel.ranking_weight',
  'intentFunnel.optimal_offset': 'intent_funnel.optimal_offset',
  'intentFunnel.sigma': 'intent_funnel.sigma',
  'intentFunnel.min_confidence': 'intent_funnel.min_confidence',
  'intentFunnel.navigational_confidence_threshold': 'intent_funnel.navigational_confidence_threshold',
  // FR-050 — Seasonality & Temporal Demand Matching
  'seasonality.enabled': 'seasonality.enabled',
  'seasonality.ranking_weight': 'seasonality.ranking_weight',
  'seasonality.min_history_months': 'seasonality.min_history_months',
  'seasonality.min_seasonal_strength': 'seasonality.min_seasonal_strength',
  'seasonality.anticipation_window_months': 'seasonality.anticipation_window_months',
  'seasonality.w_current': 'seasonality.w_current',
  'seasonality.w_anticipation': 'seasonality.w_anticipation',
  'seasonality.index_cap': 'seasonality.index_cap',
  // FR-099 DARB
  'darb.enabled': 'darb.enabled',
  'darb.ranking_weight': 'darb.ranking_weight',
  'darb.out_degree_saturation': 'darb.out_degree_saturation',
  'darb.min_host_value': 'darb.min_host_value',
  // FR-100 KMIG
  'kmig.enabled': 'kmig.enabled',
  'kmig.ranking_weight': 'kmig.ranking_weight',
  'kmig.attenuation': 'kmig.attenuation',
  'kmig.max_hops': 'kmig.max_hops',
  // FR-101 TAPB
  'tapb.enabled': 'tapb.enabled',
  'tapb.ranking_weight': 'tapb.ranking_weight',
  'tapb.apply_to_articulation_node_only': 'tapb.apply_to_articulation_node_only',
  // FR-102 KCIB
  'kcib.enabled': 'kcib.enabled',
  'kcib.ranking_weight': 'kcib.ranking_weight',
  'kcib.min_kcore_spread': 'kcib.min_kcore_spread',
  // FR-103 BERP
  'berp.enabled': 'berp.enabled',
  'berp.ranking_weight': 'berp.ranking_weight',
  'berp.min_component_size': 'berp.min_component_size',
  // FR-104 HGTE
  'hgte.enabled': 'hgte.enabled',
  'hgte.ranking_weight': 'hgte.ranking_weight',
  'hgte.min_host_out_degree': 'hgte.min_host_out_degree',
  // FR-105 RSQVA
  'rsqva.enabled': 'rsqva.enabled',
  'rsqva.ranking_weight': 'rsqva.ranking_weight',
  'rsqva.min_queries_per_page': 'rsqva.min_queries_per_page',
  'rsqva.min_query_clicks': 'rsqva.min_query_clicks',
  'rsqva.max_vocab_size': 'rsqva.max_vocab_size',
};

const ALERT_THRESHOLDS: Record<string, { warnBelow?: number; warnAbove?: number; dangerBelow?: number; dangerAbove?: number }> = {
  'weightedAuthority.ranking_weight': { warnAbove: 0.18, dangerAbove: 0.22 },
  'weightedAuthority.position_bias': { warnBelow: 0.1, warnAbove: 0.9, dangerBelow: 0.05, dangerAbove: 0.96 },
  'weightedAuthority.empty_anchor_factor': { warnBelow: 0.2, warnAbove: 0.95, dangerBelow: 0.12, dangerAbove: 0.99 },
  'weightedAuthority.bare_url_factor': { warnBelow: 0.15, warnAbove: 0.9, dangerBelow: 0.1, dangerAbove: 0.96 },
  'weightedAuthority.weak_context_factor': { warnBelow: 0.2, warnAbove: 0.95, dangerBelow: 0.12, dangerAbove: 0.99 },
  'weightedAuthority.isolated_context_factor': { warnBelow: 0.15, warnAbove: 0.9, dangerBelow: 0.1, dangerAbove: 0.96 },
  'linkFreshness.ranking_weight': { warnAbove: 0.1, dangerAbove: 0.13 },
  'linkFreshness.recent_window_days': { warnBelow: 14, warnAbove: 60, dangerBelow: 10, dangerAbove: 80 },
  'linkFreshness.newest_peer_percent': { warnAbove: 0.45, dangerAbove: 0.49 },
  'linkFreshness.min_peer_count': { warnAbove: 15, dangerAbove: 18 },
  'linkFreshness.w_recent': { warnAbove: 0.65, dangerAbove: 0.85 },
  'linkFreshness.w_growth': { warnAbove: 0.65, dangerAbove: 0.85 },
  'linkFreshness.w_cohort': { warnAbove: 0.45, dangerAbove: 0.65 },
  'linkFreshness.w_loss': { warnAbove: 0.25, dangerAbove: 0.4 },
  'phraseMatching.ranking_weight': { warnAbove: 0.08, dangerAbove: 0.095 },
  'phraseMatching.context_window_tokens': { warnBelow: 5, warnAbove: 11, dangerBelow: 4, dangerAbove: 12 },
  'learnedAnchor.ranking_weight': { warnAbove: 0.08, dangerAbove: 0.095 },
  'learnedAnchor.minimum_anchor_sources': { warnAbove: 8, dangerAbove: 10 },
  'learnedAnchor.minimum_family_support_share': { warnAbove: 0.4, dangerAbove: 0.48 },
  'rareTermPropagation.ranking_weight': { warnAbove: 0.08, dangerAbove: 0.095 },
  'rareTermPropagation.max_document_frequency': { warnAbove: 7, dangerAbove: 9 },
  'rareTermPropagation.minimum_supporting_related_pages': { warnAbove: 3, dangerAbove: 4 },
  'fieldAwareRelevance.ranking_weight': { warnAbove: 0.12, dangerAbove: 0.145 },
  'fieldAwareRelevance.title_field_weight': { warnAbove: 0.65, dangerAbove: 0.85 },
  'fieldAwareRelevance.body_field_weight': { warnAbove: 0.65, dangerAbove: 0.85 },
  'fieldAwareRelevance.scope_field_weight': { warnAbove: 0.4, dangerAbove: 0.6 },
  'fieldAwareRelevance.learned_anchor_field_weight': { warnAbove: 0.4, dangerAbove: 0.6 },
  'ga4Gsc.ranking_weight': { warnAbove: 0.12, dangerAbove: 0.2 },
  'clickDistance.ranking_weight': { warnAbove: 0.15, dangerAbove: 0.18 },
  'clickDistance.k_cd': { warnBelow: 2.0, warnAbove: 5.0, dangerBelow: 1.0, dangerAbove: 5.8 },
  'clickDistance.b_cd': { warnBelow: 0.4, warnAbove: 0.9, dangerBelow: 0.2, dangerAbove: 0.97 },
  'clickDistance.b_ud': { warnAbove: 0.5, dangerAbove: 0.75 },
  'feedbackRerank.ranking_weight': { warnAbove: 0.15, dangerAbove: 0.3 },
  'feedbackRerank.exploration_rate': { warnBelow: 0.7, warnAbove: 2.5, dangerBelow: 0.4, dangerAbove: 4.0 },
  'silo.same_silo_boost': { warnAbove: 0.4, dangerAbove: 0.8 },
  'silo.cross_silo_penalty': { warnAbove: 0.4, dangerAbove: 0.8 },
  'clustering.similarity_threshold': { warnAbove: 0.1, dangerAbove: 0.135 },
  'clustering.suppression_penalty': { warnBelow: 5, warnAbove: 30, dangerBelow: 2, dangerAbove: 40 },
  'slateDiversity.diversity_lambda': { warnBelow: 0.4, dangerBelow: 0.2 },
  'slateDiversity.score_window': { warnAbove: 0.6, dangerAbove: 0.85 },
  'slateDiversity.similarity_cap': { warnBelow: 0.75, dangerBelow: 0.71 },
  // FR-038 — Information Gain Scoring
  'informationGain.ranking_weight': { warnAbove: 0.08, dangerAbove: 0.10 },
  'informationGain.min_source_chars': { warnBelow: 80, dangerBelow: 50 },
  // FR-039 — Entity Salience Match
  'entitySalience.ranking_weight': { warnAbove: 0.08, dangerAbove: 0.10 },
  'entitySalience.max_salient_terms': { warnAbove: 20, dangerAbove: 24 },
  'entitySalience.max_site_document_frequency': { warnAbove: 60, dangerAbove: 80 },
  // FR-040 - Multimedia Boost
  'multimediaSignal.ranking_weight': { warnAbove: 0.15, dangerAbove: 0.20 },
  'multimediaSignal.fallback_value': { warnBelow: 0.4, warnAbove: 0.6, dangerBelow: 0.25, dangerAbove: 0.75 },
  // FR-041 - Originality Provenance Scoring
  'originalityProvenance.ranking_weight': { warnAbove: 0.08, dangerAbove: 0.10 },
  'originalityProvenance.resemblance_threshold': { warnBelow: 0.40, warnAbove: 0.75, dangerBelow: 0.25, dangerAbove: 0.90 },
  'originalityProvenance.containment_threshold': { warnBelow: 0.65, dangerAbove: 0.92 },
  // FR-042 - Fact Density Scoring
  'factDensity.ranking_weight': { warnAbove: 0.08, dangerAbove: 0.10 },
  'factDensity.min_word_count': { warnBelow: 80, warnAbove: 250, dangerBelow: 50, dangerAbove: 350 },
  'factDensity.density_cap_per_100_words': { warnBelow: 4, warnAbove: 12, dangerBelow: 2, dangerAbove: 18 },
  'factDensity.filler_penalty_weight': { warnAbove: 0.65, dangerAbove: 0.85 },
  // FR-043 - Semantic Drift Penalty
  'semanticDrift.ranking_weight': { warnAbove: 0.06, dangerAbove: 0.10 },
  'semanticDrift.tokens_per_sequence': { warnBelow: 12, warnAbove: 40, dangerBelow: 8, dangerAbove: 60 },
  'semanticDrift.block_size_in_sequences': { warnBelow: 4, warnAbove: 10, dangerBelow: 2, dangerAbove: 14 },
  'semanticDrift.anchor_similarity_threshold': { warnBelow: 0.10, warnAbove: 0.30, dangerBelow: 0.05, dangerAbove: 0.40 },
  'semanticDrift.min_word_count': { warnBelow: 120, warnAbove: 320, dangerBelow: 80, dangerAbove: 500 },
  // FR-044 - Internal Search Intensity Signal
  'internalSearch.ranking_weight': { warnAbove: 0.05, dangerAbove: 0.08 },
  'internalSearch.recent_days': { warnBelow: 2, warnAbove: 7, dangerBelow: 1, dangerAbove: 14 },
  'internalSearch.baseline_days': { warnBelow: 14, warnAbove: 60, dangerBelow: 7, dangerAbove: 90 },
  'internalSearch.max_active_queries': { warnAbove: 400, dangerAbove: 800 },
  'internalSearch.min_recent_count': { warnAbove: 8, dangerAbove: 12 },
  // FR-045 — Anchor Diversity & Exact-Match Reuse Guard
  'anchorDiversity.ranking_weight': { warnAbove: 0.10, dangerAbove: 0.15 },
  'anchorDiversity.max_exact_match_share': { warnBelow: 0.25, warnAbove: 0.75, dangerBelow: 0.20, dangerAbove: 0.90 },
  'anchorDiversity.max_exact_match_count': { warnAbove: 7, dangerAbove: 10 },
  // FR-046 — Multi-Query Fan-Out for Stage 1 Retrieval
  'keywordStuffing.ranking_weight': { warnAbove: 0.10, dangerAbove: 0.15 },
  'keywordStuffing.alpha': { warnAbove: 10, dangerAbove: 15 },
  'keywordStuffing.tau': { warnBelow: 0.15, warnAbove: 0.80, dangerBelow: 0.10, dangerAbove: 1.20 },
  'keywordStuffing.dirichlet_mu': { warnBelow: 500, warnAbove: 8000, dangerBelow: 250, dangerAbove: 12000 },
  'keywordStuffing.top_k_stuff_terms': { warnAbove: 10, dangerAbove: 15 },
  'linkFarm.ranking_weight': { warnAbove: 0.10, dangerAbove: 0.15 },
  'linkFarm.min_scc_size': { warnBelow: 3, warnAbove: 20, dangerAbove: 40 },
  'linkFarm.density_threshold': { warnBelow: 0.35, warnAbove: 0.85, dangerBelow: 0.20, dangerAbove: 0.95 },
  'linkFarm.lambda': { warnAbove: 1.5, dangerAbove: 2.5 },
  'fanOut.max_sub_queries': { warnAbove: 4, dangerAbove: 5 },
  'fanOut.min_segment_words': { warnBelow: 25, warnAbove: 150, dangerBelow: 20, dangerAbove: 200 },
  'fanOut.rrf_k': { warnBelow: 15, warnAbove: 100, dangerBelow: 10, dangerAbove: 120 },
  // FR-047 — Navigation Path Prediction
  'navigationPath.ranking_weight': { warnAbove: 0.08, dangerAbove: 0.12 },
  'navigationPath.lookback_days': { warnBelow: 14, warnAbove: 180, dangerBelow: 7, dangerAbove: 365 },
  'navigationPath.min_sessions': { warnBelow: 10, warnAbove: 200, dangerBelow: 5, dangerAbove: 500 },
  'navigationPath.min_transition_count': { warnAbove: 20, dangerAbove: 40 },
  // FR-048 — Topical Authority Cluster Density
  'topicalCluster.ranking_weight': { warnAbove: 0.08, dangerAbove: 0.12 },
  'topicalCluster.min_cluster_size': { warnBelow: 3, warnAbove: 25, dangerBelow: 2, dangerAbove: 50 },
  'topicalCluster.max_staleness_days': { warnBelow: 3, warnAbove: 60, dangerBelow: 1, dangerAbove: 90 },
  // FR-049 — Query Intent Funnel Alignment
  'intentFunnel.ranking_weight': { warnAbove: 0.06, dangerAbove: 0.10 },
  'intentFunnel.sigma': { warnBelow: 0.5, warnAbove: 2.5, dangerBelow: 0.3, dangerAbove: 3.0 },
  'intentFunnel.min_confidence': { warnAbove: 0.7, dangerAbove: 0.85 },
  // FR-050 — Seasonality & Temporal Demand Matching
  'seasonality.ranking_weight': { warnAbove: 0.06, dangerAbove: 0.10 },
  'seasonality.min_history_months': { warnBelow: 8, dangerBelow: 6 },
  'seasonality.min_seasonal_strength': { warnAbove: 0.6, dangerAbove: 0.8 },
  'seasonality.index_cap': { warnBelow: 2.0, warnAbove: 6.0, dangerBelow: 1.5, dangerAbove: 10.0 },
};

@Component({
  selector: 'app-settings',
  standalone: true,
  templateUrl: './settings.component.html',
  styleUrls: ['./settings.component.scss'],
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatCardModule,
    MatCheckboxModule,
    MatChipsModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatSelectModule,
    MatSnackBarModule,
    MatTabsModule,
    MatTooltipModule,
    MatDividerModule,
    MatProgressSpinnerModule,
    DatePipe,
    WeightDiagnosticsCardComponent,
    PerformanceSettingsComponent,
    HelpersSettingsComponent,
    MetaAlgorithmsTabComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SettingsComponent implements OnInit, OnDestroy, HasUnsavedChanges {
  private siloSvc = inject(SiloSettingsService);
  private notifSvc = inject(NotificationService);
  desktopSvc = inject(DesktopNotificationService);
  private audioSvc = inject(AudioCueService);
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
  private readonly _settingsRuntimeUpdates$ = new Subject<void>();
  private destroy$ = new Subject<void>();

  loading = true;
  isDirty = false;
  savingSettings = false;
  savingWeightedAuthority = false;
  savingLinkFreshness = false;
  savingPhraseMatching = false;
  savingLearnedAnchor = false;
  savingRareTermPropagation = false;
  savingFieldAwareRelevance = false;
  savingGA4GSC = false;

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
  savingClickDistance = false;
  savingFeedbackRerank = false;
  savingClustering = false;
  savingSlate = false;
  savingXenForo = false;
  savingWordPress = false;
  savingWebhooks = false;
  recalculatingWeightedAuthority = false;
  recalculatingLinkFreshness = false;
  recalculatingClickDistance = false;
  recalculatingClustering = false;
  runningWordPressSync = false;
  creatingGroup = false;
  savingGA4Telemetry = false;
  savingMatomoTelemetry = false;
  testingGA4Telemetry = false;
  testingGA4TelemetryRead = false;
  testingMatomoTelemetry = false;
  testingGSCConnection = false;
  testingXenForo = false;
  testingWordPress = false;
  testingWebhooks = false;
  runningGSCSync = false;
  savingGoogleAuth = false;
  savingNotifPrefs = false;
  testingNotification = false;

  // ── Crawler settings ──────────────────────────────────────────
  crawlerExcludedPaths: string[] = [
    '/members/', '/login/', '/register/', '/account/',
    '/search/', '/admin.php', '/help/',
  ];
  newCrawlerExclusion = '';

  notifPrefs: NotificationPreferences = {
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
  };

  // Tab persistence
  selectedTabIndex = Number(localStorage.getItem('settings_active_tab') || '0');

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
    same_silo_boost: 0.10, // Increased from 0.05 to match research
    cross_silo_penalty: 0.10, // Increased from 0.05 to match research
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
    title_field_weight: 0.4,
    body_field_weight: 0.3,
    scope_field_weight: 0.15,
    learned_anchor_field_weight: 0.15,
  };

  private readonly DEFAULT_HEALTH = {
    status: 'stale',
    label: 'Pending check',
    name: '',
    description: '',
    issue: '',
    fix: '',
    last_success: null,
    is_healthy: false
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
  gscPrivateKey = '';
  gscManualBackfillDays = 180;
  googleAuthClientId = '';
  googleAuthClientSecret = '';
  googleOAuth: GoogleOAuthSettings = {
    client_id: '',
    client_secret_configured: false,
    oauth_connected: false,
    status: 'not_configured',
    message: 'Paste the Google OAuth client ID and secret once, then sign in once.',
    last_sync: null,
  };
  showGA4FallbackFields = false;
  showGSCFallbackFields = false;
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
  ga4TelemetrySecret = '';
  ga4TelemetryReadPrivateKey = '';
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
  savingSpamGuards = false;
  anchorDiversity: AnchorDiversitySettings = {
    enabled: true,
    ranking_weight: 0.03,
    min_history_count: 3,
    max_exact_match_share: 0.4,
    max_exact_match_count: 3,
    hard_cap_enabled: false,
  };
  savingAnchorDiversity = false;
  keywordStuffing: KeywordStuffingSettings = {
    enabled: true,
    ranking_weight: 0.04,
    alpha: 6.0,
    tau: 0.3,
    dirichlet_mu: 2000,
    top_k_stuff_terms: 5,
  };
  savingKeywordStuffing = false;
  linkFarm: LinkFarmSettings = {
    enabled: true,
    ranking_weight: 0.03,
    min_scc_size: 3,
    density_threshold: 0.6,
    lambda: 0.8,
  };
  savingLinkFarm = false;
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
    score_window: 0.30,
    similarity_cap: 0.90,
  };
  // Group C — Stage-1 candidate-retriever flags.
  // Default off; flipping either on activates RRF fusion (pick #31).
  // See backend/apps/pipeline/services/candidate_retrievers.py.
  stage1Retrievers: Stage1RetrieverSettings = {
    lexical_retriever_enabled: false,
    query_expansion_retriever_enabled: false,
  };
  savingStage1Retrievers = false;

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
  savingPhase6Picks = false;

  // FR-099 through FR-105 — graph-topology ranking signals.
  // See docs/specs/fr099-*.md through docs/specs/fr105-*.md.
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
  xenforo: XenForoSettings = {
    base_url: '',
    api_key_configured: false,
    health: this.DEFAULT_HEALTH,
  };
  xfApiKey = '';

  wordpress: WordPressSettings = {
    base_url: '',
    username: '',
    app_password_configured: false,
    sync_enabled: false,
    sync_hour: 3,
    sync_minute: 0,
    health: this.DEFAULT_HEALTH,
  };
  wordpressPassword = '';

  webhookSettings: WebhookSettings = { xf_secret_configured: false, wp_secret_configured: false };
  xfWebhookSecret = '';
  wpWebhookSecret = '';

  // Weight presets
  weightPresets: WeightPreset[] = [];
  loadingPresets = false;
  applyingPreset = false;
  savingPreset = false;
  deletingPreset = false;
  renamingPresetId: number | null = null;
  newPresetName = '';
  renamePresetValue = '';
  showSavePresetInput = false;

  // Weight history
  weightHistory: WeightAdjustmentHistory[] = [];
  challengers: RankingChallenger[] = [];
  loadingChallengers = false;
  triggeringWeightTune = false;
  evaluatingChallenger = false;
  loadingHistory = false;
  rollingBack = false;
  currentWeights: Record<string, string> = {};

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

  get recommendedPreset(): WeightPreset | null {
    return this.weightPresets.find((preset) => preset.is_system && preset.name.toLowerCase().includes('recommended')) ?? null;
  }

  get noSourceConnected(): boolean {
    return !this.xenforo.health.is_healthy && !this.wordpress.health.is_healthy;
  }

  hasUnsavedChanges(): boolean {
    return this.isDirty;
  }

  markDirty(): void {
    this.isDirty = true;
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
    if (!t) return `No tooltip defined for "${key}" - add an entry to SETTING_TOOLTIPS in settings.component.ts`;
    
    const lines: string[] = [];
    
    // Add dynamic severity alerts
    const currentValue = this.valueFor(key);
    if (typeof currentValue === 'number') {
      const severity = this.fieldSeverity(currentValue, key);
      if (severity === 'warn') {
        lines.push('⚠️ AMBER ALERT: This value is unusually strong. Monitor closely for over-optimized links.');
      }
      if (severity === 'danger') {
        lines.push('🚨 RED ALERT: This value is in the risky range! It may cause unnatural link patterns.');
      }
    }

    lines.push(`DEFINITION: ${t.definition}`);
    lines.push(`IMPACT: ${t.impact}`);
    lines.push(`RECOMMENDED: ${this.recommendedValueLabel(key) ?? t.default}`);
    lines.push(`EXAMPLE: ${t.example}`);
    lines.push(`VALID RANGE: ${t.range}`);
    
    return lines.join('\n\n');
  }

  valueFor(key: string): any {
    const parts = key.split('.');
    if (parts.length !== 2) return null;
    const [section, field] = parts;
    return (this as any)[section]?.[field];
  }

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

  telemetryStatusLabel(status: string): string {
    return {
      connected: 'Connected',
      saved: 'Saved',
      error: 'Error',
      not_configured: 'Not set up',
    }[status] ?? 'Unknown';
  }

  telemetryStatusClass(status: string): string {
    return `status-pill--${status === 'connected' || status === 'healthy' ? 'success' : (status === 'error' || status === 'down') ? 'danger' : (status === 'warning' || status === 'stale') ? 'warning' : status === 'saved' ? 'status' : 'muted'}`;
  }

  getHealthIcon(status: string): string {
    switch (status) {
      case 'healthy': return 'check_circle';
      case 'warning': return 'warning';
      case 'error':   return 'error';
      case 'down':    return 'dangerous';
      case 'stale':   return 'update';
      default:        return 'help_outline';
    }
  }

  lastSyncLabel(sync: { completed_at: string | null; started_at: string | null; rows_written: number } | null): string {
    if (!sync) return 'Never synced';
    const stamp = sync.completed_at || sync.started_at;
    if (!stamp) return `${sync.rows_written} rows written`;
    return `${new Date(stamp).toLocaleString()} • ${sync.rows_written} rows written`;
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

  saveGoogleAuthSettings(): void {
    this.savingGoogleAuth = true;
    const payload: { client_id: string; client_secret?: string } = {
      client_id: this.googleAuthClientId.trim(),
    };
    if (this.googleAuthClientSecret.trim()) {
      payload.client_secret = this.googleAuthClientSecret.trim();
    }
    this.siloSvc.updateGoogleOAuthSettings(payload).pipe(takeUntil(this.destroy$), this.markForCheckOnComplete()).subscribe({
      next: (googleOAuth) => {
        this.googleOAuth = googleOAuth;
        this.googleAuthClientId = googleOAuth.client_id;
        this.googleAuthClientSecret = '';
        this.ga4Telemetry = {
          ...this.ga4Telemetry,
          google_oauth_client_id: googleOAuth.client_id,
          google_oauth_client_secret_configured: googleOAuth.client_secret_configured,
          oauth_connected: googleOAuth.oauth_connected,
        };
        this.ga4Gsc = {
          ...this.ga4Gsc,
          oauth_connected: googleOAuth.oauth_connected,
        };
        this.savingGoogleAuth = false;
        this.snack.open('Google app settings saved.', undefined, { duration: 3000 });
      },
      error: (error) => {
        this.savingGoogleAuth = false;
        this.snack.open(error?.error?.detail || 'Failed to save Google app settings.', 'Dismiss', { duration: 4000 });
      },
    });
  }

  private presetMatchesCurrent(preset: WeightPreset): boolean {
    const presetEntries = Object.entries(preset.weights ?? {});
    if (!presetEntries.length) return false;
    return presetEntries.every(([key, value]) => this.normalizeComparableValue(this.currentWeights[key]) === this.normalizeComparableValue(value));
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
      { label: 'March 2026 PageRank', currentEnabled: this.weightedAuthority.ranking_weight > 0, recommendedEnabled: this.isFeatureEnabledInPreset(recommended, 'weighted_authority.ranking_weight') },
      { label: 'Link Freshness', currentEnabled: this.linkFreshness.ranking_weight > 0, recommendedEnabled: this.isFeatureEnabledInPreset(recommended, 'link_freshness.ranking_weight') },
      { label: 'Phrase Matching', currentEnabled: this.phraseMatching.ranking_weight > 0, recommendedEnabled: this.isFeatureEnabledInPreset(recommended, 'phrase_matching.ranking_weight') },
      { label: 'Learned Anchors', currentEnabled: this.learnedAnchor.ranking_weight > 0, recommendedEnabled: this.isFeatureEnabledInPreset(recommended, 'learned_anchor.ranking_weight') },
      { label: 'Rare-Term Propagation', currentEnabled: this.rareTermPropagation.enabled && this.rareTermPropagation.ranking_weight > 0, recommendedEnabled: this.isFeatureEnabledInPreset(recommended, 'rare_term_propagation.enabled') && this.isFeatureEnabledInPreset(recommended, 'rare_term_propagation.ranking_weight') },
      { label: 'Field-Aware Relevance', currentEnabled: this.fieldAwareRelevance.ranking_weight > 0, recommendedEnabled: this.isFeatureEnabledInPreset(recommended, 'field_aware_relevance.ranking_weight') },
      { label: 'GA4 + Search Console', currentEnabled: this.ga4Gsc.ranking_weight > 0, recommendedEnabled: this.isFeatureEnabledInPreset(recommended, 'ga4_gsc.ranking_weight') },
      { label: 'Click Distance', currentEnabled: this.clickDistance.ranking_weight > 0, recommendedEnabled: this.isFeatureEnabledInPreset(recommended, 'click_distance.ranking_weight') },
      { label: 'Anchor Diversity', currentEnabled: this.anchorDiversity.enabled && this.anchorDiversity.ranking_weight > 0, recommendedEnabled: this.isFeatureEnabledInPreset(recommended, 'anchor_diversity.enabled') && this.isFeatureEnabledInPreset(recommended, 'anchor_diversity.ranking_weight') },
      { label: 'Keyword Stuffing', currentEnabled: this.keywordStuffing.enabled && this.keywordStuffing.ranking_weight > 0, recommendedEnabled: this.isFeatureEnabledInPreset(recommended, 'keyword_stuffing.enabled') && this.isFeatureEnabledInPreset(recommended, 'keyword_stuffing.ranking_weight') },
      { label: 'Link-Farm Detection', currentEnabled: this.linkFarm.enabled && this.linkFarm.ranking_weight > 0, recommendedEnabled: this.isFeatureEnabledInPreset(recommended, 'link_farm.enabled') && this.isFeatureEnabledInPreset(recommended, 'link_farm.ranking_weight') },
      { label: 'Silo Ranking', currentEnabled: this.settings.mode !== 'disabled', recommendedEnabled: this.isFeatureEnabledInPreset(recommended, 'silo.mode') },
      { label: 'Feedback Reranking', currentEnabled: this.feedbackRerank.enabled && this.feedbackRerank.ranking_weight > 0, recommendedEnabled: this.isFeatureEnabledInPreset(recommended, 'explore_exploit.enabled') && this.isFeatureEnabledInPreset(recommended, 'explore_exploit.ranking_weight') },
      { label: 'Near-Duplicate Clustering', currentEnabled: this.clustering.enabled, recommendedEnabled: this.isFeatureEnabledInPreset(recommended, 'clustering.enabled') },
      { label: 'Slate Diversity', currentEnabled: this.slateDiversity.enabled, recommendedEnabled: this.isFeatureEnabledInPreset(recommended, 'slate_diversity.enabled') },
      { label: 'Graph Candidate Generation', currentEnabled: this.graphCandidate.enabled, recommendedEnabled: this.isFeatureEnabledInPreset(recommended, 'graph_candidate.enabled') },
      { label: 'Value Model Scoring', currentEnabled: this.valueModel.enabled, recommendedEnabled: this.isFeatureEnabledInPreset(recommended, 'value_model.enabled') },
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
    this.route.fragment.pipe(takeUntil(this.destroy$), this.markForCheckOnComplete()).subscribe(fragment => {
      if (fragment) {
        this.syncTabWithFragment(fragment);
      }
    });

    this.reload();

    // Phase R1.4 — settings.runtime is staff-only; non-staff users will
    // receive a subscription.ack with denied=["settings.runtime"] and the
    // stream stays silent, which is the intended no-op.
    this.realtime
      .subscribeTopic('settings.runtime')
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe(() => this._settingsRuntimeUpdates$.next());

    // Debounce so a batch save of N AppSetting rows produces ONE reload
    // and ONE snackbar, not N.
    this._settingsRuntimeUpdates$
      .pipe(debounceTime(500), takeUntil(this.destroy$))
      .subscribe(() => {
        // Don't steal state if the user is mid-edit. The snackbar gives
        // them the cue; they choose when to reload by closing the toast.
        if (this.hasAnyDirtyForm()) {
          this.snack.open(
            'Settings changed in another tab. Save or discard your edits to reload.',
            'Dismiss',
            { duration: 6000 },
          );
          return;
        }
        this.snack.open('Settings updated from another tab.', 'Dismiss', { duration: 3000 });
        this.reload();
      });
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
      'helpers': 7,
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
      notifPrefs: this.notifSvc.loadPreferences(),
    }).pipe(takeUntil(this.destroy$), this.markForCheckOnComplete()).subscribe({
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
          this.darb = { ...this.darb, ...(data.fr099Fr105.darb || {}) };
          this.kmig = { ...this.kmig, ...(data.fr099Fr105.kmig || {}) };
          this.tapb = { ...this.tapb, ...(data.fr099Fr105.tapb || {}) };
          this.kcib = { ...this.kcib, ...(data.fr099Fr105.kcib || {}) };
          this.berp = { ...this.berp, ...(data.fr099Fr105.berp || {}) };
          this.hgte = { ...this.hgte, ...(data.fr099Fr105.hgte || {}) };
          this.rsqva = { ...this.rsqva, ...(data.fr099Fr105.rsqva || {}) };
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
        this.notifPrefs = { ...this.notifPrefs, ...data.notifPrefs };
        this.currentWeights = data.currentWeights;
        this.loadGroupsAndScopes();
      },
      error: () => {
        this.loading = false;
        this.snack.open('Failed to load settings', 'Dismiss', { duration: 4000 });
      },
    });
    this.reloadPresetsAndHistory(true); // pass true to trigger auto-apply check
  }

  private refreshCurrentWeights(): void {
    this.siloSvc.getCurrentWeights().pipe(takeUntil(this.destroy$), this.markForCheckOnComplete()).subscribe({
      next: (weights) => {
        this.currentWeights = weights;
      },
    });
  }

  reloadPresetsAndHistory(shouldCheckAutoApply = false): void {
    this.loadingPresets = true;
    this.loadingHistory = true;
    this.siloSvc.listWeightPresets().pipe(takeUntil(this.destroy$), this.markForCheckOnComplete()).subscribe({
      next: (presets) => { 
        this.weightPresets = presets; 
        this.loadingPresets = false;
        if (shouldCheckAutoApply) {
          this.checkAndAutoApplyRecommended();
        }
      },
      error: () => { this.loadingPresets = false; },
    });
    this.siloSvc.listWeightHistory().pipe(takeUntil(this.destroy$), this.markForCheckOnComplete()).subscribe({
      next: (history) => { this.weightHistory = history; this.loadingHistory = false; },
      error: () => { this.loadingHistory = false; },
    });
    this.loadChallengers();
  }

  private checkAndAutoApplyRecommended(): void {
    // If we have history or current weights don't look like "brand new", don't auto-apply.
    if (this.weightHistory.length > 0) return;
    
    const recommended = this.recommendedPreset;
    if (recommended && !this.matchedPreset) {
      this.siloSvc.applyWeightPreset(recommended.id).pipe(takeUntil(this.destroy$), this.markForCheckOnComplete()).subscribe({
        next: () => {
          this.snack.open('System Recommended settings applied by default.', undefined, { duration: 3000 });
          this.reload();
        }
      });
    }
  }

  applyPreset(preset: WeightPreset): void {
    if (!confirm(`Apply preset "${preset.name}"? This will overwrite all current weight settings.`)) return;
    this.applyingPreset = true;
    this.siloSvc.applyWeightPreset(preset.id).pipe(takeUntil(this.destroy$), this.markForCheckOnComplete()).subscribe({
      next: () => {
        this.applyingPreset = false;
        this.snack.open(`Preset "${preset.name}" applied. Reloading settings...`, undefined, { duration: 3000 });
        this.reload();
      },
      error: (err) => {
        this.applyingPreset = false;
        this.snack.open(err?.error?.detail || 'Failed to apply preset', 'Dismiss', { duration: 4000 });
      },
    });
  }

  saveCurrentAsPreset(): void {
    const name = this.newPresetName.trim();
    if (!name) return;
    this.savingPreset = true;
    this.siloSvc.getCurrentWeights().pipe(takeUntil(this.destroy$), this.markForCheckOnComplete()).subscribe({
      next: (weights) => {
        this.siloSvc.createWeightPreset({ name, weights }).pipe(takeUntil(this.destroy$), this.markForCheckOnComplete()).subscribe({
          next: () => {
            this.savingPreset = false;
            this.newPresetName = '';
            this.showSavePresetInput = false;
            this.snack.open(`Preset "${name}" saved.`, undefined, { duration: 2500 });
            this.reloadPresetsAndHistory();
          },
          error: (err) => {
            this.savingPreset = false;
            this.snack.open(err?.error?.detail || err?.error?.name?.[0] || 'Failed to save preset', 'Dismiss', { duration: 4000 });
          },
        });
      },
      error: () => {
        this.savingPreset = false;
        this.snack.open('Failed to read current weights', 'Dismiss', { duration: 4000 });
      },
    });
  }

  startRenamePreset(preset: WeightPreset): void {
    this.renamingPresetId = preset.id;
    this.renamePresetValue = preset.name;
  }

  confirmRenamePreset(preset: WeightPreset): void {
    const name = this.renamePresetValue.trim();
    if (!name || name === preset.name) { this.renamingPresetId = null; return; }
    this.siloSvc.renameWeightPreset(preset.id, name).pipe(takeUntil(this.destroy$), this.markForCheckOnComplete()).subscribe({
      next: () => {
        this.renamingPresetId = null;
        this.snack.open('Preset renamed.', undefined, { duration: 2000 });
        this.reloadPresetsAndHistory();
      },
      error: (err) => {
        this.renamingPresetId = null;
        this.snack.open(err?.error?.detail || 'Failed to rename preset', 'Dismiss', { duration: 4000 });
      },
    });
  }

  deletePreset(preset: WeightPreset): void {
    if (!confirm(`Delete preset "${preset.name}"? This cannot be undone.`)) return;
    this.deletingPreset = true;
    this.siloSvc.deleteWeightPreset(preset.id).pipe(takeUntil(this.destroy$), this.markForCheckOnComplete()).subscribe({
      next: () => {
        this.deletingPreset = false;
        this.snack.open(`Preset "${preset.name}" deleted.`, undefined, { duration: 2500 });
        this.reloadPresetsAndHistory();
      },
      error: (err) => {
        this.deletingPreset = false;
        this.snack.open(err?.error?.detail || 'Failed to delete preset', 'Dismiss', { duration: 4000 });
      },
    });
  }

  rollbackWeights(row: WeightAdjustmentHistory): void {
    const dateStr = new Date(row.created_at).toLocaleString();
    if (!confirm(`Roll back to weights from ${dateStr}? This will overwrite all current weight settings.`)) return;
    this.rollingBack = true;
    this.siloSvc.rollbackWeights(row.id).pipe(takeUntil(this.destroy$), this.markForCheckOnComplete()).subscribe({
      next: () => {
        this.rollingBack = false;
        this.snack.open(`Rolled back to weights from ${dateStr}. Reloading...`, undefined, { duration: 3000 });
        this.reload();
      },
      error: (err) => {
        this.rollingBack = false;
        this.snack.open(err?.error?.detail || 'Rollback failed', 'Dismiss', { duration: 4000 });
      },
    });
  }

  triggerWeightTune(): void {
    if (!confirm('Run the auto-tune now? This will analyse recent data and may propose new weights.')) return;
    this.triggeringWeightTune = true;
    this.siloSvc.triggerWeightTune().pipe(takeUntil(this.destroy$), this.markForCheckOnComplete()).subscribe({
      next: () => {
        this.triggeringWeightTune = false;
        this.snack.open('Weight-tune task queued. Check back in a moment.', undefined, { duration: 3000 });
        setTimeout(() => this.loadChallengers(), 5000);
      },
      error: (err) => {
        this.triggeringWeightTune = false;
        this.snack.open(err?.error?.detail || 'Failed to queue the tune task.', 'Dismiss', { duration: 4000 });
      },
    });
  }

  historySourceLabel(source: string): string {
    return {
      auto_tune: 'Auto-tune',
      manual: 'Manual',
      preset_applied: 'Preset applied',
      r_auto: 'Legacy R tune',
      cs_auto_tune: 'Auto-tuner (Python L-BFGS)',
    }[source] ?? source;
  }

  // ── FR-018 Weight Tuning ──────────────────────────────────────────────────

  get pendingChallenger(): RankingChallenger | null {
    return this.challengers.find((c) => c.status === 'pending') ?? null;
  }

  loadChallengers(): void {
    this.loadingChallengers = true;
    this.siloSvc.listChallengers().pipe(takeUntil(this.destroy$), this.markForCheckOnComplete()).subscribe({
      next: (challengers) => { this.challengers = challengers; this.loadingChallengers = false; },
      error: () => { this.loadingChallengers = false; },
    });
  }


  promoteChallenger(challenger: RankingChallenger): void {
    if (!confirm('Promote this challenger? Its weights will become active immediately.')) return;
    this.evaluatingChallenger = true;
    this.siloSvc.evaluateChallenger(challenger.run_id).pipe(takeUntil(this.destroy$), this.markForCheckOnComplete()).subscribe({
      next: () => {
        this.evaluatingChallenger = false;
        this.snack.open('Challenger evaluation queued. Reload the page to see the new weights.', undefined, { duration: 4000 });
        this.loadChallengers();
      },
      error: () => {
        this.evaluatingChallenger = false;
        this.snack.open('Failed to queue challenger evaluation.', 'Dismiss', { duration: 4000 });
      },
    });
  }

  rejectChallenger(challenger: RankingChallenger): void {
    if (!confirm('Reject this challenger? It will not be applied.')) return;
    this.siloSvc.rejectChallenger(challenger.id).pipe(takeUntil(this.destroy$), this.markForCheckOnComplete()).subscribe({
      next: () => {
        this.snack.open('Challenger rejected.', undefined, { duration: 2500 });
        this.loadChallengers();
      },
      error: () => this.snack.open('Failed to reject challenger.', 'Dismiss', { duration: 4000 }),
    });
  }

  challengerImprovementPct(c: RankingChallenger): string {
    if (c.predicted_quality_score == null || c.champion_quality_score == null || c.champion_quality_score === 0) return '';
    const pct = ((c.predicted_quality_score - c.champion_quality_score) / c.champion_quality_score) * 100;
    return (pct >= 0 ? '+' : '') + pct.toFixed(1) + '%';
  }

  challengerDiffKeys(c: RankingChallenger): string[] {
    return Object.keys(c.candidate_weights ?? {});
  }

  deltaKeys(delta: Record<string, any> | null | undefined): string[] {
    return delta ? Object.keys(delta) : [];
  }

  formatDeltaLine(key: string, entry: { previous: string | null; new: string | null }): string {
    return `${key}: ${entry.previous ?? '-'} -> ${entry.new ?? '-'}`;
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  savePhraseMatchingSettings(): void {
    this.savingPhraseMatching = true;
    this.siloSvc.updatePhraseMatchingSettings(this.phraseMatching)
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
      next: (phraseMatching) => {
        this.phraseMatching = phraseMatching;
        this.refreshCurrentWeights();
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
    this.siloSvc.updateLearnedAnchorSettings(this.learnedAnchor)
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
      next: (learnedAnchor) => {
        this.learnedAnchor = learnedAnchor;
        this.refreshCurrentWeights();
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
    this.siloSvc.updateRareTermPropagationSettings(this.rareTermPropagation)
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
      next: (rareTermPropagation) => {
        this.rareTermPropagation = rareTermPropagation;
        this.refreshCurrentWeights();
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
    this.siloSvc.updateFieldAwareRelevanceSettings(this.fieldAwareRelevance)
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
      next: (fieldAwareRelevance) => {
        this.fieldAwareRelevance = fieldAwareRelevance;
        this.refreshCurrentWeights();
        this.savingFieldAwareRelevance = false;
        this.snack.open('Field-aware relevance settings saved', undefined, { duration: 2500 });
      },
      error: (error) => {
        this.savingFieldAwareRelevance = false;
        this.snack.open(error?.error?.detail || 'Failed to save field-aware relevance settings', 'Dismiss', { duration: 4000 });
      },
    });
  }

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

    this.siloSvc.updateGSCSettings(payload).pipe(takeUntil(this.destroy$), this.markForCheckOnComplete()).subscribe({
      next: (ga4Gsc: GSCSettings) => {
        this.ga4Gsc = ga4Gsc;
        this.gscManualBackfillDays = Math.max(
          Number(ga4Gsc.sync_lookback_days || 1),
          Number(ga4Gsc.manual_backfill_suggested_days || 180),
        );
        this.gscPrivateKey = '';
        this.savingGA4GSC = false;
        this.snack.open('Search Console settings saved.', undefined, { duration: 3000 });
      },
      error: (error: any) => {
        this.savingGA4GSC = false;
        this.snack.open(error?.error?.detail || 'Failed to save settings.', 'Dismiss', { duration: 4000 });
      },
    });
  }

  authorizeGoogle(): void {
    this.siloSvc.getGoogleAuthUrl().pipe(takeUntil(this.destroy$), this.markForCheckOnComplete()).subscribe({
      next: (res) => {
        if (res.authorization_url) {
          window.location.href = res.authorization_url;
        }
      },
      error: (err) => {
        this.snack.open('Failed to start Google authorization: ' + (err?.error?.detail || 'Unknown error'), 'Dismiss', { duration: 5000 });
      }
    });
  }

  unlinkGoogleAccount(): void {
    if (!confirm('Are you sure you want to unlink your Google account? Access to GA4 and GSC via OAuth will be revoked.')) return;
    this.siloSvc.unlinkGoogleAccount().pipe(takeUntil(this.destroy$), this.markForCheckOnComplete()).subscribe({
      next: () => {
        this.snack.open('Google account unlinked.', undefined, { duration: 3000 });
        this.reload();
      },
      error: (err) => {
        this.snack.open('Failed to unlink Google account: ' + (err?.error?.detail || 'Unknown error'), 'Dismiss', { duration: 5000 });
      }
    });
  }

  testGSCConnection(): void {
    this.testingGSCConnection = true;
    this.siloSvc.testGSCConnection({
      property_url: this.ga4Gsc.property_url.trim() || undefined,
      client_email: this.ga4Gsc.client_email.trim() || undefined,
      private_key: this.gscPrivateKey.trim() || undefined,
    }).pipe(takeUntil(this.destroy$), this.markForCheckOnComplete()).subscribe({
      next: (result: AnalyticsConnectionResult) => {
        this.testingGSCConnection = false;
        this.ga4Gsc = {
          ...this.ga4Gsc,
          connection_status: result.status,
          connection_message: result.message,
        };
        this.snack.open(result.message, undefined, { duration: 3500 });
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
      },
    });
  }

  testXenForoConnection(): void {
    this.testingXenForo = true;
    this.siloSvc.testXenForoConnection({
      base_url: this.xenforo.base_url?.trim() || undefined,
      api_key: this.xfApiKey?.trim() || undefined,
    }).pipe(takeUntil(this.destroy$), this.markForCheckOnComplete()).subscribe({
      next: (result: AnalyticsConnectionResult) => {
        this.testingXenForo = false;
        this.snack.open(result.message, undefined, { duration: 3500 });
      },
      error: (error) => {
        this.testingXenForo = false;
        const message = error?.error?.message || error?.error?.detail || 'XenForo connection failed';
        this.snack.open(message, 'Dismiss', { duration: 4500 });
      },
    });
  }

  testWordPressConnection(): void {
    this.testingWordPress = true;
    this.siloSvc.testWordPressConnection({
      base_url: this.wordpress.base_url?.trim() || undefined,
      username: this.wordpress.username?.trim() || undefined,
      app_password: this.wordpressPassword?.trim() || undefined,
    }).pipe(takeUntil(this.destroy$), this.markForCheckOnComplete()).subscribe({
      next: (result: AnalyticsConnectionResult) => {
        this.testingWordPress = false;
        this.snack.open(result.message, undefined, { duration: 3500 });
      },
      error: (error) => {
        this.testingWordPress = false;
        const message = error?.error?.message || error?.error?.detail || 'WordPress connection failed';
        this.snack.open(message, 'Dismiss', { duration: 4500 });
      },
    });
  }

  testWebhookEndpoints(): void {
    this.testingWebhooks = true;
    this.siloSvc.testWebhookEndpoints()
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
      next: (result: AnalyticsConnectionResult) => {
        this.testingWebhooks = false;
        this.snack.open(result.message, undefined, { duration: 3500 });
      },
      error: (error) => {
        this.testingWebhooks = false;
        const message = error?.error?.message || error?.error?.detail || 'Webhook test failed';
        this.snack.open(message, 'Dismiss', { duration: 4500 });
      },
    });
  }

  runGSCSync(): void {
    const lookbackDays = Math.max(1, Number(this.gscManualBackfillDays || this.ga4Gsc.sync_lookback_days));
    if (!confirm(`Run a GSC performance sync now? This will re-read the last ${lookbackDays} days and replace matching rows with the new country-filtered data.`)) return;
    this.runningGSCSync = true;
    this.siloSvc.runGSCSync({ lookback_days: lookbackDays }).pipe(takeUntil(this.destroy$), this.markForCheckOnComplete()).subscribe({
      next: (res) => {
        this.runningGSCSync = false;
        this.snack.open(res?.message || 'GSC performance sync queued.', undefined, { duration: 3500 });
      },
      error: (err) => {
        this.runningGSCSync = false;
        this.snack.open(err?.error?.detail || 'Failed to queue GSC sync', 'Dismiss', { duration: 4000 });
      },
    });
  }


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

    this.siloSvc.updateGA4TelemetrySettings(payload)
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
      next: (ga4Telemetry) => {
        this.ga4Telemetry = ga4Telemetry;
        this.ga4TelemetrySecret = '';
        this.ga4TelemetryReadPrivateKey = '';
        this.savingGA4Telemetry = false;
        this.snack.open('GA4 telemetry settings saved', undefined, { duration: 2500 });
      },
      error: (error) => {
        this.savingGA4Telemetry = false;
        this.snack.open(error?.error?.detail || 'Failed to save GA4 telemetry settings', 'Dismiss', { duration: 4000 });
      },
    });
  }

  testGA4TelemetryConnection(): void {
    this.testingGA4Telemetry = true;
    this.siloSvc.testGA4TelemetryConnection({
      measurement_id: this.ga4Telemetry.measurement_id.trim() || undefined,
      api_secret: this.ga4TelemetrySecret.trim() || undefined,
    }).pipe(takeUntil(this.destroy$), this.markForCheckOnComplete()).subscribe({
      next: (result: AnalyticsConnectionResult) => {
        this.testingGA4Telemetry = false;
        this.ga4Telemetry = {
          ...this.ga4Telemetry,
          connection_status: result.status,
          connection_message: result.message,
        };
        this.snack.open(result.message, undefined, { duration: 3000 });
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
    }).pipe(takeUntil(this.destroy$), this.markForCheckOnComplete()).subscribe({
      next: (result: AnalyticsConnectionResult) => {
        this.testingGA4TelemetryRead = false;
        this.ga4Telemetry = {
          ...this.ga4Telemetry,
          read_connection_status: result.status,
          read_connection_message: result.message,
        };
        this.snack.open(result.message, undefined, { duration: 3000 });
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
      },
    });
  }

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

    this.siloSvc.updateMatomoTelemetrySettings(payload)
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
      next: (matomoTelemetry) => {
        this.matomoTelemetry = matomoTelemetry;
        this.matomoTelemetryToken = '';
        this.savingMatomoTelemetry = false;
        this.snack.open('Matomo telemetry settings saved', undefined, { duration: 2500 });
      },
      error: (error) => {
        this.savingMatomoTelemetry = false;
        this.snack.open(error?.error?.detail || 'Failed to save Matomo telemetry settings', 'Dismiss', { duration: 4000 });
      },
    });
  }

  testMatomoTelemetryConnection(): void {
    this.testingMatomoTelemetry = true;
    this.siloSvc.testMatomoTelemetryConnection({
      url: this.matomoTelemetry.url.trim() || undefined,
      site_id_xenforo: this.matomoTelemetry.site_id_xenforo.trim() || undefined,
      token_auth: this.matomoTelemetryToken.trim() || undefined,
    }).pipe(takeUntil(this.destroy$), this.markForCheckOnComplete()).subscribe({
      next: (result: AnalyticsConnectionResult) => {
        this.testingMatomoTelemetry = false;
        this.matomoTelemetry = {
          ...this.matomoTelemetry,
          connection_status: result.status,
          connection_message: result.message,
        };
        this.snack.open(result.message, undefined, { duration: 3000 });
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
      },
    });
  }

  saveGraphCandidateSettings(): void {
    this.savingGraphCandidate = true;
    this.siloSvc.updateGraphCandidateSettings(this.graphCandidate)
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
      next: (graphCandidate) => {
        this.graphCandidate = graphCandidate;
        this.refreshCurrentWeights();
        this.savingGraphCandidate = false;
        this.snack.open('Graph candidate settings saved', undefined, { duration: 2500 });
      },
      error: (error) => {
        this.savingGraphCandidate = false;
        this.snack.open(error?.error?.detail || 'Failed to save graph candidate settings', 'Dismiss', { duration: 4000 });
      },
    });
  }

  saveValueModelSettings(): void {
    this.savingValueModel = true;
    this.siloSvc.updateValueModelSettings(this.valueModel)
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
      next: (valueModel) => {
        this.valueModel = valueModel;
        this.refreshCurrentWeights();
        this.savingValueModel = false;
        this.snack.open('Value model settings saved', undefined, { duration: 2500 });
      },
      error: (error) => {
        this.savingValueModel = false;
        this.snack.open(error?.error?.detail || 'Failed to save value model settings', 'Dismiss', { duration: 4000 });
      },
    });
  }

  triggerGraphRebuild(): void {
    if (!confirm('Manually rebuild the bipartite knowledge graph? This will trigger a full refresh of entity nodes.')) return;
    this.isGraphRebuilding = true;
    this.siloSvc.rebuildKnowledgeGraph().pipe(takeUntil(this.destroy$), this.markForCheckOnComplete()).subscribe({
      next: () => {
        this.isGraphRebuilding = false;
        this.snack.open('Knowledge graph rebuild queued.', undefined, { duration: 3000 });
      },
      error: (err) => {
        this.isGraphRebuilding = false;
        this.snack.open(err?.error?.detail || 'Failed to trigger graph rebuild', 'Dismiss', { duration: 4500 });
      },
    });
  }

  saveLinkFreshnessSettings(): void {
    this.savingLinkFreshness = true;
    this.siloSvc.updateLinkFreshnessSettings(this.linkFreshness)
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
      next: (linkFreshness) => {
        this.linkFreshness = linkFreshness;
        this.refreshCurrentWeights();
        this.savingLinkFreshness = false;
        this.snack.open('Link Freshness settings saved', undefined, { duration: 2500 });
      },
      error: (error) => {
        this.savingLinkFreshness = false;
        this.snack.open(error?.error?.detail || 'Failed to save Link Freshness settings', 'Dismiss', { duration: 4000 });
      },
    });
  }

  saveSpamGuardSettings(): void {
    this.savingSpamGuards = true;
    this.siloSvc.updateSpamGuardSettings(this.spamGuards)
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
      next: (spamGuards) => {
        this.spamGuards = spamGuards;
        this.savingSpamGuards = false;
        this.snack.open('Spam guard settings saved', undefined, { duration: 2500 });
      },
      error: (error) => {
        this.savingSpamGuards = false;
        this.snack.open(error?.error?.detail || 'Failed to save spam guard settings', 'Dismiss', { duration: 4000 });
      },
    });
  }

  saveAnchorDiversitySettings(): void {
    this.savingAnchorDiversity = true;
    this.siloSvc.updateAnchorDiversitySettings(this.anchorDiversity)
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
      next: (anchorDiversity) => {
        this.anchorDiversity = anchorDiversity;
        this.refreshCurrentWeights();
        this.savingAnchorDiversity = false;
        this.snack.open('Anchor Diversity settings saved', undefined, { duration: 2500 });
      },
      error: (error) => {
        this.savingAnchorDiversity = false;
        this.snack.open(error?.error?.detail || error?.error?.error || 'Failed to save Anchor Diversity settings', 'Dismiss', { duration: 4000 });
      },
    });
  }

  saveKeywordStuffingSettings(): void {
    this.savingKeywordStuffing = true;
    this.siloSvc.updateKeywordStuffingSettings(this.keywordStuffing)
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
      next: (keywordStuffing) => {
        this.keywordStuffing = keywordStuffing;
        this.refreshCurrentWeights();
        this.savingKeywordStuffing = false;
        this.snack.open('Keyword Stuffing settings saved', undefined, { duration: 2500 });
      },
      error: (error) => {
        this.savingKeywordStuffing = false;
        this.snack.open(error?.error?.detail || error?.error?.error || 'Failed to save Keyword Stuffing settings', 'Dismiss', { duration: 4000 });
      },
    });
  }

  saveLinkFarmSettings(): void {
    this.savingLinkFarm = true;
    this.siloSvc.updateLinkFarmSettings(this.linkFarm)
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
      next: (linkFarm) => {
        this.linkFarm = linkFarm;
        this.refreshCurrentWeights();
        this.savingLinkFarm = false;
        this.snack.open('Link-Farm settings saved', undefined, { duration: 2500 });
      },
      error: (error) => {
        this.savingLinkFarm = false;
        this.snack.open(error?.error?.detail || error?.error?.error || 'Failed to save Link-Farm settings', 'Dismiss', { duration: 4000 });
      },
    });
  }

  // FR-099 through FR-105 — saves all 7 signals via the grouped endpoint.
  // Each card's Save button calls this; we set the per-signal spinner so
  // the right card shows "Saving..." while the whole batch goes up.
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
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
        next: (saved) => {
          if (saved?.darb) this.darb = { ...this.darb, ...saved.darb };
          if (saved?.kmig) this.kmig = { ...this.kmig, ...saved.kmig };
          if (saved?.tapb) this.tapb = { ...this.tapb, ...saved.tapb };
          if (saved?.kcib) this.kcib = { ...this.kcib, ...saved.kcib };
          if (saved?.berp) this.berp = { ...this.berp, ...saved.berp };
          if (saved?.hgte) this.hgte = { ...this.hgte, ...saved.hgte };
          if (saved?.rsqva) this.rsqva = { ...this.rsqva, ...saved.rsqva };
          this.refreshCurrentWeights();
          spinnerSetter(false);
          this.snack.open(`${name} settings saved`, undefined, { duration: 2500 });
        },
        error: (error) => {
          spinnerSetter(false);
          this.snack.open(error?.error?.detail || error?.error?.error || `Failed to save ${name} settings`, 'Dismiss', { duration: 4000 });
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

  // Group C — Stage-1 candidate retriever flags. Both default off;
  // flipping either on activates RRF fusion (#31) on the next pipeline
  // pass with no other code change.
  saveStage1RetrieverSettings(): void {
    this.savingStage1Retrievers = true;
    this.siloSvc.updateStage1RetrieverSettings(this.stage1Retrievers)
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
        next: (saved) => {
          if (saved) {
            this.stage1Retrievers = { ...this.stage1Retrievers, ...saved };
          }
          this.savingStage1Retrievers = false;
          this.snack.open(
            'Stage-1 retrievers saved',
            undefined,
            { duration: 2500 },
          );
        },
        error: (error) => {
          this.savingStage1Retrievers = false;
          this.snack.open(
            error?.error?.detail
              || error?.error?.error
              || 'Failed to save Stage-1 retrievers',
            'Dismiss',
            { duration: 4000 },
          );
        },
      });
  }

  // Phase 6 — 10 optional-pick master switches. All default ON via
  // the seed migration. Single Save button posts the whole tree.
  savePhase6PickSettings(): void {
    this.savingPhase6Picks = true;
    this.siloSvc.updatePhase6PickSettings(this.phase6Picks)
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
        next: (saved) => {
          if (saved) {
            this.phase6Picks = { ...this.phase6Picks, ...saved };
          }
          this.savingPhase6Picks = false;
          this.snack.open(
            'Optional pick toggles saved',
            undefined,
            { duration: 2500 },
          );
        },
        error: (error) => {
          this.savingPhase6Picks = false;
          this.snack.open(
            error?.error?.detail
              || error?.error?.error
              || 'Failed to save optional pick toggles',
            'Dismiss',
            { duration: 4000 },
          );
        },
      });
  }

  saveClickDistanceSettings(): void {
    this.savingClickDistance = true;
    this.siloSvc.updateClickDistanceSettings(this.clickDistance)
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
      next: (clickDistance) => {
        this.clickDistance = clickDistance;
        this.refreshCurrentWeights();
        this.savingClickDistance = false;
        this.snack.open('Click distance settings saved', undefined, { duration: 2500 });
      },
      error: (error) => {
        this.savingClickDistance = false;
        this.snack.open(error?.error?.detail || 'Failed to save click distance settings', 'Dismiss', { duration: 4000 });
      },
    });
  }

  saveFeedbackRerankSettings(): void {
    this.savingFeedbackRerank = true;
    this.siloSvc.updateFeedbackRerankSettings(this.feedbackRerank)
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
      next: (feedbackRerank) => {
        this.feedbackRerank = feedbackRerank;
        this.refreshCurrentWeights();
        this.savingFeedbackRerank = false;
        this.snack.open('Explore/Exploit reranking settings saved', undefined, { duration: 2500 });
      },
      error: (error) => {
        this.savingFeedbackRerank = false;
        this.snack.open(error?.error?.detail || 'Failed to save explore/exploit settings', 'Dismiss', { duration: 4000 });
      },
    });
  }

  saveClusteringSettings(): void {
    this.savingClustering = true;
    this.siloSvc.updateClusteringSettings(this.clustering)
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
      next: (clustering) => {
        this.clustering = clustering;
        this.refreshCurrentWeights();
        this.savingClustering = false;
        this.snack.open('Clustering settings saved', undefined, { duration: 2500 });
      },
      error: (error) => {
        this.savingClustering = false;
        this.snack.open(error?.error?.detail || 'Failed to save clustering settings', 'Dismiss', { duration: 4000 });
      },
    });
  }

  saveSlateDiversitySettings(): void {
    this.savingSlate = true;
    this.siloSvc.updateSlateDiversitySettings(this.slateDiversity)
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
      next: (slateDiversity) => {
        this.slateDiversity = slateDiversity;
        this.refreshCurrentWeights();
        this.savingSlate = false;
        this.snack.open('Slate diversity settings saved', undefined, { duration: 2500 });
      },
      error: (error) => {
        this.savingSlate = false;
        this.snack.open(error?.error?.error || 'Failed to save slate diversity settings', 'Dismiss', { duration: 4000 });
      },
    });
  }

  recalculateClickDistance(): void {
    this.recalculatingClickDistance = true;
    this.siloSvc.recalculateClickDistance()
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
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

  recalculateClustering(): void {
    this.recalculatingClustering = true;
    this.siloSvc.recalculateClustering()
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
      next: (response) => {
        this.recalculatingClustering = false;
        this.snack.open(`Clustering recalculation started (${response.job_id.slice(0, 8)})`, 'Dismiss', { duration: 5000 });
      },
      error: (error) => {
        this.recalculatingClustering = false;
        this.snack.open(error?.error?.detail || 'Failed to start clustering recalculation', 'Dismiss', { duration: 4000 });
      },
    });
  }

  private loadGroupsAndScopes(): void {
    this.siloSvc.listSiloGroups()
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
      next: (groups) => {
        this.siloGroups = groups;
        this.siloSvc.listScopes()
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

  saveSettings(): void {
    this.savingSettings = true;
    this.siloSvc.updateSettings(this.settings)
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
      next: (settings) => {
        this.settings = settings;
        this.refreshCurrentWeights();
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
    this.siloSvc.updateWeightedAuthoritySettings(this.weightedAuthority)
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
      next: (weightedAuthority) => {
        this.weightedAuthority = weightedAuthority;
        this.refreshCurrentWeights();
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
    this.siloSvc.recalculateWeightedAuthority()
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
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
    this.siloSvc.recalculateLinkFreshness()
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
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
    this.siloSvc.updateXenForoSettings(payload)
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
      next: () => {
        this.xfApiKey = '';
        this.savingXenForo = false;
        this.siloSvc.getXenForoSettings()
          .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
          .subscribe({
          next: (xf) => { this.xenforo = { ...this.xenforo, ...xf }; },
          error: () => {},
        });
        this.snack.open('XenForo credentials saved.', 'Dismiss', { duration: 3000 });
      },
      error: (err) => {
        this.savingXenForo = false;
        this.snack.open(err?.error?.detail || 'Failed to save XenForo settings.', 'Dismiss', { duration: 4000 });
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

    this.siloSvc.updateWordPressSettings(payload)
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
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

  get xfWebhookUrl(): string { return `${window.location.origin}/api/sync/webhooks/xenforo/`; }
  get wpWebhookUrl(): string { return `${window.location.origin}/api/sync/webhooks/wordpress/`; }

  saveWebhookSettings(): void {
    const payload: WebhookSettingsUpdate = {};
    if (this.xfWebhookSecret.trim()) payload.xf_webhook_secret = this.xfWebhookSecret.trim();
    if (this.wpWebhookSecret.trim()) payload.wp_webhook_secret = this.wpWebhookSecret.trim();
    this.savingWebhooks = true;
    this.siloSvc.updateWebhookSettings(payload)
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
      next: (result) => {
        this.webhookSettings = result;
        this.xfWebhookSecret = '';
        this.wpWebhookSecret = '';
        this.savingWebhooks = false;
        this.snack.open('Webhook secrets saved.', undefined, { duration: 2500 });
      },
      error: (err) => {
        this.savingWebhooks = false;
        this.snack.open(err?.error?.detail || 'Failed to save webhook secrets.', 'Dismiss', { duration: 4000 });
      },
    });
  }

  saveAllSettings(): void {
    this.savingSettings = true;
    
    const wordpressPayload: WordPressSettingsUpdate = {
      base_url: this.wordpress.base_url.trim(),
      username: this.wordpress.username.trim(),
      sync_enabled: this.wordpress.sync_enabled,
      sync_hour: Number(this.wordpress.sync_hour),
      sync_minute: Number(this.wordpress.sync_minute),
    };
    if (this.wordpressPassword.trim()) {
      wordpressPayload.app_password = this.wordpressPassword.trim();
    }

    const ga4TelemetryPayload: GA4TelemetryUpdate = {
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
      ga4TelemetryPayload.api_secret = this.ga4TelemetrySecret.trim();
    }
    if (this.ga4TelemetryReadPrivateKey.trim()) {
      ga4TelemetryPayload.read_private_key = this.ga4TelemetryReadPrivateKey.trim();
    }

    const googleOAuthPayload: { client_id: string; client_secret?: string } = {
      client_id: this.googleAuthClientId.trim(),
    };
    if (this.googleAuthClientSecret.trim()) {
      googleOAuthPayload.client_secret = this.googleAuthClientSecret.trim();
    }

    const matomoTelemetryPayload: MatomoTelemetryUpdate = {
      enabled: this.matomoTelemetry.enabled,
      url: this.matomoTelemetry.url.trim(),
      site_id_xenforo: this.matomoTelemetry.site_id_xenforo.trim(),
      site_id_wordpress: this.matomoTelemetry.site_id_wordpress.trim(),
      sync_enabled: this.matomoTelemetry.sync_enabled,
      sync_lookback_days: Number(this.matomoTelemetry.sync_lookback_days),
    };
    if (this.matomoTelemetryToken.trim()) {
      matomoTelemetryPayload.token_auth = this.matomoTelemetryToken.trim();
    }

    const gscPayload: GSCSettingsUpdate = {
      ranking_weight: Number(this.ga4Gsc.ranking_weight),
      property_url: this.ga4Gsc.property_url.trim(),
      client_email: this.ga4Gsc.client_email.trim(),
      sync_enabled: this.ga4Gsc.sync_enabled,
      sync_lookback_days: Number(this.ga4Gsc.sync_lookback_days),
    };
    if (this.gscPrivateKey.trim()) {
      gscPayload.private_key = this.gscPrivateKey.trim();
    }

    forkJoin({
      settings: this.siloSvc.updateSettings(this.settings),
      authority: this.siloSvc.updateWeightedAuthoritySettings(this.weightedAuthority),
      freshness: this.siloSvc.updateLinkFreshnessSettings(this.linkFreshness),
      phrase: this.siloSvc.updatePhraseMatchingSettings(this.phraseMatching),
      learned: this.siloSvc.updateLearnedAnchorSettings(this.learnedAnchor),
      rare: this.siloSvc.updateRareTermPropagationSettings(this.rareTermPropagation),
      relevance: this.siloSvc.updateFieldAwareRelevanceSettings(this.fieldAwareRelevance),
      ga4: this.siloSvc.updateGSCSettings(gscPayload),
      googleOAuth: this.siloSvc.updateGoogleOAuthSettings(googleOAuthPayload),
      ga4Telemetry: this.siloSvc.updateGA4TelemetrySettings(ga4TelemetryPayload),
      matomoTelemetry: this.siloSvc.updateMatomoTelemetrySettings(matomoTelemetryPayload),
      click: this.siloSvc.updateClickDistanceSettings(this.clickDistance),
      spamGuards: this.siloSvc.updateSpamGuardSettings(this.spamGuards),
      anchorDiversity: this.siloSvc.updateAnchorDiversitySettings(this.anchorDiversity),
      keywordStuffing: this.siloSvc.updateKeywordStuffingSettings(this.keywordStuffing),
      linkFarm: this.siloSvc.updateLinkFarmSettings(this.linkFarm),
      explore: this.siloSvc.updateFeedbackRerankSettings(this.feedbackRerank),
      clustering: this.siloSvc.updateClusteringSettings(this.clustering),
      slate: this.siloSvc.updateSlateDiversitySettings(this.slateDiversity),
      graph: this.siloSvc.updateGraphCandidateSettings(this.graphCandidate),
      value: this.siloSvc.updateValueModelSettings(this.valueModel),
      wordpress: this.siloSvc.updateWordPressSettings(wordpressPayload)
    }).pipe(takeUntil(this.destroy$), this.markForCheckOnComplete()).subscribe({
      next: (results) => {
        this.settings = results.settings;
        this.weightedAuthority = results.authority;
        this.linkFreshness = results.freshness;
        this.phraseMatching = results.phrase;
        this.learnedAnchor = results.learned;
        this.rareTermPropagation = results.rare;
        this.fieldAwareRelevance = results.relevance;
        this.ga4Gsc = results.ga4;
        this.googleOAuth = results.googleOAuth;
        this.gscPrivateKey = '';
        this.ga4Telemetry = results.ga4Telemetry;
        this.matomoTelemetry = results.matomoTelemetry;
        this.clickDistance = results.click;
        this.spamGuards = results.spamGuards;
        this.anchorDiversity = results.anchorDiversity;
        this.keywordStuffing = results.keywordStuffing;
        this.linkFarm = results.linkFarm;
        this.feedbackRerank = results.explore;
        this.clustering = results.clustering;
        this.slateDiversity = results.slate;
        this.graphCandidate = results.graph;
        this.valueModel = results.value;
        this.wordpress = results.wordpress;
        this.wordpressPassword = '';
        this.ga4TelemetrySecret = '';
        this.ga4TelemetryReadPrivateKey = '';
        this.googleAuthClientId = results.googleOAuth.client_id;
        this.googleAuthClientSecret = '';
        this.matomoTelemetryToken = '';
        
        this.savingSettings = false;
        this.isDirty = false;
        this.snack.open('All settings saved successfully', undefined, { duration: 3000 });
        this.refreshCurrentWeights();
      },
      error: (err) => {
        this.savingSettings = false;
        this.snack.open(err?.error?.detail || 'One or more settings failed to save', 'Dismiss', { duration: 5000 });
      }
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
    }).pipe(takeUntil(this.destroy$), this.markForCheckOnComplete()).subscribe({
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
    this.siloSvc.runWordPressSync()
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
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
    this.siloSvc.createSiloGroup(this.newGroup)
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
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
    }).pipe(takeUntil(this.destroy$), this.markForCheckOnComplete()).subscribe({
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
    this.siloSvc.deleteSiloGroup(group.id)
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
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
    this.siloSvc.updateScopeSilo(scope.id, siloGroupId)
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
      next: (updated) => {
        Object.assign(scope, updated);
        this.snack.open('Scope assignment saved', undefined, { duration: 2000 });
      },
      error: () => {
        this.snack.open('Failed to save scope assignment', 'Dismiss', { duration: 4000 });
      },
    });
  }

  // ── Notification preferences ──────────────────────────────────────

  saveNotifPrefs(): void {
    this.savingNotifPrefs = true;
    this.notifSvc.savePreferences(this.notifPrefs)
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
      next: (saved) => {
        this.notifPrefs = saved;
        this.savingNotifPrefs = false;
        this.snack.open('Notification preferences saved.', undefined, { duration: 2500 });
      },
      error: () => {
        this.savingNotifPrefs = false;
        this.snack.open('Failed to save notification preferences.', 'Dismiss', { duration: 4000 });
      },
    });
  }

  sendTestNotification(severity: string): void {
    this.testingNotification = true;
    this.notifSvc.sendTestNotification(severity)
      .pipe(takeUntil(this.destroy$), this.markForCheckOnComplete())
      .subscribe({
      next: () => {
        this.testingNotification = false;
        this.snack.open('Test notification sent.', undefined, { duration: 2500 });
        this.audioSvc.playTone(severity === 'error' || severity === 'urgent' ? 'error' : 'warning');
      },
      error: () => {
        this.testingNotification = false;
        this.snack.open('Failed to send test notification.', 'Dismiss', { duration: 4000 });
      },
    });
  }

  async requestDesktopPermission(): Promise<void> {
    const result = await this.desktopSvc.requestPermission();
    if (result === 'granted') {
      this.snack.open('Desktop notifications enabled.', undefined, { duration: 2500 });
    } else if (result === 'denied') {
      this.snack.open('Desktop notifications blocked by the browser.', 'Dismiss', { duration: 5000 });
    }
  }

  // ── Crawler exclusion helpers ─────────────────────────────────
  addCrawlerExclusion(): void {
    const path = this.newCrawlerExclusion.trim();
    if (!path || this.crawlerExcludedPaths.includes(path)) return;
    this.crawlerExcludedPaths = [...this.crawlerExcludedPaths, path];
    this.newCrawlerExclusion = '';
    this.isDirty = true;
  }

  removeCrawlerExclusion(path: string): void {
    this.crawlerExcludedPaths = this.crawlerExcludedPaths.filter((p) => p !== path);
    this.isDirty = true;
  }
}

