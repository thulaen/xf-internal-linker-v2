/**
 * Deep-link catalog — every linkable surface in the app.
 *
 * The PARAMOUNT rule in `CLAUDE.md` and `DEEP-LINKING-CATALOG.md` requires
 * every new route, tab, dialog, filter, or named scroll target to register
 * itself here in the same commit it ships. This file is the single source
 * of truth for the in-app `⌘K` quick-search bar, the "Copy link to this
 * view" button, breadcrumb labels, and the friendly "Almost there" prereq
 * dialog when a deep link is hit but a prerequisite is missing.
 *
 * Adding an entry is shape-only: TypeScript will refuse to compile if a
 * required field is absent, so the catalog can never silently drift.
 *
 * KISS v1: this catalog seeds the new MCP / Monthly-Reports surfaces plus
 * the most-trafficked existing routes (Dashboard, Settings, Jobs, Health,
 * Diagnostics, Review, Link Health). Future commits backfill the rest as
 * they touch the relevant components.
 */

import { DEV_DEEP_LINK_CATALOG } from '../../dev/dev-deep-link-catalog';

export interface DeepLinkPrereqHint {
  label: string;
  instructions: string[];
  navigateTo: string;
}

export interface DeepLinkEntry {
  /** Stable key used by quick-search and the URL `?dl=` parameter. */
  key: string;
  /** Plain-English label shown in search results and breadcrumbs. */
  label: string;
  /** One-line subtitle explaining what the page does. */
  subtitle: string;
  /** Angular route, e.g. '/diagnostics'. */
  route: string;
  /**
   * Optional tab key inside the route. The host component must declare
   * a matching `data-persist-key` attribute on the active `<mat-tab>`
   * (or use the `appPersistTab` directive — both are read by
   * `revealHiddenParent` to switch tabs after a fragment navigation).
   */
  tab?: string;
  /** Optional dialog component name to open. */
  dialog?: string;
  /** Optional named scroll target (mat-card id, section id, etc.). */
  scrollTarget?: string;
  /** Search keywords beyond the label (synonyms, error messages, etc.). */
  searchTerms: string[];
  /** Required permissions (empty / undefined = anyone authenticated). */
  requires?: string[];
  /** Friendly fallback when a required prereq is missing. */
  prereqHint?: DeepLinkPrereqHint;
}

/**
 * The catalog itself. Entries are kebab-cased by surface area:
 *   - `<surface>.<page>.<sub>` for sub-sections
 *   - `<surface>.dialog.<name>` for dialogs
 *
 * Keep entries sorted by route to make diffs easy to read.
 */
export const DEEP_LINK_CATALOG: readonly DeepLinkEntry[] = [
  {
    key: 'dashboard.main',
    label: 'Dashboard',
    subtitle: 'Overview of jobs, suggestions, and key metrics.',
    route: '/dashboard',
    searchTerms: ['dashboard', 'home', 'overview', 'metrics'],
  },
  {
    key: 'dashboard.activity-feed',
    label: 'Activity feed',
    subtitle: 'Recent sync activity and pipeline progress.',
    route: '/dashboard',
    scrollTarget: 'dashboard-activity-feed',
    searchTerms: ['activity', 'feed', 'sync activity', 'recent jobs'],
  },
  {
    key: 'dashboard.pipeline-runs',
    label: 'Pipeline runs',
    subtitle: 'Recent pipeline runs on the dashboard.',
    route: '/dashboard',
    scrollTarget: 'dashboard-pipeline-runs',
    searchTerms: ['pipeline', 'runs', 'jobs'],
  },
  {
    key: 'dashboard.pending-review',
    label: 'Pending review',
    subtitle: 'Suggestions awaiting operator review.',
    route: '/dashboard',
    scrollTarget: 'dashboard-stat-pending-review',
    searchTerms: ['pending', 'review', 'queue'],
  },
  {
    key: 'dashboard.performance-mode',
    label: 'Change Performance Mode',
    subtitle: 'CPU / GPU / safe / balanced runtime profile.',
    route: '/dashboard',
    scrollTarget: 'performance-mode',
    searchTerms: ['performance', 'mode', 'cpu', 'gpu', 'safe', 'balanced'],
  },
  {
    key: 'dashboard.runtime-mode',
    label: 'Runtime Mode',
    subtitle: 'Live runtime status and active model selection.',
    route: '/dashboard',
    scrollTarget: 'runtime-mode',
    searchTerms: ['runtime', 'mode', 'champion', 'candidate'],
  },
  {
    key: 'dashboard.what-changed',
    label: 'What Changed',
    subtitle: 'Recent system changes and actor attribution.',
    route: '/dashboard',
    scrollTarget: 'what-changed',
    searchTerms: ['changes', 'audit', 'recent'],
  },
  {
    key: 'dashboard.today-focus',
    label: 'Today Focus',
    subtitle: "Today's recommended operator focus area.",
    route: '/dashboard',
    scrollTarget: 'today-focus',
    searchTerms: ['focus', 'today', 'recommended'],
  },
  {
    key: 'dashboard.system-signals',
    label: 'System Signals',
    subtitle: 'Section grouping all live system-signal metrics.',
    route: '/dashboard',
    scrollTarget: 'system-signals',
    searchTerms: ['signals', 'metrics', 'live'],
  },
  {
    key: 'dashboard.sync-activity',
    label: 'Sync Activity',
    subtitle: 'Recent sync activity feed (imports, crawls, webhooks).',
    route: '/dashboard',
    scrollTarget: 'sync-activity',
    searchTerms: ['sync', 'activity', 'feed', 'import', 'crawl'],
  },
  {
    key: 'dashboard.fix-runbooks',
    label: 'Fix Runbooks',
    subtitle: 'One-click runbooks to clear common dashboard problems.',
    route: '/dashboard',
    scrollTarget: 'fix-runbooks-strip',
    searchTerms: ['fix', 'runbooks', 'remediation'],
  },
  {
    key: 'review.main',
    label: 'Review suggestions',
    subtitle: 'Review and approve link suggestions.',
    route: '/review',
    searchTerms: ['review', 'approve', 'reject', 'suggestions queue'],
  },
  {
    key: 'link-health.main',
    label: 'Link health',
    subtitle: 'Broken-link scanner and status tracker.',
    route: '/link-health',
    searchTerms: ['broken links', 'link health', 'scanner', '404'],
  },
  {
    key: 'jobs.main',
    label: 'Jobs',
    subtitle: 'Background job queue and history.',
    route: '/jobs',
    searchTerms: ['jobs', 'queue', 'celery', 'history', 'tasks'],
  },
  {
    key: 'health.main',
    label: 'System health',
    subtitle: 'Real-time status of data sources and services.',
    route: '/health',
    searchTerms: ['health', 'services', 'status', 'system'],
  },
  {
    key: 'health.services-section',
    label: 'Services',
    subtitle: 'Per-service uptime and health badges.',
    route: '/health',
    scrollTarget: 'services-section',
    searchTerms: ['services', 'uptime', 'badges'],
  },
  {
    key: 'diagnostics.main',
    label: 'Technical diagnostics',
    subtitle: 'Deep technical health view with error log and live runtime.',
    route: '/diagnostics',
    searchTerms: ['diagnostics', 'errors', 'pipeline gate', 'runtime'],
  },
  {
    key: 'find-bugs.main',
    label: 'Find Bugs',
    subtitle: 'Automated bug-pattern findings with confirm and triage actions.',
    route: '/find-bugs',
    searchTerms: ['find bugs', 'findbugs', 'bug patterns', 'static analysis', 'findings'],
  },
  {
    key: 'find-bugs.severity-chart',
    label: 'Find Bugs — severity spread',
    subtitle: 'Bar chart of how many findings fall into each severity level.',
    route: '/find-bugs',
    scrollTarget: 'find-bugs-severity-card',
    searchTerms: ['severity', 'severity spread', 'bug chart', 'critical high medium low'],
  },
  {
    key: 'observability.main',
    label: 'Observability',
    subtitle: 'Live health of the monitoring and quality stack (metrics, logs, traces).',
    route: '/observability',
    searchTerms: ['observability', 'stack health', 'metrics', 'logs', 'traces', 'monitoring'],
  },
  {
    key: 'work-queue.main',
    label: 'Work Queue',
    subtitle: 'Repair control center for AutoIssues, Paper Trail, and agent tasks.',
    route: '/work-queue',
    searchTerms: ['work queue', 'agent queue', 'autoissues', 'paper trail', 'repair tasks'],
  },
  {
    key: 'mcp.main',
    label: 'AI Agents (MCP)',
    subtitle:
      'Connect Claude Code, Codex, and Antigravity. Live MCP server status, tools list, sentient-schedules table.',
    route: '/mcp',
    searchTerms: [
      'mcp',
      'model context protocol',
      'ai agents',
      'claude code',
      'codex',
      'antigravity',
      'tools',
      'connect',
    ],
  },
  {
    key: 'mcp.status',
    label: 'MCP server status',
    subtitle: 'Live server-health badge and recent errors.',
    route: '/mcp',
    scrollTarget: 'mcp-status-card',
    searchTerms: ['mcp status', 'health', 'error', 'live'],
  },
  {
    key: 'mcp.agents',
    label: 'AI agents detected',
    subtitle: 'Per-agent install + connection status.',
    route: '/mcp',
    scrollTarget: 'mcp-agents-card',
    searchTerms: ['agents', 'detected', 'installed', 'claude code', 'codex'],
  },
  {
    key: 'mcp.tools',
    label: 'MCP tools exposed',
    subtitle: 'List of tools your AI agent can call against this app.',
    route: '/mcp',
    scrollTarget: 'mcp-tools-card',
    searchTerms: ['tools', 'mcp tools', 'list orphans', 'top candidates'],
  },
  {
    key: 'mcp.schedules',
    label: 'Schedules (sentient)',
    subtitle: 'Every registered schedule + recent runs + recovered-run flag.',
    route: '/mcp',
    scrollTarget: 'mcp-schedules-card',
    searchTerms: ['schedule', 'cron', 'tracker', 'missed runs', 'recovery'],
  },
  {
    key: 'reports.monthly',
    label: 'Monthly reports',
    subtitle: 'Top-50 link suggestions auto-generated on the 1st of every month.',
    route: '/reports/monthly',
    searchTerms: [
      'monthly',
      'reports',
      'top 50',
      'top-50',
      'link suggestions report',
    ],
  },
  {
    key: 'settings.main',
    label: 'Settings',
    subtitle: 'Theme, silo controls, and app settings.',
    route: '/settings',
    searchTerms: ['settings', 'config', 'theme', 'silo'],
  },
  {
    key: 'settings.pagerank',
    label: 'PageRank settings',
    subtitle: 'PageRank weight, damping, and refresh schedule.',
    route: '/settings',
    tab: 'ranking-weights',
    scrollTarget: 'settings-pagerank',
    searchTerms: ['pagerank', 'weight', 'damping'],
  },
  {
    key: 'settings.link-freshness',
    label: 'Link Freshness',
    subtitle: 'Decay function controlling how recency boosts links.',
    route: '/settings',
    tab: 'ranking-weights',
    scrollTarget: 'settings-link-freshness',
    searchTerms: ['link freshness', 'recency', 'decay'],
  },
  {
    key: 'settings.phrase-matching',
    label: 'Phrase Matching',
    subtitle: 'Phrase-level scoring weights and stop-word handling.',
    route: '/settings',
    tab: 'ranking-weights',
    scrollTarget: 'settings-phrase-matching',
    searchTerms: ['phrase matching', 'phrase scoring'],
  },
  {
    key: 'settings.learned-anchors',
    label: 'Learned Anchors',
    subtitle: 'Anchor-text learning from operator approvals.',
    route: '/settings',
    tab: 'ranking-weights',
    scrollTarget: 'settings-learned-anchors',
    searchTerms: ['learned anchors', 'anchor', 'training'],
  },
  {
    key: 'settings.rare-term',
    label: 'Rare Term Boost',
    subtitle: 'IDF boost for rare query terms.',
    route: '/settings',
    tab: 'ranking-weights',
    scrollTarget: 'settings-rare-term',
    searchTerms: ['rare term', 'idf', 'boost'],
  },
  {
    key: 'settings.field-aware-relevance',
    label: 'Field-Aware Relevance',
    subtitle: 'Per-field scoring weights (title, body, anchor, headers).',
    route: '/settings',
    tab: 'ranking-weights',
    scrollTarget: 'settings-field-aware-relevance',
    searchTerms: ['field aware relevance', 'bm25f', 'fields'],
  },
  {
    key: 'settings.traffic-search-signals',
    label: 'Traffic & Search Signals',
    subtitle: 'GA4 / GSC traffic-derived ranking inputs.',
    route: '/settings',
    tab: 'ranking-weights',
    scrollTarget: 'settings-traffic-search-signals',
    searchTerms: ['traffic', 'search signals', 'ga4', 'gsc'],
  },
  {
    key: 'settings.click-distance',
    label: 'Click Distance',
    subtitle: 'Click-distance penalty / reward in ranking.',
    route: '/settings',
    tab: 'ranking-weights',
    scrollTarget: 'settings-click-distance',
    searchTerms: ['click distance', 'shortest path'],
  },
  {
    key: 'settings.spam-guards',
    label: 'Spam Guards',
    subtitle: 'Spam-pattern detectors that suppress suggestions.',
    route: '/settings',
    tab: 'ranking-weights',
    scrollTarget: 'settings-spam-guards',
    searchTerms: ['spam guards', 'spam', 'penalty'],
  },
  {
    key: 'settings.feedback-reranking',
    label: 'Feedback Reranking',
    subtitle: 'Operator-feedback reranker weights.',
    route: '/settings',
    tab: 'ranking-weights',
    scrollTarget: 'settings-feedback-reranking',
    searchTerms: ['feedback', 'reranking', 'reranker'],
  },
  {
    key: 'settings.near-duplicate-clustering',
    label: 'Near-Duplicate Clustering',
    subtitle: 'Cluster size and threshold for near-duplicate URLs.',
    route: '/settings',
    tab: 'ranking-weights',
    scrollTarget: 'settings-near-duplicate-clustering',
    searchTerms: ['near duplicate', 'clustering', 'simhash'],
  },
  {
    key: 'settings.slate-diversity',
    label: 'Slate Diversity',
    subtitle: 'MMR-style diversity penalty for the suggestion slate.',
    route: '/settings',
    tab: 'ranking-weights',
    scrollTarget: 'settings-slate-diversity',
    searchTerms: ['slate diversity', 'mmr', 'diversity'],
  },
  {
    key: 'settings.graph-candidates',
    label: 'Graph Candidates',
    subtitle: 'Graph-walk candidate generation budgets.',
    route: '/settings',
    tab: 'ranking-weights',
    scrollTarget: 'settings-graph-candidates',
    searchTerms: ['graph candidates', 'random walk'],
  },
  {
    key: 'settings.value-model-scoring',
    label: 'Value-Model Scoring',
    subtitle: 'Final value-model scoring weights.',
    route: '/settings',
    tab: 'ranking-weights',
    scrollTarget: 'settings-value-model-scoring',
    searchTerms: ['value model', 'scoring'],
  },
  {
    key: 'embeddings.main',
    label: 'Embeddings',
    subtitle: 'Switch providers, run bake-offs, audit embedding quality.',
    route: '/embeddings',
    searchTerms: ['embeddings', 'providers', 'bake-off', 'bge', 'openai', 'gemini'],
  },
  {
    key: 'graph.main',
    label: 'Link graph',
    subtitle: 'Visualise the internal link graph.',
    route: '/graph',
    searchTerms: ['graph', 'link graph', 'topology', 'visualisation'],
  },
  {
    key: 'graph.network-viz',
    label: 'Link graph — network map',
    subtitle: 'A map of your pages as dots and the links between them as lines; colour shows page importance.',
    route: '/graph',
    scrollTarget: 'graph-network-viz-card',
    searchTerms: ['network', 'force graph', 'node link', 'pagerank', 'silo map'],
  },
  {
    key: 'graph.context-distribution',
    label: 'Link graph — context distribution',
    subtitle: 'Pie of links inside real content (contextual) vs weak spots vs isolated.',
    route: '/graph',
    scrollTarget: 'graph-context-distribution-card',
    searchTerms: ['context', 'contextual', 'weak context', 'isolated', 'link quality pie'],
  },
  {
    key: 'graph.anchor-frequency',
    label: 'Link graph — anchor text frequency',
    subtitle: 'The 15 most-used link phrases and how often each one appears.',
    route: '/graph',
    scrollTarget: 'graph-anchor-text-frequency-card',
    searchTerms: ['anchor', 'anchor text', 'link phrase', 'over-optimised anchors'],
  },
  {
    key: 'graph.velocity',
    label: 'Link graph — network velocity',
    subtitle: 'Links created vs links that disappeared, day by day.',
    route: '/graph',
    scrollTarget: 'graph-velocity-card',
    searchTerms: ['velocity', 'freshness', 'links created', 'links disappeared', 'churn'],
  },
  {
    key: 'graph.signals',
    label: 'Link graph — structural signals',
    subtitle: 'Off-path structural link candidates and communities from NetworKit.',
    route: '/graph/signals',
    searchTerms: ['graph signals', 'networkit', 'adamic-adar', 'communities', 'structural candidates'],
  },
  {
    key: 'analytics.main',
    label: 'Analytics',
    subtitle: 'SEO impact reports from Google Search Console and Google Analytics 4.',
    route: '/analytics',
    searchTerms: ['analytics', 'gsc', 'ga4', 'search console', 'reports'],
  },
  {
    key: 'analytics.funnel',
    label: 'Analytics — funnel performance',
    subtitle: 'How many visitors move from one step to the next; a big drop means people leave at that step.',
    route: '/analytics',
    scrollTarget: 'analytics-funnel',
    searchTerms: ['funnel', 'impressions clicks views', 'conversion funnel'],
  },
  {
    key: 'analytics.algorithm-versions',
    label: 'Analytics — algorithm performance',
    subtitle: 'Compares how well each version of the ranking math performed.',
    route: '/analytics',
    scrollTarget: 'analytics-algorithm',
    searchTerms: ['algorithm', 'version comparison', 'model version', 'ctr engagement'],
  },
  {
    key: 'analytics.engagement-trend',
    label: 'Analytics — engagement trend',
    subtitle: 'Daily clicks next to engagement rate as a percent.',
    route: '/analytics',
    scrollTarget: 'analytics-trend',
    searchTerms: ['trend', 'engagement trend', 'clicks over time', 'ctr trend'],
  },
  {
    key: 'analytics.device-mix',
    label: 'Analytics — device mix',
    subtitle: 'Share of visits by device.',
    route: '/analytics',
    scrollTarget: 'analytics-device-mix-card',
    searchTerms: ['device', 'device mix', 'mobile desktop tablet'],
  },
  {
    key: 'analytics.channel-mix',
    label: 'Analytics — channel mix',
    subtitle: 'Share of visits by traffic source.',
    route: '/analytics',
    scrollTarget: 'analytics-channel-mix-card',
    searchTerms: ['channel', 'channel mix', 'traffic source', 'organic search direct'],
  },
  {
    key: 'analytics.geographic-mix',
    label: 'Analytics — geographic mix',
    subtitle: 'Visits by country.',
    route: '/analytics',
    scrollTarget: 'analytics-geographic-mix-card',
    searchTerms: ['geographic', 'geo', 'country', 'countries'],
  },
  {
    key: 'analytics.traffic-lift-scatter',
    label: 'Analytics — traffic vs lift scatter',
    subtitle: 'Each dot is a suggestion: page traffic vs the percent change after the link.',
    route: '/analytics',
    scrollTarget: 'analytics-traffic-lift-scatter-card',
    searchTerms: ['scatter', 'traffic lift', 'uplift', 'baseline clicks'],
  },
  {
    key: 'analytics.engagement-mix',
    label: 'Analytics — engagement mix',
    subtitle: 'Bars showing how visits split across quick-exit, 30-second, and 60-second dwell.',
    route: '/analytics',
    scrollTarget: 'analytics-engagement-mix',
    searchTerms: ['engagement', 'dwell', 'quick exit', 'mix', 'session quality'],
  },
  {
    key: 'analytics.cohort-by-platform',
    label: 'Analytics — cohort by platform',
    subtitle: 'How applied suggestions perform broken out by traffic platform.',
    route: '/analytics',
    scrollTarget: 'analytics-cohort-by-platform-card',
    searchTerms: ['cohort', 'platform', 'breakdown', 'applied suggestions'],
  },
  {
    key: 'analytics.cohort-by-anchor-family',
    label: 'Analytics — cohort by anchor family',
    subtitle: 'How applied suggestions perform grouped by the kind of link phrase used.',
    route: '/analytics',
    scrollTarget: 'analytics-cohort-by-anchor-family-card',
    searchTerms: ['cohort', 'anchor family', 'anchor text', 'breakdown'],
  },
  {
    key: 'alerts.main',
    label: 'Alerts',
    subtitle: 'Operator alert centre.',
    route: '/alerts',
    searchTerms: ['alerts', 'notifications', 'warnings'],
  },
  {
    key: 'alerts.detail',
    label: 'Alert detail',
    subtitle: 'Single-alert view with traceback, actor, and resolution timeline.',
    route: '/alerts',
    searchTerms: ['alert detail', 'single alert', 'traceback'],
  },
  {
    key: 'scheduled-updates.main',
    label: 'Scheduled updates',
    subtitle: 'Background refresh jobs (11 am – 11 pm serial runner).',
    route: '/scheduled-updates',
    searchTerms: ['scheduled', 'updates', 'background jobs', 'runner'],
  },
  {
    key: 'behavioral-hubs.main',
    label: 'Behavioural hubs',
    subtitle: 'Co-navigation article clusters from GA4 session data.',
    route: '/behavioral-hubs',
    searchTerms: ['behavioural', 'hubs', 'co-navigation', 'clusters'],
  },
  {
    key: 'crawler.main',
    label: 'Web crawler',
    subtitle: 'Crawl your sites for SEO audit, broken links, and content discovery.',
    route: '/crawler',
    searchTerms: ['crawler', 'crawl', 'seo audit', 'discovery'],
  },
  {
    key: 'error-log.main',
    label: 'Error log',
    subtitle: 'Background job errors with plain-English explanations.',
    route: '/error-log',
    tab: 'internal',
    searchTerms: ['errors', 'log', 'failures', 'tracebacks'],
  },
  {
    key: 'error-log.glitchtip',
    label: 'GlitchTip',
    subtitle: 'Frontend + backend errors as captured by the GlitchTip integration.',
    route: '/error-log',
    tab: 'glitchtip',
    searchTerms: ['glitchtip', 'sentry', 'frontend errors'],
  },
  {
    key: 'error-log.all',
    label: 'All errors',
    subtitle: 'Combined view across every error source.',
    route: '/error-log',
    tab: 'all',
    searchTerms: ['all errors', 'combined', 'merged'],
  },
  {
    key: 'error-log.auto-issues',
    label: 'Auto-Issues',
    subtitle: 'Cross-source-deduped issues from GlitchTip, internal errors, Pyroscope. Read lessons_learned from prior fixes.',
    route: '/error-log',
    tab: 'auto-issues',
    searchTerms: ['auto-issues', 'registry', 'lessons learned', 'dedup'],
  },
  {
    key: 'error-log.pyroscope',
    label: 'Pyroscope',
    subtitle: 'Continuous profiling — flamegraphs of hot Python code.',
    route: '/error-log',
    tab: 'pyroscope',
    searchTerms: ['pyroscope', 'profiling', 'flamegraph', 'cpu hot'],
  },
  {
    key: 'performance.main',
    label: 'Performance',
    subtitle: 'Benchmark results for C++ and Python hot paths.',
    route: '/performance',
    searchTerms: ['performance', 'benchmark', 'speed', 'c++'],
  },
  {
    key: 'performance.trend-chart',
    label: 'Performance — trend chart',
    subtitle: 'How long each benchmarked function takes (in milliseconds) over time — lower is faster.',
    route: '/performance',
    scrollTarget: 'performance-trend-chart-card',
    searchTerms: ['performance trend', 'benchmark history', 'mean time', 'milliseconds'],
  },
  {
    key: 'operations-feed.main',
    label: 'Operations feed',
    subtitle: 'Live commentary of what the system is doing right now.',
    route: '/operations-feed',
    searchTerms: ['operations', 'feed', 'live', 'commentary'],
  },
  {
    key: 'preferences.main',
    label: 'Preferences',
    subtitle: 'Personal preferences — theme, accessibility, passkeys.',
    route: '/preferences',
    searchTerms: ['preferences', 'profile', 'me', 'passkeys'],
  },
  {
    key: 'admin-models.main',
    label: 'Admin models',
    subtitle: 'Champion/candidate model registry — promote, retire, audit.',
    route: '/admin/models',
    searchTerms: ['admin', 'models', 'champion', 'candidate', 'registry'],
  },
  {
    key: 'audit.undo-timeline',
    label: 'Undo timeline (audit)',
    subtitle: 'Audit-trail timeline with one-click undo for recent operator actions.',
    route: '/audit/undo-timeline',
    searchTerms: ['undo', 'audit', 'timeline', 'history'],
  },
  ...DEV_DEEP_LINK_CATALOG,
];

/** Look up an entry by its key. Returns undefined for unknown keys. */
export function findDeepLink(key: string): DeepLinkEntry | undefined {
  return DEEP_LINK_CATALOG.find((entry) => entry.key === key);
}

/**
 * Return every entry whose label, subtitle, route, or searchTerms contain
 * the given (lower-cased) query. KISS substring match — good enough for the
 * `⌘K` quick-search bar at v1; can swap in fuzzy matching later.
 */
export function searchDeepLinks(query: string): DeepLinkEntry[] {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  return DEEP_LINK_CATALOG.filter((entry) => {
    if (entry.label.toLowerCase().includes(q)) return true;
    if (entry.subtitle.toLowerCase().includes(q)) return true;
    if (entry.route.toLowerCase().includes(q)) return true;
    return entry.searchTerms.some((term) => term.toLowerCase().includes(q));
  });
}
