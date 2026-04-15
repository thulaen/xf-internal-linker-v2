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
  /** Group this command is listed under. Keep the set small. */
  section: 'Navigation' | 'Deep links';
  /** Where to go when the command is executed. */
  target: DeepLinkTarget;
}

/**
 * Initial static command list.
 *
 * Rules for adding commands:
 *  - Only add a deep-link entry if the target id is verified to exist in the DOM.
 *  - Prefer labels that read like a human task ("Change Performance Mode"), not raw page names.
 *  - Keep keywords focused — they widen the search, so noise hurts relevance.
 */
export const COMMANDS: Command[] = [
  // Navigation ---------------------------------------------------------
  {
    id: 'nav-dashboard',
    label: 'Dashboard',
    description: 'Overview of jobs, suggestions, and metrics',
    icon: 'dashboard',
    keywords: ['home', 'overview'],
    section: 'Navigation',
    target: { route: '/dashboard' },
  },
  {
    id: 'nav-review',
    label: 'Review Suggestions',
    description: 'Review and approve link suggestions',
    icon: 'rate_review',
    keywords: ['suggestions', 'approve'],
    section: 'Navigation',
    target: { route: '/review' },
  },
  {
    id: 'nav-link-health',
    label: 'Link Health',
    description: 'Broken link scanner and status',
    icon: 'link_off',
    keywords: ['broken', 'scanner'],
    section: 'Navigation',
    target: { route: '/link-health' },
  },
  {
    id: 'nav-graph',
    label: 'Link Graph',
    description: 'Visualize the internal link graph',
    icon: 'account_tree',
    keywords: ['d3', 'visual', 'network'],
    section: 'Navigation',
    target: { route: '/graph' },
  },
  {
    id: 'nav-behavioral-hubs',
    label: 'Behavioral Hubs',
    description: 'Co-navigation clusters from GA4 sessions',
    icon: 'hub',
    keywords: ['clusters', 'ga4', 'co-navigation'],
    section: 'Navigation',
    target: { route: '/behavioral-hubs' },
  },
  {
    id: 'nav-analytics',
    label: 'Analytics',
    description: 'SEO impact reports from GSC and GA4',
    icon: 'bar_chart',
    keywords: ['gsc', 'ga4', 'seo', 'reports', 'attribution'],
    section: 'Navigation',
    target: { route: '/analytics' },
  },
  {
    id: 'nav-jobs',
    label: 'Jobs',
    description: 'Background job queue and history',
    icon: 'pending_actions',
    keywords: ['queue', 'history', 'tasks', 'quarantine'],
    section: 'Navigation',
    target: { route: '/jobs' },
  },
  {
    id: 'nav-health',
    label: 'System Health',
    description: 'Real-time status of data sources and services',
    icon: 'health_and_safety',
    keywords: ['cpu', 'gpu', 'status', 'services', 'uptime'],
    section: 'Navigation',
    target: { route: '/health' },
  },
  {
    id: 'nav-settings',
    label: 'Settings',
    description: 'Theme, silos, and application settings',
    icon: 'settings',
    keywords: ['preferences', 'config'],
    section: 'Navigation',
    target: { route: '/settings' },
  },
  {
    id: 'nav-alerts',
    label: 'Alerts',
    description: 'Operator alert center',
    icon: 'notifications',
    keywords: ['notifications', 'issues', 'warnings'],
    section: 'Navigation',
    target: { route: '/alerts' },
  },
  {
    id: 'nav-crawler',
    label: 'Web Crawler',
    description: 'Crawl sites for SEO audit and discovery',
    icon: 'travel_explore',
    keywords: ['crawl', 'spider', 'discovery'],
    section: 'Navigation',
    target: { route: '/crawler' },
  },
  {
    id: 'nav-error-log',
    label: 'Error Log',
    description: 'Background job errors with plain-English explanations',
    icon: 'bug_report',
    keywords: ['errors', 'bugs', 'failures'],
    section: 'Navigation',
    target: { route: '/error-log' },
  },
  {
    id: 'nav-performance',
    label: 'Performance',
    description: 'Benchmark results for C++ and Python hot paths',
    icon: 'speed',
    keywords: ['benchmarks', 'cpp', 'fast'],
    section: 'Navigation',
    target: { route: '/performance' },
  },
  {
    id: 'nav-diagnostics',
    label: 'Technical Diagnostics',
    description: 'Deep diagnostic data for developers',
    icon: 'memory',
    keywords: ['tech', 'debug'],
    section: 'Navigation',
    target: { route: '/diagnostics' },
  },

  // Deep links (verified target ids) ----------------------------------
  {
    // Target: frontend/src/app/dashboard/performance-mode/performance-mode.component.ts:62
    id: 'deep-performance-mode',
    label: 'Change Performance Mode',
    description: 'Dashboard -> Performance Mode card',
    icon: 'tune',
    keywords: ['perf', 'cpu', 'gpu', 'balanced', 'safe', 'high performance'],
    section: 'Deep links',
    target: { route: '/dashboard', fragment: 'performance-mode', targetId: 'performance-mode' },
  },
  {
    // Target: frontend/src/app/health/health.component.html:196 -> <section id="services-section">
    id: 'deep-service-health',
    label: 'Check Service Health',
    description: 'Health -> Services section',
    icon: 'fact_check',
    keywords: ['services', 'status', 'uptime'],
    section: 'Deep links',
    target: { route: '/health', fragment: 'services-section', targetId: 'services-section' },
  },
];
