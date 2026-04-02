import { CommonModule, DatePipe } from '@angular/common';
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
import { MatTabsModule } from '@angular/material/tabs';
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
  GA4GSCSettings,
  FeedbackRerankSettings,
  ClusteringSettings,
  SlateDiversitySettings,
  WeightPreset,
  WeightAdjustmentHistory,
  AnalyticsConnectionResult,
  GA4TelemetrySettings,
  GA4TelemetryUpdate,
  MatomoTelemetrySettings,
  MatomoTelemetryUpdate,
} from './silo-settings.service';

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
  // Click Distance
  'ga4Gsc.ranking_weight': {
    definition: 'How much first-party search and behavior data influences the final ranking.',
    impact: 'Higher values reward destinations that already earn stronger search clicks and better on-site engagement.',
    default: '0.05',
    example: 'Start at 0.05 so analytics acts like a light tie-breaker instead of overruling relevance.',
    range: '0 to 0.3',
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
    definition: 'Configure your WordPress API connection and sync schedule.',
    impact: 'Ensures the app has the latest content and can push suggested links back to WordPress.',
    default: 'API configuration',
    example: 'Set the sync hour to 03:00 UTC for daily updates.',
    range: 'URL and credentials',
  },
  'tabs.library_history': {
    definition: 'Save weight presets and view your adjustment history.',
    impact: 'Allows you to experiment with different weights and quickly rollback if needed.',
    default: 'Snapshot library',
    example: 'Save your "Black Friday" weights as a preset.',
    range: 'Presets and logs',
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
};

@Component({
  selector: 'app-settings',
  standalone: true,
  templateUrl: './settings.component.html',
  styleUrls: ['./settings.component.scss'],
  imports: [
    CommonModule,
    DatePipe,
    FormsModule,
    MatButtonModule,
    MatCardModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatSelectModule,
    MatSnackBarModule,
    MatTabsModule,
    MatTooltipModule,
  ],
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
  savingGA4GSC = false;
  savingGA4Telemetry = false;
  savingMatomoTelemetry = false;
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
  testingGA4Telemetry = false;
  testingGA4TelemetryRead = false;
  testingMatomoTelemetry = false;

  // Tab persistence
  selectedTabIndex = Number(localStorage.getItem('settings_active_tab') || '0');

  onTabChange(index: number): void {
    this.selectedTabIndex = index;
    localStorage.setItem('settings_active_tab', String(index));
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
  ga4Gsc: GA4GSCSettings = {
    ranking_weight: 0.05,
  };
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
  wordpress: WordPressSettings = {
    base_url: '',
    username: '',
    app_password_configured: false,
    sync_enabled: false,
    sync_hour: 3,
    sync_minute: 0,
  };
  wordpressPassword = '';

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
  loadingHistory = false;
  rollingBack = false;
  triggeringRTune = false;
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
    return `status-pill--${status === 'connected' ? 'success' : status === 'error' ? 'danger' : status === 'saved' ? 'status' : 'muted'}`;
  }

  lastSyncLabel(sync: { completed_at: string | null; started_at: string | null; rows_written: number } | null): string {
    if (!sync) return 'Never synced';
    const stamp = sync.completed_at || sync.started_at;
    if (!stamp) return `${sync.rows_written} rows written`;
    return `${new Date(stamp).toLocaleString()} • ${sync.rows_written} rows written`;
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
      { label: 'Silo Ranking', currentEnabled: this.settings.mode !== 'disabled', recommendedEnabled: this.isFeatureEnabledInPreset(recommended, 'silo.mode') },
      { label: 'Feedback Reranking', currentEnabled: this.feedbackRerank.enabled && this.feedbackRerank.ranking_weight > 0, recommendedEnabled: this.isFeatureEnabledInPreset(recommended, 'explore_exploit.enabled') && this.isFeatureEnabledInPreset(recommended, 'explore_exploit.ranking_weight') },
      { label: 'Near-Duplicate Clustering', currentEnabled: this.clustering.enabled, recommendedEnabled: this.isFeatureEnabledInPreset(recommended, 'clustering.enabled') },
      { label: 'Slate Diversity', currentEnabled: this.slateDiversity.enabled, recommendedEnabled: this.isFeatureEnabledInPreset(recommended, 'slate_diversity.enabled') },
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
      ga4Gsc: this.siloSvc.getGA4GSCSettings(),
      ga4Telemetry: this.siloSvc.getGA4TelemetrySettings(),
      matomoTelemetry: this.siloSvc.getMatomoTelemetrySettings(),
      wordpress: this.siloSvc.getWordPressSettings(),
      clickDistance: this.siloSvc.getClickDistanceSettings(),
      feedbackRerank: this.siloSvc.getFeedbackRerankSettings(),
      clustering: this.siloSvc.getClusteringSettings(),
      slateDiversity: this.siloSvc.getSlateDiversitySettings(),
      currentWeights: this.siloSvc.getCurrentWeights(),
    }).pipe(takeUntil(this.destroy$)).subscribe({
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
        this.ga4Telemetry = { ...this.ga4Telemetry, ...data.ga4Telemetry };
        this.matomoTelemetry = { ...this.matomoTelemetry, ...data.matomoTelemetry };
        this.wordpress = { ...this.wordpress, ...data.wordpress };
        this.clickDistance = { ...this.clickDistance, ...data.clickDistance };
        this.feedbackRerank = { ...this.feedbackRerank, ...data.feedbackRerank };
        this.clustering = { ...this.clustering, ...data.clustering };
        this.slateDiversity = { ...this.slateDiversity, ...data.slateDiversity };
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
    this.siloSvc.getCurrentWeights().pipe(takeUntil(this.destroy$)).subscribe({
      next: (weights) => {
        this.currentWeights = weights;
      },
    });
  }

  reloadPresetsAndHistory(shouldCheckAutoApply = false): void {
    this.loadingPresets = true;
    this.loadingHistory = true;
    this.siloSvc.listWeightPresets().pipe(takeUntil(this.destroy$)).subscribe({
      next: (presets) => { 
        this.weightPresets = presets; 
        this.loadingPresets = false;
        if (shouldCheckAutoApply) {
          this.checkAndAutoApplyRecommended();
        }
      },
      error: () => { this.loadingPresets = false; },
    });
    this.siloSvc.listWeightHistory().pipe(takeUntil(this.destroy$)).subscribe({
      next: (history) => { this.weightHistory = history; this.loadingHistory = false; },
      error: () => { this.loadingHistory = false; },
    });
  }

  private checkAndAutoApplyRecommended(): void {
    // If we have history or current weights don't look like "brand new", don't auto-apply.
    if (this.weightHistory.length > 0) return;
    
    const recommended = this.recommendedPreset;
    if (recommended && !this.matchedPreset) {
      this.siloSvc.applyWeightPreset(recommended.id).pipe(takeUntil(this.destroy$)).subscribe({
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
    this.siloSvc.applyWeightPreset(preset.id).pipe(takeUntil(this.destroy$)).subscribe({
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
    this.siloSvc.getCurrentWeights().pipe(takeUntil(this.destroy$)).subscribe({
      next: (weights) => {
        this.siloSvc.createWeightPreset({ name, weights }).pipe(takeUntil(this.destroy$)).subscribe({
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
    this.siloSvc.renameWeightPreset(preset.id, name).pipe(takeUntil(this.destroy$)).subscribe({
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
    this.siloSvc.deleteWeightPreset(preset.id).pipe(takeUntil(this.destroy$)).subscribe({
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
    this.siloSvc.rollbackWeights(row.id).pipe(takeUntil(this.destroy$)).subscribe({
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

  triggerRTune(): void {
    if (!confirm('Queue the R auto-tune task now? This will run in the background and may update your weights.')) return;
    this.triggeringRTune = true;
    this.siloSvc.triggerRTune().pipe(takeUntil(this.destroy$)).subscribe({
      next: () => {
        this.triggeringRTune = false;
        this.snack.open('R auto-tune task queued.', undefined, { duration: 2500 });
      },
      error: () => {
        this.triggeringRTune = false;
        this.snack.open('Failed to queue R auto-tune task.', 'Dismiss', { duration: 4000 });
      },
    });
  }

  historySourceLabel(source: string): string {
    return { r_auto: 'R auto-tune', manual: 'Manual', preset_applied: 'Preset applied' }[source] ?? source;
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
    this.siloSvc.updatePhraseMatchingSettings(this.phraseMatching).subscribe({
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
    this.siloSvc.updateLearnedAnchorSettings(this.learnedAnchor).subscribe({
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
    this.siloSvc.updateRareTermPropagationSettings(this.rareTermPropagation).subscribe({
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
    this.siloSvc.updateFieldAwareRelevanceSettings(this.fieldAwareRelevance).subscribe({
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

  saveGA4GSCSettings(): void {
    this.savingGA4GSC = true;
    this.siloSvc.updateGA4GSCSettings(this.ga4Gsc).subscribe({
      next: (ga4Gsc) => {
        this.ga4Gsc = ga4Gsc;
        this.refreshCurrentWeights();
        this.savingGA4GSC = false;
        this.snack.open('GA4 and Search Console settings saved', undefined, { duration: 2500 });
      },
      error: (error) => {
        this.savingGA4GSC = false;
        this.snack.open(error?.error?.detail || error?.error?.error || 'Failed to save GA4 and Search Console settings', 'Dismiss', { duration: 4000 });
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

    this.siloSvc.updateGA4TelemetrySettings(payload).subscribe({
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
    }).subscribe({
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
    }).subscribe({
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

    this.siloSvc.updateMatomoTelemetrySettings(payload).subscribe({
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
    }).subscribe({
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

  saveLinkFreshnessSettings(): void {
    this.savingLinkFreshness = true;
    this.siloSvc.updateLinkFreshnessSettings(this.linkFreshness).subscribe({
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

  saveClickDistanceSettings(): void {
    this.savingClickDistance = true;
    this.siloSvc.updateClickDistanceSettings(this.clickDistance).subscribe({
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
    this.siloSvc.updateFeedbackRerankSettings(this.feedbackRerank).subscribe({
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
    this.siloSvc.updateClusteringSettings(this.clustering).subscribe({
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
    this.siloSvc.updateSlateDiversitySettings(this.slateDiversity).subscribe({
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
    this.siloSvc.updateWeightedAuthoritySettings(this.weightedAuthority).subscribe({
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

    forkJoin({
      settings: this.siloSvc.updateSettings(this.settings),
      authority: this.siloSvc.updateWeightedAuthoritySettings(this.weightedAuthority),
      freshness: this.siloSvc.updateLinkFreshnessSettings(this.linkFreshness),
      phrase: this.siloSvc.updatePhraseMatchingSettings(this.phraseMatching),
      learned: this.siloSvc.updateLearnedAnchorSettings(this.learnedAnchor),
      rare: this.siloSvc.updateRareTermPropagationSettings(this.rareTermPropagation),
      relevance: this.siloSvc.updateFieldAwareRelevanceSettings(this.fieldAwareRelevance),
      ga4: this.siloSvc.updateGA4GSCSettings(this.ga4Gsc),
      ga4Telemetry: this.siloSvc.updateGA4TelemetrySettings(ga4TelemetryPayload),
      matomoTelemetry: this.siloSvc.updateMatomoTelemetrySettings(matomoTelemetryPayload),
      click: this.siloSvc.updateClickDistanceSettings(this.clickDistance),
      explore: this.siloSvc.updateFeedbackRerankSettings(this.feedbackRerank),
      clustering: this.siloSvc.updateClusteringSettings(this.clustering),
      slate: this.siloSvc.updateSlateDiversitySettings(this.slateDiversity),
      wordpress: this.siloSvc.updateWordPressSettings(wordpressPayload)
    }).pipe(takeUntil(this.destroy$)).subscribe({
      next: (results) => {
        this.settings = results.settings;
        this.weightedAuthority = results.authority;
        this.linkFreshness = results.freshness;
        this.phraseMatching = results.phrase;
        this.learnedAnchor = results.learned;
        this.rareTermPropagation = results.rare;
        this.fieldAwareRelevance = results.relevance;
        this.ga4Gsc = results.ga4;
        this.ga4Telemetry = results.ga4Telemetry;
        this.matomoTelemetry = results.matomoTelemetry;
        this.clickDistance = results.click;
        this.feedbackRerank = results.explore;
        this.clustering = results.clustering;
        this.slateDiversity = results.slate;
        this.wordpress = results.wordpress;
        this.wordpressPassword = '';
        this.ga4TelemetrySecret = '';
        this.ga4TelemetryReadPrivateKey = '';
        this.matomoTelemetryToken = '';
        
        this.savingSettings = false;
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
