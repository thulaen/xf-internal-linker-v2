import { Page } from '@playwright/test';

const appearanceConfig = {
  primaryColor: '#0078d4',
  accentColor: '#0f6cbd',
  fontSize: 'medium',
  layoutWidth: 'wide',
  sidebarWidth: 'standard',
  density: 'comfortable',
  headerBg: '#0066cc',
  siteName: 'XF Internal Linker',
  showScrollToTop: true,
  footerText: 'XF Internal Linker V2',
  showFooter: true,
  footerBg: '#faf9f8',
  logoUrl: '',
  faviconUrl: '',
  presets: [],
};

const dashboardData = {
  suggestion_counts: {
    pending: 18,
    approved: 7,
    rejected: 3,
    applied: 12,
    total: 40,
  },
  content_count: 284,
  open_broken_links: 5,
  last_sync: {
    completed_at: '2026-03-30T22:15:00Z',
    source: 'WordPress',
    mode: 'incremental',
    items_synced: 24,
  },
  pipeline_runs: [
    {
      run_id: 'run-12345678-aaaa-bbbb-cccc-1234567890ab',
      run_state: 'completed',
      rerun_mode: 'skip_pending',
      suggestions_created: 16,
      destinations_processed: 42,
      duration_display: '2m 13s',
      created_at: '2026-03-30T21:55:00Z',
    },
    {
      run_id: 'run-abcdef12-aaaa-bbbb-cccc-1234567890ab',
      run_state: 'running',
      rerun_mode: 'skip_pending',
      suggestions_created: 4,
      destinations_processed: 18,
      duration_display: null,
      created_at: '2026-03-31T07:05:00Z',
    },
  ],
  recent_imports: [
    {
      job_id: 'job-1001',
      status: 'completed',
      source: 'WordPress',
      mode: 'incremental',
      items_synced: 24,
      created_at: '2026-03-30T21:00:00Z',
      completed_at: '2026-03-30T21:04:00Z',
    },
  ],
};

const diagnosticsOverview = {
  summary: {
    healthy: 6,
    degraded: 1,
    failed: 1,
    not_configured: 0,
    planned_only: 0,
  },
  top_urgent_issues: [
    {
      id: 101,
      conflict_type: 'crawler_delay',
      title: 'Crawler backlog growing',
      description: 'Fresh pages are waiting longer than usual.',
      severity: 'medium',
      location: 'workers/crawler',
      why: 'The queue rose after the last import.',
      next_step: 'Scale workers or lower the batch size.',
      resolved: false,
      created_at: '2026-03-31T07:00:00Z',
    },
  ],
};

const reviewSuggestions = {
  count: 1,
  next: null,
  previous: null,
  results: [
    {
      suggestion_id: 'sugg-001',
      status: 'pending',
      score_final: 0.91,
      destination: 101,
      destination_title: 'Internal Linking Guide',
      destination_url: 'https://example.test/internal-linking-guide',
      destination_content_type: 'article',
      destination_source_label: 'Docs',
      destination_silo_group: 1,
      destination_silo_group_name: 'SEO',
      host: 202,
      host_title: 'Anchor Text Best Practices',
      host_sentence_text: 'Use internal linking guide examples when teaching anchor text.',
      host_content_type: 'article',
      host_source_label: 'Blog',
      host_silo_group: 1,
      host_silo_group_name: 'SEO',
      same_silo: true,
      anchor_phrase: 'internal linking guide',
      anchor_edited: 'internal linking guide',
      anchor_confidence: 'strong',
      repeated_anchor: false,
      rejection_reason: '',
      reviewed_at: null,
      is_applied: false,
      created_at: '2026-03-31T08:00:00Z',
    },
  ],
};

export async function mockDashboardApis(page: Page): Promise<void> {
  await page.route('**/api/**', async (route) => {
    const url = route.request().url();

    if (url.endsWith('/api/settings/appearance/')) {
      await route.fulfill({ json: appearanceConfig });
      return;
    }

    if (url.endsWith('/api/dashboard/')) {
      await route.fulfill({ json: dashboardData });
      return;
    }

    if (url.endsWith('/api/system/status/overview/')) {
      await route.fulfill({ json: diagnosticsOverview });
      return;
    }

    if (url.includes('/api/suggestions/')) {
      await route.fulfill({ json: reviewSuggestions });
      return;
    }

    // Keep the smoke test quiet if the UI probes other API paths.
    await route.fulfill({ status: 200, json: {} });
  });
}
