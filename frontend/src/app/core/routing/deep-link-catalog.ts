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
  /** Optional tab key inside the route (matches `MatTabGroup` persistKey). */
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
    key: 'diagnostics.main',
    label: 'Technical diagnostics',
    subtitle: 'Deep technical health view with error log and live runtime.',
    route: '/diagnostics',
    searchTerms: ['diagnostics', 'errors', 'pipeline gate', 'runtime'],
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
    key: 'analytics.main',
    label: 'Analytics',
    subtitle: 'SEO impact reports from Google Search Console and Google Analytics 4.',
    route: '/analytics',
    searchTerms: ['analytics', 'gsc', 'ga4', 'search console', 'reports'],
  },
  {
    key: 'alerts.main',
    label: 'Alerts',
    subtitle: 'Operator alert centre.',
    route: '/alerts',
    searchTerms: ['alerts', 'notifications', 'warnings'],
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
    searchTerms: ['errors', 'log', 'failures', 'tracebacks'],
  },
  {
    key: 'performance.main',
    label: 'Performance',
    subtitle: 'Benchmark results for C++ and Python hot paths.',
    route: '/performance',
    searchTerms: ['performance', 'benchmark', 'speed', 'c++'],
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
