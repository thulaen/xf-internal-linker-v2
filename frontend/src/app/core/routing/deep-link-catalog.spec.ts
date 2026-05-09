import { DEEP_LINK_CATALOG, findDeepLink, searchDeepLinks } from './deep-link-catalog';

/**
 * Drift-detection tests for the deep-link catalog. The catalog is a runtime
 * source of truth for the Cmd-K command palette, the `?dl=` URL handler, and
 * (in the future) breadcrumb labels. If two entries collide on `key`, or a
 * route is missing, those features silently misroute. These tests catch that
 * before it ships.
 */
describe('DEEP_LINK_CATALOG', () => {
  it('has at least one entry', () => {
    expect(DEEP_LINK_CATALOG.length).toBeGreaterThan(0);
  });

  it('has unique keys', () => {
    const keys = DEEP_LINK_CATALOG.map((e) => e.key);
    const dupes = keys.filter((k, i) => keys.indexOf(k) !== i);
    expect(dupes).toEqual([]);
  });

  it('has well-formed kebab-case keys', () => {
    const bad = DEEP_LINK_CATALOG.filter((e) => !/^[a-z][a-z0-9-]*(\.[a-z0-9][a-z0-9-]*)+$/.test(e.key));
    expect(bad.map((e) => e.key)).toEqual([]);
  });

  it('every route starts with a slash', () => {
    const bad = DEEP_LINK_CATALOG.filter((e) => !e.route.startsWith('/'));
    expect(bad.map((e) => e.key)).toEqual([]);
  });

  it('every searchTerms array has at least one entry', () => {
    const bad = DEEP_LINK_CATALOG.filter((e) => !e.searchTerms || e.searchTerms.length === 0);
    expect(bad.map((e) => e.key)).toEqual([]);
  });

  it('every label is non-empty and short enough to fit in a Cmd-K row', () => {
    const bad = DEEP_LINK_CATALOG.filter((e) => !e.label || e.label.length > 60);
    expect(bad.map((e) => e.key)).toEqual([]);
  });

  it('every subtitle is non-empty and reasonable for a one-line description', () => {
    const bad = DEEP_LINK_CATALOG.filter((e) => !e.subtitle || e.subtitle.length > 200);
    expect(bad.map((e) => e.key)).toEqual([]);
  });

  it('scrollTarget values are kebab-case ids (no leading #)', () => {
    const bad = DEEP_LINK_CATALOG.filter(
      (e) => e.scrollTarget && (e.scrollTarget.startsWith('#') || /\s/.test(e.scrollTarget))
    );
    expect(bad.map((e) => e.key)).toEqual([]);
  });

  it('covers every concrete route declared in app.routes.ts', () => {
    // Must be kept in sync with `frontend/src/app/app.routes.ts`. The login
    // page, server-error page, and the wildcard `**` are intentionally
    // excluded — they are not user-shareable surfaces. `/alerts/:id` is
    // covered by the `alerts.detail` entry whose route is `/alerts`
    // (the catalog points at the index page; the detail handler reads
    // the id segment from the active route itself).
    const expectedRoutes = [
      '/dashboard',
      '/review',
      '/embeddings',
      '/link-health',
      '/graph',
      '/analytics',
      '/jobs',
      '/settings',
      '/health',
      '/mcp',
      '/reports/monthly',
      '/diagnostics',
      '/alerts',
      '/scheduled-updates',
      '/behavioral-hubs',
      '/crawler',
      '/error-log',
      '/performance',
      '/operations-feed',
      '/preferences',
      '/admin/models',
      '/audit/undo-timeline',
    ];
    const cataloged = new Set(DEEP_LINK_CATALOG.map((e) => e.route));
    const missing = expectedRoutes.filter((r) => !cataloged.has(r));
    expect(missing).toEqual([]);
  });
});

describe('findDeepLink()', () => {
  it('returns the entry for a known key', () => {
    const entry = findDeepLink('dashboard.main');
    expect(entry).toBeDefined();
    expect(entry?.route).toBe('/dashboard');
  });

  it('returns undefined for an unknown key', () => {
    expect(findDeepLink('does.not.exist')).toBeUndefined();
  });
});

describe('searchDeepLinks()', () => {
  it('returns nothing for an empty query', () => {
    expect(searchDeepLinks('')).toEqual([]);
    expect(searchDeepLinks('   ')).toEqual([]);
  });

  it('matches by label substring (case-insensitive)', () => {
    const hits = searchDeepLinks('dashboard');
    expect(hits.length).toBeGreaterThan(0);
    for (const hit of hits) {
      const haystack = (
        hit.label +
        hit.subtitle +
        hit.route +
        hit.searchTerms.join(' ')
      ).toLowerCase();
      expect(haystack).toContain('dashboard');
    }
  });

  it('matches via searchTerms when label and subtitle do not contain the query', () => {
    // 'flamegraph' is a searchTerm on `error-log.pyroscope` but not in its
    // label or subtitle.
    const hits = searchDeepLinks('flamegraph');
    expect(hits.some((e) => e.key === 'error-log.pyroscope')).toBe(true);
  });
});
