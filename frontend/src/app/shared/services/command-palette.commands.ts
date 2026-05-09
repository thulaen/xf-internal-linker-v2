import { DEEP_LINK_CATALOG, type DeepLinkEntry } from '../../core/routing/deep-link-catalog';
import type { DeepLinkTarget } from './navigation-coordinator.service';

/**
 * One command that can be surfaced by the global Command Palette (Ctrl+K / Cmd+K).
 * Each command is a plain-English jump to a specific place in the app.
 */
export interface Command {
  /** Stable id used for tracking and testing. */
  id: string;
  /** Primary label shown to the user, e.g. "Change Performance Mode". */
  label: string;
  /** Secondary line, e.g. "Dashboard -> Performance Mode". */
  description: string;
  /** Extra search terms (synonyms, nicknames, acronyms). */
  keywords?: string[];
  /** Material icon ligature, e.g. "tune". */
  icon: string;
  /** Group this command is listed under. */
  section: 'Navigation' | 'Deep links';
  /** Where to go when the command is executed. */
  target: DeepLinkTarget;
}

// The palette's icon vocabulary. Falls back to `link` for anything not mapped.
// Keep the keys aligned with `DeepLinkEntry.key` so adding a new catalog
// entry only requires a one-line icon mapping if you want a custom glyph.
const ICONS_BY_KEY: Record<string, string> = {
  'dashboard.main': 'dashboard',
  'dashboard.activity-feed': 'history',
  'dashboard.pipeline-runs': 'pending_actions',
  'dashboard.pending-review': 'rate_review',
  'dashboard.performance-mode': 'tune',
  'review.main': 'rate_review',
  'link-health.main': 'link_off',
  'jobs.main': 'pending_actions',
  'health.main': 'health_and_safety',
  'health.services-section': 'fact_check',
  'diagnostics.main': 'memory',
  'mcp.main': 'smart_toy',
  'mcp.status': 'monitor_heart',
  'mcp.agents': 'group',
  'mcp.tools': 'build',
  'mcp.schedules': 'schedule',
  'reports.monthly': 'description',
  'settings.main': 'settings',
  'settings.pagerank': 'tune',
  'settings.link-freshness': 'tune',
  'settings.phrase-matching': 'tune',
  'settings.learned-anchors': 'tune',
  'settings.rare-term': 'tune',
  'settings.field-aware-relevance': 'tune',
  'settings.traffic-search-signals': 'tune',
  'settings.click-distance': 'tune',
  'settings.spam-guards': 'tune',
  'settings.feedback-reranking': 'tune',
  'settings.near-duplicate-clustering': 'tune',
  'settings.slate-diversity': 'tune',
  'settings.graph-candidates': 'tune',
  'settings.value-model-scoring': 'tune',
  'embeddings.main': 'memory',
  'graph.main': 'account_tree',
  'analytics.main': 'bar_chart',
  'alerts.main': 'notifications',
  'alerts.detail': 'notifications_active',
  'scheduled-updates.main': 'update',
  'behavioral-hubs.main': 'hub',
  'crawler.main': 'travel_explore',
  'error-log.main': 'bug_report',
  'error-log.auto-issues': 'auto_fix_high',
  'error-log.pyroscope': 'whatshot',
  'performance.main': 'speed',
  'operations-feed.main': 'rss_feed',
  'preferences.main': 'manage_accounts',
  'admin-models.main': 'model_training',
  'audit.undo-timeline': 'history_toggle_off',
};

function iconFor(entry: DeepLinkEntry): string {
  return ICONS_BY_KEY[entry.key] ?? (entry.scrollTarget ? 'anchor' : 'link');
}

function entryToCommand(entry: DeepLinkEntry): Command {
  const isMainEntry = !entry.scrollTarget && !entry.tab && !entry.dialog;
  return {
    id: `dl-${entry.key}`,
    label: entry.label,
    description: entry.subtitle,
    keywords: [...entry.searchTerms],
    icon: iconFor(entry),
    section: isMainEntry ? 'Navigation' : 'Deep links',
    target: {
      route: entry.route,
      fragment: entry.scrollTarget,
      targetId: entry.scrollTarget,
    },
  };
}

/**
 * The full command list, derived from the deep-link catalog. Adding a new
 * catalog entry instantly surfaces it here — there is no second list to
 * keep in sync. The PARAMOUNT rule in `CLAUDE.md` and `DEEP-LINKING-CATALOG.md`
 * is satisfied by this single derivation.
 */
export const COMMANDS: Command[] = DEEP_LINK_CATALOG.map(entryToCommand);
