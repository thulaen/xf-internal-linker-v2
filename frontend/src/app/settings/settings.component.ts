import { CommonModule } from '@angular/common';
import { Component, OnInit, OnDestroy, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { forkJoin, Subject, takeUntil } from 'rxjs';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
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
  FeedbackRerankSettings,
  ClusteringSettings,
  SlateDiversitySettings,
} from './silo-settings.service';

interface SettingTooltip {
  definition: string;
  impact: string;
  default: string;
  example: string;
  range: string;
}

const SETTING_TOOLTIPS: Record<string, SettingTooltip> = {
  // ── March 2026 PageRank ─────────────────────────────────────────
  'weightedAuthority.ranking_weight': {
    definition: 'How much the PageRank authority score contributes to the final link ranking.',
    impact: 'Higher values make authority the dominant factor. Links will strongly prefer high-authority destinations.',
    default: '0.2',
    example: 'Raising to 0.25 makes authority the top signal. Setting to 0 turns this off entirely.',
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
  // ── Link Freshness ──────────────────────────────────────────────
  'linkFreshness.ranking_weight': {
    definition: 'How much the freshness score influences the final ranking.',
    impact: 'Higher values reward destinations that are actively gaining new inbound links.',
    default: '0 (off)',
    example: 'Setting to 0.05 gives a gentle freshness boost. Raising to 0.15 makes freshness a strong signal.',
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
  // ── Phrase Matching ─────────────────────────────────────────────
  'phraseMatching.ranking_weight': {
    definition: 'How much the phrase match score influences the final ranking.',
    impact: 'Higher values reward destinations whose title or text closely matches the linking phrase.',
    default: '0 (off)',
    example: 'Setting to 0.05 gives a gentle phrase boost. Raising to 0.1 makes it a significant factor.',
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
  // ── Learned Anchors ─────────────────────────────────────────────
  'learnedAnchor.ranking_weight': {
    definition: 'How much the learned anchor score influences the final ranking.',
    impact: 'Higher values reward destinations that already have real-world anchor text pointing to them.',
    default: '0 (off)',
    example: 'Setting to 0.05 gives a gentle boost. Raising above 0.08 may over-fit to past link patterns.',
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
    example: 'Disabling is rarely useful — only consider it if you need to debug which anchors are being filtered.',
    range: 'Enabled / Disabled',
  },
  // ── Rare-Term Propagation ───────────────────────────────────────
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
    default: '0 (off)',
    example: 'Setting to 0.03 gently helps thin pages. Raising above 0.08 may over-reward borrowed terms.',
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
  // ── Field-Aware Relevance ───────────────────────────────────────
  'fieldAwareRelevance.ranking_weight': {
    definition: 'How much the field-aware relevance score influences the final ranking.',
    impact: 'Higher values reward destinations whose title, body, or anchor text aligns with the source sentence.',
    default: '0 (off)',
    example: 'Setting to 0.05 gives a gentle relevance boost. Raising above 0.12 may dominate other signals.',
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
  // ── Click Distance ──────────────────────────────────────────────
  'clickDistance.ranking_weight': {
    definition: 'How much the click-distance score influences the final ranking.',
    impact: 'Higher values prefer destinations structurally closer to the homepage or entry points.',
    default: '0 (off)',
    example: 'Setting to 0.1 gently favours shallower pages. Raising above 0.15 may over-penalise deep content.',
    range: '0 to 0.2',
  },
  'clickDistance.k_cd': {
    definition: 'Depth sensitivity — controls how steeply the score drops off as click-distance from the homepage increases.',
    impact: 'Higher values aggressively penalise pages many clicks from the homepage. Lower values are more lenient.',
    default: '1.5',
    example: 'Raising to 4.0 strongly penalises deep pages. Lowering to 0.5 makes depth almost irrelevant.',
    range: '0.5 to 5.0',
  },
  'clickDistance.b_cd': {
    definition: 'Click-distance bias — blends raw click-distance with a smoothed version to avoid extreme scores.',
    impact: 'Higher values smooth out very deep or very shallow pages. Lower values use the raw depth score.',
    default: '0.1',
    example: 'Raising to 0.5 adds strong smoothing. Lowering to 0 uses raw click-distance directly.',
    range: '0 to 1',
  },
  'clickDistance.b_ud': {
    definition: 'URL-depth bias — blends the URL depth (number of slashes in the path) into the score.',
    impact: 'Higher values prefer pages with shorter URL paths. Lower values ignore URL depth.',
    default: '0.1',
    example: 'Raising to 0.5 gives strong weight to URL shortness. Lowering to 0 ignores URL path depth.',
    range: '0 to 1',
  },
  // ── Silo Ranking ────────────────────────────────────────────────
  'silo.mode': {
    definition: 'Sets how strictly the system enforces topic silo boundaries when ranking links.',
    impact: '"Disabled" ignores silos entirely. "Prefer same silo" boosts same-silo matches. "Strict same silo" blocks cross-silo links when both pages have silo assignments.',
    default: 'Disabled',
    example: 'Start with "Prefer same silo" to keep link suggestions on-topic without hard blocking.',
    range: 'Disabled / Prefer same silo / Strict same silo',
  },
  'silo.same_silo_boost': {
    definition: 'A score bonus added to destinations that belong to the same topic silo as the source page.',
    impact: 'Higher values make the system strongly prefer linking within the same silo group.',
    default: '0',
    example: 'Raising to 0.2 noticeably prioritises same-silo links. Raising to 0.5 may nearly eliminate cross-silo suggestions.',
    range: '0 and above (no hard maximum)',
  },
  'silo.cross_silo_penalty': {
    definition: 'A score deduction applied to destinations that belong to a different silo from the source page.',
    impact: 'Higher values suppress cross-silo suggestions more aggressively.',
    default: '0',
    example: 'Raising to 0.2 significantly reduces cross-silo suggestions. Raising to 0.5 makes them rare.',
    range: '0 and above (no hard maximum)',
  },
  // ── Feedback Rerank ─────────────────────────────────────────────
  'feedbackRerank.enabled': {
    definition: 'Turns on the explore/exploit reranking system, which uses historical reviewer feedback to improve suggestions over time.',
    impact: 'Enabled gradually learns from accept/reject decisions. Disabled keeps ranking purely algorithmic.',
    default: 'Off',
    example: 'Enable once you have reviewed at least a few hundred suggestions so the system has data to learn from.',
    range: 'On / Off',
  },
  'feedbackRerank.ranking_weight': {
    definition: 'How strongly historical reviewer feedback adjusts the final link ranking.',
    impact: 'Higher values make the feedback signal dominant. Lower values keep it as a subtle nudge.',
    default: '0.2',
    example: 'Raising to 0.8 means feedback controls most of the ranking. Lowering to 0.05 keeps it light.',
    range: '0 to 1',
  },
  'feedbackRerank.exploration_rate': {
    definition: 'Controls how much the system explores links with little historical data versus exploiting known-good ones.',
    impact: 'Higher values aggressively test uncertain link pairs. Lower values rely more on established patterns.',
    default: '1.0',
    example: 'Raising to 5 or above pushes many untested links to the top for review. Lowering to 0.1 exploits known winners.',
    range: '0 to 10',
  },
  // ── Clustering ──────────────────────────────────────────────────
  'clustering.enabled': {
    definition: 'Turns on near-duplicate destination clustering based on semantic embedding similarity.',
    impact: 'Enabled prevents suggesting multiple redundant links to effectively the same content. Disabled treats every URL as unique.',
    default: 'Off',
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
    default: '0.5',
    example: 'Set to 1.0 to almost always hide duplicates. Set to 0.1 to just slightly demote them.',
    range: '0 to 2.0',
  },
  // ── Slate Diversity ─────────────────────────────────────────────
  'slateDiversity.enabled': {
    definition: 'Turns on FR-015 MMR (Maximal Marginal Relevance) diversity reranking for the final per-host link slate.',
    impact: 'When enabled, the 3 suggestions for each host thread are chosen to cover different topics. When disabled, the top 3 by score are used regardless of similarity.',
    default: 'On',
    example: 'Enable to prevent three nearly-identical destination links appearing on the same thread.',
    range: 'On / Off',
  },
  'slateDiversity.diversity_lambda': {
    definition: 'MMR lambda — controls the balance between relevance and diversity in the final slate.',
    impact: 'Higher values (closer to 1.0) keep the most relevant suggestions. Lower values force more variety even if the alternatives score lower.',
    default: '0.7',
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
    impact: 'Purely diagnostic — does not block selection. Helps you understand when the diversity reranker is doing meaningful work.',
    default: '0.90',
    example: 'Lower to 0.80 to flag moderately similar pairs. Keep at 0.90 to only flag near-clones.',
    range: '0.70 to 0.99',
  },
};

const EXTREME_THRESHOLDS: Record<string, { warnBelow?: number; warnAbove?: number }> = {
  'weightedAuthority.ranking_weight': { warnAbove: 0.2 },
  'weightedAuthority.position_bias': { warnBelow: 0.1, warnAbove: 0.9 },
  'weightedAuthority.empty_anchor_factor': { warnBelow: 0.2, warnAbove: 0.95 },
  'weightedAuthority.bare_url_factor': { warnBelow: 0.15, warnAbove: 0.9 },
  'weightedAuthority.weak_context_factor': { warnBelow: 0.2, warnAbove: 0.95 },
  'weightedAuthority.isolated_context_factor': { warnBelow: 0.15, warnAbove: 0.9 },
  'linkFreshness.ranking_weight': { warnAbove: 0.1 },
  'linkFreshness.recent_window_days': { warnBelow: 14, warnAbove: 60 },
  'linkFreshness.newest_peer_percent': { warnAbove: 0.45 },
  'linkFreshness.min_peer_count': { warnAbove: 15 },
  'phraseMatching.ranking_weight': { warnAbove: 0.08 },
  'phraseMatching.context_window_tokens': { warnBelow: 5, warnAbove: 11 },
  'learnedAnchor.ranking_weight': { warnAbove: 0.08 },
  'learnedAnchor.minimum_anchor_sources': { warnAbove: 8 },
  'learnedAnchor.minimum_family_support_share': { warnAbove: 0.4 },
  'rareTermPropagation.ranking_weight': { warnAbove: 0.08 },
  'rareTermPropagation.max_document_frequency': { warnAbove: 7 },
  'fieldAwareRelevance.ranking_weight': { warnAbove: 0.12 },
  'clickDistance.ranking_weight': { warnAbove: 0.15 },
  'clickDistance.k_cd': { warnAbove: 3.5 },
  'clickDistance.b_cd': { warnAbove: 0.6 },
  'clickDistance.b_ud': { warnAbove: 0.6 },
  'feedbackRerank.ranking_weight': { warnAbove: 0.75 },
  'feedbackRerank.exploration_rate': { warnAbove: 5.0 },
  'silo.same_silo_boost': { warnAbove: 0.4 },
  'silo.cross_silo_penalty': { warnAbove: 0.4 },
  'clustering.similarity_threshold': { warnAbove: 0.1 },
  'clustering.suppression_penalty': { warnAbove: 1.0 },
  'slateDiversity.diversity_lambda': { warnBelow: 0.4 },
  'slateDiversity.score_window': { warnAbove: 0.6 },
  'slateDiversity.similarity_cap': { warnBelow: 0.75 },
};

@Component({
  selector: 'app-settings',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatCardModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatSelectModule,
    MatSnackBarModule,
    MatTooltipModule,
  ],
  templateUrl: './settings.component.html',
  styleUrls: ['./settings.component.scss'],
})
export class SettingsComponent implements OnInit, OnDestroy {
  private siloSvc = inject(SiloSettingsService);
  private snack = inject(MatSnackBar);
  private destroy$ = new Subject<void>();

  loading = true;
  savingSettings = false;
  savingWeightedAuthority = false;
  savingLinkFreshness = false;
  savingPhraseMatching = false;
  savingLearnedAnchor = false;
  savingRareTermPropagation = false;
  savingFieldAwareRelevance = false;
  savingClickDistance = false;
  savingFeedbackRerank = false;
  savingClustering = false;
  savingSlate = false;
  savingWordPress = false;
  recalculatingWeightedAuthority = false;
  recalculatingLinkFreshness = false;
  recalculatingClickDistance = false;
  recalculatingClustering = false;
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
  feedbackRerank: FeedbackRerankSettings = {
    enabled: false,
    ranking_weight: 0.2,
    exploration_rate: 1.0,
  };
  clustering: ClusteringSettings = {
    enabled: false,
    similarity_threshold: 0.04,
    suppression_penalty: 0.5,
  };
  slateDiversity: SlateDiversitySettings = {
    enabled: true,
    diversity_lambda: 0.7,
    score_window: 0.30,
    similarity_cap: 0.90,
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

  tip(key: string): string {
    const t = SETTING_TOOLTIPS[key];
    if (!t) return `⚠ No tooltip defined for "${key}" — add an entry to SETTING_TOOLTIPS in settings.component.ts`;
    return [
      `Definition: ${t.definition}`,
      `Linking impact: ${t.impact}`,
      `Recommended default: ${t.default}`,
      `Example: ${t.example}`,
      `Valid range: ${t.range}`,
    ].join('\n\n');
  }

  isExtreme(value: number | undefined | null, key: string): boolean {
    if (value == null) return false;
    const threshold = EXTREME_THRESHOLDS[key];
    if (!threshold) return false;
    if (threshold.warnAbove !== undefined && value > threshold.warnAbove) return true;
    if (threshold.warnBelow !== undefined && value < threshold.warnBelow) return true;
    return false;
  }

  ngOnInit(): void {
    this.reload();
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
      wordpress: this.siloSvc.getWordPressSettings(),
      clickDistance: this.siloSvc.getClickDistanceSettings(),
      feedbackRerank: this.siloSvc.getFeedbackRerankSettings(),
      clustering: this.siloSvc.getClusteringSettings(),
      slateDiversity: this.siloSvc.getSlateDiversitySettings(),
    }).pipe(takeUntil(this.destroy$)).subscribe({
      next: (data) => {
        this.settings = data.settings;
        this.weightedAuthority = data.weightedAuthority;
        this.linkFreshness = data.linkFreshness;
        this.phraseMatching = data.phraseMatching;
        this.learnedAnchor = data.learnedAnchor;
        this.rareTermPropagation = data.rareTermPropagation;
        this.fieldAwareRelevance = data.fieldAwareRelevance;
        this.wordpress = data.wordpress;
        this.clickDistance = data.clickDistance;
        this.feedbackRerank = data.feedbackRerank;
        this.clustering = data.clustering;
        this.slateDiversity = data.slateDiversity;
        this.loadGroupsAndScopes();
      },
      error: () => {
        this.loading = false;
        this.snack.open('Failed to load settings', 'Dismiss', { duration: 4000 });
      },
    });
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
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

  saveFeedbackRerankSettings(): void {
    this.savingFeedbackRerank = true;
    this.siloSvc.updateFeedbackRerankSettings(this.feedbackRerank).subscribe({
      next: (feedbackRerank) => {
        this.feedbackRerank = feedbackRerank;
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
    this.siloSvc.updateClusteringSettings(this.clustering).subscribe({
      next: (clustering) => {
        this.clustering = clustering;
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
    this.siloSvc.updateSlateDiversitySettings(this.slateDiversity).subscribe({
      next: (slateDiversity) => {
        this.slateDiversity = slateDiversity;
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

  recalculateClustering(): void {
    this.recalculatingClustering = true;
    this.siloSvc.recalculateClustering().subscribe({
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
